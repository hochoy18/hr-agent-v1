"""interview_plan / exam_generate / resume_screening 的单步准备节点。

chat 侧这三个意图都是"解析 + 引导确认"的单步响应（真正的执行由文件流 exec
子图或前端专用端点完成），节点调用 AgentService 的业务 handler，作为单节点
子图挂入主图。
"""
from __future__ import annotations

from typing import Any, Dict

from langgraph.config import RunnableConfig

from app.agent.nodes.legacy import _respond, _route_result, _service


async def interview_plan_prepare(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    response = await service._handle_interview_plan_chat(
        message=state["user_message"],
        user_id=config["configurable"]["user_id"],
        intent=state.get("intent") or "interview_plan",
        route_result=_route_result(state),
        selected_tool=service.tool_registry.get("interview_plan"),
        memory_context=state.get("memory_context") or "",
        conversation_id=state.get("conversation_id"),
    )
    return await _respond(config, response)


async def exam_generate_prepare(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    response = await service._handle_exam_generate_chat(
        message=state["user_message"],
        user_id=config["configurable"]["user_id"],
        intent=state.get("intent") or "exam_generate",
        route_result=_route_result(state),
        selected_tool=service.tool_registry.get("exam_generate"),
        normalized_attachments=state.get("attachments") or [],
        memory_context=state.get("memory_context") or "",
        conversation_id=state.get("conversation_id"),
    )
    return await _respond(config, response)


async def resume_screening_prepare(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    response = service._handle_resume_screening_chat(
        state.get("intent") or "resume_screening",
        _route_result(state),
        service.tool_registry.get("resume_screening"),
        state.get("attachments") or [],
    )
    return await _respond(config, response)
