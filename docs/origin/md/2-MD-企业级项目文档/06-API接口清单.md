# API 接口协议

## 1. 文档目的

本文档定义 HR Agent 后端 API 的联调协议，包括通用请求约定、认证方式、分页规则、错误结构、核心接口参数、请求示例、响应示例、文件上传格式和 SSE 流式响应格式。

本文档面向前端开发、后端开发、测试、联调和上线验收人员。接口基础路径为：

```text
/api/v1
```

## 2. 通用约定

### 2.1 请求协议

| 项 | 约定 |
| --- | --- |
| 协议 | HTTP/HTTPS |
| 数据格式 | JSON，文件上传使用 `multipart/form-data` |
| 字符编码 | UTF-8 |
| 时间格式 | ISO 8601 字符串 |
| ID 格式 | UUID，少量考试分享场景可使用字符串 ID |
| 鉴权方式 | Bearer Token |

### 2.2 通用 Header

普通 JSON 请求：

```http
Content-Type: application/json
Authorization: Bearer <access_token>
```

文件上传请求：

```http
Content-Type: multipart/form-data
Authorization: Bearer <access_token>
```

流式请求：

```http
Accept: text/event-stream
Content-Type: application/json
Authorization: Bearer <access_token>
```

### 2.3 分页约定

列表接口统一建议支持以下查询参数，具体以接口实现为准：

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| page | int | 否 | 1 | 页码，从 1 开始 |
| size | int | 否 | 10 | 每页数量 |
| keyword | string | 否 | 空 | 搜索关键词 |
| status | string | 否 | 空 | 状态过滤 |

分页响应建议结构：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "size": 10,
  "pages": 0
}
```

### 2.4 通用错误结构

后端错误响应统一为：

```json
{
  "error": {
    "message": "验证失败",
    "type": "ValidationError",
    "details": {
      "errors": [
        {
          "field": "body -> title",
          "message": "Field required",
          "type": "missing"
        }
      ]
    }
  }
}
```

常见状态码：

| 状态码 | 含义 | 场景 |
| --- | --- | --- |
| 400 | 请求错误 | 外键无效、业务参数冲突 |
| 401 | 未认证 | Token 缺失、无效或过期 |
| 403 | 权限不足 | 普通用户访问管理接口 |
| 404 | 资源不存在 | 查询不存在的 JD、文档、试卷 |
| 409 | 资源冲突 | 用户名、邮箱、角色名重复 |
| 422 | 参数校验失败 | 必填字段缺失、字段格式错误 |
| 500 | 服务端错误 | 数据库、外部服务或程序异常 |

## 3. 认证接口

### 3.1 用户注册

```http
POST /api/v1/auth/register
```

权限：无需登录。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| username | string | 是 | 用户名，3-50 字符，唯一 |
| email | string | 是 | 邮箱，唯一 |
| password | string | 是 | 密码，至少 6 位 |
| full_name | string | 否 | 姓名 |
| phone | string | 否 | 手机号 |
| department | string | 否 | 部门 |
| position | string | 否 | 职位 |
| employee_id | string | 否 | 员工编号 |
| bio | string | 否 | 简介 |

请求示例：

```json
{
  "username": "hr_zhang",
  "email": "hr_zhang@example.com",
  "password": "test123",
  "full_name": "张三",
  "department": "人力资源部",
  "position": "HR 专员"
}
```

响应示例：

```json
{
  "id": "6fbbf4ff-6c2a-4db2-8c8a-7a7d6b0f2a01",
  "username": "hr_zhang",
  "email": "hr_zhang@example.com",
  "full_name": "张三",
  "phone": null,
  "department": "人力资源部",
  "position": "HR 专员",
  "employee_id": null,
  "role": "employee",
  "is_active": true,
  "is_superuser": false,
  "is_verified": false,
  "avatar_url": null,
  "last_login": null,
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00"
}
```

### 3.2 用户登录

```http
POST /api/v1/auth/login
```

权限：无需登录。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| email | string | 是 | 登录邮箱 |
| password | string | 是 | 密码 |

请求示例：

```json
{
  "email": "hr_zhang@example.com",
  "password": "test123"
}
```

响应示例：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 691200
}
```

### 3.3 获取当前用户

```http
GET /api/v1/auth/me
```

权限：已登录。

响应示例：

```json
{
  "id": "6fbbf4ff-6c2a-4db2-8c8a-7a7d6b0f2a01",
  "username": "hr_zhang",
  "email": "hr_zhang@example.com",
  "full_name": "张三",
  "role": "hr_specialist",
  "is_active": true,
  "is_superuser": false,
  "is_verified": true
}
```

## 4. 用户与角色接口

### 4.1 用户列表

```http
GET /api/v1/users/?page=1&size=10&keyword=hr
```

权限：超级管理员。

响应示例：

```json
[
  {
    "id": "6fbbf4ff-6c2a-4db2-8c8a-7a7d6b0f2a01",
    "username": "hr_zhang",
    "email": "hr_zhang@example.com",
    "full_name": "张三",
    "department": "人力资源部",
    "position": "HR 专员",
    "role": "hr_specialist",
    "is_superuser": false,
    "is_verified": true,
    "is_active": true,
    "roles": [
      {
        "id": "4c930674-c5f5-4ff0-a915-6c7f4f004f5b",
        "name": "HR 专员",
        "description": "招聘业务操作角色",
        "is_builtin": true,
        "created_at": "2026-06-09T10:00:00",
        "updated_at": "2026-06-09T10:00:00"
      }
    ]
  }
]
```

### 4.2 管理员创建用户

```http
POST /api/v1/users/admin/users
```

权限：超级管理员。

请求示例：

```json
{
  "username": "training_admin",
  "email": "training_admin@example.com",
  "password": "test123",
  "full_name": "李四",
  "department": "培训部",
  "position": "培训管理员",
  "role": "employee"
}
```

### 4.3 分配用户角色

```http
PUT /api/v1/users/admin/users/{user_id}/roles
```

权限：超级管理员。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| role_ids | UUID[] | 是 | 角色 ID 列表 |

请求示例：

```json
{
  "role_ids": [
    "4c930674-c5f5-4ff0-a915-6c7f4f004f5b"
  ]
}
```

