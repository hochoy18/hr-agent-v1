"""路由节点：规则快通道 + 受控 ReAct 决策（复用 AgentService 既有实现）。"""
from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.config import RunnableConfig

from app.agent import reasoning
from app.agent.state import AgentState
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)


async def route_intent_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """构建对话记忆并决策意图，写入 state 供条件边分发。"""
    service: AgentService = config["configurable"]["agent_service"]
    message = state["user_message"]
    conversation_id = state.get("conversation_id")
    user_id = config["configurable"]["user_id"]
    normalized_attachments = state.get("attachments") or []

    # 文件流等端点的直通执行：跳过决策与记忆，直达目标节点
    preset = state.get("preset_intent")
    if preset:
        logger.info("LangGraph 路由直通 preset=%s", preset)
        return {
            "intent": preset,
            "agent_plan": {"mode": "tool", "intent": preset, "reason": "端点直通执行。", "reply": None, "source": "preset"},
            "route": None,
            "memory_context": "",
            "dest_node": preset,
        }

    # 把本 thread 累积产物注入 service：编辑/删除链路反查"刚才那个"优先用图状态，
    # 不再只依赖前端落库的 Message.context.agent_response（无 checkpointer 门面路径为空，
    # 自动回退 Message 反查）
    service._graph_artifacts = state.get("artifacts") or []

    memory_context = await reasoning.build_conversation_memory(service, conversation_id, user_id, message)
    intent, agent_plan = await reasoning.resolve_intent_and_plan(
        service,
        message=message,
        normalized_attachments=normalized_attachments,
        memory_context=memory_context,
        confirmed_requirements=state.get("confirmed_requirements"),
        agent_plan=state.get("agent_plan"),
        user_id=user_id,
        conversation_id=conversation_id,
        artifacts=state.get("artifacts") or [],
    )

    route_result = service._route_for_intent(intent, message)

    # 条件边只读 state，所以在这里把目标节点算好；skill 类意图进 skill_draft（确认回传由条件边放行到 send）
    if agent_plan.get("mode") == "chat" or intent == "general":
        dest_node = "chat"
    elif intent in service.skill_dispatcher.bundles:
        dest_node = "skill_draft"
    else:
        dest_node = intent

    logger.info("LangGraph 路由完成 intent=%s dest=%s source=%s", intent, dest_node, agent_plan.get("source"))
    return {
        "intent": intent,
        "agent_plan": agent_plan,
        "route": route_result.get("route"),
        "memory_context": memory_context,
        "dest_node": dest_node,
    }
