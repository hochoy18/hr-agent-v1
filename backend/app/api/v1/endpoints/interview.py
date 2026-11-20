"""面试生命周期端点：创建会议、上传面试材料、拉取转写、AI 评价。

挂载前缀 /interviews。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.interview import (
    InterviewCandidateUpdateRequest,
    InterviewEvaluation,
    InterviewEvaluationUpdateRequest,
    InterviewListResponse,
    InterviewRecordSettings,
    InterviewResponse,
    InterviewStartRequest,
    InterviewUpdateRequest,
    TencentTranscriptRequest,
)
from app.services.interview_service import InterviewService, apply_dimension_aliases
from app.services.meeting_service import MeetingServiceError

router = APIRouter()


def _with_current_dimension_names(interview) -> InterviewResponse:
    """响应里把旧维度名映射成当前名称，列表与详情保持同一套叫法。"""
    payload = InterviewResponse.model_validate(interview)
    if payload.evaluation:
        payload.evaluation = apply_dimension_aliases(payload.evaluation)
    return payload


@router.post("/start", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def start_interview(
    request: InterviewStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    try:
        interview = await InterviewService(db).start_interview(current_user.id, request)
    except MeetingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _with_current_dimension_names(interview)


@router.get("/", response_model=InterviewListResponse)
async def list_interviews(
    resume_evaluation_id: Optional[UUID] = None,
    page: int = 1,
    size: int = 20,
    sync: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewListResponse:
    data = await InterviewService(db).list_interviews(
        current_user.id,
        resume_evaluation_id=resume_evaluation_id,
        page=page,
        size=size,
        sync_meeting=sync,
    )
    return InterviewListResponse(
        items=[_with_current_dimension_names(item) for item in data["items"]],
        total=data["total"],
        page=data["page"],
        size=data["size"],
    )


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    interview = await InterviewService(db).get_interview(interview_id, current_user.id)
    return _with_current_dimension_names(interview)


@router.get("/{interview_id}/record-settings", response_model=InterviewRecordSettings)
async def get_record_settings(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewRecordSettings:
    data = await InterviewService(db).get_record_settings(interview_id, current_user.id)
    return InterviewRecordSettings(**data)


@router.patch("/{interview_id}", response_model=InterviewResponse)
async def update_interview(
    interview_id: UUID,
    request: InterviewUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    try:
        interview = await InterviewService(db).update_interview(
            interview_id, current_user.id, request
        )
    except MeetingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _with_current_dimension_names(interview)


@router.post("/{interview_id}/sync", response_model=InterviewResponse)
async def sync_interview(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    try:
        interview = await InterviewService(db).sync_meeting_status(interview_id, current_user.id)
    except MeetingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _with_current_dimension_names(interview)


@router.post("/{interview_id}/cancel", response_model=InterviewResponse)
async def cancel_interview(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    interview = await InterviewService(db).cancel_interview(interview_id, current_user.id)
    return _with_current_dimension_names(interview)


@router.post("/{interview_id}/media", response_model=InterviewResponse)
async def upload_media(
    interview_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    candidate_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    service = InterviewService(db)
    interview = await service.get_interview(interview_id, current_user.id)
    interview = await service.save_media(interview, file, candidate_name)
    background_tasks.add_task(InterviewService.process_media, interview.id)
    return _with_current_dimension_names(interview)


@router.patch("/{interview_id}/candidate", response_model=InterviewResponse)
async def update_candidate(
    interview_id: UUID,
    request: InterviewCandidateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    interview = await InterviewService(db).update_candidate_name(
        interview_id, current_user.id, request.candidate_name
    )
    return _with_current_dimension_names(interview)


@router.post("/{interview_id}/transcript/tencent", response_model=InterviewResponse)
async def pull_tencent_transcript(
    interview_id: UUID,
    background_tasks: BackgroundTasks,
    request: Optional[TencentTranscriptRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    service = InterviewService(db)
    interview = await service.get_interview(interview_id, current_user.id)
    if interview.meeting_status == "cancelled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="会议已取消，无法拉取录制")

    interview.analysis_status = "transcribing"
    interview.error_message = None
    await db.commit()
    await db.refresh(interview)

    payload = request or TencentTranscriptRequest()
    background_tasks.add_task(
        InterviewService.pull_tencent_transcript,
        interview.id,
        payload.record_file_id,
        payload.meeting_code,
    )
    return _with_current_dimension_names(interview)


@router.post("/{interview_id}/analyze", response_model=InterviewResponse)
async def analyze_interview(
    interview_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    service = InterviewService(db)
    interview = await service.get_interview(interview_id, current_user.id)
    if not interview.transcript:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少面试转写内容")

    if interview.analysis_status == "analyzing":
        # 防重入：分析已在后台任务进行，重复触发会重启分析拖慢出结果；
        # 服务重启可能把状态卡在 analyzing，超过 10 分钟允许重新触发
        updated_at = interview.updated_at
        if updated_at and datetime.utcnow() - updated_at < timedelta(minutes=10):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="正在分析中，请等待本次分析完成")
    interview.analysis_status = "analyzing"
    interview.error_message = None
    await db.commit()
    await db.refresh(interview)

    background_tasks.add_task(InterviewService.analyze, interview.id)
    return _with_current_dimension_names(interview)


@router.get("/{interview_id}/evaluation", response_model=InterviewEvaluation)
async def get_evaluation(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewEvaluation:
    interview = await InterviewService(db).get_interview(interview_id, current_user.id)
    if not interview.evaluation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未生成面试评价")
    return InterviewEvaluation(**apply_dimension_aliases(interview.evaluation))


@router.patch("/{interview_id}/evaluation", response_model=InterviewEvaluation)
async def update_evaluation(
    interview_id: UUID,
    request: InterviewEvaluationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewEvaluation:
    """人工修订评分。只改分数，不改判定标签；原分与修订原因一并留痕。"""
    interview = await InterviewService(db).update_evaluation_scores(
        interview_id,
        current_user.id,
        request,
        operator=current_user.full_name or current_user.username or "",
    )
    return InterviewEvaluation(**apply_dimension_aliases(interview.evaluation))