### 4.4 角色管理接口

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| GET | `/users/admin/roles` | 查询角色列表 | 超级管理员 |
| POST | `/users/admin/roles` | 创建角色 | 超级管理员 |
| DELETE | `/users/admin/roles/{role_id}` | 删除角色 | 超级管理员 |
| GET | `/users/me/roles` | 查询当前用户角色 | 已登录 |

创建角色请求：

```json
{
  "name": "HR 负责人",
  "description": "查看招聘数据和候选人评估结果",
  "is_builtin": false
}
```

## 5. HR Agent 接口

> 说明：Agent 的对话入口已迁移到 LangGraph 图（`/agent/graph/*`）。早期文档中的 `/agent/chat`、`/agent/chat/stream` 已不存在，请以本章为准。

### 5.1 对话（LangGraph）

```http
POST /api/v1/agent/graph/chat
Content-Type: application/json
Authorization: Bearer <token>
```

权限：已登录。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| message | string | 是 | 用户自然语言需求 |
| thread_id | string | 否 | 会话线程 ID，建议传 `conversation_id`；缺省由后端生成并在事件中返回 |
| auto_execute | boolean | 否 | 是否自动执行低风险生成类工具，默认 true |
| confirmed_requirements | object | 否 | 用户确认后的结构化需求（也可走 5.2 恢复接口） |
| attachments | object[] | 否 | 附件元信息：`name`、`extension`、`content_base64` 等 |

请求示例：

```json
{
  "message": "帮我生成一个上海前端工程师 JD，要求 3 年经验，熟悉 Vue 3 和 Element Plus",
  "thread_id": "3f2a...",
  "auto_execute": true,
  "attachments": []
}
```

响应：`text/event-stream`，每帧形如 `data: {json}\n\n`，流以 `data: [DONE]` 结束。

| 事件 `type` | 关键字段 | 说明 |
| --- | --- | --- |
| `progress` | `node`、`steps` | 图节点进度与步骤列表 |
| `delta` | `delta`、`section` | 文本增量，`section` 标识所属区块（jd / scoring_criteria / …） |
| `artifact` | `artifact` 或 `response` | 产物就绪 |
| `interrupt` | `thread_id`、`payload` | 等待用户确认，前端渲染确认卡片 |
| `final` | `thread_id`、`response` | 本轮终态，`response` 为完整 `AgentChatResponse`，每轮唯一 |
| `error` | `error` | 异常信息 |

`AgentChatResponse` 字段：`message`、`intent`、`route`、`steps`、`artifacts`、`suggestions`、`requires_confirmation`、`missing_fields`。

### 5.2 确认后恢复（interrupt resume）

```http
POST /api/v1/agent/graph/resume
Content-Type: application/json
```

用途：前端收到 `interrupt` 事件、用户填写确认卡片后调用，继续被暂停的 thread。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| thread_id | string | 是 | `interrupt` 事件返回的线程 ID |
| value | object | 是 | 确认载荷（沿用 `confirmed_requirements` 结构，可含 `action: "send_email"` 等） |

响应：与 5.1 相同的 SSE 事件流。若服务端未启用 checkpointer，会降级为一次带 `confirmed_requirements` 的普通执行并直接返回 `final`。

### 5.3 Agent 文件流接口

以下端点带预设意图，图内跳过路由决策直达执行节点，SSE 事件格式与 5.1 一致。

| 方法 | 路径 | 用途 | 传参方式 | 权限 |
| --- | --- | --- | --- | --- |
| POST | `/agent/stream` | 确认后执行 JD 生成链（前端 thread 丢失时的降级通道，必须带 `confirmed_requirements`） | JSON | 已登录 |
| POST | `/agent/resume-screen/stream` | 批量上传简历并流式评分 | multipart：`job_description_id`（必填）、`conversation_id`、`files[]` | 已登录 |
| POST | `/agent/interview-plan/stream` | 基于已评分简历流式生成面试方案 | multipart：`resume_evaluation_id` 等 | 已登录 |
| POST | `/agent/exam/stream` | 流式生成试卷 | JSON | 已登录 |
| POST | `/agent/exam/document-stream` | 直接上传参考附件（≤5 个）直通 `exam_exec` 生成试卷，供 Agent 对话页使用；试卷页走知识库选文档路径（`/hr-workflows/papers/generate`） | multipart：`exam_requirements`（JSON 字符串）、`conversation_id`、`files[]` | 已登录 |

## 6. HR 工作流接口

### 6.1 解析招聘需求

```http
POST /api/v1/hr-workflows/parse-requirements
```

权限：已登录。

请求示例：

```json
{
  "requirements": "招聘一个上海前端工程师，3 年经验，本科，熟悉 Vue 3，薪资 20-30K"
}
```

响应示例：

```json
{
  "position_title": "前端工程师",
  "location": "上海",
  "experience_level": "3 年",
  "education": "本科",
  "salary_range": "20-30K",
  "skills": ["Vue 3"],
  "missing_fields": []
}
```

### 6.2 生成 JD

```http
POST /api/v1/hr-workflows/generate-jd
```

权限：已登录。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| requirements | string | 是 | 岗位需求描述 |
| position_title | string | 否 | 岗位名称 |
| department | string | 否 | 部门 |
| experience_level | string | 否 | 经验要求 |
| conversation_id | string | 否 | 对话 ID |
| stream | boolean | 否 | 是否流式输出 |

请求示例：

```json
{
  "requirements": "负责企业后台前端开发，熟悉 Vue 3、Element Plus、接口联调",
  "position_title": "前端工程师",
  "department": "技术部",
  "experience_level": "3 年",
  "stream": true
}
```

响应示例：

```json
{
  "title": "前端工程师",
  "content": "岗位职责：\n1. 负责企业后台前端开发...\n任职要求：\n1. 熟悉 Vue 3...",
  "requirements": "负责企业后台前端开发，熟悉 Vue 3、Element Plus、接口联调",
  "meta_data": {
    "source": "dify",
    "workflow_type": "jd_generation"
  }
}
```

### 6.3 生成评分标准

```http
POST /api/v1/hr-workflows/generate-scoring-criteria
```

权限：已登录。

请求示例：

```json
{
  "jd_content": "岗位职责：负责 Vue 3 企业后台开发...",
  "job_title": "前端工程师",
  "requirements": {
    "skills": ["Vue 3", "Element Plus", "Axios"],
    "experience": "3 年"
  },
  "stream": true
}
```

响应示例：

