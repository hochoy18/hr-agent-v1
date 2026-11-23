# examples

## async_generator_usage.ipynb

AsyncGenerator 用法速览（代码为主，5 个模块）：基础惰性迭代 → yield 间 await →
项目 progress/delta/final 事件流协议 → 真实 `_emit_generator`（legacy.py）→
真实 `LLMService.stream_response` 流式输出（1 次 LLM 调用）。

## debug_agent_graph.ipynb

针对 `app/agent/graph.py` `build_graph()` 的全流程调试 Notebook：逐节点观察
**route_intent 路由 → 意图子图 → jd_confirm interrupt 暂停 → Command(resume) 恢复执行** 的状态流转。

### 运行方式

1. 选择 kernel：`HR Agent Backend (.venv)`（已注册；若不存在执行
   `.venv/bin/python -m ipykernel install --user --name hr-agent-backend --display-name "HR Agent Backend (.venv)"`）
2. 从 `backend/` 或 `backend/examples/` 启动 Jupyter / VS Code，按顺序执行单元格。

### 两种模式

- **沙箱模式（默认，§0–§7）**：LLM/Dify 全部打桩、`AgentService(db=None)`、MemorySaver 内存
  checkpoint。不发起任何外部调用、不写数据库，适合调试图拓扑、interrupt/resume 机制、
  checkpoint 历史。依赖：`ipykernel`、`grandalf`（ASCII 图渲染，可选）。
- **真实模式（§8，`RUN_REAL=False` 默认关闭）**：真实 LLM/Dify + AsyncPostgresSaver。
  ⚠️ 消耗模型配额，JD 链路会向数据库写入 JD 与评分标准记录。

### 覆盖场景

| 场景 | 对应 HTTP 入口 |
|---|---|
| A 路由探针（只决策不执行） | — |
| B JD 全链路 interrupt → resume（含必填字段缺失变体） | `POST /agent/graph/chat` + `/agent/graph/resume` |
| C preset_intent 直通 exec 节点 | `POST /agent/resume-screen/stream` 等文件流端点 |
| D chat 分支 + 同 thread 多轮 / 子图命名空间 | `POST /agent/graph/chat` |
| §7 checkpoint 历史 / thread 列表 / 回滚重放说明 | — |

## test_reasoning_real_cases.ipynb

针对 `app/agent/reasoning.py`（route_intent 节点的意图决策 + 会话记忆）的
**真实链路**测试：真实 DB 会话 + 真实 LLM 路由器（react 模式），不打桩、不 Fake。
所有 case 模拟 HR Agent 现有业务场景，**全程只读数据库、不执行删除**。

### 运行方式

同上（kernel `HR Agent Backend (.venv)`）。前提：`.env` 已配置 `LLM_API_KEY`，
`DATABASE_URL` 可连通，且库里有真实对话消息（自动选消息最多的用户）。

### 覆盖场景

| 章节 | 场景 | LLM 调用 |
|---|---|---|
| §1 | 规则快通道 11 例：JD 生成/编辑、评分标准编辑、删除、简历筛选、试卷、面试、邮件、追问循环 | 无 |
| §2 | confirmed_requirements 直通（JD 确认 / send_email skill 确认） | 无 |
| §3 | 真实会话记忆构建（去重 / limit 截断 / 非 UUID 短路） | 无 |
| §4 | 真实 ReAct 路由：闲聊 / 资源盘点 / 记忆回顾 / 模糊招聘需求（ask_user） | 4 次 |
| §4.1 | 回退复盘：递归上限 8 不够 / structured_response 缺失 → 调高上限重试观察成功链路 | 2 次 |
| §5 | AGENT_ROUTER_MODE=rule vs react 对比 | 无 |
| §6 | 删除候选追问：真实同名 JD 候选清单 + 指代/名称继承 + 防劫持回归 | 无 |
| §7 | search_resources 只读观察工具直调（jd/resume/interview/exam） | 无 |
| §8 | route_intent_node 整节点执行，验证 dest_node 三种分发（resource_delete/chat/skill_draft） | 1 次 |

> ⚠️ 共约 7 次真实路由 LLM 调用（每次 5–35s，消耗模型配额）。
> 若 §4 的 B/C 出现 `source=fallback`，属多层兜底设计正常生效，§4.1 会复盘原因。
