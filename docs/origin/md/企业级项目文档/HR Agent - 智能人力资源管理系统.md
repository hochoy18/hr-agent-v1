# HR Agent - 智能人力资源管理系统

## 一、项目概述

HR Agent 是一个以**自然语言对话为核心交互方式**的智能 HR 管理系统。用户不需要在多个页面和菜单之间跳转，而是可以通过一个统一的 Agent 对话界面，用自然语言下达指令（如"帮我生成一个前端工程师的 JD"），系统自动理解意图、调度对应工具、执行任务并返回结果。

### 核心理念

- **对话即操作**：用户通过自然语言描述需求，LangGraph 编排的 Agent 自动路由到对应意图子图
- **工具编排**：Agent 作为"调度中心"，根据意图选择合适的工具（JD 生成/修改、简历筛选、面试计划、试卷生成、资源删除、邮件草稿）
- **确认即执行**：关键操作需要用户确认后才执行（如发送邮件、删除资源），确认是图上的真暂停而非提示词约束
- **过程可留痕**：面试从建会到评价全程留痕，评分必须能指回逐字稿原文

---

## 二、技术架构

```
┌─────────────────────────────────────────────────────┐
│                     前端 (Vue 3)                      │
│   Element Plus  │  Pinia  │  Vue Router  │  ECharts  │
├─────────────────────────────────────────────────────┤
│                  REST API / SSE 流式                  │
├─────────────────────────────────────────────────────┤
│                 后端 (FastAPI + Python)               │
│                                                       │
│  ┌──────────────┐  ┌──────────┐  ┌────────────────┐ │
│  │ LangGraph     │  │ Intent   │  │ RAG 检索增强    │ │
│  │ 主图+意图子图  │  │ Service  │  │ 向量+阈值+Rerank│ │
│  └──────────────┘  └──────────┘  └────────────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ Skill    │  │ Dify     │  │ LLM Service         │ │
│  │ System   │  │ 工作流    │  │ (Qwen)              │ │
│  └──────────┘  └──────────┘  └────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ 面试评价引擎  │  │ 腾讯会议 MCP  │  │ 语音转写ASR │ │
│  │ 规则JSON+模型 │  │ 建会/取消/录制│  │ ffmpeg+ASR │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
├─────────────────────────────────────────────────────┤
│          PostgreSQL + pgvector (向量存储)            │
└─────────────────────────────────────────────────────┘
```

### 技术栈

