"""JD 意图子图：解析 → 确认（interrupt / 兼容回传）→ 执行生成链。

拆成三个节点的关键原因：
    - LangGraph 的 interrupt 发生时，节点内此前的状态写入会被丢弃，resume 后整个
      节点从头重跑。把 LLM 解析放在独立节点（jd_prepare 先完成），确认节点只做
      interrupt，避免 resume 后重复解析导致结果漂移。
    - 无 checkpointer 的调用路径（AgentService.chat() 兼容门面 / 评测）不能 interrupt，
      jd_confirm 检测不到 thread_id 时直接返回 requires_confirmation 响应，与旧
      confirmed_requirements 回传语义完全一致。
"""
from __future__ import annotations

from typing import Any, Dict, List

from langgraph.config import RunnableConfig
from langgraph.types import interrupt

from app.agent.nodes.legacy import _respond
from app.schemas.agent import AgentArtifact, AgentStep


async def jd_prepare(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """解析招聘需求；已有确认信息时跳过解析。"""
    from app.services.agent_service import AgentService

    service: AgentService = config["configurable"]["agent_service"]
    if state.get("confirmed_requirements"):
        return {}

    parsed = await service._parse_requirements(
        state["user_message"],
        state.get("conversation_id"),
        state.get("memory_context") or "",
    )
    missing: List[str] = service._missing_required_fields(parsed)
    selected_tool = service.tool_registry.get("jd")

    if missing:
        message = "我先补齐 JD 生成的必要信息，再生成会更稳。请在弹窗里确认或补充这些字段。"
        steps = [
            service._planning_step(selected_tool, "已选择 JD 生成工具；先补齐必要字段再执行。"),
            AgentStep(id="parse", title="解析招聘需求", status="completed", detail=service._brief_requirements(parsed), tool="parse_requirements"),
            AgentStep(id="confirm", title="确认招聘信息", status="pending", detail=f"待补充：{'、'.join(service._field_label(field) for field in missing)}"),
            AgentStep(id="jd", title="生成岗位 JD", status="pending", tool="generate_jd"),
        ]
    else:
        message = "我已提取到 JD 生成所需信息。请在弹窗中确认，确认后我再调用 JD 生成工具。"
        steps = [
            service._planning_step(selected_tool, "已选择 JD 生成工具；等待用户确认后执行。"),
            AgentStep(id="parse", title="解析招聘需求", status="completed", detail=service._brief_requirements(parsed), tool="parse_requirements"),
            AgentStep(id="confirm", title="确认招聘信息", status="pending", detail="等待用户确认后执行生成。"),
            AgentStep(id="jd", title="生成岗位 JD", status="pending", tool="generate_jd"),
        ]

    payload = {
        "message": message,
        "intent": "jd",
        "route": state.get("route"),
        "steps": [step.model_dump() for step in steps],
        "artifacts": [AgentArtifact(type="requirements", title="待确认招聘需求", content=parsed).model_dump()],
        "missing_fields": missing,
        "suggestions": [],
    }
    return {
        "parsed_requirements": parsed,
        "jd_missing_fields": missing,
        "jd_interrupt_payload": payload,
    }


async def jd_confirm(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """等待用户确认：有 checkpointer 时 interrupt 暂停；否则直接返回确认请求响应（旧语义）。"""
    if state.get("confirmed_requirements"):
        return {}

    payload = state.get("jd_interrupt_payload") or {}
    configurable = config.get("configurable") or {}
    if not configurable.get("thread_id"):
        # 兼容门面（无 checkpointer）：以普通响应结束本轮，前端按旧契约回传 confirmed_requirements
        return {
            "final_response": {**payload, "requires_confirmation": True},
            "steps": payload.get("steps") or [],
            "artifacts": payload.get("artifacts") or [],
        }

    # LangGraph 人机确认：暂停图执行，resume 值即旧 confirmed_requirements 结构
    resume_value = interrupt(payload)
    return {"confirmed_requirements": resume_value if isinstance(resume_value, dict) else {}}


async def jd_execute(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """确认完成：执行 JD → 评分标准 → 保存 的生成链。"""
    from app.agent.nodes.legacy import _emit_generator, _respond, _respond_from_event
    from app.services.agent_service import AgentService

    service: AgentService = config["configurable"]["agent_service"]
    confirmed = state.get("confirmed_requirements")

    if (config.get("configurable") or {}).get("streaming"):
        # 流式路径：复用旧 stream_recruitment_agent（Dify 流式 + 阶段进度），事件经 writer 透传
        final_event = await _emit_generator(service.stream_recruitment_agent(
            state["user_message"],
            config["configurable"]["user_id"],
            state.get("conversation_id"),
            confirmed,
        ))
        if final_event:
            return _respond_from_event(final_event)

    parsed = service._normalize_requirements(confirmed, state["user_message"])
    response = await service._run_recruitment_agent(
        state["user_message"],
        state.get("conversation_id"),
        state.get("route"),
        parsed_requirements=parsed,
        user_id=config["configurable"]["user_id"],
    )
    return await _respond(config, response)
