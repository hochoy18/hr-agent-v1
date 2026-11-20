# HR Agent - 智能人力资源管理系统

## 一、项目概述

HR Agent 是一个以**自然语言对话为核心交互方式**的智能 HR 管理系统。用户不需要在多个页面和菜单之间跳转，而是可以通过一个统一的 Agent 对话界面，用自然语言下达指令（如"帮我生成一个前端工程师的 JD"），系统自动理解意图、调度对应工具、执行任务并返回结果。

### 核心理念

- **对话即操作**：用户通过自然语言描述需求，AI Agent 自动路由到对应功能模块
- **工具编排**：Agent 作为"调度中心"，根据意图选择合适的工具（JD 生成、简历筛选、面试计划等）
- **确认即执行**：关键操作需要用户确认后才执行（如发送邮件），确认过程是图上的真暂停而非提示词约束

---

## 二、技术架构

```
┌──────────────────────────────────────────────────────┐
│                      前端 (Vue 3)                     │
│   Element Plus  │  Pinia  │  Vue Router  │  ECharts   │
├──────────────────────────────────────────────────────┤
│                REST API / SSE 事件流                   │
├──────────────────────────────────────────────────────┤
│               后端 (FastAPI + Python)                  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │          LangGraph 主图 (app/agent/)            │  │
│  │  START → route_intent → 条件边 → 意图子图 → END  │  │
│  │                                                │  │
│  │  route_intent   规则快通道 → 观察型 ReAct 路由   │  │
│  │  意图子图        jd / jd_edit / criteria_edit /  │  │
│  │                 resource_delete / skill / ...    │  │
│  │  chat 节点       create_agent ReAct 工具循环     │  │
│  │  人机确认        interrupt ⇄ Command(resume)     │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐  │
│  │ 业务链路  │ │ Skill    │ │ RAG 检索 │ │ LLM 工厂 │  │
│  │ chains/  │ │ System   │ │ +Rerank │ │ChatOpenAI│  │
│  └──────────┘ └──────────┘ └─────────┘ └──────────┘  │
├──────────────────────────────────────────────────────┤
│ PostgreSQL：业务表 + pgvector + LangGraph 状态表        │
└──────────────────────────────────────────────────────┘
```

### 技术栈

| 层级   | 技术                                      |
| ------ | ----------------------------------------- |
| 前端   | Vue 3, Vite, Element Plus, Pinia, ECharts |
| 后端   | Python 3.10+, FastAPI, SQLAlchemy (异步)   |
| Agent 编排 | LangGraph 1.0（主图 + 意图子图 + interrupt 确认 + PostgreSQL checkpoint） |
| 数据库 | PostgreSQL + pgvector (向量搜索)           |
| AI 模型 | 通义千问 (Qwen-Max), text-embedding-v1    |
| 工作流 | Dify 工作流引擎                           |
| 向量检索 | LangChain + pgvector + Rerank (gte-rerank-v2) |
| 评审口径 | JSON 规则文件（`app/rules/`），同时生成提示词与算分参数 |
| 测试   | pytest（`backend/tests/`，111 例）         |
| 部署   | Docker + Docker Compose                   |

---

## 三、项目结构

