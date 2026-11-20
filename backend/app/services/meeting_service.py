"""腾讯会议 MCP 服务封装。

个人版账号无法调用开放平台 REST API（/v1/meetings），因此走腾讯会议云端 MCP：
JSON-RPC 2.0 -> https://mcp.meeting.tencent.com/mcp/wemeet-open/v1

MCP 返回结构（两层 JSON 字符串）：
    result.content[0].text = '{"_meta": {...}, "data": {"status_code": 200, "body": "{...}"}}'
本模块负责解包并暴露 create_meeting / cancel_meeting / get_meeting。
"""
import json
import logging
import platform
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.schemas.meeting import MeetingCreateRequest, MeetingInfo

logger = logging.getLogger(__name__)

# 额度熔断：命中 500246（MCP 使用次数上限）后，短时间内直接短路所有调用，
# 避免每次点按钮都白打一次 HTTP、刷满日志
_QUOTA_BLOCK_SECONDS = 300
_quota_blocked_until = 0.0

# get_meeting 短期缓存：一次列表同步里 N 条记录、反复打开修改弹窗时避免重复请求
_MEETING_CACHE_TTL = 60
_MEETING_CACHE_MAX = 256
_meeting_cache: Dict[str, "tuple[float, Dict[str, Any]]"] = {}


class MeetingServiceError(Exception):
    """腾讯会议调用失败。status_code 用于映射 HTTP 响应。"""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _client_info() -> Dict[str, str]:
    return {
        "os": platform.system() or "Linux",
        "agent": "HR Agent",
        "model": settings.LLM_MODEL,
    }


def _quota_blocked() -> bool:
    return time.monotonic() < _quota_blocked_until


def _block_quota(seconds: int = _QUOTA_BLOCK_SECONDS) -> None:
    global _quota_blocked_until
    _quota_blocked_until = time.monotonic() + seconds
    logger.warning("腾讯会议 MCP 额度耗尽，%s 秒内不再发起调用", seconds)


def _cache_get(meeting_id: str) -> Optional[Dict[str, Any]]:
    entry = _meeting_cache.get(meeting_id)
    if not entry:
        return None
    cached_at, body = entry
    if time.monotonic() - cached_at > _MEETING_CACHE_TTL:
        _meeting_cache.pop(meeting_id, None)
        return None
    return body


def _cache_put(meeting_id: str, body: Dict[str, Any]) -> None:
    if len(_meeting_cache) >= _MEETING_CACHE_MAX:
        oldest = min(_meeting_cache.items(), key=lambda kv: kv[1][0])[0]
        _meeting_cache.pop(oldest, None)
    _meeting_cache[meeting_id] = (time.monotonic(), body)


def invalidate_meeting_cache(meeting_id: Optional[str] = None) -> None:
    """本地改过会议（修改/取消）后调用，避免读到旧缓存。"""
    if meeting_id:
        _meeting_cache.pop(str(meeting_id), None)
    else:
        _meeting_cache.clear()


def _extract_error(body: Any) -> tuple[Optional[int], str]:
    """从腾讯接口 body 里取出 error_code / message，取不到就回落成截断原文。

    兼容三种形态：body 是 JSON 字符串、body 是 dict、body 是纯文本。
    错误字段名在不同接口里有 error_info / error_info.error_code / error 多种写法。
    """
    if isinstance(body, str):
        text = body.strip()
        try:
            body = json.loads(text) if text else {}
        except ValueError:
            return None, text[:300]
    if not isinstance(body, dict):
        return None, str(body)[:300]

    info = body.get("error_info") or body.get("error") or {}
    if isinstance(info, dict):
        raw_code = info.get("new_error_code") or info.get("error_code") or info.get("code")
        message = (
            info.get("new_error_message")
            or info.get("message")
            or info.get("err_msg")
            or json.dumps(info, ensure_ascii=False)[:300]
        )
        code: Optional[int]
        try:
            code = int(raw_code) if raw_code is not None else None
        except (TypeError, ValueError):
            code = None
        return code, str(message)
    if info:
        return None, str(info)[:300]

    raw = json.dumps(body, ensure_ascii=False)
    return None, raw[:300]


# 常见业务错误码的处置建议，直接拼到异常信息里，避免前端只看到一串 JSON
_ERROR_ADVICE: Dict[int, str] = {
    500246: "（腾讯会议 MCP 使用次数已达上限，需在腾讯会议侧升级套餐或更换 Token）",
    500245: "（腾讯会议 MCP 调用频率超限，稍后重试）",
    190200: "（Token 失效或权限不足，请重新获取 TENCENT_MEETING_TOKEN）",
}


