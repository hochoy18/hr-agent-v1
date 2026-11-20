"""HR Agent 的 LangGraph 图编排实现。

目录结构：
    state.py       AgentState 定义
    checkpoint.py  AsyncPostgresSaver 检查点器
    graph.py       主图构建（路由 + 意图节点）
    bridge.py      图调用桥（非流式 / 流式 / resume）
    nodes/         路由节点与意图节点
"""
