"""文件驱动流式的图执行节点（简历批量评分 / 面试方案 / 试卷生成）。

专用 HTTP 端点（/agent/resume-screen/stream 等）解析 FormData 后，以 preset_intent
直接把图路由到对应 exec 节点；文件与定位参数经 RunnableConfig["configurable"] 传入
（不进 checkpoint，避免大 payload 落库），节点内部复用既有流式生成器，事件经
stream writer 透传给 bridge.run_stream()。
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from langgraph.config import RunnableConfig

from app.agent.nodes.legacy import (
    _emit_generator,
    _respond_from_event,
    _service,
)


def _exec_params(config: RunnableConfig) -> Dict[str, Any]:
    return (config.get("configurable") or {}).get("preset_params") or {}


def _exec_files(config: RunnableConfig):
    return (config.get("configurable") or {}).get("files") or []


async def resume_exec_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    params = _exec_params(config)
    files = _exec_files(config)
    final_event = await _emit_generator(service.stream_resume_screening(
        user_id=config["configurable"]["user_id"],
        job_description_id=UUID(str(params["job_description_id"])),
        files=files,
        conversation_id=state.get("conversation_id"),
    ))
    return _respond_from_event(final_event)


async def interview_exec_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    params = _exec_params(config)
    final_event = await _emit_generator(service.stream_interview_plan(
        user_id=config["configurable"]["user_id"],
        resume_evaluation_id=UUID(str(params["resume_evaluation_id"])),
        conversation_id=state.get("conversation_id"),
    ))
    return _respond_from_event(final_event)


async def exam_exec_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    service = _service(config)
    params = _exec_params(config)
    files = _exec_files(config)
    generator = (
        service.stream_exam_generation_with_documents(
            user_id=config["configurable"]["user_id"],
            exam_requirements=params["exam_requirements"],
            files=files,
            conversation_id=state.get("conversation_id"),
        )
        if files
        else service.stream_exam_generation(
            user_id=config["configurable"]["user_id"],
            exam_requirements=params["exam_requirements"],
            conversation_id=state.get("conversation_id"),
        )
    )
    final_event = await _emit_generator(generator)
    return _respond_from_event(final_event)
