"""ReAct 路由器的只读资源查询工具。

只供 route_intent 的观察型路由使用：模型先查询"刚才那个/上次那个"指向的真实资源，
再输出结构化决策。这里不暴露任何写操作，删除/发送/落库仍由确定性子图执行。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 同一请求共享一个 AsyncSession，串行化工具内的查询，避免并发操作报错
_tool_lock = asyncio.Lock()

_RESOURCE_TYPES = ("jd", "criteria", "resume", "interview", "exam")


def _dump(data: Any, limit: int = 1200) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:limit]


def _context(config: RunnableConfig):
    configurable = config["configurable"]
    return (
        configurable["agent_service"],
        configurable["user_id"],
        configurable.get("conversation_id"),
    )


def _compact(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(item.get("id") or "")[:8],
        "name": str(item.get("name") or item.get("title") or "")[:80],
        "updated_at": str(item.get("updated_at") or item.get("created_at") or "")[:19],
    }


async def _search(service, resource_type: str, user_id, conversation_id, keyword: str) -> List[Dict[str, Any]]:
    if resource_type == "jd":
        return await service._resolve_recent_jd_candidates(user_id, conversation_id, keyword)
    if resource_type == "criteria":
        return await service._resolve_recent_criteria_candidates(user_id, conversation_id, keyword)

    recent = await service._recent_generated_resources(
        resource_type, user_id, conversation_id, limit=5
    )
    if recent:
        if keyword:
            return service._match_delete_resources(recent, keyword) or recent
        return recent

    saved = await service._list_deletable_resources(resource_type, user_id, keyword)
    if keyword and saved:
        matched = service._match_delete_resources(saved, keyword)
        return matched or saved
    return saved


@tool
async def search_resources(
    config: RunnableConfig,
    resource_type: Literal["jd", "criteria", "resume", "interview", "exam"],
    keyword: str = "",
) -> str:
    """查询当前用户/当前对话最近的资源，用于理解“刚才那个、上次那个、这个”等指代。

    资源类型：
    - jd: 岗位 JD
    - criteria: 评分标准
    - resume: 简历评分记录/候选人
    - interview: 面试方案
    - exam: 试卷

    keyword 可选，用于按名称/关键词缩小范围。返回紧凑列表（id 前 8 位、名称、更新时间），
    不返回正文。用户要求修改/删除时，先调用本工具确认目标，不要臆造名称或 ID。
    """
    service, user_id, conversation_id = _context(config)
    async with _tool_lock:
        items = await _search(service, resource_type, user_id, conversation_id, keyword)
    return _dump({
        "resource_type": resource_type,
        "keyword": keyword,
        "items": [_compact(item) for item in (items or [])[:5]],
    })


ROUTER_TOOLS = [search_resources]
