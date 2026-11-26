# Agent 服务拆分设计 · 渐进组件化（仅设计，不改代码）

> 本版已合入校验代理的逐边复核结论（4 处边界修正 + 迁移顺序调整），并经主线 6 处抽样核实（S328/369 await、C547 补题走 exam_service、C703 exam→context、C1109/1123/1141 loop 读 tool_registry、C305/361 skills 用 email、R381 match 为纯函数）。

## Context

现状：`AgentService`（app/services/agent_service.py）+ 三个 mixin（app/agent/chains/{core,editing,resources}.py）合计约 4000 行，是**同一个巨型类的物理拆分**而非逻辑分层：

- mixin 之间互相交叉调用（editing→resources 的资源定位、resources→core 的 _stream_text、core→resources 的解析/生成），没有独立边界；
- 全部状态（db / llm_service / dify_service / tool_registry / skill_dispatcher / _graph_artifacts）挂在宿主 self 上，任何方法都能摸到任何资源；
- 文件边界 ≠ 功能边界：解析散在 resources+editing、流式协议在 resources、显示工程在 core、闭环推进在 core+editing；
- LangGraph 节点（app/agent/nodes/*.py）直接调用 service 的**私有方法**，拆分必须给这些调用点兼容路径；
- editing.py 头部冗余 import 等机械拆分痕迹。

用户诉求：结合功能与业务场景给出"再拆分"的设计。**本轮交付 = 设计方案**（对话讲清 + 本计划文件），不改代码、不写文档。目标形态经用户确认 = **渐进组件化**：mixin 最终消失，按功能域拆成构造注入的组件类，AgentService 退化为薄编排器；迁移分步、每步行为不变可验证；**第 4 步清理经用户确认必做**。

## 设计原则

1. **文件边界 = 功能域边界 = 业务场景边界**：一个组件 owning 一个功能域（对应深度导读的 A–J 域），域内方法不再跨文件散落。
2. **依赖显式化**：组件只通过构造函数拿到自己需要的资源（db / llm / dify / dispatcher / exam_service），不再共享宿主 self；依赖方向单向（编排器→组件；组件间仅允许 deletion/loop/exam→context 这类下游依赖；叶子层 utils/events 零业务导入）。
3. **无状态优先下沉**：不读 self 状态的方法（事件封装、SSE 入站/出站协议、正则兜底、试卷渲染格式）先变成模块级纯函数，可单测。
4. **兼容优先**：节点侧私有方法调用点与评测脚本 chat() 入口在迁移期保持可用（一行委托层），最后一步才清理。
5. **行为不变**：流式事件协议（progress/delta/artifact/final）、阈值常量（60 分 / 0.35 / 8:2 / 20 字符 / 10 条历史等）、兜底链语义、**用户可见文案逐字**（nodes/editing.py:5-6、nodes/resources.py:7 注释明示文案是评测契约）全部保持。

## 内部依赖盘点事实（行号实测）

- 规模/方法数：S 13 / C 41 / E 22 / R 60；四文件**无任何 staticmethod/classmethod**；唯一 property 是 dify_service。
- **零 self 纯函数（P0）共 56 个**：C 19 + E 6 + R 31（如 _safe_json_loads R912、_clean_optional_value R1001、_dedupe_stream_delta R890、_format_exam_question_block C648、_parse_selection_ordinal E302、_build_jd_update_payload E515）→ 第一步按落点规则下沉，零风险。
- **交叉调用环**：C↔R 双向（C 用 R 的解析/生成/流工具；R 用 C 的 _stream_text C251、_normalize_candidate_match_text C917、_recent_resume_screening_groups C987）；E→C/R；**S→mixin 单向、mixin 从不回调 S** → 编排器地位天然成立。环上全部边经复核均为"工具误置"，拆入叶子/下游层后剩余业务边天然单向。
- **"公共工具箱"病灶**：R 被跨文件调用 33 个方法、C 21 个 → 现状 R/C 兼任公共工具层；拆分必须先把"工具"与"业务"分离，否则组件间继续环。
- **E 高内聚**：仅 _resolve_interview_exam_followup E568 被外部调（S326、C703）→ E 是**按域重切**的最佳试点；但 E 整体拆入 context/rewriting/persistence 三处，**不是单一组件**，故组件化试点改用 rewriting（E482-513 仅 2 方法、仅 llm 依赖、外部调用点仅 nodes/editing.py:154,314）。
- 归属修正（校验后定稿）：
  - _normalize_candidate_match_text（C917，E/R 都用）→ **utils/text_utils 叶子**；
  - _format_memory_for_prompt / _normalize_memory_text（C783/791/777，E/R/reasoning 都用）→ **utils 叶子**（若放 context 会造 context↔parsing 模块级环：context 的 followup 解析需 parsing 规则函数 E574，parsing 需 memory prompt E54,123/R464）；
  - _stream_text（C251）+ SSE 入站三件套 _normalize_sse_chunk/_extract_stream_delta/_dedupe_stream_delta + _extract_answer（R875/839/890/827）→ **events 叶子**（出站封装与入站协议同属无状态线协议层；由此**不需要 rendering→generation 边**）；
  - 资源定位三件套 _recent_generated_resources/_list_deletable_resources/_match_delete_resources + _resource_search_text（R171/…/381）→ **context**（放 deletion 会造 context↔deletion 新环；E→R 的 8 处调用变 context 内部）；_match_delete_resources 体为纯函数（R381-398 已核实），做 context 模块内函数；
  - _recent_resume_screening_groups（C987）→ **context**（消费方跨 loop C978 与 deletion R155，方法体是"最近产物反查+db 回填"与 context 同构；放 loop 会强增 deletion→loop 边）；60 分语义常量仍归 loop，按参数传入；纯分组部分可再抽 loop 模块函数；
  - _select_exam_knowledge_files（R488，0.35 阈值）→ **exam**（唯一调用方 S397，本质是出题输入准备；单方法单调用方不值得独立 kb 模块）；
  - _inherit_delete_type_from_candidates（R94，reasoning.py:169 消费）→ context。
- **死代码**：_handle_intent_fallback（S446）全仓库无调用方（复核确认）→ 第一步即可删除。
- _parse_exam_requirements（R479）async 但体内无 await → 可改 sync，**但必须推迟到第 4 步**：S328、S369 仍 `await`（已核实），提前改 sync 会 TypeError。
- llm_service **8 处内联懒赋值**（C286,840；E59,128,490,507；R67,468）→ 组件化时统一为懒 provider 闭包；intent_service 四文件内零使用（仅 reasoning.py:106 外部用）→ 属性保留但可移出核心构造路径；email_send_service（S91 = EmailSendService(db)）被 C305,361 skill phase 使用 → **skills 组件注入必需**。
- **loop 注入修正**：C1109,1123,1141 读 self.tool_registry（只读 dict）→ loop 需要 tool_registry；该区域不触 db（分组查询经 context）→ loop **不需要 db**。
- **exam 注入修正**：补题走 exam_service.generate_exam（C547 已核实），组件体不碰 llm_service → exam 注入 **db + exam_service + context**，草稿"llm（补题）"有误；exam 跨服务调私有 ExamService._parse_exam_content（C563,592）与内联 ExamService(self.db)（C608）→ 保持同 db session，标记技术债。
- **registry 修正**：build_tool_registry 读 dispatcher.bundles（C109）→ 收 **dispatcher 实例**（非 skills 目录路径）；同模块收 route_for_intent(registry,…)（C123）。
- _graph_artifacts：不在 __init__，nodes/routing.py:39 写入、R180 getattr 防御读、routing_agent.py:142 读 → `__init__` 显式初始化 `self._graph_artifacts = []` 后 routing.py:39 写入仍工作；按调用参数传 context，不进组件状态（避免跨请求残留）。
- 补充消费方：**tools/router_tools.py** → E._resolve_recent_jd_candidates/_resolve_recent_criteria_candidates + R._recent_generated_resources/_list_deletable_resources/_match_delete_resources；**:19 模块级 _tool_lock 串行化同 session 查询 → 组件化不得引入同请求并发 db 访问**。
- bridge.py:34-39 已有 _stream_text 等价副本（6 字符切片一致）→ 第一步统一到 events，行为不变。
- S1030-1041 对 inner stream 事件 steps/artifacts 的拼接手术 → **留在编排器**，不下放 exam。
- routing_agent.py:90 路由 agent 缓存按 (intents, tool_text) 键控 → registry 输出内容须保持稳定。
- 编排器保留清单补全：除 chat() + 5 handler + 5 stream 门面外，还有同步执行链 _run_recruitment_agent（C161，nodes/jd.py:111 消费）。

## 目标结构（终态，12 模块）

新增 `app/agent/components/`（目录名实施时可与 chains 并存过渡），每域一个模块。**matching.py 取消**（normalize 入 utils、定位/匹配入 context），rendering.py 更名 **exam.py**：

| 模块 | 组件/形态 | 职责（源域） | 注入依赖 |
|---|---|---|---|
| events.py | 模块级函数（不建类） | 出站事件封装 _stream_event/_tool_stream_event/_resume_stream_event（C407,731,752）、_stream_text 切片（C251）、_planning_step（C149）、**入站 SSE 适配** _normalize_sse_chunk/_extract_stream_delta/_dedupe_stream_delta/_extract_answer（R875/839/890/827）（J/A） | 无 |
| parsing.py | RequestParsers | 需求/删除/JD编辑/标准编辑/试卷配置 双通道解析 + 正则兜底（_fallback_exam_parse R1097）+ 意图判定规则族（_is_*，reasoning.py 与 context/exam/loop 函数级消费）+ 附件规范化 _normalize_attachments/_filter_attachments（bridge 消费）（B） | llm |
| generation.py | ContentGateway | Dify type1/2/4 同步+流式（R539/612/735…）+ 同步兜底降级链 + 模拟切片（调 events）（C） | dify |
| exam.py | ExamFlow | 试卷内容流与渲染（C463-729 全部）：*** 双缓冲、竖线六段转 markdown（_format_exam_question_block C648 模块函数）、缺题补齐（经 exam_service.generate_exam）、分值分配、8:2 约束文案（C723）、KB 选择 _select_exam_knowledge_files（R488）（J） | db + exam_service + context |
| rewriting.py | ContentRewriter | JD/评分标准 LLM 全文重写（"保留结构只改被要求部分"，E482-513）（D 的改写半） | llm |
| context.py | ReferenceResolver | 三级记忆查找（R171）、saved_*_id 翻译、资源定位三件套 + search_text、挂起编辑上下文（E194/E369）、中文序数（E302 模块函数）、criteria 折叠、_resolve_recent_jd/criteria_candidates（E204+）、_resolve_interview_exam_followup（E568）、_recent_resume_screening_groups（C987）、_inherit_delete_type_from_candidates（R94）（E） | db |
| persistence.py | ResourceWriter | JD/标准/考试文档落库（sha256 去重，R773/805）、update payload（E515/546 模块函数）、edit_history 留 10 条（D） | db |
| deletion.py | ResourceDeleter | 关键词清洗、四类删除分发（R274/400）、级联统计、部分失败容忍（F）；定位/匹配调 context | db + context |
| loop.py | RecruitmentLoop | 60 分分组 summary（C932）、followup action 决策（C978-1143）、闭环推进（G）；分组反查经 context | context + tool_registry（只读 dict） |
| candidates.py | CandidateResolver | 四态判定（R651）+ candidate_id 防幻觉校验、50 上限（H） | db + llm |
| skills.py | SkillMailFlow | SKILL.md 草稿、draft→confirm→send 状态机（C258/341）（I） | skill_dispatcher + llm + email_send_service |
| registry.py | build_tool_registry(dispatcher) + route_for_intent(registry,…) 模块函数 | 7 工具 + skill bundle 声明（C109/123）（A） | dispatcher 实例 |

`AgentService` 保留：chat() 门面、5 个意图 handler、5 个 stream 门面（S463,599,771,850,956）、同步执行链 _run_recruitment_agent（C161）、S1030-1041 inner-stream 事件拼接手术——只做**流程编排与事件组装**；__init__ 构造组件实例并显式初始化 _graph_artifacts；db/tool_registry/skill_dispatcher/llm_service/email_send_service/intent_service/dify_service 属性全程保留。

**模块形态沿仓库惯例**：组件类收所需资源构造参数（db-bound 按请求 new，同 ExamService(db)）；无状态域（events/registry/域内纯计算）做成**模块级函数、不建类**（同 qa_pairing.py / transcript_segmenter.py 惯例）；通用文本/JSON 类扩 **app/utils/text_utils.py**（已有先例 :198 split_options），不新建 shared 模块。

**56 个 P0 落点规则**：
- R1 跨域+领域无关文本/JSON → utils/text_utils：_clean_optional_value(R1001)、_safe_json_loads(R912)、_normalize_candidate_match_text(C917)、_normalize_memory_text(C777)、_safe_int(R974)、_normalize_optional_list、memory prompt 两函数(C783,791)。
- R2 跨域+流式/事件协议 → events 模块函数：_dedupe_stream_delta、_extract_stream_delta、_normalize_sse_chunk、_extract_answer、_stream_text、_planning_step、三个事件封装。
- R3 单域纯计算 → 属主模块内私有函数（不建类、不进 utils）：_format_exam_question_block→exam；_build_jd/criteria_update_payload→persistence；_parse_selection_ordinal→context；_fallback_exam_parse→parsing；_build_resume_screening_loop_summary→loop；_match_delete_resources/_resource_search_text→context。
- 叶子保证：utils/events 不导入任何业务组件；**函数导入会加载整个模块**，故 parsing 模块整体不得反向导入 context。

**兼容委托层（迁移期）**：AgentService 上保留全部被外部消费的私有方法为**原名原参（含关键字参数名，nodes/resources.py:185-192 按 keyword 传参）**一行委托；约 60 个调用点、消费文件：bridge / reasoning / routing_agent / nodes×7（routing,jd,editing,resources,legacy,skill,planning）/ tools/router_tools（+chat_tools 仅属性）；最后一步才改写消费方并删委托。

## 断环手法与组件依赖图

**C↔R 环三步断**：① 跨域共享纯工具下沉叶子（utils / events）；② 业务方法归域（R 的生成→generation、落库→persistence、定位/匹配→context，C 的闭环→loop、候选人→candidates、试卷→exam）；③ 组件间只留单向边。

环上边逐条归属（校验表压缩）：
- R→C _stream_text（R570,645,764）→ events；R→C _normalize_candidate_match_text（R113…397）→ utils；R→C _recent_resume_screening_groups（R155）→ context；R→C _format_memory_for_prompt（R464）→ utils；
- C→R SSE 三件套+_extract_answer（C489-490,514,562）→ events；C→R _safe_json_loads/_clean_optional_value（C843,541,712,874）→ utils；C→R _recent_generated_resources（C993）→ context；
- E→C memory prompt/match text（E54,123,232,477）→ utils；E→C _is_followup_interview_exam_request（E574）→ parsing 函数层；E→R 规则族/json/list（E62-78,105-107）→ parsing/utils；E→R recent/list/match/search_text（E204…576）→ context 内部；
- C→E、S→E _resolve_interview_exam_followup（C703、S326）→ context。

依赖箭头（终态，DAG 无环）：
- 构造/注入边：orchestrator → 全部组件 + registry 函数；deletion → context；loop → context（+tool_registry dict）；**exam → context**（C703→E568，必需边）
- 模块函数导入边：{generation, exam, skills, loop} → events；{parsing, generation, exam, context, candidates, deletion, loop, persistence} → utils；{context, exam, loop} → parsing（仅规则函数；parsing 不 import context，无环）
- **不存在的边**：exam→generation（SSE 已进 events）；loop→candidates（C970-1143 无调用证据）；context→deletion（匹配三件套已归 context）；parsing→context（memory prompt 已进 utils）
- events / utils / registry → 零业务下游

## 常量归属表（各域自持，不做全局大杂烩）

| 常量 | 现位置 | 终态归属 |
|---|---|---|
| 60 分闭环阈值 | C935,978、S705,722 | loop.py（context 分组方法按参数接收） |
| 0.35 KB 置信度 | R517 | exam.py（KB 选择） |
| 8:2 出题配比文案 / 1500 字符方案截取 | C723 / C728 | exam.py |
| 20 字符去重裁剪阈值 | R903 | events.py（SSE 适配） |
| 6 字符模拟流式切片 | C255（bridge.py:38 同值副本） | events.py |
| edit_history 留 10 条 | E526,555 | persistence.py |
| 50 候选人上限 | C802 | candidates.py |
| 8 条消息挂起扫描 | E369 | context.py |
| 2500 字符跟进内容拼接 | E568 | context.py |
| 3000 字符补题避重上下文 | C544 | exam.py |
| RESUME_ATTACHMENT_EXTENSIONS/FORMATS | S28-29 | parsing.py；迁移期 agent_service 保留再导出；**保持与 ResumeParserService、前端 isResumeFile 三处同步的注释约束** |
| 记忆 12 条 / 6000 字 | reasoning.py:262-263 | 原地不动（reasoning 自持） |

## 组件接口签名示例（终态草案）

- `ReferenceResolver.recent_generated_resources(resource_type, user_id, conversation_id=None, limit=12, *, graph_artifacts=None) -> List[Dict]`（三级查找；graph_artifacts 按参数传入，委托层传 self._graph_artifacts）
- `ContentGateway.generate_jd_stream(original_text, parsed, conversation_id) -> AsyncGenerator[str, None]`（内部含 events SSE 适配 + 同步兜底 + 模拟切片，调用方无感知）
- `SkillMailFlow.handle(intent, message, user_id, route, selected_tool, memory_context, confirmed_requirements=None) -> AgentChatResponse`
- `ResourceDeleter.delete_matched(matches, *, user_id) -> DeleteReport(deleted, failures, cascaded_criteria_count)`
- `RequestParsers.parse_jd_edit(message, memory_context) -> JdEditRequest`（dataclass 沿 chains/types.py 惯例）

## 业务场景 → 组件序列（行号实测）

- **生成 JD**：nodes/jd.py:30→parsing(R452)；jd.py:101→S463→generation(R539)→persistence(R773 经 S522)→generation(R735 经 S531)→persistence(R805 经 S547)
- **两轮改 JD**：nodes/editing.py:58→parsing(E46)；:84→context(E194 挂起目标/序数)；:154→rewriting(E482)；:184→persistence(E515 payload+edit_history)
- **筛选→面试→试卷**：S599→loop(C932 经 S705)；S771→candidates(R651 经 S794)→generation(R612 经 S805)；S850→exam(C688 经 S871)→context(E568 经 C703)→exam(C463 经 S885、C518 经 S905)→persistence(save_exam S939)
- **删除刚才的试卷**：nodes/resources.py:37→parsing(R48)；:123→context(R171)；:134→context(R381 匹配)；:185→deletion(R274)
- **邮件 Skill**：nodes/skill.py:34→skills(C258)；:64→skills(C341)（+events）

## 迁移四步（每步行为不变；第 4 步经用户确认必做）

1. **抽共享叶子断环**（先定工具箱归属，避免方法二次搬运）：utils/text_utils 扩容（R1）+ events 建模块（R2，含 bridge.py:34-39 副本统一）+ parsing 规则函数层 + memory prompt 入 utils；mixin 方法变一行委托；按 R3 下沉单域纯函数；为代表性纯函数补单测；顺带删死代码 _handle_intent_fallback。**此步即断 C↔R 环**。
2. **按域重切 chains/（仍 mixin）**：试点 **E 文件**（高内聚、唯一外部入口 E568）；重切为与目标模块同名的 mixin 文件，方法名不变、nodes 零改动；清冗余 import。
3. **组件化（留委托）**：试点改为 **rewriting**（E482-513 仅 2 方法、仅 llm、外部点仅 nodes/editing.py:154,314，最能验证懒 provider+委托模式）；随后 skills → context → deletion/loop/candidates → parsing/generation/persistence/exam；AgentService 原私有方法保留一行委托；llm_service 保持可写普通属性 + provider 闭包（8 处内联懒赋值统一改调 provider，legacy 写回对组件随后可见）；_graph_artifacts 在 __init__ 显式初始化。
4. **清理终态**：改写消费文件约 60 个调用点为组件实例或 service 公开方法调用，删委托层与三个 mixin 类；**_parse_exam_requirements 此步才改 sync**（S328/369 的 await 同步改写）；_graph_artifacts 按参数传 context；兼容矩阵 grep 归零确认。chat() 与五 stream 门面为永久外部契约，不删。

## 风险与兼容（外部盘点事实，行号实测）

**兼容红线①：外部私有方法/属性调用点**（拆分后必须保留委托或同步改写）：
- bridge.py:69,134 `_normalize_attachments`
- nodes/routing.py:54 `_route_for_intent`；**:39 写 `service._graph_artifacts`**（图状态注入点）
- nodes/jd.py:30,35,41-43,49,50,110,111（解析/缺字段/规划步/规范化/同步执行链）
- nodes/editing.py:58,60,84,99,108,119,154,184,222,224,248,263,279,314,344（编辑全链）
- nodes/resources.py:37-185（删除全链 + 闭环 followup 三方法；:185-192 关键字传参）
- nodes/legacy.py:93-123 `_handle_general_chat`/`_build_memory_augmented_prompt`；:106-110 **读写 `service.llm_service`**
- nodes/skill.py:34,46,64；nodes/planning.py:18,32,47
- **reasoning.py:101-169,294-297**：意图判定规则族（_is_jd_edit_request/_is_criteria_edit_*/_is_followup_*）、_inherit_delete_type_from_candidates(:169)、_normalize_memory_text
- **routing_agent.py:52 读 tool_registry、:142 读 _graph_artifacts**；:90 缓存键 (intents, tool_text) → registry 输出稳定
- 属性级耦合：`service.db`（reasoning.py:274,283、tools/chat_tools.py:34-79、nodes/editing.py:152,182）、`tool_registry`（多节点）、`skill_dispatcher`（reasoning.py:60）、`llm_service`（legacy.py）
- **tools/router_tools.py** → E._resolve_recent_jd_candidates / _resolve_recent_criteria_candidates + R._recent_generated_resources / _list_deletable_resources / _match_delete_resources；:19 _tool_lock → 禁止同请求并发 db 访问

