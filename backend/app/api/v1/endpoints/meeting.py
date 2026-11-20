"""腾讯会议 API 端点（基于官方 MCP，个人版账号可用）。

挂载前缀 /meetings：
    POST /meetings/                 创建面试会议，返回 join_url / meeting_code
    GET  /meetings/{meeting_id}     查询会议详情
    POST /meetings/{meeting_id}/cancel  取消会议

Token 配置在 backend/.env 的 TENCENT_MEETING_TOKEN，等同个人账号身份，切勿提交仓库。
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.schemas.meeting import (
    MeetingCancelResponse,
    MeetingCreateRequest,
    MeetingCreateResponse,
)
from app.schemas.user import User as UserSchema
from app.services.meeting_service import MeetingService, MeetingServiceError

router = APIRouter()


@router.get("/status")
async def meeting_status(current_user: UserSchema = Depends(get_current_user)) -> Dict[str, Any]:
    """检查腾讯会议 MCP 是否已配置。"""
    service = MeetingService()
    return {"configured": service.configured}


@router.post("/", response_model=MeetingCreateResponse)
async def create_meeting(
    request: MeetingCreateRequest,
    current_user: UserSchema = Depends(get_current_user),
) -> MeetingCreateResponse:
    try:
        meetings = await MeetingService().create_meeting(request)
    except MeetingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return MeetingCreateResponse(meetings=meetings)


@router.get("/{meeting_id}")
async def get_meeting(
    meeting_id: str,
    current_user: UserSchema = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        return await MeetingService().get_meeting(meeting_id)
    except MeetingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{meeting_id}/cancel", response_model=MeetingCancelResponse)
async def cancel_meeting(
    meeting_id: str,
    current_user: UserSchema = Depends(get_current_user),
) -> MeetingCancelResponse:
    try:
        await MeetingService().cancel_meeting(meeting_id)
    except MeetingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return MeetingCancelResponse(meeting_id=meeting_id)