```json
{
  "title": "前端工程师简历评分标准",
  "total_score": "100",
  "content": "评分维度包括技术能力、项目经验、岗位匹配度...",
  "scoring_dimensions": [
    {
      "name": "前端技术能力",
      "max_score": 40,
      "description": "Vue 3、组件化、工程化、接口联调能力"
    },
    {
      "name": "项目经验",
      "max_score": 30,
      "description": "企业后台、复杂表单、权限系统等项目经验"
    }
  ]
}
```

### 6.4 HR 工作流接口汇总

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| POST | `/hr-workflows/parse-requirements` | 解析招聘需求 | 已登录 |
| POST | `/hr-workflows/generate-jd` | 生成 JD | 已登录 |
| POST | `/hr-workflows/generate-scoring-criteria` | 生成评分标准 | 已登录 |
| POST | `/hr-workflows/evaluate` | 简历评估 | 已登录 |
| POST | `/hr-workflows/generate-interview-plan-by-resume` | 基于简历生成面试方案 | 已登录 |
| POST | `/hr-workflows/papers/parse-intent` | 解析试卷需求 | 已登录 |
| POST | `/hr-workflows/papers/generate` | 生成试卷 | 已登录 |
| POST | `/hr-workflows/papers/submit` | 提交考试答案 | 可按业务免登录 |

## 7. JD 接口

### 7.1 保存 JD

```http
POST /api/v1/job-descriptions/save
```

权限：已登录。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| title | string | 是 | 岗位标题 |
| content | string | 是 | JD 正文 |
| department | string | 否 | 部门 |
| location | string | 否 | 工作地点 |
| salary_range | string | 否 | 薪资范围 |
| experience_level | string | 否 | 经验要求 |
| education | string | 否 | 学历要求 |
| job_type | string | 否 | 岗位类型 |
| skills | string[] | 否 | 技能列表 |
| requirements | string | 否 | 原始需求 |
| status | string | 否 | 状态，默认 draft |
| meta_data | object | 否 | 元数据 |
| conversation_id | string | 否 | 对话 ID |

请求示例：

```json
{
  "title": "前端工程师",
  "department": "技术部",
  "location": "上海",
  "salary_range": "20-30K",
  "experience_level": "3 年",
  "education": "本科",
  "job_type": "全职",
  "skills": ["Vue 3", "Element Plus", "Axios"],
  "content": "岗位职责：负责企业后台前端开发...",
  "requirements": "需要熟悉 Vue 3 和后台系统开发",
  "status": "draft"
}
```

响应示例：

```json
{
  "id": "9d8a3f90-2cd9-4e56-83d7-c8c3f98d2b71",
  "title": "前端工程师",
  "department": "技术部",
  "location": "上海",
  "salary_range": "20-30K",
  "experience_level": "3 年",
  "education": "本科",
  "job_type": "全职",
  "skills": ["Vue 3", "Element Plus", "Axios"],
  "content": "岗位职责：负责企业后台前端开发...",
  "requirements": "需要熟悉 Vue 3 和后台系统开发",
  "status": "draft",
  "meta_data": null,
  "conversation_id": null,
  "workflow_type": "jd_generation",
  "user_id": "6fbbf4ff-6c2a-4db2-8c8a-7a7d6b0f2a01",
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00",
  "is_active": true
}
```

### 7.2 JD 列表

```http
GET /api/v1/job-descriptions/?page=1&size=10&keyword=前端
```

权限：已登录。

响应示例：

```json
{
  "items": [
    {
      "id": "9d8a3f90-2cd9-4e56-83d7-c8c3f98d2b71",
      "title": "前端工程师",
      "location": "上海",
      "status": "draft",
      "content": "岗位职责：...",
      "user_id": "6fbbf4ff-6c2a-4db2-8c8a-7a7d6b0f2a01",
      "created_at": "2026-06-09T10:00:00",
      "updated_at": "2026-06-09T10:00:00",
      "is_active": true
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

### 7.3 JD 详情、更新与删除

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/job-descriptions/{jd_id}` | 获取 JD 详情 |
| PUT | `/job-descriptions/{jd_id}` | 更新 JD，字段均可选 |
| DELETE | `/job-descriptions/{jd_id}` | 删除 JD |

更新请求示例：

```json
{
  "salary_range": "25-35K",
  "status": "active"
}
```

## 8. 评分标准接口

### 8.1 保存评分标准

```http
POST /api/v1/scoring-criteria/save
```

权限：已登录。

请求示例：

```json
{
  "title": "前端工程师简历评分标准",
  "job_title": "前端工程师",
  "content": "总分 100 分，按技术能力、项目经验、沟通协作等维度评分。",
  "total_score": "100",
  "scoring_dimensions": [
    {
      "name": "前端技术能力",
      "max_score": 40,
      "description": "Vue 3、组件化、工程化能力"
    },
    {
      "name": "项目经验",
      "max_score": 30,
      "description": "企业后台、权限、复杂表单经验"
    }
  ],
  "job_description_id": "9d8a3f90-2cd9-4e56-83d7-c8c3f98d2b71",
  "status": "draft"
}
```

响应示例：

```json
{
  "id": "cebc6e60-e28c-41fa-9f08-40dc2f88f744",
  "title": "前端工程师简历评分标准",
  "job_title": "前端工程师",
  "content": "总分 100 分...",
  "criteria_data": null,
  "total_score": "100",
  "scoring_dimensions": [
    {
      "name": "前端技术能力",
      "max_score": 40,
      "description": "Vue 3、组件化、工程化能力"
    }
  ],
  "status": "draft",
  "job_description_id": "9d8a3f90-2cd9-4e56-83d7-c8c3f98d2b71",
  "workflow_type": "scoring_criteria_generation",
  "user_id": "6fbbf4ff-6c2a-4db2-8c8a-7a7d6b0f2a01",
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00",
  "is_active": true
}
```

### 8.2 评分标准管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/scoring-criteria/` | 分页查询评分标准 |
| GET | `/scoring-criteria/{criteria_id}` | 获取评分标准详情 |
| PUT | `/scoring-criteria/{criteria_id}` | 更新评分标准 |
| DELETE | `/scoring-criteria/{criteria_id}` | 删除评分标准 |

## 9. 简历评估接口

### 9.1 自动评估简历

```http
POST /api/v1/resume-evaluation/evaluate-auto
```

权限：已登录。

请求类型：`multipart/form-data`。