```
hr-agent-study/
├── backend/                        # 后端 (FastAPI)
│   ├── main.py                     # 应用入口，FastAPI 生命周期
│   ├── requirements.txt            # Python 依赖
│   ├── Dockerfile / docker-compose.yml
│   ├── alembic.ini                 # 数据库迁移
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── api.py              # 路由聚合（20 个模块）
│   │   │   └── endpoints/          # 各模块 API 端点
│   │   │       ├── agent.py        # HR Agent 对话/流式接口
│   │   │       ├── agent_graph.py  # LangGraph 版 Agent
│   │   │       ├── auth.py         # 认证（JWT）
│   │   │       ├── users.py        # 用户管理
│   │   │       ├── chat.py         # 对话管理
│   │   │       ├── conversations.py
│   │   │       ├── documents.py    # 文档上传/管理
│   │   │       ├── knowledge_base.py
│   │   │       ├── knowledge_assistant.py
│   │   │       ├── job_description.py
│   │   │       ├── resume_evaluation.py
│   │   │       ├── interview_plan.py
│   │   │       ├── scoring_criteria.py
│   │   │       ├── exam_management.py
│   │   │       ├── email_configs.py
│   │   │       ├── hr_workflows.py  # HR 工作流
│   │   │       ├── intent_router.py # 意图路由
│   │   │       ├── meeting.py      # 腾讯会议
│   │   │       ├── interview.py    # 面试记录 / 转写 / AI 评价
│   │   │       └── stats.py         # 统计
│   │   ├── core/                   # 核心配置
│   │   │   ├── config.py           # 全局配置 (Pydantic Settings)
│   │   │   ├── database.py         # PostgreSQL + pgvector 连接
│   │   │   ├── security.py         # JWT + OAuth2
│   │   │   └── middleware.py       # 自定义中间件
│   │   ├── models/                 # 数据库模型 (SQLAlchemy)
│   │   │   ├── user.py             # 用户 + 角色 (RBAC)
│   │   │   ├── conversation.py     # 对话 + 消息
│   │   │   ├── document.py         # 文档
│   │   │   ├── knowledge_base.py   # 知识库
│   │   │   ├── exam.py             # 试卷 + 试题
│   │   │   ├── exam_result.py      # 考试结果
│   │   │   ├── resume_evaluation.py # 简历评分
│   │   │   ├── email_config.py     # 邮箱配置
│   │   │   └── ...
│   │   ├── schemas/                # Pydantic 请求/响应模型
│   │   ├── agent/                  # ★ LangGraph Agent（图 + 节点 + 工具）
│   │   │   ├── graph.py            # 主图构建：路由 + 意图子图条件边
│   │   │   ├── state.py            # AgentState（27 字段，artifacts 跨轮累积）
│   │   │   ├── bridge.py           # 图调用门面：run_chat / resume / run_stream（SSE）
│   │   │   ├── reasoning.py        # 意图决策（规则快通道 + 观察型 ReAct 路由）
│   │   │   ├── routing_agent.py    # create_agent 路由器 + RouterDecision 结构化输出
│   │   │   ├── checkpoint.py       # AsyncPostgresSaver（thread_id = conversation_id）
│   │   │   ├── llm.py              # ChatOpenAI 工厂（对话模型 / 路由模型分开）
│   │   │   ├── nodes/              # 节点：routing/jd/editing/resources/skill/
│   │   │   │                       #       planning/files/chat_agent/legacy
│   │   │   ├── tools/              # chat_tools（4 个只读查询）、router_tools（资源检索）
│   │   │   └── chains/             # 业务链路 mixin：core / editing / resources
│   │   ├── services/               # 业务逻辑层
│   │   │   ├── agent_service.py    # ★ Agent 业务门面：工具注册表 + 共享辅助
│   │   │   ├── agent_skills.py     # ★ Skill 插件系统
│   │   │   ├── intent_service.py   # 意图分类
│   │   │   ├── llm_service.py      # LLM 调用封装
│   │   │   ├── rag_service.py      # RAG 检索增强
│   │   │   ├── embedding_service.py # 向量嵌入
│   │   │   ├── rerank_service.py   # 重排序
│   │   │   ├── dify_service.py     # Dify 工作流
│   │   │   ├── interview_service.py     # ★ 面试生命周期 + AI 评价流水线
│   │   │   ├── transcript_segmenter.py  # ★ 转写结构化（说话人轮次）
│   │   │   ├── qa_pairing.py            # ★ 问答配对（纯代码）
│   │   │   ├── interview_prompts.py     # ★ 判定/打分提示词
│   │   │   ├── transcription_service.py # 音视频转写
│   │   │   ├── meeting_service.py       # 腾讯会议 API
│   │   │   ├── email_service.py    # 邮件发送
│   │   │   ├── exam_service.py     # 考试管理
│   │   │   └── ...
│   │   ├── evaluations/            # 评测框架：agent / dify / rag 三套 runner + 规则评分器
│   │   ├── rules/                  # ★ 评审规则文件（提示词与算分的唯一来源）
│   │   │   ├── interview_rules_v1.json  # 档位定义 + 算分参数 + 权重
│   │   │   ├── render.py                # 规则 → 提示词片段
│   │   │   └── __init__.py              # load_rules() / rule_version()
│   │   └── utils/                  # 工具函数
│   ├── skills/                       # ★ Skill 插件目录
│   │   └── hr-agent-email/           # 邮件发送 Skill
│   │       ├── SKILL.md              # Skill 说明文档
│   │       ├── skill.json            # Skill 清单
│   │       ├── config.txt            # 邮箱配置
│   │       ├── scripts/              # Skill 执行脚本
│   │       └── references/           # 参考文档
│   ├── scripts/                    # 数据库管理、种子数据、算法自查工具
│   │   ├── seed_roles.py           # 初始化角色与默认用户
│   │   ├── inspect_transcript.py   # ★ 转写结构化 / 问答配对 / 判定自查
│   │   ├── score_drift.py          # ★ 同一份稿重复评分，测量分数漂移
│   │   └── ...
│   ├── tests/                      # pytest（services / api / fixtures）
│   ├── evals/                      # 评测集与报告：agent_cases / dify_cases / rag_cases / reports
│   └── uploads/                    # 文件上传目录
├── frontend/                       # 前端 (Vue 3 + Vite)
│   ├── src/
│   │   ├── api/                    # 接口请求封装 (Axios)
│   │   │   ├── agent.js            # ★ Agent：graph/chat、graph/resume、文件流端点
│   │   │   └── interview.js        # ★ 面试：会议 / 材料上传 / 评价 / 人工修订
│   │   ├── views/
│   │   │   ├── agent/HRAgent.vue   # ★ HR Agent 对话界面
│   │   │   ├── dashboard/          # 工作台
│   │   │   ├── recruitment/        # 智能招聘
│   │   │   │   ├── JDGenerator.vue       # JD 生成
│   │   │   │   ├── ResumeScreening.vue   # 简历筛选
│   │   │   │   └── SmartInterview.vue    # 智能面试
│   │   │   ├── training/           # 智能培训
│   │   │   │   ├── ExamGenerator.vue     # 试卷生成
│   │   │   │   ├── ExamManagement.vue    # 考试管理
│   │   │   │   └── AutoGrading.vue       # 自动阅卷
│   │   │   ├── assistant/          # 知识助理
│   │   │   │   ├── KnowledgeAssistant.vue # 知识问答
│   │   │   │   └── KnowledgeBase.vue     # 知识库管理
│   │   │   └── system/             # 系统管理
│   │   │       ├── UsersManagement.vue
│   │   │       ├── RolesManagement.vue
│   │   │       └── EmailManagement.vue
│   │   ├── router/index.js         # 路由配置
│   │   ├── stores/                 # Pinia 状态管理
│   │   └── layouts/                # 页面布局
│   └── package.json
```