**兼容红线②**：`AgentService.chat()` 签名（S101-110）= 外部评测契约（agent_eval_runner 不在本仓库，仅 S116 注释引用）；`stream_*` 五门面（S463,599,771,850,956）被 nodes/files.py、nodes/jd.py 消费；tests/test_emit_generator.py:22 monkeypatch 依赖 `legacy.get_stream_writer` 模块级符号（legacy.py:18，迁移期不动）；**用户可见文案逐字保持**（nodes/editing.py:5-6、nodes/resources.py:7）。

**技术债与约束**：
- exam 跨服务私有调用 ExamService._parse_exam_content（C563,592）+ 内联 ExamService(self.db)（C608）→ 保持同 db session，标记技术债（后续可给 ExamService 加公开 parse/allocate 接口）
- S1030-1041 inner-stream steps/artifacts 拼接手术留编排器，不下放 exam
- llm_service **不可改只读 property**（legacy.py:106-107 就地赋值会 AttributeError）；若日后改 property 必须带 setter
- _graph_artifacts 显式化后 routing.py:39 写入仍工作；R180 getattr 防御读改为 context 显式关键字参数 graph_artifacts=None

**可复用仓库惯例**：
- db-bound 业务服务收 db 构造参数、按请求 new（ExamService(db) 等）；无状态模型客户端无参构造 + 懒加载（DifyService/LLMService）
- 纯函数模块落点：app/utils/text_utils.py 扩容（:198 split_options 先例）或 app/services/ 平级无类模块（qa_pairing.py、transcript_segmenter.py）
- "收 service 参数的模块级函数"协作层已成型：reasoning.py、routing_agent.py —— 半纯编排函数沿此惯例
- skill 加载器 app/services/agent_skills.py：build_default_skill_dispatcher()、bundle.resolve_phase()
- llm_service 现状是 None + 使用点判空再建（**不是 property**）；dify_service 才是懒 property（S95-100）；组件收 `llm_provider: Callable[[], LLMService]` 闭包保持"不配置不加载"语义