表单字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 简历文件，支持 PDF/DOC/DOCX |
| job_description_id | UUID | 是 | 关联 JD |
| scoring_criteria_id | UUID | 否 | 关联评分标准 |
| conversation_id | string | 否 | 对话 ID |

请求示例：

```bash
curl -X POST "http://localhost:8000/api/v1/resume-evaluation/evaluate-auto" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/resume.pdf" \
  -F "job_description_id=9d8a3f90-2cd9-4e56-83d7-c8c3f98d2b71" \
  -F "scoring_criteria_id=cebc6e60-e28c-41fa-9f08-40dc2f88f744"
```

响应示例：

```json
{
  "id": "8f8fa2c8-442c-4f6e-a2a4-e67a7ef3a110",
  "evaluation_metrics": [
    {
      "name": "前端技术能力",
      "score": 34,
      "max": 40,
      "reason": "候选人具备 Vue 3 和企业后台项目经验。"
    }
  ],
  "total_score": 86,
  "name": "王五",
  "position": "前端工程师",
  "workYears": 4,
  "education": "本科",
  "age": 28,
  "sex": "男",
  "school": "某某大学",
  "resume_content": "王五，4 年前端开发经验...",
  "original_filename": "王五-前端工程师.pdf",
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00"
}
```

### 9.2 简历评估历史

```http
GET /api/v1/resume-evaluation/history?page=1&size=10
```

权限：已登录。

响应结构：

```json
{
  "items": [
    {
      "id": "8f8fa2c8-442c-4f6e-a2a4-e67a7ef3a110",
      "original_filename": "王五-前端工程师.pdf",
      "candidate_name": "王五",
      "candidate_position": "前端工程师",
      "total_score": 86,
      "job_description_id": "9d8a3f90-2cd9-4e56-83d7-c8c3f98d2b71",
      "created_at": "2026-06-09T10:00:00",
      "updated_at": "2026-06-09T10:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

### 9.3 简历评估管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/resume-evaluation/supported-formats` | 查询支持格式 |
| GET | `/resume-evaluation/{evaluation_id}` | 获取评估详情 |
| PUT | `/resume-evaluation/{evaluation_id}/status` | 更新候选人状态 |
| DELETE | `/resume-evaluation/{evaluation_id}` | 删除评估 |
| POST | `/resume-evaluation/export-zip` | 批量导出 |

批量导出请求示例：

```json
{
  "resume_ids": [
    "8f8fa2c8-442c-4f6e-a2a4-e67a7ef3a110"
  ]
}
```

## 10. 面试方案接口

### 10.1 保存生成的面试方案

```http
POST /api/v1/interview-plans/save-generated
```

权限：已登录。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| content | string | 是 | 面试方案内容 |
| candidate_name | string | 否 | 候选人姓名 |
| candidate_position | string | 否 | 应聘岗位 |

请求示例：

```json
{
  "candidate_name": "王五",
  "candidate_position": "前端工程师",
  "content": "一、面试目标...\n二、核心问题...\n三、评分建议..."
}
```

响应示例：

```json
{
  "id": "60d41d78-1f33-4bda-b09d-344f983cad7b",
  "candidate_name": "王五",
  "candidate_position": "前端工程师",
  "content": "一、面试目标...",
  "resume_evaluation_id": "8f8fa2c8-442c-4f6e-a2a4-e67a7ef3a110",
  "user_id": "6fbbf4ff-6c2a-4db2-8c8a-7a7d6b0f2a01",
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00"
}
```

### 10.2 面试方案管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/interview-plans/` | 分页查询面试方案 |
| GET | `/interview-plans/{plan_id}` | 获取方案详情 |
| PUT | `/interview-plans/{plan_id}` | 更新方案 |
| DELETE | `/interview-plans/{plan_id}` | 删除方案 |

## 11. 文档与知识库接口

### 11.1 上传文档

```http
POST /api/v1/documents/upload
```

权限：已登录。

请求类型：`multipart/form-data`。

表单字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 文档文件 |
| knowledge_base_id | UUID | 否 | 归属知识库 |
| category | string | 否 | 分类 |
| tags | string[] | 否 | 标签 |

请求示例：

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/hr-policy.pdf" \
  -F "category=HR制度"
```

响应示例：

```json
{
  "id": "34af92e7-2c97-464c-9b54-7e7b9cf34a15",
  "filename": "hr-policy.pdf",
  "category": "HR制度",
  "tags": null,
  "knowledge_base_id": null,
  "file_path": "uploads/hr-policy.pdf",
  "file_size": 204800,
  "file_hash": "ab12cd34",
  "mime_type": "application/pdf",
  "extracted_content": null,
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00"
}
```

### 11.2 处理文档

```http
POST /api/v1/documents/{document_id}/process
```

权限：已登录。

响应示例：

```json
{
  "id": "34af92e7-2c97-464c-9b54-7e7b9cf34a15",
  "filename": "hr-policy.pdf",
  "extracted_content": "第一章 总则...",
  "updated_at": "2026-06-09T10:05:00"
}
```

### 11.3 文档管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/documents/` | 查询文档列表 |
| GET | `/documents/{document_id}` | 查询文档详情 |
| GET | `/documents/{document_id}/chunks` | 查询文档切片 |
| DELETE | `/documents/{document_id}` | 删除文档 |

### 11.4 创建知识库

```http
POST /api/v1/knowledge-base/
```

权限：已登录。

请求示例：

```json
{
  "name": "HR 制度知识库",
  "description": "用于员工制度问答",
  "is_public": false,
  "is_searchable": true,
  "category": "HR",
  "tags": ["制度", "员工手册"]
}
```

响应示例：

```json
{
  "id": "d32af56c-5539-4970-9875-1edb2f34eada",
  "name": "HR 制度知识库",
  "description": "用于员工制度问答",
  "is_public": false,
  "is_searchable": true,
  "category": "HR",
  "tags": ["制度", "员工手册"],
  "document_count": 0,
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00"
}
```

### 11.5 知识助手问答

```http
POST /api/v1/knowledge-assistant/ask
```

权限：已登录。

请求示例：

```json
{
  "question": "员工年假规则是什么？",
  "knowledge_base_id": "d32af56c-5539-4970-9875-1edb2f34eada",
  "conversation_id": null
}
```

响应示例：

