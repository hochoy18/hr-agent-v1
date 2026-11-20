"""图调用桥：把 AgentService.chat() / HTTP 流式路径接入 LangGraph 图。

AgentGraphService 负责：
    - run_chat()：非流式调用（评测与旧入口的兼容路径）。ainvoke 到终态，若发生
      interrupt 则组装 requires_confirmation=True 的响应，与旧链路同构。
    - resume()：Command(resume=...) 恢复被 interrupt 的 thread（阶段2 启用）。
    - run_stream()：阶段3 提供基于 astream 的事件流。

configurable 约定：
    agent_service   本请求的 AgentService 实例（内含 db session，不进 checkpoint）
    user_id         UUID
    thread_id       LangGraph checkpoint 的 thread，等于 conversation_id
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

from langgraph.types import Command

from app.agent.graph import build_graph
from app.agent.state import AgentState
from app.schemas.agent import AgentArtifact, AgentChatResponse, AgentStep

if TYPE_CHECKING:
    from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

_shared_graph = None


async def _stream_text(text: str):
    """把完整文本按小片段产出，模拟逐字流式（旧 AgentService._stream_text 等价实现）。"""
    if not text:
        return
    for index in range(0, len(text), 6):
        yield text[index:index + 6]


def get_shared_graph(checkpointer=None):
    """进程内共享一份编译图；checkpointer 变化时重建。"""
    global _shared_graph
    if _shared_graph is None:
        _shared_graph = build_graph(checkpointer)
    return _shared_graph


class AgentGraphService:
    """LangGraph 图的调用门面。"""

    def __init__(self, checkpointer=None):
        self.graph = build_graph(checkpointer)

    async def run_chat(
        self,
        *,
        agent_service: AgentService,
        message: str,
        user_id: UUID,
        conversation_id: Optional[str] = None,
        auto_execute: bool = True,
        confirmed_requirements: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        seed_agent_plan: Optional[Dict[str, Any]] = None,
    ) -> AgentChatResponse:
        """非流式执行：等价于旧 AgentService.chat() 的语义。"""
        normalized_attachments = agent_service._normalize_attachments(attachments or [])
        inputs: Dict[str, Any] = {
            "user_message": message,
            "attachments": normalized_attachments,
            "confirmed_requirements": confirmed_requirements,
            "auto_execute": auto_execute,
            "conversation_id": conversation_id,
            "agent_plan": seed_agent_plan,
            "preset_intent": None,
            "final_response": None,
        }
        config = {
            "configurable": {
                "agent_service": agent_service,
                "user_id": user_id,
                "thread_id": conversation_id or "",
            }
        }
        result = await self.graph.ainvoke(inputs, config)
        return self._response_from_result(result)

    async def resume(
        self,
        *,
        agent_service: AgentService,
        thread_id: str,
        value: Dict[str, Any],
        user_id: UUID,
    ) -> AgentChatResponse:
        """恢复被 interrupt 的 thread：value 即旧 confirmed_requirements 结构。"""
        config = {
            "configurable": {
                "agent_service": agent_service,
                "user_id": user_id,
                "thread_id": thread_id,
            }
        }
        result = await self.graph.ainvoke(Command(resume=value), config)
        return self._response_from_result(result)

    async def run_stream(
        self,
        *,
        agent_service: AgentService,
        user_id: UUID,
        conversation_id: Optional[str] = None,
        message: Optional[str] = None,
        auto_execute: bool = True,
        confirmed_requirements: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        resume_value: Optional[Dict[str, Any]] = None,
        preset_intent: Optional[str] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ):
        """流式执行：astream(updates+custom) → SSE 事件 dict。

        resume_value 非空时以 Command(resume=...) 恢复被 interrupt 的 thread；
        preset_intent 非空时跳过决策直通对应执行节点（文件流端点），extra_config
        合并进 configurable（files 等大 payload 不进 checkpoint）。
        事件契约：
            {"type": "progress", "node": "...", "steps": [...]}   节点完成（LangGraph updates）
            {"type": "delta"|"progress"|"artifact", ...}          节点内自定义事件（复用旧生成器词汇）
            {"type": "interrupt", "thread_id", "payload"}         等待用户确认
            {"type": "final", "response": AgentChatResponse, "thread_id"}  终态（有且仅有一个）
        """
        normalized_attachments = agent_service._normalize_attachments(attachments or [])
        invoke_input: Any
        if resume_value is not None:
            invoke_input = Command(resume=resume_value)
        else:
            # 新消息必须显式清零跨轮残留的 channel：agent_plan/preset_intent/final_response
            # 不清会沿用上一轮 checkpoint 里的值（如上轮 intent=jd 的计划），
            # 导致 route_intent 直接复用旧计划、跳过本轮意图决策
            invoke_input = {
                "user_message": message or "",
                "attachments": normalized_attachments,
                "confirmed_requirements": confirmed_requirements,
                "auto_execute": auto_execute,
                "conversation_id": conversation_id,
                "agent_plan": None,
                "preset_intent": preset_intent,
                "final_response": None,
            }
        configurable = {
            "agent_service": agent_service,
            "user_id": user_id,
            "thread_id": conversation_id or "",
            "streaming": True,
        }
        if extra_config:
            configurable.update(extra_config)
        config = {"configurable": configurable}

        saw_interrupt = False
        emitted_custom = False
        async for ns, mode, chunk in self.graph.astream(
            invoke_input, config, stream_mode=["updates", "custom"], subgraphs=True
        ):
            if mode == "custom":
                event = chunk.get("agent_event") if isinstance(chunk, dict) else None
                if not event:
                    continue
                emitted_custom = True
                if event.get("type") == "final":
                    # 终态统一由流结束后从 state 产出，避免双 final
                    continue
                yield event
            elif mode == "updates":
                if not isinstance(chunk, dict):
                    continue
                if "__interrupt__" in chunk:
                    saw_interrupt = True
                    continue
                for node_name, update in chunk.items():
                    if node_name.startswith("__"):
                        continue
                    # 子图内部节点带命名空间（如 "jd_edit:locate"），顶层节点直接用名字
                    display = ":".join([*ns, node_name]) if ns else node_name
                    yield {
                        "type": "progress",
                        "node": display,
                        "steps": (update or {}).get("steps") or [],
                    }

        if saw_interrupt:
            state = await self.graph.aget_state(config)
            values = state.values or {}
            payload = values.get("jd_interrupt_payload") or {}
            yield {
                "type": "interrupt",
                "thread_id": conversation_id,
                "payload": {
                    "artifacts": payload.get("artifacts") or [],
                    "missing_fields": payload.get("missing_fields") or [],
                },
            }
            yield {
                "type": "final",
                "thread_id": conversation_id,
                "response": {**payload, "requires_confirmation": True},
            }
            return

        state = await self.graph.aget_state(config)
        values = (state.values or {}) if state else {}
        final = values.get("final_response")
        if not final:
            yield {"type": "error", "error": "LangGraph 图未产出 final_response"}
            return
        if not emitted_custom and final.get("message"):
            # 未产生真实增量时，把最终回复按片段推送（与旧 stream_chat_agent 行为一致）
            async for delta in _stream_text(final["message"]):
                yield {"type": "delta", "delta": delta}
        yield {"type": "final", "thread_id": conversation_id, "response": final}

    def _response_from_result(self, result: Any) -> AgentChatResponse:
        """终态 state → AgentChatResponse；含 __interrupt__ 则返回确认请求响应。"""
        if isinstance(result, dict) and result.get("__interrupt__"):
            return self._response_from_interrupt(result)

        final = (result or {}).get("final_response")
        if final:
            return AgentChatResponse.model_validate(final)
        raise RuntimeError("LangGraph 图未产出 final_response")

    def _response_from_interrupt(self, result: Dict[str, Any]) -> AgentChatResponse:
        """interrupt 发生时组装 requires_confirmation 响应（兼容旧确认契约）。"""
        interrupts = result.get("__interrupt__") or []
        payload: Dict[str, Any] = {}
        if interrupts:
            value = getattr(interrupts[0], "value", None)
            if isinstance(value, dict):
                payload = value

        artifacts = [AgentArtifact.model_validate(item) for item in payload.get("artifacts") or []]
        return AgentChatResponse(
            message=payload.get("message") or "需要你确认后我再继续执行。",
            intent=payload.get("intent") or (result.get("intent") or "general"),
            route=payload.get("route") or result.get("route"),
            steps=[AgentStep.model_validate(item) for item in payload.get("steps") or []],
            artifacts=artifacts,
            suggestions=payload.get("suggestions") or [],
            requires_confirmation=True,
            missing_fields=payload.get("missing_fields") or [],
        )
