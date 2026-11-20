"""意图节点与子图公共工具。

意图节点已迁移为独立编译子图（graph.py）：
    jd        → nodes/jd.py 三节点链
    skill     → nodes/skill.py 两节点链
    jd_edit / criteria_edit → nodes/editing.py 四节点链
    resource_delete → nodes/resources.py 三节点链
    interview_plan / exam_generate / resume_screening → graph.py 单步子图
    文件流 exec     → nodes/files.py

本模块保留 chat 节点（create_agent ReAct 循环入口）与各子图共用的工具函数。
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, Optional

from langgraph.config import RunnableConfig, get_stream_writer

from app.schemas.agent import AgentChatResponse
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)


def _service(config: RunnableConfig) -> AgentService:
    return config["configurable"]["agent_service"]


def _route_result(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "intent": state.get("intent"),
        "route": state.get("route"),
        "query": state.get("user_message") or "",
        "kb_id": None,
    }


def _is_streaming(config: RunnableConfig) -> bool:
    return bool((config.get("configurable") or {}).get("streaming"))


async def _respond(config: RunnableConfig, response: AgentChatResponse) -> Dict[str, Any]:
    dumped = response.model_dump()
    return {
        "final_response": dumped,
        "intent": dumped.get("intent"),
        "route": dumped.get("route"),
        "steps": dumped.get("steps") or [],
        "artifacts": dumped.get("artifacts") or [],
    }


def _respond_from_event(final_event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把旧流式生成器的 final 事件转为 state 更新。"""
    dumped = (final_event or {}).get("response") or {}
    return {
        "final_response": dumped,
        "intent": dumped.get("intent"),
        "route": dumped.get("route"),
        "steps": dumped.get("steps") or [],
        "artifacts": dumped.get("artifacts") or [],
    }


async def _emit_generator(agen: AsyncGenerator[Dict[str, Any], None]) -> Optional[Dict[str, Any]]:
    """迭代旧流式生成器：非 final 事件经 stream writer 透传，返回 final 事件。"""
    writer = get_stream_writer()
    final_event: Optional[Dict[str, Any]] = None
    async for event in agen:
        if event.get("type") == "final":
            final_event = event
            continue
        if writer:
            writer({"agent_event": event})
    return final_event


async def chat_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    agent_plan = state.get("agent_plan") or {}

    # 首选 create_agent 子图（真正的 ReAct 工具循环）；未配 LLM key 或调用失败时回退规则路径
    try:
        from app.agent.llm import chat_llm_available
        from app.agent.nodes.chat_agent import run_chat_agent, run_chat_agent_stream

        if chat_llm_available():
            if _is_streaming(config):
                reply, intent = await run_chat_agent_stream(state, config)
            else:
                reply, intent = await run_chat_agent(state, config)
            response = service._handle_general_chat(agent_plan, state["user_message"])
            if reply:
                response = response.model_copy(update={"message": reply})
            return await _respond(config, response)
    except Exception as exc:
        logger.warning("create_agent chat 子图失败，回退规则路径: %s", exc)

    if _is_streaming(config):
        # 与旧 stream_chat_agent 一致：普通聊天走 LLM 原生流式
        full_text = ""
        try:
            from app.services.llm_service import LLMService

            if service.llm_service is None:
                service.llm_service = LLMService()
            prompt = service._build_memory_augmented_prompt(state["user_message"], state.get("memory_context") or "")
            writer = get_stream_writer()
            async for delta in service.llm_service.stream_response(prompt):
                full_text += delta
                if writer:
                    writer({"agent_event": {"type": "delta", "delta": delta}})
            response = service._handle_general_chat(agent_plan, state["user_message"])
            response = response.model_copy(update={"message": full_text.strip() or response.message})
            return await _respond(config, response)
        except Exception:
            # 流式中途失败：已流出的部分内容保留为最终答案，避免 final 与流式内容不一致
            response = service._handle_general_chat(agent_plan, state["user_message"])
            if full_text.strip():
                response = response.model_copy(update={"message": full_text.strip()})
            return await _respond(config, response)
    response = service._handle_general_chat(agent_plan, state["user_message"])
    return await _respond(config, response)


INTENT_NODES = {
    "chat": chat_node,
}