## 验证

**设计级（本轮，已完成）**：交叉调用边逐条确认终态归属与依赖方向合法（校验代理逐边复核 + 主线 6 处抽样）；外部调用点逐条确认兼容路径；常量/阈值归属表与源码核对。

**执行级（若后续批准实施，每步通用）**：
1. import smoke：`.venv/bin/python -c "import app.agent.graph, app.agent.bridge, app.services.agent_service"`（graph.py:21-37 拉起全部 nodes，捕获环/缺符号）
2. 调用点 grep 前后 diff 为空：`grep -rEn "service\._[a-zA-Z_]+" app/agent app/api | sort`（委托层保证 ~60 调用点不动；第 4 步要求 agent_service.py 外零命中）
3. `.venv/bin/python -m pytest tests/test_emit_generator.py -v`（3 用例；legacy.get_stream_writer 符号不动）
4. 纯函数下沉步单测代表：_dedupe_stream_delta（累计全文/小 token 不裁）、_parse_selection_ordinal（中文序数）、_format_exam_question_block（六段格式）、_safe_json_loads、_build_jd_update_payload
5. SSE 冒烟（**先录基线再比对事件序列与 final 文案**）：POST `/api/v1/agent/graph/chat`（agent_graph.py:80，interrupt 确认 payload）、`/agent/stream`（agent.py:73，progress/delta/artifact/final）、`/agent/exam/stream` 与 `/agent/exam/document-stream`（agent.py:160,189，*** 双缓冲与补题）、`/agent/resume-screen/stream`、`/agent/interview-plan/stream`
6. agent_eval_runner（仓外）每步后跑；五场景手工冒烟 = 生成 JD / 两轮改 JD / 筛选→面试→试卷 / 删除刚才的试卷 / 邮件 Skill

## 交付

对话中给出完整设计（结构表 + 依赖图 + 场景映射 + 迁移步骤 + 常量表 + 风险），本计划文件即设计存档（已合入校验修正）。**不改任何代码与文档**；若后续批准实施，从第 1 步"抽共享叶子断环"开始。