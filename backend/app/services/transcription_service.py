"""面试材料转写：音视频走 DashScope 实时语音识别，文档直接抽取文本。"""
import asyncio
import logging
import mimetypes
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback

from app.core.config import settings
from app.utils.text_utils import extract_text_content

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".amr", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}

DOCUMENT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class TranscriptionError(Exception):
    """转写失败。"""


class _CollectCallback(RecognitionCallback):
    """收集识别句子，记录错误。"""

    def __init__(self):
        self.sentences: List[Dict[str, Any]] = []
        self.error: str = ""

    def on_open(self):
        pass

    def on_event(self, result):
        try:
            sentence = result.get_sentence()
        except Exception:  # pragma: no cover - 第三方库异常兜底
            return
        if not isinstance(sentence, dict):
            return
        if sentence.get("sentence_end") is False:
            return
        if sentence.get("text"):
            self.sentences.append(sentence)

    def on_complete(self):
        pass

    def on_error(self, result):
        try:
            self.error = str(result)
        except Exception:  # pragma: no cover
            self.error = "语音识别失败"

    def on_close(self):
        pass


def detect_media_type(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    raise TranscriptionError(f"不支持的文件类型: {ext or filename}")


def _extract_audio(source_path: str) -> str:
    """用 ffmpeg 抽取 16k 单声道 WAV。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TranscriptionError("服务器未安装 ffmpeg，无法处理音视频")

    fd, wav_path = tempfile.mkstemp(prefix="interview_", suffix=".wav")
    os.close(fd)
    command = [
        ffmpeg,
        "-y",
        "-i",
        source_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        wav_path,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        os.path.exists(wav_path) and os.remove(wav_path)
        raise TranscriptionError("ffmpeg 处理超时") from exc
    if completed.returncode != 0:
        if os.path.exists(wav_path):
            os.remove(wav_path)
        raise TranscriptionError(f"ffmpeg 提取音轨失败: {completed.stderr[-500:]}")
    return wav_path


def _transcribe_audio(wav_path: str) -> Dict[str, Any]:
    if not settings.LLM_API_KEY:
        raise TranscriptionError("未配置 LLM_API_KEY，无法调用语音识别")

    dashscope.api_key = settings.LLM_API_KEY
    callback = _CollectCallback()
    recognition = Recognition(
        model=settings.DASHSCOPE_ASR_MODEL,
        callback=callback,
        format="wav",
        sample_rate=16000,
    )
    result = recognition.call(wav_path, diarization_enabled=True)
    if callback.error:
        raise TranscriptionError(f"语音识别失败: {callback.error}")

    sentences = callback.sentences
    if not sentences:
        # 同步 call() 的返回值 get_sentence() 可能是句子列表（也可能单条）
        sentence = result.get_sentence() if result else None
        if isinstance(sentence, dict):
            sentences = [sentence]
        elif isinstance(sentence, list):
            sentences = [item for item in sentence if isinstance(item, dict)]
        sentences = [item for item in sentences if item.get("text")]
    if not sentences:
        raise TranscriptionError("语音识别未返回内容")

    lines: List[str] = []
    meta_sentences: List[Dict[str, Any]] = []
    for item in sentences:
        speaker = item.get("speaker_name") or item.get("speaker_id")
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[说话人{speaker}] {text}" if speaker is not None else text)
        # 不保存词级 words，避免长面试的 transcript_meta 过大
        meta_sentences.append({
            "begin_time": item.get("begin_time"),
            "end_time": item.get("end_time"),
            "speaker": speaker,
            "text": text,
        })

    return {"text": "\n".join(lines), "meta": {"sentences": meta_sentences}}


async def transcribe_media(file_path: str, filename: str, media_type: str) -> Dict[str, Any]:
    """转写面试材料，返回 {"text", "meta", "media_type"}。"""
    if media_type == "document":
        ext = os.path.splitext(filename)[1].lower()
        mime_type = DOCUMENT_MIME_TYPES.get(ext) or mimetypes.guess_type(filename)[0] or "text/plain"
        text = await extract_text_content(file_path, mime_type)
        if not text or not text.strip():
            raise TranscriptionError("文档未提取到文本内容")
        return {"text": text.strip(), "meta": {"source": "document"}, "media_type": "document"}

    wav_path = await asyncio.to_thread(_extract_audio, file_path)
    try:
        result = await asyncio.to_thread(_transcribe_audio, wav_path)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
    result["media_type"] = media_type
    return result
