
from __future__ import annotations

import json
import logging
import hashlib
import os
import re
import asyncio
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.document import Document
from app.models.resume_evaluation import ResumeEvaluation, ResumeStatus
from app.schemas.agent import AgentArtifact, AgentChatResponse, AgentStep
from app.schemas.interview_plan import InterviewPlanCreate
from app.schemas.job_description import JobDescriptionCreate, JobDescriptionUpdate
from app.schemas.scoring_criteria import ScoringCriteriaCreate, ScoringCriteriaUpdate
from app.services.email_service import EmailSendService
from app.services.dify_service import DifyService
from app.services.agent_skills import AgentSkillBundle, AgentSkillDispatcher, build_default_skill_dispatcher
from app.services.exam_service import ExamService
from app.services.interview_plan_service import InterviewPlanService
from app.services.intent_service import IntentService
from app.services.job_description_service import JobDescriptionService
from app.services.kb_selection_service import KBSelectionService
from app.services.llm_service import LLMService
from app.services.resume_evaluation_service import ResumeEvaluationService
from app.services.scoring_criteria_service import ScoringCriteriaService
from app.utils.text_utils import extract_text_content

from app.agent.chains.types import AgentToolSpec

logger = logging.getLogger(__name__)

""" 
    核心编排、流式处理等私有方法.
"""