```json
{
  "answer": "根据已上传制度文档，员工年假规则为...",
  "sources": [
    {
      "document_id": "34af92e7-2c97-464c-9b54-7e7b9cf34a15",
      "filename": "hr-policy.pdf",
      "content": "年假规则相关片段...",
      "score": 0.86
    }
  ],
  "confidence": 0.86
}
```

### 11.6 知识库管理接口

| 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- |
| GET | `/knowledge-base/` | 知识库列表 | 已登录 |
| PUT | `/knowledge-base/{kb_id}` | 更新知识库 | 超级管理员 |
| DELETE | `/knowledge-base/{kb_id}` | 删除知识库 | 超级管理员 |
| GET | `/knowledge-assistant/config` | 获取知识助手配置 | 已登录 |
| GET | `/knowledge-assistant/documents` | 知识助手文档列表 | 已登录 |
| POST | `/knowledge-assistant/auto-select-kb` | 自动选择知识库 | 已登录 |

## 12. 试卷与考试接口

### 12.1 创建/保存试卷

```http
POST /api/v1/exam-management/papers
```

权限：已登录。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| title | string | 是 | 试卷标题 |
| subject | string | 是 | 科目 |
| description | string | 否 | 描述 |
| difficulty | string | 否 | 难度 |
| duration | int | 否 | 时长，分钟 |
| total_score | int | 是 | 总分 |
| question_types | string[] | 否 | 题型 |
| question_counts | object | 否 | 各题型数量 |
| knowledge_files | object[] | 否 | 参考资料 |
| special_requirements | string | 否 | 特殊要求 |
| content | string | 否 | 试卷正文 |
| questions | object[] | 否 | 题目列表 |

请求示例：

```json
{
  "title": "HR 制度培训考试",
  "subject": "HR 制度",
  "difficulty": "中等",
  "duration": 60,
  "total_score": 100,
  "question_types": ["single_choice", "multiple_choice", "true_false"],
  "question_counts": {
    "single_choice": 5,
    "multiple_choice": 3,
    "true_false": 2
  },
  "content": "一、单选题..."
}
```

### 12.2 生成试卷

```http
POST /api/v1/hr-workflows/papers/generate
```

权限：已登录。

请求示例：

```json
{
  "title": "HR 制度培训考试",
  "subject": "HR 制度",
  "difficulty": "中等",
  "duration": 60,
  "total_score": 100,
  "question_types": ["single_choice", "multiple_choice", "true_false"],
  "question_counts": {
    "single_choice": 5,
    "multiple_choice": 3,
    "true_false": 2
  },
  "knowledge_files": [
    {
      "document_id": "34af92e7-2c97-464c-9b54-7e7b9cf34a15",
      "filename": "hr-policy.pdf"
    }
  ],
  "special_requirements": "题目应覆盖年假、考勤、请假流程",
  "stream": true
}
```

响应示例：

```json
{
  "title": "HR 制度培训考试",
  "content": "一、单选题\n1. 员工年假规则...",
  "questions": [
    {
      "id": "q1",
      "type": "single_choice",
      "question": "员工年假规则主要依据什么？",
      "options": ["A. 制度文档", "B. 个人习惯"],
      "answer": "A",
      "score": 10,
      "explanation": "依据 HR 制度文档。"
    }
  ]
}
```

### 12.3 考试提交

```http
POST /api/v1/hr-workflows/papers/submit
```

权限：试点默认允许分享页免登录提交，管理端查看结果需登录。

请求示例：

```json
{
  "exam_id": "exam-20260609-001",
  "student_name": "赵六",
  "department": "销售部",
  "answers": {
    "q1": "A",
    "q2": ["A", "C"]
  },
  "exam_content": "一、单选题..."
}
```

响应示例：

```json
{
  "result_id": "83d2d570-02e7-4fc1-9305-7f3613488139",
  "exam_id": "exam-20260609-001",
  "student_name": "赵六",
  "score": 85,
  "submitted_at": "2026-06-09T11:00:00"
}
```

### 12.4 考试管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/exam-management/papers` | 试卷列表 |
| GET | `/exam-management/papers/{paper_id}` | 试卷详情 |
| PUT | `/exam-management/papers/{paper_id}` | 更新试卷 |
| DELETE | `/exam-management/papers/{paper_id}` | 删除试卷 |
| GET | `/exam-management/papers/{paper_id}/share` | 获取分享链接 |
| GET | `/exam-management/exam-results` | 考试结果列表 |
| GET | `/exam-management/exam-results/{result_id}` | 考试结果详情 |
| GET | `/exam-management/exam-results/{result_id}/export` | 导出考试结果 |

## 13. 邮箱配置接口

### 13.1 创建邮箱配置

```http
POST /api/v1/email-configs/
```

权限：超级管理员。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 | 配置名称 |
| email | string | 是 | 邮箱地址 |
| password | string | 是 | 邮箱密码或授权码 |
| imap_server | string | 是 | IMAP 服务器 |
| imap_port | int | 否 | 默认 993 |
| imap_ssl | boolean | 否 | 默认 true |
| smtp_server | string | 否 | SMTP 服务器 |
| smtp_port | int | 否 | 默认 587 |
| smtp_ssl | boolean | 否 | 默认 true |
| fetch_interval | int | 否 | 抓取间隔，分钟 |
| auto_fetch | boolean | 否 | 是否自动抓取 |
| subject_keywords | string | 否 | 主题过滤关键词 |

请求示例：

```json
{
  "name": "招聘邮箱",
  "email": "recruit@example.com",
  "password": "mail-auth-code",
  "imap_server": "imap.example.com",
  "imap_port": 993,
  "imap_ssl": true,
  "smtp_server": "smtp.example.com",
  "smtp_port": 587,
  "smtp_ssl": true,
  "fetch_interval": 30,
  "auto_fetch": false,
  "subject_keywords": "简历,投递"
}
```

响应示例：

```json
{
  "id": "f3d85f6a-af94-4825-a9cc-bc1e7cb12401",
  "name": "招聘邮箱",
  "email": "recruit@example.com",
  "imap_server": "imap.example.com",
  "imap_port": 993,
  "imap_ssl": true,
  "smtp_server": "smtp.example.com",
  "smtp_port": 587,
  "smtp_ssl": true,
  "fetch_interval": 30,
  "auto_fetch": false,
  "status": "active",
  "subject_keywords": "简历,投递",
  "connection_status": "unknown",
  "last_fetch_at": null,
  "created_at": "2026-06-09T10:00:00",
  "updated_at": "2026-06-09T10:00:00"
}
```