class MeetingService:
    """腾讯会议 MCP 客户端（无状态，每次请求重新建立 JSON-RPC 调用）。"""

    def __init__(
        self,
        token: Optional[str] = None,
        mcp_url: Optional[str] = None,
        skill_version: Optional[str] = None,
    ):
        self.token = token or settings.TENCENT_MEETING_TOKEN
        self.mcp_url = mcp_url or settings.TENCENT_MEETING_MCP_URL
        self.skill_version = skill_version or settings.TENCENT_MEETING_SKILL_VERSION

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def _token_hint(self) -> str:
        """Token 指纹（前 8 位），用于排查"改了 .env 没重启、进程仍在用旧 Token"的问题。"""
        return f"{self.token[:8]}…" if self.token else "未配置"

    async def _call_tool(self, name: str, arguments: Dict[str, Any], request_id: int = 1) -> Dict[str, Any]:
        if not self.token:
            raise MeetingServiceError("未配置 TENCENT_MEETING_TOKEN", status_code=503)
        if _quota_blocked():
            raise MeetingServiceError(
                "腾讯会议 MCP 使用次数已达上限，已暂停调用（约 5 分钟后自动重试）",
                status_code=429,
            )

        logger.info("腾讯会议 MCP 调用 tool=%s token=%s", name, self._token_hint)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": {"_client_info": _client_info(), **arguments}},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Tencent-Meeting-Token": self.token,
            "X-Skill-Version": self.skill_version,
        }

        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                response = await client.post(self.mcp_url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            logger.error("腾讯会议 MCP 请求失败: %s", exc)
            raise MeetingServiceError(f"腾讯会议 MCP 请求失败: {exc}", status_code=502) from exc

        if response.status_code != 200:
            raise MeetingServiceError(
                f"腾讯会议 MCP 返回 HTTP {response.status_code} (token={self._token_hint}): {response.text[:300]}",
                status_code=502,
            )

        try:
            envelope = response.json()
        except ValueError as exc:
            raise MeetingServiceError(f"腾讯会议 MCP 响应不是合法 JSON: {response.text[:300]}") from exc

        if envelope.get("error"):
            error = envelope["error"]
            raise MeetingServiceError(
                f"腾讯会议 MCP 错误: {error.get('message') or error}", status_code=502
            )

        body = self._unwrap(envelope.get("result"))
        if body is None:
            raise MeetingServiceError("腾讯会议 MCP 响应缺少 result")

        # 业务错误一般放在 body.error_info / body.error
        error_info = body.get("error_info") if isinstance(body, dict) else None
        if error_info or (isinstance(body, dict) and body.get("error")):
            code, message = _extract_error(body)
            hint = f" [error_code={code}]" if code is not None else ""
            advice = _ERROR_ADVICE.get(code or 0, "")
            raise MeetingServiceError(f"腾讯会议业务错误{hint}: {message}{advice}", status_code=502)
        return body

    def _unwrap(self, result: Any) -> Optional[Dict[str, Any]]:
        """展开 MCP result -> data -> body，返回业务 JSON。"""
        if not isinstance(result, dict):
            return None

        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict)]
            code, message = _extract_error(" ".join(texts))
            hint = f" [error_code={code}]" if code is not None else ""
            advice = _ERROR_ADVICE.get(code or 0, "")
            raise MeetingServiceError(
                f"腾讯会议工具调用失败{hint}: {message}{advice}", status_code=502
            )

        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured

        text = ""
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text") or ""
                break
        if not text:
            return None

        try:
            outer = json.loads(text)
        except ValueError:
            return {"text": text}

        if not isinstance(outer, dict):
            return {"text": str(outer)}

        # 兼容两种返回：{"data": {"status_code", "body"}} 或直接 {"status_code", "body"}
        data = outer.get("data") if isinstance(outer.get("data"), dict) else outer

        status = data.get("status_code")
        if status is not None and int(status) != 200:
            code, message = _extract_error(data.get("body"))
            if code == 500246:
                _block_quota()
            hint = f" [error_code={code}]" if code is not None else ""
            advice = _ERROR_ADVICE.get(code or 0, "")
            raise MeetingServiceError(
                f"腾讯会议接口返回 status_code={status}{hint}: {message}{advice}"
                f" (token={self._token_hint})",
                status_code=429 if code == 500246 else 502,
            )

        inner = data.get("body")
        if isinstance(inner, str):
            try:
                return json.loads(inner) if inner.strip() else {}
            except ValueError:
                return {"text": inner}
        if isinstance(inner, dict):
            return inner
        return data

    async def create_meeting(self, request: MeetingCreateRequest) -> List[MeetingInfo]:
        args: Dict[str, Any] = {
            "subject": request.subject,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "time_zone": request.time_zone,
            "auto_in_waiting_room": request.auto_in_waiting_room,
        }
        if request.password:
            args["password"] = request.password
        if request.auto_record_type:
            args["auto_record_type"] = request.auto_record_type
        if request.auto_asr is not None:
            args["auto_asr"] = request.auto_asr
        if request.only_user_join_type:
            args["only_user_join_type"] = request.only_user_join_type
        if request.invitees:
            args["invitees"] = request.invitees

        body = await self._call_tool("schedule_meeting", args)
        meetings = []
        for item in body.get("meeting_info_list") or []:
            meetings.append(
                MeetingInfo(
                    meeting_id=str(item.get("meeting_id", "")),
                    meeting_code=str(item.get("meeting_code", "") or ""),
                    join_url=item.get("join_url", "") or "",
                    subject=item.get("subject", "") or "",
                    start_time=str(item.get("start_time", "") or ""),
                    end_time=str(item.get("end_time", "") or ""),
                    password=item.get("password"),
                    raw=item,
                )
            )
        if not meetings:
            raise MeetingServiceError("腾讯会议未返回会议信息")
        return meetings

    async def cancel_meeting(self, meeting_id: str) -> Dict[str, Any]:
        body = await self._call_tool(
            "cancel_meeting", {"meeting_id": meeting_id, "is_compact": True}, request_id=2
        )
        invalidate_meeting_cache(meeting_id)
        return body

    async def get_meeting(self, meeting_id: str) -> Dict[str, Any]:
        key = str(meeting_id)
        cached = _cache_get(key)
        if cached is not None:
            return cached
        body = await self._call_tool(
            "get_meeting", {"meeting_id": key, "is_compact": True}, request_id=3
        )
        if isinstance(body, dict):
            _cache_put(key, body)
        return body

    async def update_meeting(self, meeting_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """修改已创建的会议（主题、起止时间、密码、等候室等）。"""
        arguments = {"meeting_id": str(meeting_id), **updates}
        body = await self._call_tool("update_meeting", arguments, request_id=7)
        invalidate_meeting_cache(meeting_id)
        return body

    async def call_tool(self, name: str, arguments: Dict[str, Any], request_id: int = 4) -> Dict[str, Any]:
        """调用任意 MCP 工具（供面试录制/转写等场景复用）。"""
        return await self._call_tool(name, arguments, request_id=request_id)

    async def search_records(
        self,
        meeting_id: Optional[str] = None,
        meeting_code: Optional[str] = None,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """按会议ID/会议号搜索录制文件。"""
        args: Dict[str, Any] = {"page_size": page_size, "is_compact": True}
        if meeting_id:
            args["meeting_id"] = str(meeting_id)
        if meeting_code:
            args["meeting_code"] = meeting_code
        return await self.call_tool("search_records", args, request_id=5)

    async def get_transcript(
        self,
        record_file_id: Optional[str] = None,
        meeting_id: Optional[str] = None,
        meeting_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取录制转写文本。

        未指定 record_file_id 时先按会议搜索录制，再取第一条可用的 record_file_id。
        返回 {"text": str, "record_file_id": str, "sentences": list}。
        """
        if not record_file_id:
            body = await self.search_records(meeting_id=meeting_id, meeting_code=meeting_code)
            records = body.get("records") or body.get("record_list") or []
            for item in records:
                if not isinstance(item, dict):
                    continue
                record_file_id = str(
                    item.get("record_file_id")
                    or (item.get("record_file") or {}).get("record_file_id")
                    or ""
                )
                if record_file_id and record_file_id != "0":
                    break
            if not record_file_id:
                raise MeetingServiceError("未找到该会议的录制转写文件", status_code=404)

        body = await self.call_tool(
            "record_content",
            {"record_file_id": str(record_file_id), "action": "transcript", "lang": "default"},
            request_id=6,
        )
        text, sentences = _extract_transcript(body)
        if not text.strip():
            # 留下原始返回结构：区分"录制真没有逐字稿"与"返回结构变化导致提取失败"
            logger.warning(
                "腾讯会议录制转写为空 record_file_id=%s body=%s",
                record_file_id,
                json.dumps(body, ensure_ascii=False, default=str)[:800] if isinstance(body, dict) else str(body)[:800],
            )
            if _has_transcript_payload(body):
                raise MeetingServiceError("逐字稿已生成但内容为空，可能转写未完成，请稍后重试", status_code=404)
            raise MeetingServiceError("该会议录制中没有逐字稿（可能未开启转写）", status_code=404)
        return {"text": text.strip(), "record_file_id": str(record_file_id), "sentences": sentences}


def _has_transcript_payload(body: Any, depth: int = 0) -> bool:
    """返回结构里是否已经出现逐字稿容器，用来区分"没开转写"和"转写还没出内容"。"""
    if depth > 4 or not isinstance(body, dict):
        return False
    for key in ("paragraphs", "sentences", "sentence_list", "subtitles"):
        value = body.get(key)
        if isinstance(value, list) and value:
            return True
    for key in ("minutes", "record", "data", "result", "body"):
        nested = body.get(key)
        if isinstance(nested, dict) and _has_transcript_payload(nested, depth + 1):
            return True
    return False


def _speaker_of(item: Dict[str, Any]) -> str:
    """取说话人名称：腾讯会议在段落上给 speaker 对象，其他结构可能是字符串或平铺字段。"""
    speaker = item.get("speaker")
    if isinstance(speaker, dict):
        for key in ("user_name", "nickname", "name"):
            value = speaker.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        user_id = speaker.get("user_id")
        if user_id:
            return str(user_id)
        return ""
    if isinstance(speaker, str) and speaker.strip():
        return speaker.strip()
    for key in ("speaker_name", "speaker_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return ""


def _join_words(words: List[Any]) -> str:
    """把 word 级片段拼回文本：中文直接拼，英文单词之间补一个空格。"""
    text = ""
    for word in words:
        if not isinstance(word, dict):
            continue
        piece = word.get("text")
        if not isinstance(piece, str) or not piece:
            continue
        if text and text[-1].isascii() and text[-1].isalnum() and piece[0].isascii() and piece[0].isalnum():
            text += " "
        text += piece
    return text


def _unit_text(item: Dict[str, Any]) -> str:
    """取句子/段落正文：有的结构给 text，腾讯会议只给 words[]。"""
    for key in ("text", "content", "sentence", "transcript"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    words = item.get("words")
    if isinstance(words, list):
        return _join_words(words).strip()
    return ""


def _extract_transcript(body: Any, depth: int = 0) -> tuple[str, List[Dict[str, Any]]]:
    """从 record_content 返回中容错提取句子与文本。

    腾讯会议的实际结构是 {code, more, minutes: {paragraphs: [...]}}：说话人挂在段落上，
    文字落在 sentence.words[].text，段落本身没有 text。其余 key 为兼容历史/其他返回结构保留。
    """
    if depth > 4 or not isinstance(body, dict):
        return "", []

    # 逐层下探到真正带段落/句子的容器
    for key in ("minutes", "record", "data", "result"):
        nested = body.get(key)
        if isinstance(nested, dict):
            text, sentences = _extract_transcript(nested, depth + 1)
            if text:
                return text, sentences

    paragraphs = body.get("paragraphs")
    if isinstance(paragraphs, list) and paragraphs:
        lines: List[str] = []
        collected: List[Dict[str, Any]] = []
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                continue
            speaker = _speaker_of(paragraph)
            pieces: List[tuple] = []
            for sentence in paragraph.get("sentences") or []:
                if not isinstance(sentence, dict):
                    continue
                content = _unit_text(sentence)
                if not content:
                    continue
                # 说话人一般挂在段落上；段落没带时退回句子自己带的说话人
                sentence_speaker = speaker or _speaker_of(sentence)
                pieces.append((content, sentence_speaker))
                collected.append(
                    {
                        "speaker": sentence_speaker,
                        "text": content,
                        "start_time": sentence.get("start_time"),
                        "end_time": sentence.get("end_time"),
                    }
                )
            if not pieces:
                content = _unit_text(paragraph)
                if content:
                    pieces.append((content, speaker))
                    collected.append(
                        {
                            "speaker": speaker,
                            "text": content,
                            "start_time": paragraph.get("start_time"),
                            "end_time": paragraph.get("end_time"),
                        }
                    )
            if pieces and speaker:
                # 同一段落内是同一说话人，合并成一行，读起来更接近逐字稿
                lines.append(f"[{speaker}] {''.join(text for text, _ in pieces)}")
            else:
                # 段落缺说话人时逐句成行，避免不同说话人被并成一段
                for content, sentence_speaker in pieces:
                    lines.append(f"[{sentence_speaker}] {content}" if sentence_speaker else content)
        if lines:
            return "\n".join(lines), collected

    for key in ("sentences", "sentence_list", "subtitles", "items"):
        value = body.get(key)
        if isinstance(value, list) and value:
            lines = []
            collected = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                content = _unit_text(item)
                if not content:
                    continue
                speaker = _speaker_of(item)
                lines.append(f"[{speaker}] {content}" if speaker else content)
                collected.append(
                    {
                        "speaker": speaker,
                        "text": content,
                        "start_time": item.get("start_time"),
                        "end_time": item.get("end_time"),
                    }
                )
            if lines:
                return "\n".join(lines), collected

    # 纯文本字段兜底
    for key in ("transcript", "text", "content", "body"):
        value = body.get(key)
        if isinstance(value, str) and value.strip() and not value.startswith("{"):
            return value, []
        if isinstance(value, dict):
            text, sentences = _extract_transcript(value, depth + 1)
            if text:
                return text, sentences

    return "", []