---

## 四、核心模块

### 4.1 HR Agent（Agent 对话助手）

**入口文件**: `backend/app/agent/`（图与节点）、`backend/app/api/v1/endpoints/agent_graph.py`（接口）、`frontend/src/views/agent/HRAgent.vue`

HR Agent 是整个系统的"大脑"，用 **LangGraph** 编排：一张主图做路由与分发，每个意图是独立编译的子图，确认类交互用 `interrupt` 暂停、`Command(resume=...)` 从断点继续。

```
START → route_intent ─┬─ chat             → create_agent ReAct 工具循环
                      ├─ jd_prepare       → jd_confirm（interrupt）→ jd_execute
                      ├─ jd_edit          → parse → locate → rewrite → save
                      ├─ criteria_edit    → parse → locate → rewrite → save
                      ├─ resource_delete  → parse → resolve → execute
                      ├─ skill_draft      → skill_send（响应式确认）
                      ├─ interview_plan   → 单步准备（exam_generate / resume_screening 同构）
                      └─ resume_exec      → 文件流直通（interview_exec / exam_exec 同构）
```

**关键设计**:

- **两级路由**：`route_intent` 先走规则快通道（关键词 + 附件上下文，毫秒级、不花模型调用），判不出来再走观察型 ReAct 路由——`create_agent` 带只读工具 `search_resources`，可以先查"刚才那个/上次那个"指向的真实资源，再输出结构化决策 `RouterDecision`。`AGENT_ROUTER_MODE=rule` 可关掉模型路由，只留规则。
- **路由只选路，不写数据**：删除、发送、落库全部由确定性子图执行，路由阶段不持有写工具，避免模型误触发工具链。
- **人机确认是真暂停**：JD 生成、Skill 发送在确认节点 `interrupt`，图状态落 checkpoint；前端把确认表单 POST 到 `/agent/graph/resume`，后端以 `Command(resume=value)` 继续。无 checkpointer 的兼容路径退化为"返回 `requires_confirmation` 响应 + 前端回传 `confirmed_requirements`"，与旧链路语义一致。
- **解析与确认拆成两个节点**：`interrupt` 恢复时整个节点会从头重跑，所以 LLM 解析放在 `jd_prepare` 先完成、`jd_confirm` 只负责暂停，避免 resume 后重复解析导致结果漂移。
- **状态与检查点**：`AgentState` 27 个字段，`thread_id = conversation_id`；`artifacts` 用自定义 reducer 跨轮累积（保留最近 50 条），作为"刚才那个"的产物反查来源。db session、user_id 这类不可序列化对象走 `configurable` 传递，不进 checkpoint。
- **流式事件契约**：`astream(stream_mode=["updates","custom"], subgraphs=True)` 转成 SSE，五类事件——节点进度 / 文本增量 / 产物 / `interrupt` / `final`；子图内的自定义事件会冒泡到父图，前端事件格式与旧链路兼容。
- **对话记忆**：每轮把历史对话摘要注入 `memory_context`，支持"继续""刚才那个"等指代；chat 节点自身的子图不持久化状态，连续性靠每轮注入。