### 13.2 邮箱连接测试

```http
POST /api/v1/email-configs/{config_id}/test
```

权限：超级管理员。

请求示例：

```json
{
  "imap_server": "imap.example.com",
  "imap_port": 993,
  "imap_ssl": true,
  "email": "recruit@example.com",
  "password": "mail-auth-code"
}
```

响应示例：

```json
{
  "success": true,
  "message": "邮箱连接测试成功"
}
```

### 13.3 邮箱配置管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/email-configs/` | 邮箱配置列表 |
| GET | `/email-configs/{config_id}` | 邮箱配置详情 |
| PUT | `/email-configs/{config_id}` | 更新邮箱配置 |
| DELETE | `/email-configs/{config_id}` | 删除邮箱配置 |
| POST | `/email-configs/{config_id}/fetch` | 手动抓取邮件 |
| GET | `/email-configs/{config_id}/logs` | 抓取日志 |
| GET | `/email-configs/{config_id}/latest-email` | 最近邮件 |

## 14. 统计接口

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| GET | `/stats/dashboard` | 工作台统计 | 已登录 |
| GET | `/stats/recruitment-trend` | 招聘趋势 | 已登录 |
| GET | `/stats/training-completion` | 培训完成情况 | 已登录 |
| GET | `/stats/recent-activities` | 近期活动 | 已登录 |

工作台统计响应示例：

```json
{
  "job_descriptions": 12,
  "resume_evaluations": 86,
  "interview_plans": 20,
  "exams": 4,
  "documents": 18
}
```

## 15. 腾讯会议接口

挂载前缀 `/meetings`，底层调用腾讯会议 MCP。Token 配置在 `TENCENT_MEETING_TOKEN`，未配置时相关接口返回 503。

### 15.1 检查会议能力是否可用

```http
GET /api/v1/meetings/status
```

响应：

```json
{ "configured": true }
```

### 15.2 创建会议

```http
POST /api/v1/meetings/
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| subject | string | 是 | 会议主题 |
| start_time | string | 是 | 开始时间，ISO 8601，如 `2026-11-10T10:00:00+08:00` |
| end_time | string | 是 | 结束时间，ISO 8601 |
| password | string | 否 | 会议密码，4~6 位数字 |
| auto_in_waiting_room | boolean | 否 | 是否开启等候室，默认 true |
| auto_record_type | string | 否 | 自动录制类型 |
| auto_asr | boolean | 否 | 是否自动转写（逐字稿） |
| only_user_join_type | int | 否 | 入会限制类型 |
| invitees | string[] | 否 | 受邀成员 open_id |
| time_zone | string | 否 | 时区，默认 `Asia/Shanghai` |

响应：

```json
{
  "meetings": [
    {
      "meeting_id": "1234567890",
      "meeting_code": "123 456 789",
      "join_url": "https://meeting.tencent.com/dm/xxxx",
      "subject": "张三 - 前端工程师 面试",
      "start_time": "2026-11-10T10:00:00+08:00",
      "end_time": "2026-11-10T11:00:00+08:00",
      "password": "1234",
      "raw": {}
    }
  ]
}
```

错误：`503` 未配置 Token；腾讯侧错误码（如 `190200` Token 失效）会以业务错误返回。

### 15.3 查询会议

```http
GET /api/v1/meetings/{meeting_id}
```

返回腾讯会议原始会议详情（含状态、录制与转写信息）。

### 15.4 取消会议

```http
POST /api/v1/meetings/{meeting_id}/cancel
```

响应：

```json
{ "meeting_id": "1234567890", "cancelled": true }
```

## 16. 智能面试接口

挂载前缀 `/interviews`。所有接口按 `user_id` 隔离，访问非本人记录返回 404。

### 16.1 开始面试（建会 + 建记录）

```http
POST /api/v1/interviews/start
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| resume_evaluation_id | UUID | 是 | 候选人简历评估 ID |
| interview_plan_id | string | 否 | 已保存的面试方案 ID |
| interview_plan_content | string | 否 | 未保存方案的正文（会写入快照） |
| subject | string | 否 | 会议主题，缺省「候选人 - 岗位 面试」 |
| start_time | string | 是 | 开始时间，ISO 8601 |
| end_time | string | 是 | 结束时间，ISO 8601，需晚于开始时间 |
| password | string | 否 | 4~6 位数字 |
| auto_in_waiting_room | boolean | 否 | 默认 true |
| auto_record | boolean | 否 | 是否自动云录制并转写，默认 true |
| time_zone | string | 否 | 默认 `Asia/Shanghai` |

响应：`InterviewResponse`（201），字段见 16.3。

### 16.2 面试列表与详情

```http
GET /api/v1/interviews/?page=1&size=20&resume_evaluation_id=<uuid>
GET /api/v1/interviews/{interview_id}
GET /api/v1/interviews/{interview_id}/record-settings
```

`record-settings` 返回该会议是否开启云录制/转写，用于会前提示。

### 16.3 面试记录结构（`InterviewResponse`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id / user_id / resume_evaluation_id | UUID | 记录标识与归属 |
| interview_plan_id | string | 远程方案 ID |
| candidate_name / candidate_position | string | 候选人快照 |
| subject / start_time / end_time / time_zone | string | 会议信息 |
| meeting_id / meeting_code / join_url / password | string | 腾讯会议信息 |
| auto_in_waiting_room | boolean | 等候室开关 |
| meeting_status | string | `scheduled` / `ongoing` / `cancelled` / `completed` |
| analysis_status | string | `not_started` / `transcribing` / `transcript_ready` / `analyzing` / `completed` / `failed` |
| media_type / media_filename / media_size | string / string / int | 上传材料信息 |
| transcript_source | string | `upload` / `tencent` / `document` |
| transcript | string | 逐字稿全文 |
| transcript_meta | object | 说话人、片段、候选人说话人推断依据 |
| plan_content_snapshot | string | 方案快照 |
| evaluation | object | 评价结果（结构见 04 文档 4.15） |
| total_score | float | 总分 |
| error_message | string | 最近一次失败原因 |

### 16.4 更新会议参数 / 取消

```http
PATCH /api/v1/interviews/{interview_id}
POST  /api/v1/interviews/{interview_id}/cancel
```

`PATCH` 支持修改 `subject`、`start_time`、`end_time`、`password`、`auto_in_waiting_room`、`auto_record`、`time_zone`；不传的字段不修改。

