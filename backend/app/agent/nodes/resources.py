"""resource_delete 子图节点：parse → resolve → execute。

delete_parse   LLM/规则解析删除请求。
delete_resolve 低分候选人确认、指代上下文、列表匹配三分支；无类型/无匹配/多候选
               时以引导响应结束本轮，唯一目标写入 state 交由 execute。
delete_execute _delete_matched_resources 执行删除并产出结果响应。
响应文案与 step 序列与旧 _handle_resource_delete 逐字一致（评测契约）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from langgraph.config import RunnableConfig, get_stream_writer

from app.schemas.agent import AgentArtifact, AgentChatResponse, AgentStep


def _service(config: RunnableConfig):
    return config["configurable"]["agent_service"]


def _steps_in(state: Dict[str, Any]) -> List[AgentStep]:
    return [AgentStep.model_validate(item) for item in state.get("steps") or []]


def _steps_out(steps: List[AgentStep]) -> List[Dict[str, Any]]:
    return [step.model_dump() for step in steps]


def _set_step(steps: List[AgentStep], index: int, **updates: Any) -> None:
    steps[index] = steps[index].model_copy(update=updates)


async def delete_parse(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    delete_request = await service._parse_delete_request(state["user_message"])
    steps = [
        service._planning_step(service.tool_registry.get("resource_delete"), "识别到删除类请求，准备定位目标资源。"),
        AgentStep(
            id="locate_resource",
            title="定位删除目标",
            status="running",
            detail=service._delete_target_detail(delete_request.get("type"), delete_request.get("keyword") or ""),
            tool="delete_resource",
        ),
        AgentStep(id="delete_resource", title="执行删除操作", status="pending", detail="匹配到唯一目标后执行删除。"),
    ]
    return {"delete_request": delete_request, "steps": _steps_out(steps)}


async def delete_resolve(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    delete_request = state.get("delete_request") or {}
    steps = _steps_in(state)
    resource_type = delete_request.get("type")
    keyword = delete_request.get("keyword") or ""
    message = state["user_message"]
    user_id = config["configurable"]["user_id"]
    conversation_id = state.get("conversation_id")

    # 低分候选人：先看是否带确认语义
    if (
        resource_type == "resume"
        and not delete_request.get("confirm_context_low_scores")
        and re.search(r"低分|不合格|小于\s*60|低于\s*60|没通过|未通过", message)
    ):
        followup_action = await service._resolve_resume_screening_followup_action(message, user_id, conversation_id)
        if followup_action.get("action") == "confirm_delete_low_scores":
            return {"final_response": service._build_resume_screening_followup_response(
                followup_action, "/recruitment/resume-screening", service.tool_registry.get("resource_delete"),
            ).model_dump()}

    if resource_type == "resume" and delete_request.get("confirm_context_low_scores"):
        low_score_matches = await service._recent_low_score_resume_resources(user_id, conversation_id)
        if not low_score_matches:
            return {"final_response": AgentChatResponse(
                message="我没有在当前对话最近的评分结果里找到低分候选人，因此没有执行删除。你可以先完成简历评分，或明确说出候选人姓名。",
                intent="resource_delete",
                route="/recruitment/resume-screening",
                steps=[
                    service._planning_step(service.tool_registry.get("resource_delete"), "识别到确认删除低分候选人的请求。"),
                    AgentStep(id="locate_resource", title="定位低分候选人", status="failed", detail="没有找到可删除的低分候选人。"),
                ],
                suggestions=["先评分简历", "说出候选人姓名", "查看简历筛选列表"],
            ).model_dump()}
        steps = [
            service._planning_step(service.tool_registry.get("resource_delete"), "用户确认删除最近评分中的低分候选人。"),
            AgentStep(id="locate_resource", title="定位低分候选人", status="completed", detail=f"匹配到 {len(low_score_matches)} 位低分候选人。"),
            AgentStep(id="delete_resource", title="执行删除操作", status="running", detail="正在删除低分简历记录。"),
        ]
        return {
            "delete_matches": low_score_matches,
            "delete_steps": _steps_out(steps),
            "delete_keyword": "低分候选人",
            "delete_from_context": True,
        }

    if not resource_type:
        # 上一轮刚列出删除候选清单时，用户直接回名称/指代应继承清单的资源类型
        inherited = service._inherit_delete_type_from_candidates(
            state.get("artifacts") or [], message
        )
        if inherited:
            resource_type, matched_by_name = inherited
            delete_request = {**delete_request, "type": resource_type}
            if matched_by_name and not keyword:
                keyword = message
            _set_step(steps, 1, detail=service._delete_target_detail(resource_type, keyword))
        else:
            _set_step(steps, 1, status="failed", detail="缺少要删除的资源类型。")
            return {"final_response": AgentChatResponse(
                message="我还不确定你要删除哪类内容。请明确说明要删除 JD、简历记录、面试方案还是试卷，例如：帮我删除产品经理的 JD。",
                intent="resource_delete",
                route=None,
                steps=steps,
                artifacts=[],
                suggestions=["删除产品经理的 JD", "删除张三的简历记录", "删除 Java 试卷"],
            ).model_dump()}

    context_first = bool(delete_request.get("context_reference")) and not keyword
    if context_first:
        context_matches = await service._recent_generated_resources(resource_type, user_id, conversation_id)
        if context_matches:
            matches = context_matches if delete_request.get("delete_all") else context_matches[:1]
            return {
                "delete_matches": matches,
                "delete_steps": _steps_out(steps),
                "delete_keyword": keyword,
                "delete_from_context": True,
            }

    resources = await service._list_deletable_resources(resource_type, user_id, keyword)
    matches = service._match_delete_resources(resources, keyword, delete_request.get("latest"))
    if not matches:
        _set_step(steps, 1, status="failed", detail="没有找到匹配资源。")
        return {"final_response": AgentChatResponse(
            message=f"没有找到匹配的{service._resource_type_label(resource_type)}。你可以换个名称再试，或先到对应列表确认名称。",
            intent="resource_delete",
            route=service._resource_type_route(resource_type),
            steps=steps,
            artifacts=[AgentArtifact(
                type="delete_resource_result",
                title="删除结果",
                content={"resource_type": resource_type, "keyword": keyword, "deleted": [], "matches": []},
            )],
            suggestions=service._delete_suggestions(resource_type),
        ).model_dump()}

    if len(matches) > 1 and not delete_request.get("delete_all"):
        _set_step(steps, 1, status="running", detail=f"找到 {len(matches)} 个匹配项，需要用户确认。")
        candidates_artifact = AgentArtifact(
            type="delete_resource_candidates",
            title="待确认删除目标",
            content={"resource_type": resource_type, "keyword": keyword, "candidates": matches[:8]},
        )
        return {"final_response": AgentChatResponse(
            message=(
                f"我找到了 {len(matches)} 个匹配的{service._resource_type_label(resource_type)}，为避免误删，请说得更具体一点：\n"
                + "\n".join(f"- {item['name']}" for item in matches[:8])
            ),
            intent="resource_delete",
            route=service._resource_type_route(resource_type),
            steps=steps,
            artifacts=[candidates_artifact.model_dump()],
            suggestions=["补充更完整的名称", "说“删除最新的那个”", "到列表中确认后再删除"],
        ).model_dump(),
            "artifacts": [candidates_artifact.model_dump()],
            "steps": _steps_out(steps),
        }

    return {
        "delete_request": delete_request,
        "delete_matches": matches,
        "delete_steps": _steps_out(steps),
        "delete_keyword": keyword,
        "delete_from_context": False,
    }


async def delete_execute(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    delete_request = state.get("delete_request") or {}
    steps = _steps_in(state) if not state.get("delete_steps") else _steps_in({"steps": state["delete_steps"]})
    response = await service._delete_matched_resources(
        resource_type=delete_request.get("type"),
        matches=state.get("delete_matches") or [],
        user_id=config["configurable"]["user_id"],
        steps=steps,
        keyword=state.get("delete_keyword") or "",
        matched_from_context=bool(state.get("delete_from_context")),
    )
    dumped = response.model_dump()
    return {
        "final_response": dumped,
        "steps": dumped.get("steps") or [],
        "artifacts": dumped.get("artifacts") or [],
    }