**接口**:

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/agent/graph/chat` | 自然语言对话，SSE 流式 |
| POST | `/api/v1/agent/graph/resume` | 恢复被 interrupt 的会话，SSE 流式 |
| POST | `/api/v1/agent/stream` | JD 生成直通（`preset_intent=jd`，跳过路由） |
| POST | `/api/v1/agent/resume-screen/stream` | 简历筛选直通（`preset_intent=resume_exec`） |
| POST | `/api/v1/agent/interview-plan/stream` | 面试方案直通（`preset_intent=interview_exec`） |
| POST | `/api/v1/agent/exam/stream`、`/exam/document-stream` | 试卷生成直通（`preset_intent=exam_exec`） |

文件流端点走同一张图，只是带 `preset_intent` 跳过意图决策直达执行节点——避免前端上传大文件时再跑一次路由。

**可调度的工具**:

| 工具 | 意图 | 对应动作 |
|------|------|----------|
| JD 生成 | `jd` | `generate_jd` |
| JD 修改 | `jd_edit` | `edit_jd` |
| 评分标准修改 | `criteria_edit` | `edit_scoring_criteria` |
| 简历批量筛选 | `resume_screening` | `evaluate_resume` |
| 面试方案生成 | `interview_plan` | `generate_interview_plan` |
| 试卷生成 | `exam_generate` | `generate_exam` |
| 资源删除 | `resource_delete` | `delete_resource` |
| 邮件生成/发送 | `email_notification` | 通过 Skill 插件系统调度 |

除上表业务工具，`chat` 节点还挂了 4 个只读查询工具（查 JD / 简历评分 / 面试方案 / 试卷列表），让模型能回答"我有哪些 JD"这类问题而不必跳页；路由器另有 `search_resources` 用于指代消解。两类工具都只读，写操作一律不在模型手里。

### 4.2 智能招聘

**路由前缀**: `/recruitment/`

#### JD 生成 (`JDGenerator.vue`)
- 基于自然语言描述生成完整职位描述
- 同时自动生成配套的简历评分标准
- 流式输出生成内容
- 支持 JD 历史管理与导出

#### 简历筛选 (`ResumeScreening.vue`)
- 批量上传 PDF/DOC/DOCX 简历
- 基于 JD 自动评分和匹配度分析
- 支持手动调整评分、查看评分理由
- 依赖 Dify 工作流进行简历解析

#### 智能面试 (`SmartInterview.vue`)

**会前**

- 从已评分的简历创建面试记录，一键创建腾讯会议（主题、时间、密码、等候室、云录制）
- 同步会议状态与真实起止时间
- 根据候选人简历和 JD 自动生成面试方案（题目、考察维度、评分标准）
- 可选关联已有面试方案，方案内容快照进面试记录（后续改方案不影响历史面试）

**会后**

- 两种材料来源：上传录音/视频/文档（文档可直接是逐字稿）、拉取腾讯会议录制转写
- 上传前确认**候选人姓名**（用于判断转写里谁在回答），分析后仍可修改；改名会作废旧评价并允许重新分析
- AI 应答质量评价：4 个维度 0-4 分 + 加权总分 + 推荐结论，逐条引用转写原话作为证据（链路见第五节）
- **人工修订**：逐维改分、可一并改推荐结论、修订原因必填，保留 AI 原分与修订历史

### 4.3 智能培训

**路由前缀**: `/training/`

#### 试卷生成 (`ExamGenerator.vue`)
- 上传参考文档（PDF/Word/TXT）自动生成试卷
- 支持配置题型、难度、分值、题量
- 流式生成，实时预览

#### 考试管理 (`ExamManagement.vue`)
- 试卷列表管理、搜索过滤
- 生成考试分享链接（无需登录）
- 查看考试结果与答题统计

#### 自动阅卷 (`AutoGrading.vue`)
- 客观题自动评分
- 考试成绩汇总与分析

### 4.4 知识助理

**路由前缀**: `/assistant/`

- **知识问答**：基于上传的知识库文档进行 RAG 问答
- **知识库管理**：创建/管理知识库、上传文档、自动向量化
- **混合检索**：向量相似度 + 文本匹配的融合排序
- **Rerank 重排**：使用 gte-rerank-v2 模型提升检索精度
- **查询增强**：自动改写用户查询以提升召回率

### 4.5 系统管理

**路由前缀**: `/system/`

- **用户管理**：用户 CRUD，支持搜索和分页
- **角色管理**：RBAC 权限控制（admin/hr_manager/hr_specialist/employee）
- **邮箱管理**：配置 IMAP/SMTP 邮箱，自动抓取简历邮件，定时调度

---

## 五、面试 AI 评价链路

**入口**：`POST /api/v1/interviews/{id}/analyze`

### 5.1 流水线

```
转写文本
   │
   ├─① transcript_segmenter   纯代码：解析说话人标签、同一人连续发言合并成"轮"、渲染成可回源的结构化文本
   │                          候选人身份 = 人工填写的姓名匹配说话人标签，对不上时抽样让模型在既有标签里指认
   ├─② qa_pairing             纯代码：面试官连续轮攒成提问块，遇候选人轮成组；候选人先开口记入"开场自述"，
   │                          结尾有提问无人回应仍成组（未作答信号）
   ├─③ LLM 逐组判定           只打标签：verdict / substance / followup / note，不配对、不打分
   │                          代码配不出组时（候选人标签缺失、单人转写）才退回全文自行配对
   └─④ LLM 单次打分 + 代码算分  打分入参含判定结果与统计；两维由代码按规则推导并覆盖模型分，总分按权重折算
