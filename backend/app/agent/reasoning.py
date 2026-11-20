"""Agent 推理编排：意图决策（规则快通道 + 观察型 ReAct 路由）与会话记忆构建。

从 agent_service mixin 迁入 agent 包：这些是 LangGraph route_intent 节点的"大脑"，
与业务链路无关。共享的文本/附件工具函数（_filter_attachments、_format_memory_for_prompt、
_is_jd_edit_request 等）仍留在 service 上，本模块经 service 引用，避免双份实现。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.models.conversation import Conversation, Message, MessageRole
from app.agent.chains.types import ReActDecision

logger = logging.getLogger(__name__)

_VALID_ROUTER_MODES = {"rule", "react"}
_router_mode_warned = False


def router_mode() -> str:
    """读取路由模式；非法值按 rule 处理，避免配置笔误触发额外 LLM 调用。"""
    global _router_mode_warned
    mode = str(getattr(settings, "AGENT_ROUTER_MODE", "rule") or "rule").strip().lower()
    if mode in _VALID_ROUTER_MODES:
        return mode
    if not _router_mode_warned:
        logger.warning("未知 AGENT_ROUTER_MODE=%s，按 rule 处理", mode)
        _router_mode_warned = True
    return "rule"


async def resolve_intent_and_plan(
    service,
    message: str,
    normalized_attachments: List[Dict[str, Any]],
    memory_context: str,
    confirmed_requirements: Optional[Dict[str, Any]],
    agent_plan: Optional[Dict[str, Any]] = None,
    user_id=None,
    conversation_id: Optional[str] = None,
    artifacts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """意图与执行计划决策（route_intent 节点入口）。

    1.用户已回传 confirmed_requirements：跳过规划，直通确认后的工具链。
      - 有 action 且匹配 skill（如 send_email）→ 对应 skill intent。
      - 否则默认 jd 工具链。
    2.否则：规则快通道 → 观察型 ReAct 路由（失败回退本地关键词规则）。

    返回 (intent, agent_plan)。
    """
    if confirmed_requirements:
        confirmation_action = str(confirmed_requirements.get("action") or "").strip()
        confirmed_skill = service.skill_dispatcher.match_confirmation_action(confirmation_action) if confirmation_action else None
        if confirmed_skill:
            intent = confirmed_skill.intent
            agent_plan = {
                "mode": "tool",
                "intent": confirmed_skill.intent,
                "reason": f"用户已确认 {confirmed_skill.bundle_name} 所需信息，继续执行 skill。",
                "reply": None,
                "source": "confirmed_skill_action",
            }
        else:
            intent = "jd"
            agent_plan = {
                "mode": "tool",
                "intent": "jd",
                "reason": "用户已确认 JD 生成信息，继续执行 JD 工具链。",
                "reply": None,
                "source": "confirmed_requirements",
            }
        return intent, agent_plan

    agent_plan = agent_plan or build_rule_agent_plan(
        service, message, normalized_attachments, memory_context, artifacts
    )
    if agent_plan is None:
        agent_plan = await plan_agent_action(
            service,
            message,
            normalized_attachments,
            memory_context,
            user_id=user_id,
            conversation_id=conversation_id,
        )
    return agent_plan["intent"], agent_plan


def classify_agent_intent(service, message: str, attachments: List[Dict[str, Any]]) -> str:
    """轻量意图分类：优先规则和附件上下文，不为路由单独调用大模型。"""
    lowered = message.lower()
    if re.search(r"删除|删掉|移除|清理", message) and re.search(r"jd|职位|岗位|简历|候选人|面试|试卷|考试", lowered):
        return "resource_delete"
    if service._is_criteria_edit_request(message):
        return "criteria_edit"
    if service._is_jd_edit_request(message):
        return "jd_edit"

    fast_intent = service.intent_service.classify_intent_fast(message)
    if fast_intent in service.tool_registry:
        return fast_intent

    if service._filter_attachments(attachments, {"pdf", "doc", "docx", "txt", "md", "markdown"}) and re.search(r"评分|筛选|匹配|简历|候选人", message):
        return "resume_screening"
    if service._filter_attachments(attachments, {"pdf", "doc", "docx", "txt", "md", "markdown"}) and re.search(r"试卷|考试|出题|题目|笔试", message):
        return "exam_generate"
    if service._is_followup_resume_screening_loop_request(message) or service._is_followup_interview_exam_request(message):
        return "interview_plan" if service._is_followup_resume_screening_loop_request(message) else "exam_generate"
    if re.search(r"试卷|考试|出题|题目|笔试", message):
        return "exam_generate"
    if re.search(r"招聘|岗位|职位|jd|job", lowered):
        return "jd"
    if re.search(r"面试|候选人|邀约|通知|邮件", message):
        return "email_notification" if re.search(r"邮件|通知|邀约|邀请", message) else "interview_plan"
    return "general"


def build_rule_agent_plan(
    service,
    message: str,
    attachments: List[Dict[str, Any]],
    memory_context: str = "",
    artifacts: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """规则快通道：明确命中 HR 工具意图时跳过 LLM 决策。"""
    if classify_agent_intent(service, message, attachments) == "resource_delete":
        return {
            "mode": "tool",
            "intent": "resource_delete",
            "reason": "用户明确要求删除招聘相关产物，调用删除资源工具。",
            "reply": None,
            "source": "delete_rule",
        }
    if service._is_criteria_edit_request(message) or service._is_criteria_edit_followup(message, memory_context):
        return {
            "mode": "tool",
            "intent": "criteria_edit",
            "reason": "用户要求修改评分标准，先定位最近评分标准并确认修改要求。",
            "reply": None,
            "source": "criteria_edit_rule",
        }
    if service._is_jd_edit_request(message) or service._is_jd_edit_followup(message, memory_context):
        return {
            "mode": "tool",
            "intent": "jd_edit",
            "reason": "用户要求修改已有 JD，先定位最近 JD 并确认修改要求。",
            "reply": None,
            "source": "jd_edit_rule",
        }
    rule_intent = classify_agent_intent(service, message, attachments)
    if rule_intent in {"jd", "resume_screening", "interview_plan", "exam_generate", "email_notification"}:
        return {
            "mode": "tool",
            "intent": rule_intent,
            "reason": "本地规则已明确识别到 HR 工具任务，优先进入对应业务链路。",
            "reply": None,
            "source": "rule_intent",
        }
    # 兜底：上一轮刚列出删除候选清单，用户回复的是候选名称/指代且未命中其它意图时，
    # 继续删除确认流程。必须放在通用意图规则之后，避免“生成一个JD<候选名>”这类
    # 含候选名称的明确意图被抢先路由进删除流程
    if service._inherit_delete_type_from_candidates(artifacts or [], message):
        return {
            "mode": "tool",
            "intent": "resource_delete",
            "reason": "上一轮刚列出删除候选清单，用户回复的是候选名称或指代，继续删除确认流程。",
            "reply": None,
            "source": "delete_followup_rule",
        }
    return None


def _allowed_intents(service) -> List[str]:
    return sorted({*service.tool_registry.keys(), "general"})


def _decision_to_plan(decision: ReActDecision) -> Dict[str, Any]:
    return {
        "mode": decision.mode,
        "intent": decision.intent,
        "action": decision.action,
        "confidence": decision.confidence,
        "reason": decision.thought,
        "observation": decision.observation,
        "reply": decision.reply,
        "source": decision.source,
    }


async def plan_agent_action(
    service,
    message: str,
    attachments: List[Dict[str, Any]],
    memory_context: str = "",
    user_id=None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """观察型 ReAct 路由：create_agent 只读工具循环 + 结构化决策。

    有限动作空间版本：模型只能在 chat / use_tool / ask_user 中选择，
    use_tool 只能选择 tool_registry 声明过的业务工具。
    `AGENT_ROUTER_MODE=react`（默认）时走真实工具循环，模型可先调用
    search_resources 观察"刚才那个/上次那个"指向的资源再决策；
    `rule` 模式或 LLM 不可用/调用失败时，回退 classify_agent_intent() 的本地规则。
    """
    if router_mode() == "react" and user_id is not None:
        from app.agent.llm import chat_llm_available

        if chat_llm_available():
            try:
                from app.agent.routing_agent import run_router_agent

                decision = await run_router_agent(
                    service=service,
                    message=message,
                    attachments=attachments,
                    memory_context=memory_context,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    allowed_intents=_allowed_intents(service),
                )
                if decision.intent in _allowed_intents(service):
                    return _decision_to_plan(ReActDecision(
                        mode=decision.mode,
                        intent=decision.intent,
                        action=decision.action,
                        thought=decision.thought,
                        observation=decision.observation or "ReAct 路由已查询工具观察现状。",
                        confidence=decision.confidence,
                        reply=decision.reply,
                        source="react_router",
                    ))
                logger.info("ReAct 路由意图非法 intent=%s，回退本地规则", decision.intent)
            except Exception as exc:
                logger.warning("ReAct 路由失败，回退本地规则: %s", exc)

    fallback_intent = classify_agent_intent(service, message, attachments)
    fallback_action = "use_tool" if fallback_intent in service.tool_registry else "chat"
    decision = ReActDecision(
        mode="tool" if fallback_intent in service.tool_registry else "chat",
        intent=fallback_intent,
        action=fallback_action,
        thought="ReAct 路由不可用后，使用本地关键词和附件规则选择下一步。",
        observation="本地规则已给出可执行意图。" if fallback_action == "use_tool" else "未匹配到需要调用的工具。",
        source="fallback",
    )
    return _decision_to_plan(decision)


async def build_conversation_memory(
    service,
    conversation_id: Optional[str],
    user_id: UUID,
    current_message: str,
    limit: int = 12,
    max_chars: int = 6000,
) -> str:
    """读取最近消息拼成文本记忆（ReAct 决策 / 聊天 / 解析 / 指代消解共用）。"""
    if not conversation_id:
        return ""
    try:
        conversation_uuid = UUID(str(conversation_id))
    except Exception:
        return ""

    try:
        conversation_result = await service.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_uuid,
                Conversation.user_id == user_id,
            )
        )
        if not conversation_result.scalar_one_or_none():
            return ""

        result = await service.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_uuid)
            .order_by(Message.created_at.desc())
            .limit(limit + 3)
        )
        messages = list(reversed(result.scalars().all()))
    except Exception as exc:
        logger.warning("读取 Agent 对话记忆失败: %s", exc)
        return ""

    normalized_current = service._normalize_memory_text(current_message)
    memory_lines: List[str] = []
    for item in messages:
        content = service._normalize_memory_text(item.content)
        if not content:
            continue
        if item.role == MessageRole.USER and normalized_current and content.startswith(normalized_current):
            continue
        role_label = "用户" if item.role == MessageRole.USER else "助手"
        if item.role == MessageRole.SYSTEM:
            role_label = "系统"
        memory_lines.append(f"{role_label}: {content[:900]}")

    memory = "\n".join(memory_lines)
    if len(memory) > max_chars:
        memory = memory[-max_chars:]
    return memory.strip()