### 16.5 同步会议状态

```http
POST /api/v1/interviews/{interview_id}/sync
```

向腾讯会议拉取最新状态并回写 `meeting_status`。会议已结束的记录会自动跳过高频同步。

### 16.6 上传面试材料

```http
POST /api/v1/interviews/{interview_id}/media
Content-Type: multipart/form-data
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 音视频（audio/video）或文档（逐字稿/纪要） |
| media_type | string | 否 | 不传时按扩展名推断 |

限制：音视频单文件大小受 `INTERVIEW_MEDIA_MAX_MB`（默认 500MB）约束；超限返回 413。

响应：更新后的 `InterviewResponse`（`media_type`、`media_filename`、`analysis_status` 变化）。

### 16.7 修正候选人姓名

```http
PATCH /api/v1/interviews/{interview_id}/candidate
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| candidate_name | string | 否 | 传值覆盖，传空表示清空；最大 100 字符 |

### 16.8 拉取腾讯会议转写

```http
POST /api/v1/interviews/{interview_id}/transcript/tencent
```

从腾讯会议拉取该场会议的录制转写文本，写入 `transcript`，`transcript_source=tencent`。会议未开启云录制/转写时返回业务错误。

### 16.9 触发分析

```http
POST /api/v1/interviews/{interview_id}/analyze
```

行为：

1. 校验候选人姓名已确认（未确认时要求先调用 16.7）。
2. 若 `transcript` 为空且材料为音视频，先转写（`analysis_status=transcribing`）。
3. 分段、识别候选人说话人、配对问答。
4. 规则 + 模型评分，归一化并判定是否待定。
5. 写入 `evaluation`、`total_score`，`analysis_status=completed`；异常时 `failed` 并写 `error_message`。

响应：更新后的 `InterviewResponse`。

### 16.10 查询与修订评价

```http
GET   /api/v1/interviews/{interview_id}/evaluation
PATCH /api/v1/interviews/{interview_id}/evaluation
```

`PATCH` 请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| dimensions | object[] | 否 | 维度修订：`name`、`score`、`reason` |
| total_score | number | 否 | 直接修订总分（与维度修订二选一） |
| note | string | 否 | 修订说明 |

修订规则：取值范围校验（0 ≤ score ≤ max）、重算总分、保留原始 AI 分数（`ai_score`）、标记 `manual=true`、记录修订记录。

## 17. 接口总览

以下为当前代码实际注册的全部接口（共 119 个，含 `/health`；前缀统一为 `/api/v1`）。除注册、登录、考试分享查询外，均需 `Authorization: Bearer <token>`。

### 17.1 认证与用户（15）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 登录获取 Token |
| POST | `/auth/refresh` | 刷新 Token |
| GET | `/auth/me` | 当前用户信息 |
| GET | `/users/` | 用户列表（超管） |
| GET | `/users/{user_id}` | 用户详情 |
| PUT | `/users/{user_id}` | 更新用户 |
| DELETE | `/users/{user_id}` | 删除用户（超管） |
| POST | `/users/admin/users` | 管理员创建用户 |
| GET | `/users/admin/users/{user_id}/roles` | 查看用户角色 |
| PUT | `/users/admin/users/{user_id}/roles` | 分配用户角色 |
| GET | `/users/admin/roles` | 角色列表 |
| POST | `/users/admin/roles` | 创建角色 |
| DELETE | `/users/admin/roles/{role_id}` | 删除角色 |
| GET | `/users/me/roles` | 我的角色 |

### 17.2 会话与消息（9）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/conversations/` | 会话列表 |
| POST | `/conversations/` | 创建会话 |
| GET | `/conversations/{conversation_id}` | 会话详情 |
| PUT | `/conversations/{conversation_id}` | 更新会话 |
| DELETE | `/conversations/{conversation_id}` | 删除会话 |
| GET | `/conversations/{conversation_id}/messages` | 消息列表 |
| POST | `/conversations/{conversation_id}/messages` | 追加消息 |
| PUT | `/conversations/{conversation_id}/messages/{message_id}` | 更新消息 |
| DELETE | `/conversations/{conversation_id}/messages/{message_id}` | 删除消息 |

### 17.3 通用对话（4）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/chat/send` | 发送消息 |
| POST | `/chat/stream` | 流式对话 |
| GET | `/chat/suggestions` | 建议问题 |
| POST | `/chat/feedback` | 消息反馈 |

### 17.4 HR Agent（7）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/agent/graph/chat` | LangGraph 对话（SSE） |
| POST | `/agent/graph/resume` | 恢复 interrupt（SSE） |
| POST | `/agent/stream` | JD 生成链直通（需 `confirmed_requirements`） |
| POST | `/agent/resume-screen/stream` | 简历批量评分（multipart） |
| POST | `/agent/interview-plan/stream` | 面试方案生成（multipart） |
| POST | `/agent/exam/stream` | 试卷生成（JSON） |
| POST | `/agent/exam/document-stream` | 基于上传附件试卷生成（multipart，对话页使用） |

### 17.5 HR 工作流（8）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/hr-workflows/parse-requirements` | 解析招聘需求 |
| POST | `/hr-workflows/generate-jd` | 生成 JD（Dify type=1） |
| POST | `/hr-workflows/generate-scoring-criteria` | 生成评分标准（type=2） |
| POST | `/hr-workflows/evaluate` | 简历评估（type=3） |
| POST | `/hr-workflows/generate-interview-plan-by-resume` | 生成面试方案（type=4） |
| POST | `/hr-workflows/papers/parse-intent` | 解析考试意图（type=5） |
| POST | `/hr-workflows/papers/generate` | 生成试卷 |
| POST | `/hr-workflows/papers/submit` | 提交答卷 |

### 17.6 JD / 评分标准 / 面试方案（15）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/job-descriptions/save` | 保存 JD |
| PUT | `/job-descriptions/{jd_id}` | 更新 JD |
| GET | `/job-descriptions/{jd_id}` | JD 详情 |
| GET | `/job-descriptions/` | JD 列表 |
| DELETE | `/job-descriptions/{jd_id}` | 删除 JD |
| POST | `/scoring-criteria/save` | 保存评分标准 |
| PUT | `/scoring-criteria/{criteria_id}` | 更新评分标准 |
| GET | `/scoring-criteria/{criteria_id}` | 评分标准详情 |
| GET | `/scoring-criteria/` | 评分标准列表 |
| DELETE | `/scoring-criteria/{criteria_id}` | 删除评分标准 |
| POST | `/interview-plans/save-generated` | 保存生成的方案 |
| PUT | `/interview-plans/{plan_id}` | 更新方案 |
| GET | `/interview-plans/{plan_id}` | 方案详情 |
| GET | `/interview-plans/` | 方案列表 |
| DELETE | `/interview-plans/{plan_id}` | 删除方案 |