```

每次完整评价 = **2 次模型调用**（1 次逐组判定 + 1 次打分），不做多次采样。两个例外各多 1 次：姓名与说话人标签对不上时需指认候选人身份；代码配不出问答组时需全文自行配对。

### 5.2 评价维度与权重

| 维度 | 计分方式 | 权重 |
|------|----------|------|
| 问答一致性 | 由 verdict 分布算正面率 → 落档 | 35% |
| 事实信息量 | 由 substance 分布算均值 → 落档 | 35% |
| 逻辑条理性 | 模型按 rubric 判档 | 15% |
| 表达组织能力 | 模型按 rubric 判档 | 15% |

- 总分 = `Σ(权重 × 分数/满分) / Σ权重 × 100`。只计可评分维度，缺失维度的权重按比例归一到其余维度，少一维不压低总分。
- **追问深度**（followup）不计入候选人分数，统计为「面试执行度」，衡量面试官是否压到细节。
- 可评分维度 <3、转写 <800 字、问答全失败、判定缺标签 ≥20% 任一命中 → 结论强制「待定」并在 notes 说明原因。

### 5.3 规则文件是唯一来源

`backend/app/rules/interview_rules_v1.json` 同时充当**提示词生成源**和**算分参数来源**：

- 三字段（verdict / substance / followup）共 12 档，每档带 `criteria`（判据）、`requires`（何时命中）、`excludes`（什么情况不算）、`examples{hit,miss,ambiguous}`（含反例）、`precedence`（判序）、`engine`（rule / llm / hybrid）
- `derivation` 定义两维的推导方式：正面率权重、阈值分档、事实层级分值、半舍入、样本下限、未作答组不计入均值
- `dimension_weights` 定义总分权重；`render.py` 把规则渲染成判定提示词的「字段定义」段和打分提示词的「算分口径」段
- 代码在导入时把 `derivation` / `dimension_weights` 编译成常量，评价结果的 `rule_version` 记录本次按哪版规则计算

**改口径只改这一个文件，并升 `rule_version`**——不允许只改提示词或只改代码。`test_interview_rules.py` 与 `test_rule_render.py` 把 JSON 取值、代码常量、提示词渲染三者锁在一起。常量在模块导入时编译（`load_rules()` 还带 `lru_cache`），改完需重启服务。

**未纳入规则文件**：逻辑条理性、表达组织能力（合计 30% 权重）。这两维目前只有文字 rubric，实测填充词密度、平均句长、结构词密度等文本指标与内容质量无正相关（结构词密度为 −0.36），写进文件只是把主观判断换个格式存放。文件里的 `unscored` 记录了该判断与纳入条件（先影子模式跑 20~30 份真实稿，与人工基准相关性达 0.6 以上再纳入）。

### 5.4 人工修订

`PATCH /api/v1/interviews/{id}/evaluation`，三条设计约束：

1. **只改分数，不改判定标签**——verdict / substance 始终是模型的，修订语义是"不同意这个档"，不是重判问答组；
2. **AI 原分只在首次修订时定格**，之后再改仍以模型那版为基准，避免基准自身漂移；
3. **素材不足（insufficient）的维度一旦人工给分即转为可评分**并计入总分。

留痕写在 `evaluation.manual_override`：修订次数、AI 原总分、`history[]`（时间 / 操作人 / 原因 / 每维改前改后 / 结论变更 / 修订前后总分），保留最近 20 条。

### 5.5 自查与实测工具

```bash
# 只跑结构化与配对、不调模型：四项校验（内容守恒 / 段号连续 / 相邻轮说话人不同 / 原文行号可定位）
python scripts/inspect_transcript.py <转写文件> --candidate 姓名

