"""主图构建：START → route_intent →（条件边）→ 意图子图 → END。

主图只做路由与分发；每个意图是独立编译的子图（StateGraph.compile() 后作为节点挂入）：
    - jd             jd_prepare → jd_confirm(interrupt) → jd_execute
    - jd_edit        parse → locate → rewrite → save（4 节点，确认响应结束本轮）
    - criteria_edit  parse → locate → rewrite → save
    - resource_delete parse → resolve → execute
    - skill          skill_draft → skill_send（响应式确认）
    - interview_plan / exam_generate / resume_screening   单步准备子图
    - chat           create_agent ReAct 工具循环（作为普通节点调用）
    - resume_exec / interview_exec / exam_exec   文件流直通执行

子图与主图共用 AgentState schema，channel 值自动透传；子图内 get_stream_writer
的自定义事件会冒泡到父图 astream，SSE 事件契约不变。
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes.editing import (
    criteria_edit_locate,
    criteria_edit_parse,
    criteria_edit_rewrite,
    criteria_edit_save,
    jd_edit_locate,
    jd_edit_parse,
    jd_edit_rewrite,
    jd_edit_save,
)
from app.agent.nodes.files import exam_exec_node, interview_exec_node, resume_exec_node
from app.agent.nodes.jd import jd_confirm, jd_execute, jd_prepare
from app.agent.nodes.legacy import INTENT_NODES
from app.agent.nodes.planning import exam_generate_prepare, interview_plan_prepare, resume_screening_prepare
from app.agent.nodes.resources import delete_execute, delete_parse, delete_resolve
from app.agent.nodes.routing import route_intent_node
from app.agent.nodes.skill import skill_draft_node, skill_send_node
from app.agent.state import AgentState

EXEC_NODES = {
    "resume_exec": resume_exec_node,
    "interview_exec": interview_exec_node,
    "exam_exec": exam_exec_node,
}


def _sequential_subgraph(steps: list[tuple[str, Any]], end_after: set[str]) -> CompiledStateGraph:
    """构建"节点顺序链 + 完成即终止"的意图子图。

    end_after 中的节点写入 final_response 后子图结束，其余情况继续走下一节点。
    """
    builder = StateGraph(AgentState)
    for name, node_fn in steps:
        builder.add_node(name, node_fn)
    builder.add_edge(START, steps[0][0])
    for index, (name, _node_fn) in enumerate(steps):
        if name not in end_after:
            if index + 1 < len(steps):
                builder.add_edge(name, steps[index + 1][0])
            continue
        if index + 1 < len(steps):
            nxt = steps[index + 1][0]

            def _route(state, nxt: str = nxt) -> str:
                return END if state.get("final_response") else nxt

            builder.add_conditional_edges(name, _route, {nxt: nxt, END: END})
        else:
            builder.add_conditional_edges(name, lambda state: END, {END: END})
    if steps[-1][0] not in end_after:
        builder.add_edge(steps[-1][0], END)
    return builder.compile()


def _compile_editing_subgraphs() -> Dict[str, CompiledStateGraph]:
    jd_edit = _sequential_subgraph(
        [
            ("parse", jd_edit_parse),
            ("locate", jd_edit_locate),
            ("rewrite", jd_edit_rewrite),
            ("save", jd_edit_save),
        ],
        end_after={"locate", "rewrite", "save"},
    )
    criteria_edit = _sequential_subgraph(
        [
            ("parse", criteria_edit_parse),
            ("locate", criteria_edit_locate),
            ("rewrite", criteria_edit_rewrite),
            ("save", criteria_edit_save),
        ],
        end_after={"locate", "rewrite", "save"},
    )
    return {"jd_edit": jd_edit, "criteria_edit": criteria_edit}


def _compile_delete_subgraph() -> CompiledStateGraph:
    return _sequential_subgraph(
        [
            ("parse", delete_parse),
            ("resolve", delete_resolve),
            ("execute", delete_execute),
        ],
        end_after={"resolve", "execute"},
    )


def _compile_planning_subgraphs() -> Dict[str, CompiledStateGraph]:
    result: Dict[str, CompiledStateGraph] = {}
    for name, node_fn in (
        ("interview_plan", interview_plan_prepare),
        ("exam_generate", exam_generate_prepare),
        ("resume_screening", resume_screening_prepare),
    ):
        builder = StateGraph(AgentState)
        builder.add_node("prepare", node_fn)
        builder.add_edge(START, "prepare")
        builder.add_edge("prepare", END)
        result[name] = builder.compile()
    return result


def build_graph(checkpointer=None) -> CompiledStateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("route_intent", route_intent_node)
    builder.add_node("jd_prepare", jd_prepare)
    builder.add_node("jd_confirm", jd_confirm)
    builder.add_node("jd_execute", jd_execute)
    builder.add_node("skill_draft", skill_draft_node)
    builder.add_node("skill_send", skill_send_node)
    builder.add_node("chat", INTENT_NODES["chat"])

    intent_subgraphs: Dict[str, CompiledStateGraph] = {}
    intent_subgraphs.update(_compile_editing_subgraphs())
    intent_subgraphs["resource_delete"] = _compile_delete_subgraph()
    intent_subgraphs.update(_compile_planning_subgraphs())
    for name, subgraph in intent_subgraphs.items():
        builder.add_node(name, subgraph)

    for name, node_fn in EXEC_NODES.items():
        builder.add_node(name, node_fn)

    builder.add_edge(START, "route_intent")
    builder.add_conditional_edges(
        "route_intent",
        _route_destination,
        {
            "chat": "chat",
            "jd_prepare": "jd_prepare",
            "jd_edit": "jd_edit",
            "criteria_edit": "criteria_edit",
            "resource_delete": "resource_delete",
            "resume_screening": "resume_screening",
            "interview_plan": "interview_plan",
            "exam_generate": "exam_generate",
            "skill_draft": "skill_draft",
            "resume_exec": "resume_exec",
            "interview_exec": "interview_exec",
            "exam_exec": "exam_exec",
        },
    )
    builder.add_edge("jd_prepare", "jd_confirm")
    builder.add_conditional_edges(
        "jd_confirm",
        _after_jd_confirm,
        {"jd_execute": "jd_execute", END: END},
    )
    builder.add_edge("jd_execute", END)
    builder.add_conditional_edges(
        "skill_draft",
        _after_skill_draft,
        {"skill_send": "skill_send", END: END},
    )
    builder.add_edge("skill_send", END)
    for name in [*intent_subgraphs.keys(), *EXEC_NODES.keys()]:
        builder.add_edge(name, END)

    return builder.compile(checkpointer=checkpointer)


def _route_destination(state) -> str:
    dest = state.get("dest_node") or "chat"
    if dest == "jd":
        return "jd_prepare"
    return dest


def _after_jd_confirm(state):
    # confirmed_requirements 非空 = 用户已确认（interrupt resume / 兼容回传），继续执行；
    # 否则 jd_confirm 本轮产出的是确认请求响应，直接结束。不读 final_response：
    # checkpoint 跨轮残留的旧值会误判
    if state.get("confirmed_requirements"):
        return "jd_execute"
    return END


def _after_skill_draft(state):
    # confirmed_requirements 非空 = 确认回传轮，skill_draft 空过，放行 send；
    # 否则草稿响应结束本轮
    if state.get("confirmed_requirements"):
        return "skill_send"
    return END
