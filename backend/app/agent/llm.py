"""LangChain 聊天模型工厂：DashScope（OpenAI 兼容）端点的 ChatOpenAI。

进程内单例；未配置 LLM_API_KEY 时 chat_llm_available() 返回 False，
调用方（chat 节点）据此回退规则路径，不构造模型实例。
"""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_chat_model = None
_router_model = None

DASHSCOPE_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def chat_llm_available() -> bool:
    return bool(getattr(settings, "LLM_API_KEY", None))


def get_chat_model():
    global _chat_model
    if _chat_model is None:
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": settings.LLM_MODEL,
            "api_key": settings.LLM_API_KEY,
            "temperature": 0.7,
        }
        base_url = getattr(settings, "LLM_BASE_URL", None) or DASHSCOPE_COMPAT_BASE_URL
        kwargs["base_url"] = base_url
        _chat_model = ChatOpenAI(**kwargs)
        logger.info("ChatOpenAI 已初始化 model=%s base_url=%s", settings.LLM_MODEL, base_url)
    return _chat_model


def get_router_model():
    """路由专用模型：temperature=0、有超时和 token 上限，避免路由循环拖慢主链路。"""
    global _router_model
    if _router_model is None:
        from langchain_openai import ChatOpenAI

        model = settings.AGENT_ROUTER_MODEL or settings.LLM_MODEL
        kwargs = {
            "model": model,
            "api_key": settings.LLM_API_KEY,
            "temperature": 0.0,
            "request_timeout": settings.AGENT_ROUTER_TIMEOUT_SECONDS,
            "max_retries": 0,
            "max_tokens": settings.AGENT_ROUTER_MAX_TOKENS,
            "model_kwargs": {"parallel_tool_calls": False},
        }
        kwargs["base_url"] = getattr(settings, "LLM_BASE_URL", None) or DASHSCOPE_COMPAT_BASE_URL
        _router_model = ChatOpenAI(**kwargs)
        logger.info(
            "Router ChatOpenAI 已初始化 model=%s timeout=%ss max_tokens=%s",
            model,
            settings.AGENT_ROUTER_TIMEOUT_SECONDS,
            settings.AGENT_ROUTER_MAX_TOKENS,
        )
    return _router_model
