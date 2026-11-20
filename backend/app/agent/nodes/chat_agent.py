"""chat/general 意图的 LangChain create_agent 子图。

用 langchain.agents.create_agent（v1 官方 agent 抽象，基于 LangGraph）替代原先的
单轮 LLM 调用：模型可多轮调用只读工具（查 JD/评分/面试方案/试卷列表）后回答，
形成真正的 Thought -> Action(tool) -> Observation -> ... -> Final Answer 循环。

要点：
    - 进程内缓存编译图；未配置 LLM_API_KEY 时不构建，chat 节点回退规则路径。
    - 无独立 checkpointer：会话连续性由每轮注入 memory_context 实现，子图状态轮次即弃。
    - 流式模式下经 stream writer 透传 token delta（复用 SSE delta 事件）。
    - 任何构建/调用异常由调用方（legacy.chat_node）兜底回退，保证评测契约稳定。
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional, Tuple

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

logger = logging.getLogger(__name__)

_agent = None
_built = False


def _build_agent():
    global _agent, _built
    if not _built:
        from langchain.agents import create_agent

        from app.agent.llm import get_chat_model
        from app.agent.tools.chat_tools import CHAT_TOOLS
        from app.services.llm_service import LLMService

        _agent = create_agent(
            model=get_chat_model(),
            tools=CHAT_TOOLS,
            system_prompt=LLMService().system_prompt,
            # 显式关闭子 agent 持久化：它默认自带 InMemorySaver，checkpoint 循环会
            # 强制要求 config 带 thread_id，而主图的 thread_id 不应泄漏进子图。
            # 会话连续性由每轮注入 memory_context 实现。
            checkpointer=False,
            name="hr_chat_agent",
        )
        _built = True
        logger.info("chat agent（create_agent）已构建，tools=%d", len(CHAT_TOOLS))
    return _agent


def _inner_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """子图不带 checkpointer，剔除 checkpoint 相关键；保留 db/service 供工具注入。"""
    configurable = dict(config.get("configurable") or {})
    for key in ("thread_id", "checkpoint_ns", "checkpoint_id"):
        configurable.pop(key, None)
    return {"configurable": configurable}


def _text_of(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


async def run_chat_agent(state: Dict[str, Any], config: Dict[str, Any]) -> Tuple[str, str]:
    """执行 chat agent，返回 (回复文本, 意图)。异常向上抛出由调用方兜底。"""
    agent = _build_agent()
    memory_context = state.get("memory_context") or ""
    messages = []
    if memory_context:
        messages.append(SystemMessage(content=f"历史对话记忆（供理解当前消息参考）：\n{memory_context}"))
    messages.append(HumanMessage(content=state["user_message"]))

    result = await agent.ainvoke({"messages": messages}, _inner_config(config))
    final_message = (result.get("messages") or [AIMessageChunk(content="")])[-1]
    return _text_of(final_message).strip(), "general"


async def run_chat_agent_stream(state: Dict[str, Any], config: Dict[str, Any]) -> Tuple[str, str]:
    """流式执行 chat agent：token 经 stream writer 透传，返回 (完整回复, 意图)。

    已流式输出部分内容后中途失败时，返回已生成的部分文本（不再抛异常），
    避免调用方用规则兜底文案替换 final，造成"流式内容与最终答案不一致"。

    注意：不清除父图 runnable 上下文——ToolNode 注入 config 依赖它；
    父图泄漏的 thread_id 由子 agent 的 checkpointer=False 容忍。
    """
    agent = _build_agent()
    memory_context = state.get("memory_context") or ""
    messages = []
    if memory_context:
        messages.append(SystemMessage(content=f"历史对话记忆（供理解当前消息参考）：\n{memory_context}"))
    messages.append(HumanMessage(content=state["user_message"]))

    writer = get_stream_writer()
    full_text = ""
    try:
        async for chunk, _meta in agent.astream({"messages": messages}, _inner_config(config), stream_mode="messages"):
            if not isinstance(chunk, AIMessageChunk):
                continue
            if getattr(chunk, "tool_call_chunks", None):
                continue
            text = _text_of(chunk)
            if not text:
                continue
            full_text += text
            if writer:
                writer({"agent_event": {"type": "delta", "delta": text}})
    except Exception:
        if full_text.strip():
            logger.warning(
                "chat agent 流式中途失败，保留已生成部分（%d 字）: %s",
                len(full_text), traceback.format_exc().splitlines()[-1],
            )
            return full_text.strip(), "general"
        raise
    return full_text.strip(), "general"