| 层级   | 技术                                      |
| ------ | ----------------------------------------- |
| 前端   | Vue 3, Vite 7（Node 20.19+/22.12+）, Element Plus, Pinia, ECharts |
| 后端   | Python 3.11（推荐）, FastAPI, SQLAlchemy (异步) |
| Agent  | LangGraph（主图 + 意图子图 + checkpoint） |
| 数据库 | PostgreSQL + pgvector (向量搜索)           |
| AI 模型 | 通义千问 (Qwen-Max), text-embedding 系列  |
| 工作流 | Dify 工作流引擎（JD/评分标准/简历评估/面试方案/试卷意图） |
| 向量检索 | LangChain + pgvector + Rerank (gte-rerank-v2) |
| 视频会议 | 腾讯会议 MCP（`mcp.meeting.tencent.com`） |
| 语音转写 | DashScope ASR + 系统 ffmpeg |
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
│   │   │   ├── api.py              # 路由聚合（20 个模块 + /health，共 119 个接口）
│   │   │   └── endpoints/          # 各模块 API 端点
│   │   │       ├── agent.py        # Agent 文件流接口（流式评分/方案/试卷）
│   │   │       ├── agent_graph.py  # ★ LangGraph 对话入口（chat / resume）
│   │   │       ├── interview.py    # ★ 智能面试（建会/转写/分析/评价）
│   │   │       ├── meeting.py      # ★ 腾讯会议（建会/查询/取消）
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
│   │   │       └── stats.py         # 统计
│   │   ├── agent/                  # ★ LangGraph 编排
│   │   │   ├── graph.py            # 主图：START → route_intent → 意图子图 → END
│   │   │   ├── state.py            # AgentState（artifacts 跨轮累积）
│   │   │   ├── bridge.py           # SSE 事件桥接
│   │   │   ├── checkpoint.py       # checkpoint 存取
│   │   │   ├── routing_agent.py    # 受控 ReAct 路由器
│   │   │   ├── nodes/              # 意图节点（jd/editing/resources/skill/planning/files）
│   │   │   ├── chains/             # 业务编排（core/editing/resources）
│   │   │   └── tools/              # 只读工具（search_resources 等）
│   │   ├── rules/                  # ★ 面试评分规则（interview_rules_v1.json + render.py）
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
│   │   │   ├── interview.py        # ★ 面试记录（会议+转写+评价）
│   │   │   ├── exam.py             # 试卷 + 试题
│   │   │   ├── exam_result.py      # 考试结果
│   │   │   ├── resume_evaluation.py # 简历评分
│   │   │   ├── email_config.py     # 邮箱配置
│   │   │   └── ...
│   │   ├── schemas/                # Pydantic 请求/响应模型
│   │   ├── services/               # 业务逻辑层
│   │   │   ├── agent_service.py    # ★ Agent 门面与业务分支
│   │   │   ├── agent_skills.py     # ★ Skill 插件系统
│   │   │   ├── interview_service.py        # ★ 面试评价主链路
│   │   │   ├── meeting_service.py          # ★ 腾讯会议客户端
│   │   │   ├── transcription_service.py    # ★ 音视频转写
│   │   │   ├── transcript_segmenter.py     # ★ 逐字稿分段/说话人
│   │   │   ├── qa_pairing.py               # ★ 问答配对
│   │   │   ├── intent_service.py   # 意图分类
│   │   │   ├── llm_service.py      # LLM 调用封装
│   │   │   ├── rag_service.py      # RAG 检索增强
│   │   │   ├── embedding_service.py # 向量嵌入
│   │   │   ├── rerank_service.py   # 重排序
│   │   │   ├── dify_service.py     # Dify 工作流
│   │   │   ├── email_service.py    # 邮件发送
│   │   │   ├── exam_service.py     # 考试管理
│   │   │   └── ...
│   │   └── utils/                  # 工具函数
│   ├── skills/                       # ★ Skill 插件目录
│   │   └── hr-agent-email/           # 邮件发送 Skill
│   │       ├── SKILL.md              # Skill 说明文档
│   │       ├── skill.json            # Skill 清单
│   │       ├── config.txt            # 邮箱配置
│   │       ├── scripts/              # Skill 执行脚本
│   │       └── references/           # 参考文档
│   ├── tests/services/             # ★ 面试链路单测（112 例）
│   │   └── fixtures/transcripts/   # 逐字稿样本
│   ├── scripts/                    # 数据库管理、种子数据
│   └── uploads/                    # 文件上传目录（含面试音视频）
├── frontend/                       # 前端 (Vue 3 + Vite)
│   ├── src/
│   │   ├── api/                    # 接口请求封装 (Axios)
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

**入口文件**: `backend/app/services/agent_service.py`, `frontend/src/views/agent/HRAgent.vue`

HR Agent 是整个系统的"大脑"，采用 **ReAct（推理-行动）** 模式进行决策：

```
用户输入 → 意图分类 → ReAct 决策 → 工具调度 → 结果返回
                ↓
    ┌─────────────────────────────┐
    │  chat    → 普通对话回复      │
    │  use_tool → 调用业务工具     │
    │  ask_user → 追问缺失信息     │
    └─────────────────────────────┘
```

**关键设计**:
- **LangGraph 图编排**：主图只做路由分发，每个意图是独立编译子图，流程边界由节点和条件边保证
- **三层意图识别**：规则快通道（关键词） → 附件上下文推理 → 受控 ReAct 决策（结构化输出）
- **确认即暂停**：`jd_confirm`、`skill_send` 用 `interrupt()` 真暂停，前端渲染确认卡片，确认后调 `/agent/graph/resume` 恢复
- **跨轮产物**：`artifacts` 自定义 reducer 累积（上限 50 条），编辑/删除靠它反查"刚才那个"
- **流式响应**：SSE 推送 `progress` / `delta` / `artifact` / `interrupt` / `final` / `error`
- **路由不写库**：路由节点只选路，删除、发送、落库由后续确定性链路执行

**可调度的工具**:

| 工具              | 意图              | 触发条件                            |
| ----------------- | ----------------- | ----------------------------------- |
| JD 生成           | `jd`              | 提供岗位名称、地点等基本信息        |
| JD 修改           | `jd_edit`         | 定位到要改的 JD + 明确修改要求      |
| 评分标准修改      | `criteria_edit`   | 定位到评分标准 + 明确修改要求       |
| 简历批量筛选      | `resume_screening` | 上传简历文件 + 选择匹配 JD         |
| 面试计划生成      | `interview_plan`   | 已有评分简历                        |
| 试卷生成          | `exam_generate`    | 选择知识库文档 + 配置考试参数       |
| 资源删除          | `resource_delete`  | 指定要删除的资源类型和名称/候选人   |
| 邮件生成/发送     | `email_notification`| 通过 Skill 插件系统调度（只出草稿）|

