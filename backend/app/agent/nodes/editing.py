"""jd_edit / criteria_edit 子图节点。

每个意图拆为 4 节点链：parse（LLM 解析修改要求）→ locate（定位目标，多候选/缺
修改要求时以确认响应结束本轮）→ rewrite（LLM 改写正文）→ save（更新原记录）。
响应文案与 step 序列与旧 handler 逐字一致（评测契约）；流式进度经 stream writer
透传，无 checkpointer 的门面路径行为不变。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langgraph.config import RunnableConfig, get_stream_writer

from app.schemas.agent import AgentArtifact, AgentChatResponse, AgentStep

ROUTE_JD_EDIT = "/recruitment/jd-generator"
ROUTE_CRITERIA_EDIT = "/recruitment/resume-screening"


def _service(config: RunnableConfig):
    return config["configurable"]["agent_service"]


def _steps_in(state: Dict[str, Any]) -> List[AgentStep]:
    return [AgentStep.model_validate(item) for item in state.get("steps") or []]


def _steps_out(steps: List[AgentStep]) -> List[Dict[str, Any]]:
    return [step.model_dump() for step in steps]


def _emit(config: RunnableConfig, event: Dict[str, Any]) -> None:
    writer = get_stream_writer()
    if writer:
        writer({"agent_event": event})


def _final(state_updates: Dict[str, Any], response: AgentChatResponse) -> Dict[str, Any]:
    dumped = response.model_dump()
    state_updates["final_response"] = dumped
    state_updates["steps"] = dumped.get("steps") or []
    state_updates["artifacts"] = dumped.get("artifacts") or []
    return state_updates


def _done(state: Dict[str, Any]) -> bool:
    return bool(state.get("final_response"))


def _set_step(steps: List[AgentStep], index: int, **updates: Any) -> None:
    steps[index] = steps[index].model_copy(update=updates)


# ---------------------------------------------------------------- jd_edit

async def jd_edit_parse(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    edit_request = await service._parse_jd_edit_request(state["user_message"], state.get("memory_context") or "")
    steps = [
        service._planning_step(service.tool_registry.get("jd_edit"), "识别到 JD 修改请求，先定位目标 JD。"),
        AgentStep(id="locate_jd", title="定位要修改的 JD", status="running", detail="优先查找当前对话最近生成的 JD。", tool="edit_jd"),
        AgentStep(id="collect_changes", title="确认修改要求", status="pending", detail="拿到明确修改点后再改写。"),
        AgentStep(id="rewrite_jd", title="改写 JD 内容", status="pending", detail="基于原 JD 和修改要求生成新版。"),
        AgentStep(id="save_jd", title="保存修改", status="pending", detail="更新原 JD 记录。"),
    ]
    plan_response = AgentChatResponse(
        message="正在定位要修改的 JD。",
        intent="jd_edit",
        route=ROUTE_JD_EDIT,
        steps=steps,
        artifacts=[],
        suggestions=[],
    )
    _emit(config, {"type": "plan", "response": plan_response.model_dump()})
    return {"edit_request": edit_request, "steps": _steps_out(steps)}


async def jd_edit_locate(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    edit_request = state.get("edit_request") or {}
    steps = _steps_in(state)
    keyword = edit_request.get("keyword") or ""

    candidates = await service._resolve_recent_jd_candidates(
        config["configurable"]["user_id"], state.get("conversation_id"), keyword
    )
    if not candidates:
        _set_step(steps, 1, status="failed", detail="没有找到可修改的 JD。")
        return _final({}, AgentChatResponse(
            message="我还没有找到可以修改的 JD。请先生成或保存一个 JD，或者明确告诉我要修改哪个岗位的 JD。",
            intent="jd_edit",
            route=ROUTE_JD_EDIT,
            steps=steps,
            artifacts=[],
            suggestions=["生成一个新的 JD", "说明要修改的岗位名称", "去 JD 管理查看职位"],
        ))

    if len(candidates) > 1 and keyword:
        matches = service._match_delete_resources(candidates, keyword)
        if matches:
            candidates = matches

    if len(candidates) > 1:
        _set_step(steps, 1, status="running", detail=f"找到 {len(candidates)} 个可能的 JD，需要确认。")
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=(
                "我找到了多个可能要修改的 JD。为避免改错，请告诉我具体是哪一个：\n"
                + "\n".join(f"- {service._format_jd_candidate_label(item)}" for item in candidates[:5])
            ),
            intent="jd_edit",
            route=ROUTE_JD_EDIT,
            steps=steps,
            artifacts=[AgentArtifact(type="jd_edit_candidates", title="待确认 JD", content={"candidates": candidates[:5]})],
            suggestions=["修改最新的那个 JD", "说明岗位名称", "去 JD 管理查看职位"],
        ))

    target = candidates[0]
    _set_step(steps, 1, status="completed", detail=f"已定位：{target.get('name') or '最近的 JD'}。")
    edit_instructions = service._clean_optional_value(edit_request.get("changes"))
    if not edit_instructions:
        _set_step(steps, 2, status="pending", detail="等待用户说明要修改哪些内容。")
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"可以，我找到了「{target.get('name') or '最近的 JD'}」。你想具体改哪些内容？比如薪资、地点、职责、技能要求或福利。",
            intent="jd_edit",
            route=ROUTE_JD_EDIT,
            steps=steps,
            artifacts=[AgentArtifact(
                type="jd_edit_request",
                title="等待修改要求",
                content={"job_description_id": target.get("id"), "title": target.get("name")},
            )],
            suggestions=["薪资改成 20-30K", "增加 React 和性能优化要求", "把工作地点改成长沙"],
        ))

    _set_step(steps, 2, status="completed", detail=edit_instructions)
    return {
        "edit_target": target,
        "edit_instructions": edit_instructions,
        "steps": _steps_out(steps),
    }


async def jd_edit_rewrite(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    from app.services.job_description_service import JobDescriptionService

    target = state["edit_target"]
    instructions = state["edit_instructions"]
    steps = _steps_in(state)
    _set_step(steps, 3, status="running", detail="正在生成修改后的 JD。")
    try:
        original_jd = await JobDescriptionService(service.db).get_job_description(str(target["id"]), config["configurable"]["user_id"])
        original_data = original_jd.model_dump(mode="json")
        updated_content = await service._rewrite_jd_content(original_data.get("content") or "", instructions)
        _set_step(steps, 3, status="completed", detail="已生成修改后的 JD。")
        return {
            "edit_original_data": original_data,
            "edit_updated_content": updated_content,
            "steps": _steps_out(steps),
        }
    except Exception as exc:
        _set_step(steps, 4, status="failed", detail=str(exc))
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"我找到了 JD，但保存修改时失败了：{str(exc)}",
            intent="jd_edit",
            route=ROUTE_JD_EDIT,
            steps=steps,
            artifacts=[],
            suggestions=["稍后重试", "去 JD 管理手动编辑", "重新生成 JD"],
        ))


async def jd_edit_save(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    from app.services.job_description_service import JobDescriptionService

    target = state["edit_target"]
    instructions = state["edit_instructions"]
    steps = _steps_in(state)
    _set_step(steps, 4, status="running", detail="正在保存到原 JD。")
    try:
        updated_jd = await JobDescriptionService(service.db).update_job_description(
            str(target["id"]),
            service._build_jd_update_payload(state["edit_original_data"], state["edit_updated_content"], instructions, state.get("edit_request")),
            config["configurable"]["user_id"],
        )
        _set_step(steps, 4, status="completed", detail=f"已更新 JD：{updated_jd.id}")
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"已按你的要求更新「{updated_jd.title}」。",
            intent="jd_edit",
            route=ROUTE_JD_EDIT,
            steps=steps,
            artifacts=[AgentArtifact(
                type="job_description",
                title=f"{updated_jd.title} JD",
                content=updated_jd.content,
                metadata={
                    "job_title": updated_jd.title,
                    "saved_jd_id": str(updated_jd.id),
                    "edit_instructions": instructions,
                    "route": ROUTE_JD_EDIT,
                },
            )],
            suggestions=["继续修改 JD", "基于这个 JD 筛选简历", "去 JD 管理查看职位"],
        ))
    except Exception as exc:
        _set_step(steps, 4, status="failed", detail=str(exc))
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"我找到了 JD，但保存修改时失败了：{str(exc)}",
            intent="jd_edit",
            route=ROUTE_JD_EDIT,
            steps=steps,
            artifacts=[],
            suggestions=["稍后重试", "去 JD 管理手动编辑", "重新生成 JD"],
        ))


# ---------------------------------------------------------------- criteria_edit

async def criteria_edit_parse(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    edit_request = await service._parse_criteria_edit_request(state["user_message"], state.get("memory_context") or "")
    steps = [
        service._planning_step(service.tool_registry.get("criteria_edit"), "识别到评分标准修改请求，先定位目标评分标准。"),
        AgentStep(id="locate_criteria", title="定位评分标准", status="running", detail="优先查找当前对话最近生成的评分标准。", tool="edit_scoring_criteria"),
        AgentStep(id="collect_changes", title="确认修改要求", status="pending", detail="拿到明确修改点后再改写。"),
        AgentStep(id="rewrite_criteria", title="改写评分标准", status="pending", detail="基于原评分标准和修改要求生成新版。"),
        AgentStep(id="save_criteria", title="保存修改", status="pending", detail="更新原评分标准。"),
    ]
    plan_response = AgentChatResponse(
        message="正在定位要修改的评分标准。",
        intent="criteria_edit",
        route=ROUTE_CRITERIA_EDIT,
        steps=steps,
        artifacts=[],
        suggestions=[],
    )
    _emit(config, {"type": "plan", "response": plan_response.model_dump()})
    return {"edit_request": edit_request, "steps": _steps_out(steps)}


async def criteria_edit_locate(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    edit_request = state.get("edit_request") or {}
    steps = _steps_in(state)
    keyword = edit_request.get("keyword") or ""

    candidates = await service._resolve_recent_criteria_candidates(
        config["configurable"]["user_id"], state.get("conversation_id"), keyword
    )
    if not candidates:
        _set_step(steps, 1, status="failed", detail="没有找到可修改的评分标准。")
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message="我还没有找到可以修改的评分标准。请先生成并保存评分标准，或者明确告诉我要修改哪个岗位的评分标准。",
            intent="criteria_edit",
            route=ROUTE_CRITERIA_EDIT,
            steps=steps,
            artifacts=[],
            suggestions=["生成评分标准", "说明岗位名称", "查看简历筛选"],
        ))

    if len(candidates) > 1 and keyword:
        matches = service._match_delete_resources(candidates, keyword)
        if matches:
            candidates = matches
    if len(candidates) > 1:
        _set_step(steps, 1, status="running", detail=f"找到 {len(candidates)} 个可能的评分标准，需要确认。")
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message="我找到了多个可能要修改的评分标准。请告诉我具体是哪一个：\n" + "\n".join(f"- {item['name']}" for item in candidates[:5]),
            intent="criteria_edit",
            route=ROUTE_CRITERIA_EDIT,
            steps=steps,
            artifacts=[AgentArtifact(type="criteria_edit_candidates", title="待确认评分标准", content={"candidates": candidates[:5]})],
            suggestions=["修改最新的评分标准", "说明岗位名称", "查看评分标准列表"],
        ))

    target = candidates[0]
    _set_step(steps, 1, status="completed", detail=f"已定位：{target.get('name') or '最近的评分标准'}。")
    edit_instructions = service._clean_optional_value(edit_request.get("changes"))
    if not edit_instructions:
        _set_step(steps, 2, status="pending", detail="等待用户说明要修改哪些评分规则。")
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"可以，我找到了「{target.get('name') or '最近的评分标准'}」。你想具体改哪些评分规则？比如分值、维度、淘汰项或加分项。",
            intent="criteria_edit",
            route=ROUTE_CRITERIA_EDIT,
            steps=steps,
            artifacts=[AgentArtifact(
                type="criteria_edit_request",
                title="等待修改要求",
                content={"criteria_id": target.get("id"), "title": target.get("name")},
            )],
            suggestions=["技能匹配改成 40 分", "增加大模型项目经验加分项", "降低学历权重"],
        ))

    _set_step(steps, 2, status="completed", detail=edit_instructions)
    _set_step(steps, 3, status="running", detail="正在读取原评分标准并生成修改版。")
    return {
        "edit_target": target,
        "edit_instructions": edit_instructions,
        "steps": _steps_out(steps),
    }


async def criteria_edit_rewrite(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    from app.services.scoring_criteria_service import ScoringCriteriaService

    target = state["edit_target"]
    instructions = state["edit_instructions"]
    steps = _steps_in(state)
    try:
        original = await ScoringCriteriaService(service.db).get_scoring_criteria(str(target["id"]), config["configurable"]["user_id"])
        original_data = original.model_dump(mode="json")
        updated_content = await service._rewrite_criteria_content(original_data.get("content") or "", instructions)
        _set_step(steps, 3, status="completed", detail="已生成修改后的评分标准。")
        return {
            "edit_original_data": original_data,
            "edit_updated_content": updated_content,
            "steps": _steps_out(steps),
        }
    except Exception as exc:
        _set_step(steps, 4, status="failed", detail=str(exc))
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"我找到了评分标准，但保存修改时失败了：{str(exc)}",
            intent="criteria_edit",
            route=ROUTE_CRITERIA_EDIT,
            steps=steps,
            artifacts=[],
            suggestions=["稍后重试", "重新生成评分标准", "查看简历筛选"],
        ))


async def criteria_edit_save(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    from app.services.scoring_criteria_service import ScoringCriteriaService

    target = state["edit_target"]
    instructions = state["edit_instructions"]
    steps = _steps_in(state)
    _set_step(steps, 4, status="running", detail="正在保存到原评分标准。")
    try:
        updated = await ScoringCriteriaService(service.db).update_scoring_criteria(
            str(target["id"]),
            service._build_criteria_update_payload(state["edit_original_data"], state["edit_updated_content"], instructions),
            config["configurable"]["user_id"],
        )
        _set_step(steps, 4, status="completed", detail=f"已更新评分标准：{updated.id}")
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"已按你的要求更新「{updated.title}」。",
            intent="criteria_edit",
            route=ROUTE_CRITERIA_EDIT,
            steps=steps,
            artifacts=[AgentArtifact(
                type="scoring_criteria",
                title=updated.title,
                content=updated.content,
                metadata={
                    "job_title": updated.job_title,
                    "saved_criteria_id": str(updated.id),
                    "edit_instructions": instructions,
                    "route": ROUTE_CRITERIA_EDIT,
                },
            )],
            suggestions=["继续修改评分标准", "基于这个标准筛选简历", "重新生成评分标准"],
        ))
    except Exception as exc:
        _set_step(steps, 4, status="failed", detail=str(exc))
        return _final({"steps": _steps_out(steps)}, AgentChatResponse(
            message=f"我找到了评分标准，但保存修改时失败了：{str(exc)}",
            intent="criteria_edit",
            route=ROUTE_CRITERIA_EDIT,
            steps=steps,
            artifacts=[],
            suggestions=["稍后重试", "去简历筛选手动编辑", "重新生成评分标准"],
        ))
