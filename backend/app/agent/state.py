"""AgentState：LangGraph 图的共享状态定义。

设计要点：
    - 不使用 messages/add_messages：每轮对话按 thread_id 复用图状态，artifacts 用
      自定义 reducer 跨轮累积，作为"刚才那个"产物反查的数据源（阶段2 起）。
    - db / user_id 等不可序列化对象一律通过 RunnableConfig["configurable"] 传递，
      不进入 checkpoint。
    - steps 用普通 channel（后写覆盖），每轮由意图节点产出完整列表。
"""
from typing import Annotated, Any, Dict, List, Optional, TypedDict


def add_artifacts(left: Optional[List[Dict[str, Any]]], right: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """artifacts 累积 reducer：跨轮保留全部产物，供编辑/删除链路反查。"""
    merged: List[Dict[str, Any]] = list(left or [])
    for item in right or []:
        merged.append(item)
    # 只保留有限条数，避免长会话 checkpoint 膨胀
    return merged[-50:]


class AgentState(TypedDict, total=False):
    # 本轮输入
    user_message: str
    attachments: List[Dict[str, Any]]  # 已标准化的附件
    confirmed_requirements: Optional[Dict[str, Any]]
    auto_execute: bool
    conversation_id: Optional[str]

    # 路由结果
    intent: str
    route: Optional[str]
    agent_plan: Dict[str, Any]
    memory_context: str
    dest_node: str  # 条件边目标节点（路由节点算好，条件边直接读）

    # 执行过程（每轮覆盖）
    steps: List[Dict[str, Any]]

    # 产物（跨轮累积，checkpoint 持久化）
    artifacts: Annotated[List[Dict[str, Any]], add_artifacts]

    # 终态（本轮覆盖）：完整 AgentChatResponse.model_dump()
    final_response: Optional[Dict[str, Any]]

    # JD 子图中间状态（阶段2 interrupt 确认流）
    parsed_requirements: Optional[Dict[str, Any]]
    jd_missing_fields: List[str]
    jd_interrupt_payload: Optional[Dict[str, Any]]

    # 编辑/删除子图中间状态（jd_edit / criteria_edit / resource_delete 同轮互斥，字段共用）
    edit_request: Optional[Dict[str, Any]]
    edit_target: Optional[Dict[str, Any]]
    edit_instructions: Optional[str]
    edit_original_data: Optional[Dict[str, Any]]
    edit_updated_content: Optional[str]
    delete_request: Optional[Dict[str, Any]]
    delete_matches: Optional[List[Dict[str, Any]]]
    delete_steps: Optional[List[Dict[str, Any]]]
    delete_keyword: Optional[str]
    delete_from_context: Optional[bool]

    # 文件流等端点的直通执行：路由节点见 preset_intent 时跳过决策直达对应节点
    preset_intent: Optional[str]
