"""Skill 意图（当前为 email_notification）的两节点链。

skill_draft：流式生成草稿（LLM 直出 + skill 脚本兜底），产出 email_send_request
             artifact + requires_confirmation 响应结束本轮（前端确认表单回传）。
skill_send ：confirmed_requirements.action 命中 confirmation_action 时执行发送。
             路由节点把确认回传映射为 skill intent，本轮直接落到 send 节点。

与 jd 链不同，这里不用 interrupt：前端把确认内容作为新消息发送（graphChat），
在同一线程上开启新一轮执行，语义等价且对前端零改动。
"""
from __future__ import annotations

from typing import Any, Dict

from langgraph.config import RunnableConfig

from app.agent.nodes.legacy import (
    _emit_generator,
    _respond,
    _respond_from_event,
    _service,
)
from app.services.agent_service import AgentService


async def skill_draft_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service: AgentService = _service(config)
    intent = state.get("intent") or "email_notification"
    if state.get("confirmed_requirements"):
        # 确认回传本轮直接到 send，草稿节点跳过
        return {}

    if (config.get("configurable") or {}).get("streaming"):
        final_event = await _emit_generator(service._stream_skill_draft_response(
            intent=intent,
            message=state["user_message"],
            user_id=config["configurable"]["user_id"],
            conversation_id=state.get("conversation_id"),
            route=state.get("route"),
            memory_context=state.get("memory_context") or "",
            confirmed_requirements=state.get("confirmed_requirements"),
        ))
        if final_event:
            return _respond_from_event(final_event)

    response = await service._handle_skill_intent(
        intent=intent,
        message=state["user_message"],
        user_id=config["configurable"]["user_id"],
        route=state.get("route"),
        selected_tool=service.tool_registry.get(intent),
        memory_context=state.get("memory_context") or "",
        confirmed_requirements=state.get("confirmed_requirements"),
    )
    return await _respond(config, response)


async def skill_send_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """执行 skill send 阶段：confirmed_requirements.action 必须已命中 confirmation_action。"""
    service: AgentService = _service(config)
    intent = state.get("intent") or "email_notification"
    confirmed = state.get("confirmed_requirements")

    response = await service._handle_skill_intent(
        intent=intent,
        message=state["user_message"],
        user_id=config["configurable"]["user_id"],
        route=state.get("route"),
        selected_tool=service.tool_registry.get(intent),
        memory_context=state.get("memory_context") or "",
        confirmed_requirements=confirmed,
    )
    return await _respond(config, response)