# 连模型实收的提示词一起看（改提示词前先确认规则真的渲染进去了）
python scripts/inspect_transcript.py <转写文件> --candidate 姓名 --prompt

# 从库里取某场面试的转写（支持 UUID 前缀），不必导出文件
python scripts/inspect_transcript.py --interview-id <id>

# 同一份稿重复评分，输出极差 / 标准差 / 逐组标签翻转
python scripts/score_drift.py <转写文件> --candidate 姓名 --runs 10 --concurrency 3
```

`score_drift.py` 用来回答"同一份稿重复评分会不会给出不同结果"。当前已知的漂移来源与未决项记在规则文件的 `known_gaps` 与 `docs/interview-upgrade.md`。

---

## 六、Agent Skill 插件系统

**核心文件**: `backend/app/services/agent_skills.py`

Skill 系统允许通过声明式配置扩展 Agent 的能力，无需修改核心代码。

### 工作原理

```
用户消息 "给候选人发邮件"
       ↓
route_intent 判定意图: email_notification（命中 skill bundle）
       ↓
条件边分发到 skill_draft 节点（LangGraph）
       ↓
Skill Dispatcher 找到 hr-agent-email bundle，执行 draft phase
       ↓
用户确认（skill_draft 落 interrupt，或退回 requires_confirmation 响应）
       ↓