class _AgentServiceCoreMixin:
    def _build_tool_registry(self) -> Dict[str, AgentToolSpec]:
        """声明 Agent 能自主规划的工具和前置条件
        工具注册
            jd：生成岗位 JD，并自动生成评分标准。
            resume_screening：基于 JD 批量评分简历。
            interview_plan：基于已评分简历和 JD 生成面试计划。
            exam_generate：基于上传文档生成试卷。
            resource_delete：删除 JD、简历记录、面试方案、试卷。

            之后它还会扫描 backend/skills 下的 Skill，把 Skill 也注册为 Agent 工具。
                目前项目里有邮件 Skill，对应 email_notification 意图。
        """
        tools = [
            AgentToolSpec(
                name="generate_jd",
                intent="jd",
                route="/recruitment/jd-generator",
                description="生成岗位 JD，并自动生成简历评分标准",
                prerequisites=["确认岗位名称、地点、薪资、经验、学历"],
            ),
            AgentToolSpec(
                name="edit_jd",
                intent="jd_edit",
                route="/recruitment/jd-generator",
                description="修改最近生成或保存的岗位 JD",
                prerequisites=["定位要修改的 JD", "明确修改要求"],
            ),
            AgentToolSpec(
                name="edit_scoring_criteria",
                intent="criteria_edit",
                route="/recruitment/resume-screening",
                description="修改最近生成或保存的简历评分标准",
                prerequisites=["定位要修改的评分标准", "明确修改要求"],
            ),
            AgentToolSpec(
                name="evaluate_resume",
                intent="resume_screening",
                route="/recruitment/resume-screening",
                description="基于 JD 批量评分简历",
                prerequisites=["上传 PDF/DOC/DOCX 简历", "选择用于匹配的 JD"],
            ),
            AgentToolSpec(
                name="generate_interview_plan",
                intent="interview_plan",
                route="/recruitment/smart-interview",
                description="基于已评分简历和 JD 生成面试计划",
                prerequisites=["选择一位已评分候选人"],
            ),
            AgentToolSpec(
                name="generate_exam",
                intent="exam_generate",
                route="/training/exam-generator",
                description="基于上传文档生成考试试卷",
                prerequisites=["上传参考文档", "确认试卷配置"],
            ),
            AgentToolSpec(
                name="delete_resource",
                intent="resource_delete",
                route=None,
                description="按用户描述删除已生成的 JD、简历评分记录、面试方案或试卷",
                prerequisites=["明确要删除的资源类型和名称/候选人/标题"],
            ),
        ]
        registry = {tool.intent: tool for tool in tools}

        for bundle in self.skill_dispatcher.bundles.values():
            registry[bundle.intent] = AgentToolSpec(
                name=bundle.metadata.name,
                intent=bundle.intent,
                route=bundle.metadata.route,
                description=bundle.metadata.description or f"执行 {bundle.bundle_name} skill",
                prerequisites=list(bundle.metadata.prerequisites),
            )
        return registry

    def _build_skill_dispatcher(self) -> AgentSkillDispatcher:
        """构建运行时 skill dispatcher。"""
        return build_default_skill_dispatcher()

    def _route_for_intent(self, intent: str, message: str) -> Dict[str, Any]:
        tool = self.tool_registry.get(intent)
        return {
            "intent": intent,
            "route": tool.route if tool else None,
            "query": message,
            "kb_id": None,
        }

    def _normalize_attachments(self, attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for item in attachments:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            normalized.append({
                "name": name,
                "size": item.get("size"),
                "content_type": item.get("content_type"),
                "extension": name.rsplit(".", 1)[-1].lower() if "." in name else "",
            })
        return normalized

    def _filter_attachments(self, attachments: List[Dict[str, Any]], extensions: set[str]) -> List[Dict[str, Any]]:
        return [item for item in attachments if item.get("extension") in extensions]

    def _planning_step(self, tool: Optional[AgentToolSpec], detail: str) -> AgentStep:
        if not tool:
            return AgentStep(id="plan", title="判断处理方式", status="completed", detail=detail)
        prerequisites = "；".join(tool.prerequisites)
        return AgentStep(
            id="plan",
            title="选择执行工具",
            status="completed",
            detail=f"选择工具：{tool.description}。前置条件：{prerequisites}。{detail}",
            tool=tool.name,
        )

    async def _run_recruitment_agent(
        self,
        message: str,
        conversation_id: Optional[str],
        route: Optional[str],
        parsed_requirements: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
    ) -> AgentChatResponse:
        """用户确认后，_run_recruitment_agent() 会执行：
            1. 生成 JD。
            2. 保存 JD。
            3. 基于 JD 生成评分标准。
            4. 保存评分标准。
            5. 返回两个 artifact：`job_description` 和 `scoring_criteria`。
            """
        steps: List[AgentStep] = [
            self._planning_step(self.tool_registry.get("jd"), "招聘信息已确认，开始执行生成链路。"),
            AgentStep(id="parse", title="解析招聘需求", status="running", tool="parse_requirements"),
            AgentStep(id="jd", title="生成岗位 JD", status="pending", tool="generate_jd"),
            AgentStep(id="criteria", title="生成简历评分标准", status="pending", tool="generate_scoring_criteria"),
            AgentStep(id="next", title="规划下一步", status="pending"),
        ]
        artifacts: List[AgentArtifact] = []

        parsed = parsed_requirements or await self._parse_requirements(message, conversation_id)
        steps[1] = steps[1].model_copy(update={"status": "completed", "detail": self._brief_requirements(parsed)})
        artifacts.append(AgentArtifact(type="requirements", title="结构化招聘需求", content=parsed))

        steps[2] = steps[2].model_copy(update={"status": "running"})
        jd_content = await self._generate_jd(message, parsed, conversation_id)
        saved_jd = None
        if user_id:
            saved_jd = await self._save_job_description(jd_content, parsed, message, user_id, conversation_id)
        jd_detail = "已生成可编辑岗位 JD。"
        if saved_jd:
            jd_detail = f"已生成并保存到 JD 列表，ID：{saved_jd.id}"
        steps[2] = steps[2].model_copy(update={"status": "completed", "detail": jd_detail})
        artifacts.append(AgentArtifact(
            type="job_description",
            title=f"{parsed.get('job_title') or '岗位'} JD",
            content=jd_content,
            metadata={
                "job_title": parsed.get("job_title"),
                "route": "/recruitment/jd-generator",
                "saved_jd_id": str(saved_jd.id) if saved_jd else None,
            },
        ))

        saved_criteria = None
        steps[3] = steps[3].model_copy(update={"status": "running", "detail": "正在基于 JD 生成评分标准..."})
        criteria_content = await self._generate_scoring_criteria(jd_content, parsed, conversation_id)
        if user_id:
            saved_criteria = await self._save_scoring_criteria(
                criteria_content,
                parsed,
                user_id,
                conversation_id,
                saved_jd.id if saved_jd else None,
            )
        criteria_detail = "已生成简历评分标准。"
        if saved_criteria:
            criteria_detail = f"已生成并保存评分标准，ID：{saved_criteria.id}"
        steps[3] = steps[3].model_copy(update={"status": "completed", "detail": criteria_detail})
        artifacts.append(AgentArtifact(
            type="scoring_criteria",
            title=f"{parsed.get('job_title') or '岗位'}评分标准",
            content=criteria_content,
            metadata={
                "job_title": parsed.get("job_title"),
                "saved_criteria_id": str(saved_criteria.id) if saved_criteria else None,
                "saved_jd_id": str(saved_jd.id) if saved_jd else None,
            },
        ))

        steps[4] = steps[4].model_copy(update={"status": "completed", "detail": "如需筛选简历，可以继续告诉我“筛选简历”。"})

        job_title = parsed.get("job_title") or "这个岗位"
        return AgentChatResponse(
            message=f"我已经按「{job_title}」生成并保存了 JD，同时生成了简历评分标准。你可以继续让我筛选简历、生成面试题或修改 JD。",
            intent="jd",
            route=route,
            steps=steps,
            artifacts=artifacts,
            suggestions=[
                "筛选这个 JD 的简历",
                "基于 JD 生成面试题",
                "继续修改 JD",
            ],
        )

    async def _stream_text(self, text: str) -> AsyncGenerator[str, None]:
        """把完整文本按小片段产出，模拟逐字流式。"""
        if not text:
            return
        for index in range(0, len(text), 6):
            yield text[index:index + 6]

    async def _stream_skill_draft_response(
        self,
        intent: str,
        message: str,
        user_id: UUID,
        conversation_id: Optional[str],
        route: Optional[str],
        memory_context: str,
        confirmed_requirements: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        bundle = self.skill_dispatcher.get_bundle(intent)
        selected_tool = self.tool_registry.get(intent)
        plan_response = AgentChatResponse(
            message="",
            intent=intent,
            route=route,
            steps=[
                self._planning_step(selected_tool, f"已选择 {bundle.bundle_name} skill，开始流式生成草稿。"),
                AgentStep(id="draft", title="生成邮件草稿", status="running", detail="正在逐步生成邮件草稿。", tool="draft"),
                AgentStep(id="confirm_send", title="等待人工确认", status="pending", detail="草稿生成后请确认收件人、主题和正文。"),
                AgentStep(id="send_email", title="提交邮件", status="pending", detail="确认后才会提交给 SMTP 服务器。", tool="send"),
            ],
            suggestions=[],
        )
        yield {"type": "plan", "response": plan_response.model_dump()}

        full_text = ""
        try:
            if self.llm_service is None:
                self.llm_service = LLMService()
            phase = bundle.get_phase("draft")
            # 读取SKILL.md工作流
            skill_markdown = phase.load_skill_instructions()
            # 构造草稿prompt
            prompt = self._build_skill_email_draft_prompt(message, memory_context, skill_markdown)
            async for delta in self.llm_service.stream_response(prompt):
                full_text += delta
                yield {"type": "delta", "delta": delta}
        except Exception as exc:
            logger.warning("Agent 邮件草稿真实流式生成失败，使用模板兜底: %s", exc)
            phase = bundle.get_phase("draft")
            fallback_result = await phase.run(
                {
                    "message": message,
                    "memory_context": memory_context,
                    "confirmed_requirements": confirmed_requirements or {},
                    "llm_service": self.llm_service,
                    "email_service": self.email_send_service,
                    "user_id": user_id,
                    "confirmation_action": bundle.metadata.confirmation_action,
                }
            )
            full_text = str(fallback_result.get("message") or "")
            async for delta in self._stream_text(full_text):
                yield {"type": "delta", "delta": delta}

        response = await self._handle_skill_intent(
            intent=intent,
            message=message,
            user_id=user_id,
            route=route,
            selected_tool=selected_tool,
            memory_context=memory_context,
            confirmed_requirements={
                **(confirmed_requirements or {}),
                "__draft_text": full_text.strip(),
            },
        )
        response = response.model_copy(update={"message": full_text.strip() or response.message})
        yield {"type": "final", "response": response.model_dump()}

    def _build_skill_email_draft_prompt(self, message: str, memory_context: str, skill_markdown: str) -> str:
        memory_block = f"历史上下文：\n{memory_context}\n" if memory_context else ""
        return (
            "你正在执行 hr-agent-email skill。请先遵循下面的 SKILL.md 工作流，再完成当前任务。\n\n"
            f"{skill_markdown}\n\n"
            "当前执行阶段：draft phase。\n"
            "请根据 skill 工作流生成一封中文候选人邮件草稿。\n"
            "要求：包含主题、称呼、正文、下一步动作、署名占位；如果关键信息缺失，用【待补充】标注，不要编造具体时间地点。\n"
            f"{memory_block}"
            f"用户需求：{message}"
        )

    async def _handle_skill_intent(
        self,
        intent: str,
        message: str,
        user_id: UUID,
        route: Optional[str],
        selected_tool: Optional[AgentToolSpec],
        memory_context: str,
        confirmed_requirements: Optional[Dict[str, Any]] = None,
    ) -> AgentChatResponse:
        # 根据intent获取skill资源
        bundle = self.skill_dispatcher.get_bundle(intent)
        phase_name = bundle.resolve_phase(confirmed_requirements)
        phase = bundle.get_phase(phase_name)
        result = await phase.run(
            {
                "message": message,
                "memory_context": memory_context,
                "confirmed_requirements": confirmed_requirements or {},
                "llm_service": self.llm_service,
                "email_service": self.email_send_service,
                "user_id": user_id,
                "confirmation_action": bundle.metadata.confirmation_action,
                "draft_text": (confirmed_requirements or {}).get("__draft_text"),
            }
        )
        return self._build_skill_response(
            bundle=bundle,
            result=result,
            route=route,
            selected_tool=selected_tool,
            phase_name=phase_name,
            confirmed_requirements=confirmed_requirements,
        )

    def _build_skill_response(
        self,
        bundle: AgentSkillBundle,
        result: Dict[str, Any],
        route: Optional[str],
        selected_tool: Optional[AgentToolSpec],
        phase_name: str,
        confirmed_requirements: Optional[Dict[str, Any]] = None,
    ) -> AgentChatResponse:
        raw_steps = result.get("steps") or []
        steps = [AgentStep.model_validate(step) for step in raw_steps]
        if steps and selected_tool:
            summary = (
                "用户已确认 skill 所需信息，开始执行下一阶段。"
                if confirmed_requirements
                else f"已选择 {bundle.bundle_name} skill，当前执行 {phase_name} 阶段。"
            )
            steps = [self._planning_step(selected_tool, summary), *steps]

        artifacts = [AgentArtifact.model_validate(artifact) for artifact in (result.get("artifacts") or [])]
        return AgentChatResponse(
            message=str(result.get("message") or ""),
            intent=bundle.intent,
            route=route,
            steps=steps,
            artifacts=artifacts,
            suggestions=[str(item) for item in (result.get("suggestions") or [])],
            requires_confirmation=bool(result.get("requires_confirmation")),
            missing_fields=[str(item) for item in (result.get("missing_fields") or [])],
        )

    def _stream_event(
        self,
        event_type: str,
        message: str,
        steps: List[AgentStep],
        artifacts: List[AgentArtifact],
    ) -> Dict[str, Any]:
        return {
            "type": event_type,
            "response": AgentChatResponse(
                message=message,
                intent="jd",
                route="/recruitment/jd-generator",
                steps=steps,
                artifacts=artifacts,
                suggestions=[],
            ).model_dump(),
        }

    def _format_resume_result_delta(self, result: Dict[str, Any], index: int, total: int) -> str:
        filename = result.get("filename") or "未知文件"
        name = result.get("name") or filename
        if result.get("status") == "failed":
            return f"{index}. {filename}：评分失败（{result.get('error') or '未知错误'}）\n\n"

        score = result.get("score") or 0
        position = result.get("position") or "未识别岗位"
        education = result.get("education") or "学历未识别"
        work_years = result.get("work_years")
        work_years_text = f"{work_years} 年经验" if work_years not in (None, "", 0) else "经验未识别"
        metrics = result.get("metrics") or []
        metric_summary = self._summarize_resume_metrics(metrics)

        lines = [
            f"{index}. {name}（{filename}）",
            f"- 综合评分：{score} 分",
            f"- 候选信息：{position}，{education}，{work_years_text}",
        ]
        if metric_summary:
            lines.append(f"- 评分摘要：{metric_summary}")
        lines.append("")
        return "\n".join(lines)

    def _summarize_resume_metrics(self, metrics: List[Dict[str, Any]]) -> str:
        if not metrics:
            return ""
        summaries = []
        for metric in metrics[:3]:
            name = metric.get("name") or "指标"
            score = metric.get("score")
            max_score = metric.get("max")
            reason = (metric.get("reason") or "").strip()
            score_text = f"{score}/{max_score}" if max_score is not None else str(score)
            summaries.append(f"{name} {score_text}" + (f"（{reason[:40]}）" if reason else ""))
        return "；".join(summaries)

    async def _generate_exam_content_stream(
        self,
        exam_service: ExamService,
        exam: Dict[str, Any],
        user_id: UUID,
        conversation_id: Optional[str],
    ) -> AsyncGenerator[str, None]:
        full_text = ""
        special_requirements = self._build_exam_special_requirements(exam)
        try:
            stream = await exam_service.generate_exam(
                title=exam["title"],
                subject=exam["subject"],
                total_score=exam["total_score"],
                user_id=str(user_id),
                description=exam.get("description"),
                difficulty=exam.get("difficulty"),
                duration=exam.get("duration"),
                question_types=exam.get("question_types"),
                question_counts=exam.get("question_counts"),
                knowledge_files=exam.get("knowledge_files"),
                special_requirements=special_requirements,
                conversation_id=None,
                stream=True,
            )
            async for chunk in stream:
                raw_delta = self._extract_stream_delta(self._normalize_sse_chunk(chunk))
                delta = self._dedupe_stream_delta(raw_delta, full_text)
                if not delta:
                    continue
                full_text += delta
                yield delta
        except Exception as exc:
            logger.warning("Agent 试卷流式生成失败，回退同步生成: %s", exc)

        if not full_text.strip():
            result = await exam_service.generate_exam(
                title=exam["title"],
                subject=exam["subject"],
                total_score=exam["total_score"],
                user_id=str(user_id),
                description=exam.get("description"),
                difficulty=exam.get("difficulty"),
                duration=exam.get("duration"),
                question_types=exam.get("question_types"),
                question_counts=exam.get("question_counts"),
                knowledge_files=exam.get("knowledge_files"),
                special_requirements=special_requirements,
                conversation_id=None,
                stream=False,
            )
            fallback = self._extract_answer(result).strip()
            async for delta in self._stream_text(fallback):
                yield delta

    async def _generate_missing_exam_questions(
        self,
        exam_service: ExamService,
        exam: Dict[str, Any],
        existing_content: str,
        user_id: UUID,
        conversation_id: Optional[str],
    ) -> str:
        missing_counts = self._missing_exam_question_counts(exam_service, exam, existing_content)
        if not any(missing_counts.values()):
            return ""

        logger.warning("试卷题量不足，尝试补齐缺失题目: %s", missing_counts)
        repair_exam = {
            **exam,
            "title": f"{exam.get('title') or '试卷'}补题",
            "question_counts": missing_counts,
            "question_types": [key for key, value in missing_counts.items() if value > 0],
            "total_score": sum(
                sum(scores)
                for scores in self._missing_exam_question_scores(exam, existing_content, missing_counts).values()
            ) or exam.get("total_score") or 100,
            "special_requirements": "\n".join([
                self._clean_optional_value(exam.get("special_requirements")) or "",
                "这是补题请求。只生成缺失题目，不要重复已生成题目。",
                "已生成题目如下，请避开相同题干和知识点：",
                existing_content[:3000],
            ]).strip(),
        }
        result = await exam_service.generate_exam(
            title=repair_exam["title"],
            subject=repair_exam["subject"],
            total_score=repair_exam["total_score"],
            user_id=str(user_id),
            description=repair_exam.get("description"),
            difficulty=repair_exam.get("difficulty"),
            duration=repair_exam.get("duration"),
            question_types=repair_exam.get("question_types"),
            question_counts=repair_exam.get("question_counts"),
            knowledge_files=repair_exam.get("knowledge_files"),
            special_requirements=repair_exam.get("special_requirements"),
            conversation_id=None,
            stream=False,
        )
        repair_content = self._extract_answer(result).strip()
        repair_questions = exam_service._parse_exam_content(repair_content)
        expected_repair_count = sum(missing_counts.values())
        if len(repair_questions) < expected_repair_count:
            logger.warning("试卷补题仍不足，期望 %s 题，实际 %s 题", expected_repair_count, len(repair_questions))
        return repair_content

    def _missing_exam_question_counts(
        self,
        exam_service: ExamService,
        exam: Dict[str, Any],
        content: str,
    ) -> Dict[str, int]:
        expected = {
            "single_choice": int((exam.get("question_counts") or {}).get("single_choice") or 0),
            "multiple_choice": int((exam.get("question_counts") or {}).get("multiple_choice") or 0),
            "short_answer": int((exam.get("question_counts") or {}).get("short_answer") or 0),
        }
        if not any(expected.values()):
            return {"single_choice": 0, "multiple_choice": 0, "short_answer": 0}

        actual = {"single_choice": 0, "multiple_choice": 0, "short_answer": 0}
        type_map = {
            "单选题": "single_choice",
            "单选": "single_choice",
            "多选题": "multiple_choice",
            "多选": "multiple_choice",
            "简答题": "short_answer",
            "简答": "short_answer",
        }
        for question in exam_service._parse_exam_content(content):
            key = type_map.get(str(question.get("type") or "").strip())
            if key:
                actual[key] += 1

        return {
            key: max(0, expected.get(key, 0) - actual.get(key, 0))
            for key in expected
        }

    def _missing_exam_question_scores(
        self,
        exam: Dict[str, Any],
        content: str,
        missing_counts: Dict[str, int],
    ) -> Dict[str, List[int]]:
        question_scores = ExamService(self.db)._allocate_question_scores(
            int(exam.get("total_score") or 100),
            exam.get("question_counts") or {},
        )
        return {
            key: values[-missing_counts[key]:] if missing_counts.get(key) else []
            for key, values in question_scores.items()
        }

    def _drain_exam_display_buffer(
        self,
        buffer: str,
        start_index: int,
        force: bool = False,
    ) -> tuple[str, str, int]:
        if not buffer:
            return "", "", start_index

        parts = buffer.split("***")
        if force:
            complete_parts = parts
            remaining = ""
        elif len(parts) <= 1:
            return "", buffer, start_index
        else:
            complete_parts = parts[:-1]
            remaining = parts[-1]

        markdown_parts: List[str] = []
        question_index = start_index
        for part in complete_parts:
            block = part.strip()
            if not block:
                continue
            markdown = self._format_exam_question_block(block, question_index)
            markdown_parts.append(markdown)
            question_index += 1

        return "".join(markdown_parts), remaining, question_index

    def _format_exam_question_block(self, block: str, question_index: int) -> str:
        parts = [part.strip() for part in block.split("|")]
        if len(parts) != 6:
            return f"{block}\n\n"

        question_text, question_type, options_text, correct_answers, score, explanation = parts
        question_type_label = {
            "single_choice": "单选题",
            "multiple_choice": "多选题",
            "short_answer": "简答题",
            "single": "单选题",
            "multiple": "多选题",
            "short": "简答题",
        }.get(question_type, question_type)
        lines = [
            f"### {question_index}. {question_type_label}（{score}分）",
            "",
            question_text,
        ]
        if options_text:
            option_items = [
                option.strip()
                for option in re.split(r"[;；]", options_text)
                if option.strip()
            ]
            if option_items:
                lines.extend(["", "**选项：**"])
                for option_index, option in enumerate(option_items):
                    label = chr(65 + option_index)
                    option_text = re.sub(r"^[A-ZＡ-Ｚ][\\.．、:：]\\s*", "", option)
                    lines.append(f"- {label}. {option_text}")

        lines.extend([
            "",
            f"**参考答案：** {correct_answers or '略'}",
            f"**解析：** {explanation or '略'}",
            "",
        ])
        return "\n".join(lines)

    async def _hydrate_exam_interview_context(
        self,
        exam: Dict[str, Any],
        user_id: UUID,
        conversation_id: Optional[str],
    ) -> Dict[str, Any]:
        if exam.get("interview_plan_context"):
            return exam
        text = " ".join([
            str(exam.get("special_requirements") or ""),
            str(exam.get("description") or ""),
            str(exam.get("title") or ""),
        ])
        if not self._is_followup_interview_exam_request(text):
            return exam
        context = await self._resolve_interview_exam_followup(text, user_id, conversation_id)
        if not context.get("matched"):
            return exam
        return {
            **exam,
            "interview_plan_context": context,
        }

    def _build_exam_special_requirements(self, exam: Dict[str, Any]) -> str:
        base_requirements = self._clean_optional_value(exam.get("special_requirements")) or ""
        context = exam.get("interview_plan_context") if isinstance(exam.get("interview_plan_context"), dict) else None
        if not context:
            return base_requirements

        context_text = self._clean_optional_value(context.get("content")) or ""
        context_title = self._clean_optional_value(context.get("title")) or "当前面试方案"
        parts = []
        if base_requirements:
            parts.append(base_requirements)
        parts.append(
            "请按 8:2 配比生成笔试试卷：约 80% 题目来自上传文档知识点，约 20% 题目来自面试方案中的能力验证点、风险点或追问方向。"
            "文档题要依据上传文档；面试方案导向题可以设计情境题或简答题，但要尽量结合文档业务背景。"
            "不要把面试流程、面试安排、候选人评价本身直接改写成题目。"
        )
        if context_text:
            parts.append(f"当前面试方案《{context_title}》（仅作为出题方向和权重参考，不作为题目事实来源）：\n{context_text[:1500]}")
        return "\n\n".join(parts)

    def _tool_stream_event(
        self,
        event_type: str,
        message: str,
        intent: str,
        route: str,
        steps: List[AgentStep],
        artifacts: List[AgentArtifact],
    ) -> Dict[str, Any]:
        return {
            "type": event_type,
            "response": AgentChatResponse(
                message=message,
                intent=intent,
                route=route,
                steps=steps,
                artifacts=artifacts,
                suggestions=[],
            ).model_dump(),
        }

    def _resume_stream_event(
        self,
        event_type: str,
        message: str,
        steps: List[AgentStep],
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "type": event_type,
            "response": AgentChatResponse(
                message=message,
                intent="resume_screening",
                route="/recruitment/resume-screening",
                steps=steps,
                artifacts=[
                    AgentArtifact(
                        type="resume_screening_results",
                        title="批量简历筛选结果",
                        content=results,
                    )
                ] if results else [],
                suggestions=[],
            ).model_dump(),
        }

    def _normalize_memory_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        normalized = re.sub(r"\s+", " ", str(text)).strip()
        return normalized

    def _format_memory_for_prompt(self, memory_context: str) -> str:
        if not memory_context:
            return ""
        return (
            "历史对话记忆（仅用于理解上下文和指代，不要逐字复述）：\n"
            f"{memory_context}\n\n"
        )

    def _build_memory_augmented_prompt(self, message: str, memory_context: str) -> str:
        if not memory_context:
            return message
        return (
            "请结合以下历史对话记忆回答当前用户消息。"
            "如果用户使用“继续、这个、刚才、上一个”等指代，请从历史中解析；"
            "如果历史无关，不要强行引用。\n\n"
            f"{self._format_memory_for_prompt(memory_context)}"
            f"当前用户消息：{message}"
        )

    async def _resolve_interview_candidate(
        self,
        message: str,
        user_id: UUID,
        memory_context: str = "",
    ) -> Dict[str, Any]:
        candidates = await self._recent_resume_candidates(user_id)
        candidate_text = "\n".join(
            (
                f"- id={item['id']}；姓名={item['name'] or '未提取'}；"
                f"文件={item['filename']}；岗位={item['position'] or '未提及'}；"
                f"分数={item['score'] if item['score'] is not None else '未评分'}"
            )
            for item in candidates
        ) or "无已评分候选人"
        prompt = (
            "你是 HR Agent 的候选人解析器。请判断用户是否指定了要生成面试计划的候选人，"
            "并在已评分候选人列表中匹配。只返回 JSON，不要解释。\n\n"
            "规则：\n"
            "1. 如果用户没有明确候选人姓名/文件名/“他、这位、刚才那位”等指代，返回 status=no_specific。\n"
            "2. 如果用户指定了候选人，并且候选人列表里唯一匹配，返回 status=matched 和 candidate_id。\n"
            "3. 如果用户指定了候选人，但候选人列表没有匹配，返回 status=no_match，并在 reply 中说明未找到该候选人，提醒上传他的简历并先评分。\n"
            "4. 如果匹配多个候选人，返回 status=ambiguous，并给出 candidates。\n"
            "5. reply 要自然、简洁，不能假装已找到不存在的候选人。\n\n"
            "返回 JSON 字段：\n"
            "{\n"
            "  \"status\": \"no_specific/matched/no_match/ambiguous\",\n"
            "  \"requested_name\": \"用户指定的人名或null\",\n"
            "  \"candidate_id\": \"匹配到的id或null\",\n"
            "  \"candidate_name\": \"匹配到的姓名或null\",\n"
            "  \"candidates\": [],\n"
            "  \"reply\": \"给用户的自然回复或null\"\n"
            "}\n\n"
            f"{self._format_memory_for_prompt(memory_context)}"
            f"当前用户消息：{message}\n\n"
            f"已评分候选人列表：\n{candidate_text}"
        )
        try:
            if self.llm_service is None:
                self.llm_service = LLMService()
            response = await self.llm_service.generate_response(prompt)
            parsed = self._safe_json_loads(response)
            return self._normalize_candidate_resolution(parsed, candidates, message)
        except Exception as exc:
            logger.warning("解析面试计划候选人失败，使用本地规则兜底: %s", exc)
            return self._fallback_candidate_resolution(message, candidates)

    async def _recent_resume_candidates(self, user_id: UUID, limit: int = 50) -> List[Dict[str, Any]]:
        result = await self.db.execute(
            select(ResumeEvaluation)
            .where(ResumeEvaluation.user_id == user_id)
            .order_by(ResumeEvaluation.created_at.desc())
            .limit(limit)
        )
        candidates = []
        for resume in result.scalars().all():
            candidates.append({
                "id": str(resume.id),
                "name": resume.candidate_name,
                "filename": resume.original_filename,
                "position": resume.candidate_position,
                "score": resume.total_score,
            })
        return candidates

    def _normalize_candidate_resolution(
        self,
        parsed: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        message: str,
    ) -> Dict[str, Any]:
        status = str(parsed.get("status") or "").strip().lower()
        candidate_id = self._clean_optional_value(parsed.get("candidate_id"))
        candidate_lookup = {item["id"]: item for item in candidates}
        if candidate_id and candidate_id in candidate_lookup:
            matched = candidate_lookup[candidate_id]
            return {
                "status": "matched",
                "candidate_id": candidate_id,
                "candidate_name": matched.get("name") or matched.get("filename"),
                "requested_name": self._clean_optional_value(parsed.get("requested_name")),
                "reply": self._clean_optional_value(parsed.get("reply")),
            }
        if status in {"no_match", "ambiguous", "no_specific"}:
            return {
                "status": status,
                "requested_name": self._clean_optional_value(parsed.get("requested_name")),
                "reply": self._clean_optional_value(parsed.get("reply")),
                "candidates": parsed.get("candidates") if isinstance(parsed.get("candidates"), list) else [],
            }
        return self._fallback_candidate_resolution(message, candidates)

    def _fallback_candidate_resolution(self, message: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_message = self._normalize_candidate_match_text(message)
        matches = [
            item for item in candidates
            if any(
                name and (name in normalized_message or normalized_message in name)
                for name in [
                    self._normalize_candidate_match_text(item.get("name")),
                    self._normalize_candidate_match_text(item.get("filename")),
                ]
            )
        ]
        if len(matches) == 1:
            return {
                "status": "matched",
                "candidate_id": matches[0]["id"],
                "candidate_name": matches[0].get("name") or matches[0].get("filename"),
            }
        if len(matches) > 1:
            return {"status": "ambiguous", "candidates": matches[:5]}
        has_specific_name = bool(re.search(r"生成(.{1,20}?)(?:的)?面试|(.{1,20}?)(?:的)?面试(?:计划|方案)", message))
        return {"status": "no_match" if has_specific_name else "no_specific", "requested_name": None}

    def _normalize_candidate_match_text(self, text: Optional[str]) -> str:
        return re.sub(r"[\s_\-()[\]【】（）.。·、,，]+", "", str(text or "").lower())

    def _is_followup_resume_screening_loop_request(self, message: str) -> bool:
        return bool(
            re.search(r"高分|通过|合格|大于\s*60|超过\s*60|60\s*分以上|分数高|低分|不合格|小于\s*60|低于\s*60", message)
            and re.search(r"面试|方案|计划|删除|淘汰|候选人|简历", message)
        )

    def _is_followup_interview_exam_request(self, message: str) -> bool:
        return bool(
            re.search(r"当前|这个|该|刚才|刚生成|上一个|面试方案|面试计划", message)
            and re.search(r"试卷|考试|笔试|出题|题目|测评", message)
        )

    def _build_resume_screening_loop_summary(
        self,
        results: List[Dict[str, Any]],
        threshold: int = 60,
    ) -> Dict[str, Any]:
        completed = [item for item in results if item.get("status") != "failed"]
        qualified = [item for item in completed if float(item.get("score") or 0) >= threshold]
        low_scores = [item for item in completed if float(item.get("score") or 0) < threshold]
        top_candidates = qualified[:3]

        message_parts = []
        if qualified:
            names = "、".join(self._resume_candidate_label(item) for item in top_candidates)
            message_parts.append(f"{len(qualified)} 位候选人达到 {threshold} 分及以上（{names}），建议进入面试计划阶段。")
        if low_scores:
            names = "、".join(self._resume_candidate_label(item) for item in low_scores[:3])
            message_parts.append(f"{len(low_scores)} 位候选人低于 {threshold} 分（{names}），建议标记淘汰或删除记录前先人工复核。")

        suggestions = []
        if qualified:
            suggestions.append("为高分候选人生成面试计划")
        if low_scores:
            suggestions.append("删除低分候选人的简历记录")
        suggestions.extend(["查看完整评分详情", "继续上传更多简历"])

        return {
            "threshold": threshold,
            "qualified_candidates": qualified,
            "low_score_candidates": low_scores,
            "message_suffix": ("\n\n下一步建议：" + " ".join(message_parts)) if message_parts else "",
            "suggestions": suggestions[:4],
        }

    def _resume_candidate_label(self, item: Dict[str, Any]) -> str:
        name = item.get("name") or item.get("filename") or "候选人"
        score = item.get("score")
        return f"{name} {score}分" if score is not None else str(name)

    async def _resolve_resume_screening_followup_action(
        self,
        message: str,
        user_id: UUID,
        conversation_id: Optional[str],
    ) -> Dict[str, Any]:
        if not self._is_followup_resume_screening_loop_request(message):
            return {"action": None}
        groups = await self._recent_resume_screening_groups(conversation_id, user_id, threshold=60)
        if not groups.get("has_context"):
            return {"action": "missing_context"}
        if re.search(r"删除|删掉|移除|清理|淘汰", message) and re.search(r"低分|不合格|小于\s*60|低于\s*60|没通过|未通过", message):
            return {"action": "confirm_delete_low_scores", **groups}
        if re.search(r"面试|方案|计划", message) and re.search(r"高分|通过|合格|大于\s*60|超过\s*60|60\s*分以上|分数高", message):
            return {"action": "generate_interview", **groups}
        return {"action": None}

    async def _recent_resume_screening_groups(
        self,
        conversation_id: Optional[str],
        user_id: UUID,
        threshold: int = 60,
    ) -> Dict[str, Any]:
        resources = await self._recent_generated_resources("resume", user_id, conversation_id, limit=20)
        candidate_ids = []
        for item in resources:
            if item.get("id") and item["id"] not in candidate_ids:
                candidate_ids.append(item["id"])

        if not candidate_ids:
            return {"has_context": False, "qualified_candidates": [], "low_score_candidates": []}

        result = await self.db.execute(
            select(ResumeEvaluation).where(
                ResumeEvaluation.user_id == user_id,
                ResumeEvaluation.id.in_([UUID(item) for item in candidate_ids]),
            )
        )
        evaluations = list(result.scalars().all())
        order_map = {candidate_id: index for index, candidate_id in enumerate(candidate_ids)}
        evaluations.sort(key=lambda item: order_map.get(str(item.id), 999))

        qualified = []
        low_scores = []
        for evaluation in evaluations:
            item = self._resume_evaluation_to_candidate_dict(evaluation)
            if float(evaluation.total_score or 0) >= threshold:
                qualified.append(item)
            else:
                low_scores.append(item)
        return {
            "has_context": True,
            "threshold": threshold,
            "qualified_candidates": qualified,
            "low_score_candidates": low_scores,
        }

    def _resume_evaluation_to_candidate_dict(self, evaluation: ResumeEvaluation) -> Dict[str, Any]:
        return {
            "id": str(evaluation.id),
            "name": evaluation.candidate_name or evaluation.original_filename,
            "filename": evaluation.original_filename,
            "score": evaluation.total_score or 0,
            "position": evaluation.candidate_position,
            "education": evaluation.education_level,
            "status": evaluation.status.value if evaluation.status else None,
        }

    def _build_resume_screening_followup_response(
        self,
        action: Dict[str, Any],
        route: Optional[str],
        selected_tool: Optional[AgentToolSpec],
    ) -> AgentChatResponse:
        threshold = action.get("threshold") or 60
        qualified = action.get("qualified_candidates") or []
        low_scores = action.get("low_score_candidates") or []

        if action.get("action") == "generate_interview":
            if not qualified:
                return AgentChatResponse(
                    message=f"最近这批评分里没有达到 {threshold} 分及以上的候选人，我不建议直接生成面试计划。你可以重新评分、调整 JD，或指定某个候选人继续生成。",
                    intent="interview_plan",
                    route=route,
                    steps=[
                        self._planning_step(selected_tool, "识别到基于评分结果推进面试计划的请求。"),
                        AgentStep(id="check_scores", title="检查高分候选人", status="failed", detail=f"未找到 {threshold} 分及以上候选人。"),
                    ],
                    suggestions=["重新筛选简历", "指定候选人生成面试计划", "调整评分标准"],
                )
            if len(qualified) == 1:
                candidate = qualified[0]
                return AgentChatResponse(
                    message=f"最近评分结果里，{candidate['name']} 达到 {candidate['score']} 分，符合进入面试的阈值。我已准备好直接生成他的面试计划。",
                    intent="interview_plan",
                    route=route,
                    steps=[
                        self._planning_step(selected_tool, "用户要求为高分候选人生成面试计划。"),
                        AgentStep(id="select_resume", title="锁定高分候选人", status="completed", detail=self._resume_candidate_label(candidate)),
                        AgentStep(id="generate_plan", title="生成面试计划", status="running", detail="正在调用面试计划工具。", tool="generate_interview_plan"),
                    ],
                    artifacts=[
                        AgentArtifact(
                            type="interview_plan_execute",
                            title="直接生成面试计划",
                            content={"resume_evaluation_id": candidate["id"], "candidate_name": candidate["name"]},
                        )
                    ],
                    suggestions=["生成面试计划", "查看该候选人评分", "删除低分候选人"],
                )
            return AgentChatResponse(
                message=(
                    f"最近这批有 {len(qualified)} 位候选人达到 {threshold} 分及以上。为避免一次生成太多方案，"
                    "请先选择要推进的候选人；如果你明确说“全部生成”，我再逐个生成。"
                ),
                intent="interview_plan",
                route=route,
                steps=[
                    self._planning_step(selected_tool, "用户要求为高分候选人生成面试计划，但存在多个候选人。"),
                    AgentStep(id="select_resume", title="选择高分候选人", status="running", detail=f"候选人数量：{len(qualified)}"),
                    AgentStep(id="generate_plan", title="生成面试计划", status="pending", tool="generate_interview_plan"),
                ],
                artifacts=[
                    AgentArtifact(
                        type="interview_plan_request",
                        title="选择高分候选人生成面试计划",
                        content={"requires_resume_evaluation": True, "candidates": qualified},
                    )
                ],
                suggestions=[f"生成{qualified[0]['name']}的面试计划", "全部生成面试计划", "先查看评分详情"],
            )

        if action.get("action") == "confirm_delete_low_scores":
            if not low_scores:
                return AgentChatResponse(
                    message=f"最近这批评分里没有低于 {threshold} 分的候选人，暂时不需要删除低分简历记录。",
                    intent="resume_screening",
                    route="/recruitment/resume-screening",
                    steps=[
                        self._planning_step(self.tool_registry.get("resume_screening"), "识别到低分候选人处理请求。"),
                        AgentStep(id="check_scores", title="检查低分候选人", status="completed", detail="没有低分候选人。"),
                    ],
                    suggestions=["为高分候选人生成面试计划", "继续上传简历", "查看评分详情"],
                )
            names = "、".join(self._resume_candidate_label(item) for item in low_scores[:5])
            return AgentChatResponse(
                message=(
                    f"我找到了 {len(low_scores)} 位低于 {threshold} 分的候选人：{names}。"
                    "为避免误删，我不会自动删除；如果确认删除，请回复“确认删除这些低分候选人”。"
                ),
                intent="resource_delete",
                route="/recruitment/resume-screening",
                steps=[
                    self._planning_step(self.tool_registry.get("resource_delete"), "识别到低分候选人删除建议。"),
                    AgentStep(id="locate_resource", title="定位低分候选人", status="completed", detail=f"匹配到 {len(low_scores)} 位低分候选人。"),
                    AgentStep(id="delete_resource", title="等待确认删除", status="pending", detail="用户确认后再删除。"),
                ],
                artifacts=[
                    AgentArtifact(
                        type="delete_resource_candidates",
                        title="低分候选人待确认",
                        content={"resource_type": "resume", "keyword": "低分候选人", "candidates": low_scores},
                    )
                ],
                suggestions=["确认删除这些低分候选人", "暂不删除，查看评分详情", "为高分候选人生成面试计划"],
            )

        return AgentChatResponse(
            message="我还没有找到最近一轮简历评分结果。请先完成简历评分，再让我继续生成面试计划或处理低分候选人。",
            intent="resume_screening",
            route="/recruitment/resume-screening",
            steps=[self._planning_step(self.tool_registry.get("resume_screening"), "缺少可用于闭环推进的评分上下文。")],
            suggestions=["上传简历评分", "选择 JD 后开始评分", "查看历史评分"],
        )
