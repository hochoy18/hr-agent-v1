"""chat agent 的只读业务工具。

通过 RunnableConfig 注入本请求的 AgentService（内含 db）与 user_id，
让 create_agent 驱动的对话模型能查询用户真实数据，回答"我有哪些 JD/简历评分/面试方案/试卷"。
只读、低风险——删除、发送等动作不在 chat agent 能力内，仍由主图意图节点处理。
"""
import json
import logging
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.services.exam_service import ExamService
from app.services.interview_plan_service import InterviewPlanService
from app.services.job_description_service import JobDescriptionService
from app.services.resume_evaluation_service import ResumeEvaluationService

logger = logging.getLogger(__name__)


def _dump(data: Any, limit: int = 1800) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:limit]


@tool
async def list_job_descriptions(config: RunnableConfig) -> str:
    """查询当前用户已生成的岗位 JD 列表（岗位名、地点、状态、创建时间，最多 10 条）。

    当用户询问"我有哪些 JD / 职位 / 岗位描述"时调用此工具。
    """
    service = config["configurable"]["agent_service"]
    user_id = config["configurable"]["user_id"]
    data = await JobDescriptionService(service.db).list_job_descriptions(user_id=user_id, page=1, size=10)
    return _dump(data)


@tool
async def list_resume_evaluations(config: RunnableConfig) -> str:
    """查询当前用户最近的简历评分记录（候选人、岗位、总分、状态，最多 10 条）。

    当用户询问"简历评分结果 / 候选人得分 / 评价历史"时调用此工具。
    """
    service = config["configurable"]["agent_service"]
    user_id = config["configurable"]["user_id"]
    items, total = await ResumeEvaluationService(service.db).get_evaluation_history(user_id=user_id, skip=0, limit=10)
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        rows.append({
            "id": str(getattr(item, "id", "")),
            "candidate_name": getattr(item, "candidate_name", None) or getattr(item, "filename", None) or "",
            "job_title": getattr(item, "job_title", None) or "",
            "score": getattr(item, "overall_score", None) or getattr(item, "score", None),
            "status": str(getattr(item, "status", "") or ""),
            "created_at": str(getattr(item, "created_at", "") or ""),
        })
    return _dump({"total": total, "items": rows})


@tool
async def list_interview_plans(config: RunnableConfig) -> str:
    """查询当前用户已生成的面试方案列表（候选人、岗位、创建时间，最多 10 条）。

    当用户询问"有哪些面试方案 / 面试计划"时调用此工具。
    """
    service = config["configurable"]["agent_service"]
    user_id = config["configurable"]["user_id"]
    data = await InterviewPlanService(service.db).list_interview_plans(user_id=user_id, page=1, size=10)
    return _dump(data)


@tool
async def list_exams(config: RunnableConfig) -> str:
    """查询试卷列表（标题、科目、题目数、创建时间，最多 10 条）。

    当用户询问"有哪些试卷 / 考试"时调用此工具。
    """
    service = config["configurable"]["agent_service"]
    data = await ExamService(service.db).get_exam_list(skip=0, limit=10)
    return _dump(data)


CHAT_TOOLS = [list_job_descriptions, list_resume_evaluations, list_interview_plans, list_exams]