### 4.2 智能招聘

**路由前缀**: `/recruitment/`

#### JD 生成 (`JDGenerator.vue`)
- 基于自然语言描述生成完整职位描述
- 同时自动生成配套的简历评分标准
- 流式输出生成内容
- 支持 JD 历史管理与导出

#### 简历筛选 (`ResumeScreening.vue`)
- 批量上传 PDF/DOC/DOCX/TXT/MD 简历（单文件 ≤ 10MB）
- 基于 JD 自动评分和匹配度分析
- 支持状态更新、压缩包导出、查看评分理由
- 调用 Dify 工作流（type=3）完成简历评分

#### 智能面试 (`SmartInterview.vue`)

三个 Tab：简历预览 / 面试方案 / 面试记录。

- **面试方案**：根据候选人简历和 JD 生成方案（Dify type=4），支持编辑保存
- **发起会议**：调用腾讯会议 MCP 建会，回写会议号、入会链接、密码；可同步状态、取消会议
- **材料来源**：本地上传音视频、上传文档（逐字稿/纪要）、直接拉取腾讯会议录制转写
- **需先确认姓名**：分析前必须确认候选人姓名，避免说话人错位
- **转写与配对**：ffmpeg 抽音频 → ASR 转写 → 分段与说话人识别 → 一问一答配对
- **四维评分**：问答一致性 35%、事实信息量 35%、逻辑条理性 15%、表达组织能力 15%
- **规则引擎**：判定档位与权重写在 `app/rules/interview_rules_v1.json`，规则命中的结论覆盖模型
- **证据可追溯**：每个维度引用逐字稿原文；证据不足时结论强制「待定」并说明原因
- **人工修订**：可改维度分或总分，保留原值、AI 分数与修订记录

### 4.3 智能培训/考试

**路由前缀**: `/training/`

#### 试卷生成 (`ExamGenerator.vue`)
- 从**已有知识库中选择文档**作为出题依据（不是直接上传文件）
- 支持配置题型、难度、分值、题量
- 流式生成，实时预览；题量不足时自动补题

#### 考试管理 (`ExamManagement.vue`)
- 试卷列表管理、搜索过滤
- 生成考试分享链接（无需登录）
- 查看考试结果与答题统计，支持导出

#### 自动阅卷 (`AutoGrading.vue`)
- 页面文件保留，**当前未挂菜单**；阅卷能力由试卷提交接口与考试结果页承载

### 4.4 知识助理

**路由前缀**: `/assistant/`

- **知识问答**：基于上传的知识库文档进行 RAG 问答，可不选知识库（全库检索）
- **知识库管理**：创建/管理知识库、上传文档、自动向量化、切片预览
- **混合检索**：向量相似度 + 文本匹配的融合排序（`RAG_TEXT_WEIGHT` / `RAG_CONTENT_WEIGHT`）
- **相似度门槛**：低于 `RAG_MIN_SIMILARITY_SCORE` 的召回不进入上下文，避免答非所问
- **Rerank 重排**：使用 gte-rerank-v2 模型提升检索精度
- **查询增强**：自动改写用户查询以提升召回率

### 4.5 系统管理

**路由前缀**: `/system/`

- **用户管理**：用户 CRUD，支持搜索和分页
- **角色管理**：RBAC 权限控制（admin/hr_manager/hr_specialist/employee）
- **邮箱管理**：配置 IMAP/SMTP 邮箱，自动抓取简历邮件，定时调度

---

## 五、Agent Skill 插件系统

**核心文件**: `backend/app/services/agent_skills.py`

Skill 系统允许通过声明式配置扩展 Agent 的能力，无需修改核心代码。

### 工作原理

```
用户消息 "给候选人发邮件"
       ↓
Agent 识别意图: email_notification
       ↓
Skill Dispatcher 找到 hr-agent-email bundle
       ↓
执行 draft phase → 用户确认 → 执行 send phase
```

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

## 六、AI 技术特性

### RAG 检索增强生成
- **文档向量化**：上传文档自动分块 → text-embedding 模型向量化 → pgvector 存储（分批调用）
- **混合检索**：向量相似度 + 文本匹配加权融合（权重可配）
- **相似度门槛**：低于 `RAG_MIN_SIMILARITY_SCORE` 的召回直接丢弃
- **Rerank 重排序**：gte-rerank-v2 模型对候选结果二次排序
- **查询增强**：自动扩展查询关键词，提升召回