Command(resume) / confirmed_requirements → skill_send 节点执行 send phase
```

Skill 意图在图上占两个节点（`skill_draft` → `skill_send`），中间的确认由 `interrupt` 承担；没有 checkpointer 的兼容路径（评测、旧门面调用）退化为返回 `requires_confirmation` 响应，前端回传后由条件边放行到 `skill_send`。

### Skill 结构

每个 Skill 是一个独立目录，包含：

```
backend/skills/<skill-name>/
├── SKILL.md         # Skill 描述 (YAML frontmatter)
├── skill.json       # 清单文件（声明 intent, phases, 执行脚本）
├── config.txt       # Skill 独立配置
└── scripts/         # 各阶段执行脚本
```

### skill.json 清单示例

```json
{
  "name": "hr-agent-email",
  "intent": "email_notification",
  "route": "/system/email-configs",
  "phases": ["draft", "send"],
  "default_phase": "draft",
  "confirmation_action": "send_email",
  "phase_scripts": {
    "draft": "scripts/email_draft.py:generate_email_draft",
    "send": "scripts/email_send.py:send_confirmed_email"
  }
}
```

### 已实现的 Skill

| Skill            | 意图                  | 阶段            |
| ---------------- | --------------------- | --------------- |
| hr-agent-email   | `email_notification`  | draft → send    |

---

## 七、AI 技术特性

### RAG 检索增强生成
- **文档向量化**：上传文档自动分块 → 通义千问 text-embedding-v1 向量化 → pgvector 存储
- **混合检索**：向量相似度 (70%) + 文本匹配 (30%)
- **Rerank 重排序**：gte-rerank-v2 模型对候选结果二次排序
- **查询增强**：自动扩展查询关键词，提升召回

### 图编排（LangGraph）

- **主图只做分发**：`route_intent` 决定去向，条件边把执行交给独立编译的意图子图，每个子图都从 `START` 进、到 `END` 出
- **完成即终止**：编辑/删除类子图按"节点写入 `final_response` 就结束本轮"的规则走条件边——中途需要追问或报错时不会继续跑后面的写操作
- **确认即暂停**：`interrupt` 把图暂停在 checkpoint 上，恢复走 `Command(resume=value)`，会话可跨请求继续
- **状态复用**：`thread_id` 用 `conversation_id`，同一会话跨轮共享状态；`artifacts` 跨轮累积，供"刚才那个"反查
- **一条链路两种入口**：对话入口（`/graph/chat`、`/graph/resume`）与文件流入口（`/agent/*/stream`）走同一张图，后者用 `preset_intent` 跳过路由

### 路由与决策

- **规则快通道**：关键词、附件格式、上一轮产物（判断"这是不是在改刚才那个"）三类特征先判一轮，毫秒级、不消耗模型调用
- **观察型 ReAct 路由**：规则判不出来时，模型可以先调只读工具 `search_resources` 观察当前资源，再输出结构化决策（`mode` / `action` / `intent` / `thought` / `confidence`），失败回退规则
- **写操作不进模型**：删除、发送、落库由确定性子图执行，模型只能"选路"
- **chat 节点是真 ReAct 循环**：`create_agent` 挂 4 个只读查询工具，可多轮 Thought → Action → Observation 后作答
- 路由模型与对话模型分开配置（`AGENT_ROUTER_MODEL` / `LLM_MODEL`），路由侧 `temperature=0`、带超时与 token 上限，避免选路拖慢主链路

### 对话记忆
- 基于 PostgreSQL 存储完整对话历史
- 每轮把历史摘要注入 `memory_context`，支持代词指代消解
- 图侧另有 checkpoint 状态（含累积产物），与业务表的历史记录互为补充

### 可复算的评分（面试评价）
- 能数出来的维度就交给代码算，不交给模型"整体感觉"：判定只打标签，算分按规则文件的阈值表落档
- 口径与提示词同源，模型看到的统计数字与代码算出的分数一致，reason 不会与分数打架
- 规则版本随评价结果落库，历史记录能回溯是按哪版规则算出来的

---

## 八、数据模型 (ER 概要)

```
User (用户)
├── id, username, email, role, is_superuser
├── conversations → Conversation[]
│   └── messages → Message[]
├── documents → Document[]
└── roles → Role[] (多对多)

KnowledgeBase (知识库)
├── id, name, description, category
└── documents → Document[]

Document (文档)
├── id, filename, content, embedding (pgvector)
├── knowledge_base_id → KnowledgeBase
└── uploaded_by → User

Exam (试卷)
├── id, title, subject, difficulty, duration
└── questions → Question[]

EmailConfig (邮箱配置)
├── id, email, imap/smtp 配置
└── logs → EmailFetchLog[]

ResumeEvaluation (简历评分)
├── id, candidate_name, score
├── job_description_id → JobDescription
└── model_score_detail (JSON)

Interview (面试记录)
├── id, subject, candidate_name, candidate_position
├── 会议：meeting_id / meeting_code / join_url / password / meeting_status
├── 材料：media_type / media_path / media_size
├── 转写：transcript / transcript_source / transcript_meta (JSON)
├── 评价：evaluation (JSON，含 dimensions / qa_pairs / execution / manual_override /
│        rule_version)、total_score、analysis_status
├── resume_evaluation_id → ResumeEvaluation
├── interview_plan_id → 面试方案
└── user_id → User
```

`interviews.evaluation` 是整份报告的存放处：`total_score`、`dimensions[]`、`qa_pairs[]`、`risk_signals[]`、`execution`、`summary`、`strengths`、`risks`、`recommendation`、`confidence`、`insufficient`、`notes`、`prompt_version`、`rule_version`、`manual_override`。`total_score` 另存一列，便于列表排序与统计。

**LangGraph 状态表**不在上面的 ER 图里：`AsyncPostgresSaver` 在应用启动时由 `init_checkpointer()` 自动 `setup()` 建表（`checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`），按 `thread_id = conversation_id` 存图的运行状态。会话历史仍在业务表 `messages`，两者互不替代——一个是"说过什么"，一个是"图跑到哪一步、攒了哪些产物"。

---

## 九、快速启动

### 环境要求
- Python 3.10+
- Node.js >= 16
- PostgreSQL 13+ (需启用 pgvector 扩展)
- Docker (可选)

### 1. 启动数据库

```bash
cd backend
docker compose up -d    # 启动 PostgreSQL + pgvector
```

### 2. 启动后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # 编辑 .env 填入 API Key
python scripts/seed_roles.py   # 初始化角色和默认用户
python main.py          # 启动 http://localhost:8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev             # 启动 http://localhost:3000
```

### 4. 运行测试

```bash
cd backend
./venv/bin/python -m pytest tests/ -q      # 111 例
```

Agent 链路的行为回归走评测集（不是单测，会真实调用模型）：

```bash
# 跑固定评估集，输出 JSON + Markdown 报告到 evals/reports/
python scripts/run_agent_evals.py --repeat-runs 3

# 与历史报告对比，指标回退或出现失败样例时以非零码退出（适合接 CI）
python scripts/run_agent_evals.py --baseline evals/reports/<历史报告>.json \
    --fail-on-regression --fail-on-failed-cases
```

另有 `run_rag_evals.py`、`run_dify_evals.py` 分别覆盖知识库检索与 Dify 工作流，参数风格一致。

前端改动后建议跑一次构建与 lint，避免模板/样式语法问题只在运行时暴露：

```bash
cd frontend
npx vite build --logLevel warn
npx eslint src/views/recruitment/SmartInterview.vue src/api/interview.js
```

### 5. 访问

- 前端界面：`http://localhost:3000`
- API 文档：`http://localhost:8000/api/v1/docs`
- 默认账号：`testuser` / `test123`

---

## 十、关键配置项 (`.env`)

| 配置项                     | 说明                          | 默认值           |
| -------------------------- | ----------------------------- | ---------------- |
| `LLM_API_KEY`              | 通义千问 API Key              | -                |
| `LLM_MODEL`                | 大语言模型                    | `qwen-max`       |
| `EMBEDDING_MODEL`          | 嵌入模型                      | `text-embedding-v1` |
| `QWEN_API_KEY`             | Rerank 模型 API Key           | -                |
| `RERANK_ENABLED`           | 是否启用 Rerank               | `true`           |
| `DIFY_BASE_URL` / `DIFY_API_KEY` | Dify 工作流配置         | -                |
| `RAG_MIN_SIMILARITY_SCORE` | RAG 最低相似度阈值            | `0.4`            |
| `CONTEXT_LIMIT`            | 知识库检索文档数量            | `10`             |
| `DATABASE_URL`             | 数据库连接串（业务表、向量与 LangGraph checkpoint 共用） | - |
| `DATABASE_POOL_SIZE`       | 连接池大小（psycopg 池与 asyncpg 池各自独立，合计别超 PG `max_connections`） | `10` |
| `AGENT_ROUTER_MODE`        | 路由模式：`react` 走模型路由，`rule` 只走规则（省调用） | `react` |
| `AGENT_ROUTER_MODEL`       | 路由专用模型；留空复用 `LLM_MODEL` | -            |
| `AGENT_ROUTER_TIMEOUT_SECONDS` | 路由调用超时（秒）        | `20`             |
| `AGENT_ROUTER_RECURSION_LIMIT` | 路由 agent 递归上限      | `8`              |
| `AGENT_ROUTER_MAX_TOKENS`  | 路由调用输出上限              | `800`            |
| `AGENT_ROUTER_MAX_ATTEMPTS` | 结构化决策未产出时的重试次数  | `2`              |
| `TENCENT_MEETING_TOKEN`    | 腾讯会议 MCP Token            | -                |
| `INTERVIEW_MEDIA_MAX_MB`   | 面试材料大小上限 (MB)         | `500`            |
| `INTERVIEW_ANALYSIS_MAX_CHARS` | 打分入参转写字数上限（超长截中段保留首尾） | `60000` |
| `INTERVIEW_ANALYSIS_MAX_TOKENS` | 打分调用输出上限         | `8000`           |
| `INTERVIEW_QA_WARN_CHARS`  | 判定入参告警阈值（超过只告警，不分块） | `24000` |
| `INTERVIEW_QA_MAX_TOKENS`  | 判定调用输出上限              | `16000`          |
| `INTERVIEW_LLM_SEED`       | 评价调用的采样种子            | `42`             |

