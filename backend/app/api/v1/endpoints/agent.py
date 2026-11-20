"""HR Agent API 端点

文件驱动的流式接口，挂载前缀是 /agent。全部经 LangGraph 图执行
（preset_intent 直通对应 exec 节点），SSE 事件格式与旧版兼容。

对话类入口在 endpoints/agent_graph.py（/agent/graph/*）。

接口：
    POST /agent/stream                      确认后执行 JD 生成链（前端 thread 丢失时的降级通道）
    POST /agent/resume-screen/stream        批量上传简历并流式评分
    POST /agent/interview-plan/stream       基于已评分简历流式生成面试计划
    POST /agent/exam/stream                 流式生成试卷
    POST /agent/exam/document-stream        上传参考文档流式生成试卷
"""

import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.agent.bridge import AgentGraphService
from app.agent.checkpoint import get_checkpointer
from app.core.database import get_db
from app.schemas.agent import AgentChatRequest
from app.schemas.user import User as UserSchema
from app.services.agent_service import AgentService

router = APIRouter()


def _graph_service() -> AgentGraphService:
    return AgentGraphService(checkpointer=get_checkpointer())


async def _sse_stream(events: AsyncGenerator[Dict[str, Any], None], thread_id: str) -> StreamingResponse:
    """把 bridge 事件 dict 包装为 SSE 帧并统一异常/[DONE] 处理。"""

    async def generate():
        try:
            async for event in events:
                if isinstance(event, dict):
                    event.setdefault("thread_id", thread_id)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                else:
                    yield str(event)
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc), 'thread_id': thread_id}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _read_files(files: List[UploadFile]) -> List[Dict[str, Any]]:
    payloads = []
    for upload_file in files:
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{upload_file.filename} 文件内容为空")
        payloads.append({"filename": upload_file.filename, "content": content})
    return payloads


@router.post("/stream")
async def stream_agent_progress(
    request: AgentChatRequest,
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """确认后执行 JD 生成链（图直通 jd 链；前端 thread 丢失时的降级通道）。"""
    if not request.confirmed_requirements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="stream 接口需要 confirmed_requirements",
        )
    thread_id = request.conversation_id or str(uuid.uuid4())

    async def events():
        agent_service = AgentService(db)
        graph_service = _graph_service()
        async for event in graph_service.run_stream(
            agent_service=agent_service,
            user_id=current_user.id,
            conversation_id=thread_id,
            message=request.message.strip(),
            confirmed_requirements=request.confirmed_requirements,
            preset_intent="jd",
        ):
            yield event

    return await _sse_stream(events(), thread_id)


@router.post("/resume-screen/stream")
async def stream_resume_screening(
    job_description_id: UUID = Form(...),
    conversation_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """批量上传简历并流式返回筛选进度（图直通 resume_exec 节点）。"""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少上传一份简历")
    if len(files) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多上传 20 份简历")

    file_payloads = await _read_files(files)
    thread_id = conversation_id or str(uuid.uuid4())

    async def events():
        agent_service = AgentService(db)
        graph_service = _graph_service()
        async for event in graph_service.run_stream(
            agent_service=agent_service,
            user_id=current_user.id,
            conversation_id=thread_id,
            preset_intent="resume_exec",
            extra_config={"files": file_payloads, "preset_params": {"job_description_id": str(job_description_id)}},
        ):
            yield event

    return await _sse_stream(events(), thread_id)


@router.post("/interview-plan/stream")
async def stream_interview_plan(
    resume_evaluation_id: UUID = Form(...),
    conversation_id: Optional[str] = Form(None),
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """根据已评分简历流式生成面试计划（图直通 interview_exec 节点）。"""
    thread_id = conversation_id or str(uuid.uuid4())

    async def events():
        agent_service = AgentService(db)
        graph_service = _graph_service()
        async for event in graph_service.run_stream(
            agent_service=agent_service,
            user_id=current_user.id,
            conversation_id=thread_id,
            preset_intent="interview_exec",
            extra_config={"preset_params": {"resume_evaluation_id": str(resume_evaluation_id)}},
        ):
            yield event

    return await _sse_stream(events(), thread_id)


@router.post("/exam/stream")
async def stream_exam_generation(
    request: AgentChatRequest,
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """流式生成并保存考试试卷（图直通 exam_exec 节点）。"""
    if not request.confirmed_requirements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exam stream 接口需要 confirmed_requirements",
        )
    thread_id = request.conversation_id or str(uuid.uuid4())

    async def events():
        agent_service = AgentService(db)
        graph_service = _graph_service()
        async for event in graph_service.run_stream(
            agent_service=agent_service,
            user_id=current_user.id,
            conversation_id=thread_id,
            preset_intent="exam_exec",
            extra_config={"preset_params": {"exam_requirements": request.confirmed_requirements}},
        ):
            yield event

    return await _sse_stream(events(), thread_id)


@router.post("/exam/document-stream")
async def stream_exam_generation_with_documents(
    exam_requirements: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """上传参考文档后，基于文档流式生成并保存考试试卷（图直通 exam_exec 节点）。"""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少上传一个参考文档")
    if len(files) > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多上传 5 个参考文档")

    try:
        parsed_requirements = json.loads(exam_requirements)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="考试配置 JSON 格式不正确") from exc

    file_payloads = await _read_files(files)
    thread_id = conversation_id or str(uuid.uuid4())

    async def events():
        agent_service = AgentService(db)
        graph_service = _graph_service()
        async for event in graph_service.run_stream(
            agent_service=agent_service,
            user_id=current_user.id,
            conversation_id=thread_id,
            preset_intent="exam_exec",
            extra_config={
                "files": file_payloads,
                "preset_params": {"exam_requirements": parsed_requirements},
            },
        ):
            yield event

    return await _sse_stream(events(), thread_id)
