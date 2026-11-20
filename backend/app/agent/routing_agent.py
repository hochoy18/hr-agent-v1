"""观察型 ReAct 路由：create_agent + 只读查询工具 + 结构化决策。

只做“选路”：模型可以先调用 search_resources 观察最近资源，再输出 RouterDecision。
删除、发送、落库等写操作仍由主图的确定性子图执行，本模块不持有写工具。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Literal, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field, model_validator

from app.agent.llm import get_router_model
from app.agent.tools.router_tools import ROUTER_TOOLS
from app.core.config import settings

if TYPE_CHECKING:
    from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

# (允许的 intent 集合, 工具说明) -> 编译后的 agent；skills 变化后说明变化会自然换 key
_router_agents: Dict[Tuple[FrozenSet[str], str], Any] = {}


class RouterDecision(BaseModel):
    """ReAct 路由器的结构化决策（只用于选路，不执行写操作）。"""

    mode: Literal["chat", "tool"] = Field(..., description="chat=普通对话；tool=进入业务工具链")
    action: Literal["chat", "use_tool", "ask_user"] = Field(
        ..., description="chat/use_tool/ask_user"
    )
    intent: str = Field(..., min_length=1, description="必须是系统提示中列出的 intent 之一")
    thought: str = Field(..., min_length=1, description="一句简短推理摘要")
    observation: str = Field("", description="工具观察到的现状或已知前置条件")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="0-1 置信度")
    reply: Optional[str] = Field(None, description="action=chat 时的自然回复，否则为 null")

    @model_validator(mode="after")
    def _check_action_mode(self):
        expected = "chat" if self.action == "chat" else "tool"
        if self.mode != expected:
            raise ValueError(f"mode={self.mode} 与 action={self.action} 不一致")
        return self


def _tool_text(service: "AgentService", allowed_intents: List[str]) -> str:
    lines = []
    for intent, tool in service.tool_registry.items():
        if intent not in allowed_intents:
            continue
        lines.append(
            f"- {intent}: {tool.name}，{tool.description}；前置条件：{'、'.join(tool.prerequisites)}"
        )
    return "\n".join(lines) or "- 无可用业务工具"


def _system_prompt(allowed_intents: List[str], tool_text: str) -> str:
    return (
        "你是 HR Agent 的 ReAct 路由器。你只负责选择下一步动作，不执行任何写操作；"
        "删除、发送、落库由后续确定性链路执行。\n\n"
        "你可以调用只读工具 search_resources 查询当前用户/当前对话最近的资源。"
        "当用户说“刚才、上次、这个、那个、前面的”等指代时，先调用工具观察，再决策。\n\n"
        "可用业务工具：\n"
        f"{tool_text}\n\n"
        "动作空间：\n"
        "- chat: 普通对话、打招呼、解释能力边界，不调用业务工具。\n"
        "- use_tool: 用户明确要执行 HR 任务，选择一个业务工具 intent。\n"
        "- ask_user: 目标明确但缺少关键前置条件，选择对应 intent，由业务链路追问。\n\n"
        "决策规则：\n"
        "1. 不确定时优先 chat，避免误触发工具。\n"
        "2. 生成/修改 JD、修改评分标准、简历筛选、面试计划、试卷生成、邮件草稿选择对应工具。\n"
        "3. 缺少附件、JD、候选人、考试配置等前置条件时，选择 ask_user 或 use_tool；"
        "后续工具链会生成表单/选择器。\n"
        "4. 邮件只能生成草稿，不允许自动发送。\n"
        f"5. intent 只能是这些值之一：{', '.join(allowed_intents)}。\n"
        "6. 删除类请求只有在工具观察到明确目标时才选择 resource_delete；不要臆造名称或 ID。\n"
        "7. mode 与 action 必须一致：action=chat 时 mode=chat，其余 mode=tool。\n"
        "8. thought 只写一句简短推理摘要，不要展开内部推理。\n"
    )


def _get_router_agent(allowed_intents: List[str], tool_text: str):
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    key = (frozenset(allowed_intents), tool_text)
    agent = _router_agents.get(key)
    if agent is None:
        agent = create_agent(
            model=get_router_model(),
            tools=ROUTER_TOOLS,
            system_prompt=_system_prompt(allowed_intents, tool_text),
            response_format=ToolStrategy(RouterDecision),
            name="hr_router_agent",
        )
        _router_agents[key] = agent
        logger.info(
            "ReAct 路由 agent 已构建，tools=%d intents=%d",
            len(ROUTER_TOOLS),
            len(allowed_intents),
        )
    return agent


def _attachment_text(attachments: List[Dict[str, Any]]) -> str:
    if not attachments:
        return "无"
    return "、".join(
        f"{item.get('name')}({item.get('extension') or '未知格式'})"
        for item in attachments
    )


async def run_router_agent(
    *,
    service: "AgentService",
    message: str,
    attachments: List[Dict[str, Any]],
    memory_context: str,
    user_id: Any,
    conversation_id: Optional[str],
    allowed_intents: List[str],
) -> RouterDecision:
    """执行一次观察型路由循环，返回结构化决策；失败由调用方兜底。"""
    tool_text = _tool_text(service, allowed_intents)
    agent = _get_router_agent(allowed_intents, tool_text)

    messages = []
    if memory_context:
        messages.append(
            SystemMessage(content=f"历史对话记忆（供理解当前消息参考）：\n{memory_context}")
        )
    messages.append(
        HumanMessage(
            content=(
                f"用户消息：{message}\n"
                f"附件：{_attachment_text(attachments)}\n"
                f"当前线程已累积产物数：{len(getattr(service, '_graph_artifacts', None) or [])}"
            )
        )
    )

    config = {
        "configurable": {
            "agent_service": service,
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
        "recursion_limit": settings.AGENT_ROUTER_RECURSION_LIMIT,
    }
    started = time.perf_counter()
    max_attempts = max(1, int(settings.AGENT_ROUTER_MAX_ATTEMPTS))
    decision = None
    result: Dict[str, Any] = {}
    for attempt in range(1, max_attempts + 1):
        result = await asyncio.wait_for(
            agent.ainvoke({"messages": messages}, config),
            timeout=settings.AGENT_ROUTER_TIMEOUT_SECONDS,
        )
        decision = result.get("structured_response")
        if decision is not None:
            if attempt > 1:
                logger.info("ReAct 路由结构化决策在第 %d 次尝试成功", attempt)
            break
        logger.warning(
            "ReAct 路由未产出 structured_response（第 %d/%d 次）",
            attempt,
            max_attempts,
        )

    if decision is None:
        raise RuntimeError("ReAct 路由未产出 structured_response")
    if isinstance(decision, dict):
        decision = RouterDecision.model_validate(decision)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    tool_calls = len(
        [item for item in result.get("messages") or [] if isinstance(item, ToolMessage)]
    )
    logger.info(
        "ReAct 路由完成 intent=%s action=%s confidence=%s tool_calls=%d latency_ms=%d",
        decision.intent,
        decision.action,
        decision.confidence,
        tool_calls,
        elapsed_ms,
    )
    return decision