### LangGraph + 受控 ReAct 决策
- 主图 `route_intent` 节点：构建记忆 → 规则快通道 → 受控 ReAct，输出结构化决策
- LLM 在受限动作空间（chat / use_tool / ask_user）中选择下一步，路由不执行写操作
- 规则兜底（LLM 失败时使用关键词 + 附件规则）
- 每次决策输出一句 thought 供前端展示，不暴露完整推理
- 确认型意图由 `interrupt` 真暂停，checkpoint 保存跨轮产物

### 意图分类
- 关键词快速匹配（毫秒级）
- 附件上下文推理
- LLM 兜底分类（备选）
- 支持 8 类业务意图 + 普通对话 + Skill 意图

### 对话记忆
- 基于 PostgreSQL 存储完整对话历史
- 图状态 `artifacts` 跨轮累积，支持「刚才那个」指代与编辑/删除反查
- 回退路径：会话消息 `context.agent_response`

### 面试评价引擎
- 规则文件 `interview_rules_v1.json` 定义档位、推导与权重，提示词同源渲染
- 规则命中的判定覆盖模型结论，模型自报总分不采信
- 证据不足时强制「待定」，并给出具体原因与复核提示

---

## 七、数据模型 (ER 概要)

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
├── id, candidate_name, total_score
├── job_description_id（远程 JD 的 ID）
├── scoring_criteria_id（远程评分标准 ID）
└── evaluation_metrics (JSON)

Interview (面试记录)
├── id, user_id, resume_evaluation_id
├── meeting_id / meeting_code / join_url / meeting_status
├── analysis_status, media_type / media_path
├── transcript, transcript_meta
├── evaluation (JSON：四维+问答+执行度+结论+rule_version)
└── total_score

说明：JD、评分标准、面试方案由远程 HR 服务持久化，本库不建这三张表；
面试记录中的 `plan_content_snapshot` 保存方案快照，保证评价依据不漂移。
```

---

## 八、快速启动

> 版本要求（以当前代码为准）：Python 3.11 推荐；Node.js **20.19+ 或 22.12+**（Vite 7 强制要求）；需安装 **ffmpeg**（面试音视频转写）；后端启动入口是 `main:app`（`backend/main.py`），不是 `app.main:app`；初始化角色用 `python scripts/seed_roles.py`；数据库表由后端启动时自动创建（含 pgvector 扩展与 LangGraph checkpoint 表）。完整步骤见《环境配置与部署使用》文档。

### 环境要求
- Python 3.11 推荐（3.10 亦可运行，CI 与部署以 3.11 为准）
- Node.js **20.19+ 或 22.12+**（Vite 7 强制要求，低于该版本 `npm run dev` 直接报错）
- PostgreSQL 13+（需启用 pgvector 扩展）
- **ffmpeg**（面试音视频抽音轨，转写链路必需）
- Docker（可选）

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

### 4. 访问

- 前端界面：`http://localhost:3000`
- API 文档：`http://localhost:8000/api/v1/docs`
- 默认账号：`testuser` / `test123`

---

## 九、关键配置项 (`.env`)

> 当前版本的完整配置清单以 `backend/.env.example` 为准，新增的关键项包括：`AGENT_ROUTER_MODE` / `AGENT_ROUTER_MODEL` / `AGENT_ROUTER_TIMEOUT_SECONDS` / `AGENT_ROUTER_RECURSION_LIMIT` / `AGENT_ROUTER_MAX_TOKENS` / `AGENT_ROUTER_MAX_ATTEMPTS`（Agent 路由）、`KB_QUERY_ENHANCE_ENABLED` / `KB_QUERY_EXPANSION_MAX_TERMS`（查询增强）、`RAG_MIN_SIMILARITY_SCORE`（相似度门槛）、`HR_SERVICE_HOST` / `HR_SERVICE_PORT` / `HR_SERVICE_APIKEY`（远程 JD/评分标准/方案服务）、`TENCENT_MEETING_TOKEN` / `TENCENT_MEETING_MCP_URL` / `TENCENT_MEETING_SKILL_VERSION`（腾讯会议）、`INTERVIEW_MEDIA_MAX_MB` / `INTERVIEW_ANALYSIS_MAX_CHARS` / `INTERVIEW_ANALYSIS_MAX_TOKENS` / `INTERVIEW_ANALYSIS_MAX_QA_PAIRS` / `INTERVIEW_QA_MAX_TOKENS` / `INTERVIEW_LLM_SEED`（面试分析）、`DASHSCOPE_ASR_MODEL`（语音识别）、`DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW`（连接池）。`ALGORITHM`、`ALLOWED_FILE_TYPES`、`RERANK_USE_QWEN` 写进 `.env` 不会生效。

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

