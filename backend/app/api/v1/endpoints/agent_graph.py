"""HR Agent LangGraph API 端点

挂载前缀 /agent/graph，是 Agent 模块迁移 LangGraph 后的新入口：
    POST /agent/graph/chat    自然语言对话（SSE 流）
    POST /agent/graph/resume  恢复被 interrupt 的会话（确认后继续，SSE 流）

SSE 事件契约（与旧 /agent/* 端点的事件格式兼容，新增 thread_id / interrupt / progress）：
    {"type": "progress", "node": "...", "steps": [...]}   LangGraph 节点进度
    {"type": "delta", "delta": "..."}                     文本增量
    {"type": "progress"|"artifact", "response": ...}      阶段进度/产物（旧词汇）
    {"type": "interrupt", "thread_id", "payload"}         等待用户确认
    {"type": "final", "response": AgentChatResponse, "thread_id": "..."}  终态
    {"type": "error", "error": "..."}                     异常
    事件流以 [DONE] 结束。

确认交互：chat 收到 interrupt/final(requires_confirmation) 后，前端把确认表单
（旧 confirmed_requirements 结构，含 action:"send_email" 等）POST 到 /resume，
后端以 Command(resume=value) 继续被暂停的 thread。
"""
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.agent.bridge import AgentGraphService
from app.agent.checkpoint import get_checkpointer
from app.core.database import get_db
from app.schemas.agent import AgentAttachment
from app.schemas.user import User as UserSchema
from app.services.agent_service import AgentService

router = APIRouter()


class AgentGraphChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    auto_execute: bool = True
    attachments: List[AgentAttachment] = []
    confirmed_requirements: Optional[Dict[str, Any]] = None


class AgentGraphResumeRequest(BaseModel):
    thread_id: str
    value: Dict[str, Any]


def _graph_service() -> AgentGraphService:
    """每次请求构建图服务：挂载应用级 checkpointer。"""
    return AgentGraphService(checkpointer=get_checkpointer())


async def _sse_wrapper(events: AsyncGenerator[Dict[str, Any], None], thread_id: str) -> AsyncGenerator[str, None]:
    """把 bridge 事件 dict 包装为 SSE 帧，统一补 thread_id、异常处理与 [DONE]。"""
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


def _sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/chat")
async def chat_via_graph(
    request: AgentGraphChatRequest,
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """LangGraph 版自然语言对话。thread_id 缺省时由后端生成并在事件里返回。"""
    thread_id = request.thread_id or str(uuid.uuid4())

    async def events() -> AsyncGenerator[Dict[str, Any], None]:
        agent_service = AgentService(db)
        graph_service = _graph_service()
        async for event in graph_service.run_stream(
            agent_service=agent_service,
            user_id=current_user.id,
            conversation_id=thread_id,
            message=request.message.strip(),
            auto_execute=request.auto_execute,
            attachments=[item.model_dump() for item in request.attachments],
            confirmed_requirements=request.confirmed_requirements,
        ):
            yield event

    return _sse_response(_sse_wrapper(events(), thread_id))


@router.post("/resume")
async def resume_via_graph(
    request: AgentGraphResumeRequest,
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """恢复被 interrupt 的 thread：value 即旧 confirmed_requirements 结构（含 action）。

    checkpointer 未启用时降级为一次带 confirmed_requirements 的普通 chat。
    """
    if not get_checkpointer():
        async def fallback_events() -> AsyncGenerator[Dict[str, Any], None]:
            agent_service = AgentService(db)
            graph_service = _graph_service()
            response = await graph_service.run_chat(
                agent_service=agent_service,
                message=str(request.value.get("message") or ""),
                user_id=current_user.id,
                conversation_id=request.thread_id,
                confirmed_requirements=request.value,
            )
            yield {"type": "final", "response": response.model_dump()}

        return _sse_response(_sse_wrapper(fallback_events(), request.thread_id))

    async def events() -> AsyncGenerator[Dict[str, Any], None]:
        agent_service = AgentService(db)
        graph_service = _graph_service()
        async for event in graph_service.run_stream(
            agent_service=agent_service,
            user_id=current_user.id,
            conversation_id=request.thread_id,
            resume_value=request.value,
        ):
            yield event

    return _sse_response(_sse_wrapper(events(), request.thread_id))
