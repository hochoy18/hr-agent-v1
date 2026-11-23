"""_emit_generator 单元测试：非 final 事件透传给 stream writer，final 事件作为返回值。

get_stream_writer() 依赖 LangGraph 运行时上下文（图外调用会抛 RuntimeError），
单测里用 monkeypatch 替换这个唯一边界，被测函数本身走真实代码。

运行：cd backend && .venv/bin/python -m pytest tests/test_emit_generator.py -v
"""
import pytest

from app.agent.nodes import legacy


async def _agen(events):
    """把事件列表包成异步生成器，模拟旧流式链路（progress/delta/final）。"""
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_final_returned_and_others_forwarded(monkeypatch):
    sent = []
    monkeypatch.setattr(legacy, "get_stream_writer", lambda: sent.append)

    progress = {"type": "progress", "step": "parse"}
    delta = {"type": "delta", "delta": "你好"}
    final = {"type": "final", "response": {"message": "你好", "intent": "general"}}

    result = await legacy._emit_generator(_agen([progress, delta, final]))

    assert result is final                      # final 事件被返回
    assert sent == [                            # 非 final 事件按 {"agent_event": ...} 透传
        {"agent_event": progress},
        {"agent_event": delta},
    ]


@pytest.mark.asyncio
async def test_no_final_returns_none(monkeypatch):
    sent = []
    monkeypatch.setattr(legacy, "get_stream_writer", lambda: sent.append)

    events = [{"type": "progress"}, {"type": "delta", "delta": "部分输出"}]
    result = await legacy._emit_generator(_agen(events))

    assert result is None                       # 没有 final → 返回 None
    assert len(sent) == 2                       # 所有事件都透传


@pytest.mark.asyncio
async def test_writer_unavailable_still_returns_final(monkeypatch):
    monkeypatch.setattr(legacy, "get_stream_writer", lambda: None)

    final = {"type": "final", "response": {"message": "ok"}}
    result = await legacy._emit_generator(_agen([{"type": "delta"}, final]))

    assert result is final                      # writer 缺失不报错，final 照常返回