> JD、评分标准、面试方案三类接口均由后端代理到远程 HR 服务（`HR_SERVICE_HOST:PORT`），本系统不落库。

### 17.7 简历评估（7）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/resume-evaluation/evaluate-auto` | 自动评估（上传文件） |
| GET | `/resume-evaluation/history` | 评估历史 |
| GET | `/resume-evaluation/supported-formats` | 支持格式（PDF/DOC/DOCX/TXT/MD，10MB） |
| GET | `/resume-evaluation/{evaluation_id}` | 评估详情 |
| DELETE | `/resume-evaluation/{evaluation_id}` | 删除评估 |
| PUT | `/resume-evaluation/{evaluation_id}/status` | 更新候选人状态 |
| POST | `/resume-evaluation/export-zip` | 导出简历包 |

### 17.8 文档与知识库（13）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/documents/` | 文档列表 |
| POST | `/documents/upload` | 上传文档 |
| GET | `/documents/{document_id}` | 文档详情 |
| GET | `/documents/{document_id}/chunks` | 切片预览 |
| DELETE | `/documents/{document_id}` | 删除文档（含切片与向量） |
| GET | `/knowledge-base/` | 知识库列表 |
| POST | `/knowledge-base/` | 创建知识库 |
| PUT | `/knowledge-base/{kb_id}` | 更新知识库 |
| DELETE | `/knowledge-base/{kb_id}` | 删除知识库 |
| GET | `/knowledge-assistant/config` | 助手配置 |
| POST | `/knowledge-assistant/ask` | 知识问答 |
| GET | `/knowledge-assistant/documents` | 可选文档列表 |
| POST | `/knowledge-assistant/auto-select-kb` | 自动选择知识库 |

### 17.9 试卷与考试（9）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/exam-management/papers` | 试卷列表 |
| POST | `/exam-management/papers` | 保存试卷 |
| GET | `/exam-management/papers/{paper_id}` | 试卷详情 |
| PUT | `/exam-management/papers/{paper_id}` | 更新试卷 |
| DELETE | `/exam-management/papers/{paper_id}` | 删除试卷 |
| GET | `/exam-management/papers/{paper_id}/share` | 分享用试卷内容（免登录） |
| GET | `/exam-management/exam-results` | 考试结果列表 |
| GET | `/exam-management/exam-results/{result_id}` | 结果详情 |
| GET | `/exam-management/exam-results/{result_id}/export` | 导出结果 |

### 17.10 腾讯会议与智能面试（17）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/meetings/status` | 会议能力是否配置 |
| POST | `/meetings/` | 创建会议 |
| GET | `/meetings/{meeting_id}` | 查询会议 |
| POST | `/meetings/{meeting_id}/cancel` | 取消会议 |
| POST | `/interviews/start` | 建会并创建面试记录 |
| GET | `/interviews/` | 面试列表 |
| GET | `/interviews/{interview_id}` | 面试详情 |
| GET | `/interviews/{interview_id}/record-settings` | 录制设置 |
| PATCH | `/interviews/{interview_id}` | 更新会议参数 |
| POST | `/interviews/{interview_id}/sync` | 同步会议状态 |
| POST | `/interviews/{interview_id}/cancel` | 取消面试 |
| POST | `/interviews/{interview_id}/media` | 上传音视频/文档 |
| PATCH | `/interviews/{interview_id}/candidate` | 修正候选人姓名 |
| POST | `/interviews/{interview_id}/transcript/tencent` | 拉取腾讯转写 |
| POST | `/interviews/{interview_id}/analyze` | 触发转写与分析 |
| GET | `/interviews/{interview_id}/evaluation` | 查询评价 |
| PATCH | `/interviews/{interview_id}/evaluation` | 修订评价 |

### 17.11 邮箱与统计（13）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/email-configs/` | 配置列表（超管） |
| POST | `/email-configs/` | 创建配置 |
| GET | `/email-configs/{config_id}` | 配置详情 |
| PUT | `/email-configs/{config_id}` | 更新配置 |
| DELETE | `/email-configs/{config_id}` | 删除配置 |
| POST | `/email-configs/{config_id}/test` | 连接测试 |
| POST | `/email-configs/{config_id}/fetch` | 手动抓取邮件 |
| GET | `/email-configs/{config_id}/logs` | 抓取日志 |
| GET | `/email-configs/{config_id}/latest-email` | 最近一封邮件 |
| GET | `/stats/dashboard` | 工作台统计 |
| GET | `/stats/recruitment-trend` | 招聘趋势 |
| GET | `/stats/training-completion` | 培训完成情况 |
| GET | `/stats/recent-activities` | 近期活动 |

### 17.12 其他（2）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/intent/route` | 意图识别与路由建议 |
| GET | `/health` | 健康检查（无需登录） |

## 18. 联调检查清单

| 检查项 | 标准 |
| --- | --- |
| 鉴权 Header | 除注册、登录、考试分享提交、健康检查外，接口应携带 Bearer Token |
| 401 处理 | 前端清理登录状态并跳转登录 |
| 403 处理 | 前端提示权限不足 |
| 422 处理 | 展示字段校验错误 |
| 分页接口 | 前端正确处理 `items/total/page/size/pages` |
| 文件上传 | 使用 `multipart/form-data`，字段名与接口一致 |
| SSE | 按 `type` 字段分发：`progress` / `delta` / `artifact` / `interrupt` / `final` / `error`，收到 `[DONE]` 结束 |
| 中断恢复 | 收到 `interrupt` 后必须调 `/agent/graph/resume` 才能继续，不能重新发一条消息 |
| 会议接口 | 先查 `/meetings/status`，未配置时隐藏建会入口 |
| 面试分析 | 分析前必须已完成姓名确认，否则后端拒绝 |
| 高风险操作 | 删除、邮件发送必须二次确认 |
| 敏感字段 | 密码、邮箱授权码、腾讯会议 Token 不应在前端明文回显 |
