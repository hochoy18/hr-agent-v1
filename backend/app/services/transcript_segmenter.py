"""面试转写稿结构化：解析发言段、合并同一说话人的连续发言、渲染成轮次文本。

纯代码规则，不调用模型、不做角色判断：
1. parse_transcript 把转写文本拆成原始发言段（S1..Sn，各带说话人、时间戳、正文）；
2. merge_turns 把同一说话人连续出现的若干段合成一个发言轮次，段内保留每段原文；
3. render_turns 渲染成第二步问答配对的输入：轮次头带说话人与起始时间，段内只保留原文。

候选人身份由人工填写姓名（candidate_name）传入，resolve_candidate_speaker 只按名字
对转写里的说话人标签，对不上返回 None，不做推测。对不上时的模型兜底在调用方完成
（interview_service.infer_candidate_speaker），本模块只记录标签的来源。
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Tuple

UNKNOWN_SPEAKER = "未标注"

_TIME = r"\d{1,2}:\d{2}(?::\d{2})?"
_NAME_MAX = 20


def _valid_name(name: str) -> bool:
    """判断捕获到的一串字符能否当说话人名字用（排除句子、日期这类误命中）。"""
    text = name.strip()
    if not text or len(text) > _NAME_MAX:
        return False
    if re.search(r"[\s：:，,。.！!？?；;（）()\[\]【】“”\"'…—]", text):
        return False
    # 纯数字/日期串不是名字
    if re.fullmatch(r"[\d\-/:]+", text):
        return False
    return True


# 名字+括号时间戳：伍双林(00:00:07):  后面必须跟冒号或换行，避免误吃正文里的“（10:30）”
_RE_PAREN_TS = re.compile(
    rf"^(?P<speaker>.{{1,{_NAME_MAX + 4}}}?)\s*[（(](?P<ts>{_TIME})[)）]\s*(?:[：:]\s*(?P<rest>.*)|$)"
)
# 名字+日期时间：Jeff 2026-11-09 21:01:42（腾讯会议 docx 导出，头行独占一段，时间到行尾）
_RE_SPACE_DATE = re.compile(
    rf"^(?P<speaker>.{{1,{_NAME_MAX + 4}}}?)\s+(?P<ts>\d{{4}}-\d{{1,2}}-\d{{1,2}}\s+{_TIME})\s*$"
)
# 名字+纯时间：说话人1 00:00:07（无日期版本）
_RE_SPACE_TIME = re.compile(rf"^(?P<speaker>.{{1,{_NAME_MAX + 4}}}?)\s+(?P<ts>{_TIME})\s*$")
# [说话人0] 文本 / 【说话人0】文本（ASR 输出）
_RE_BRACKET = re.compile(rf"^[\[【](?P<speaker>[^\]】\n]{{1,{_NAME_MAX}}})[\]】]\s*[：:]?\s*(?P<rest>.*)$")
# 名字：文本（非贪婪，只吃到第一个冒号）
_RE_COLON = re.compile(rf"^(?P<speaker>[^\s：:（）()\[\]【】]{{1,{_NAME_MAX}}}?)\s*[：:]\s*(?P<rest>.*)$")
# 行首的独立时间戳，如 [00:00:07] 说话人0: 文本
_RE_LEAD_TS = re.compile(rf"^[\[【]\s*(?P<ts>{_TIME})\s*[\]】]\s*")

_ASR_SPEAKER = re.compile(r"^(?:说话人|说话者|speaker)\s*\d*$", re.IGNORECASE)
_ROLE_SPEAKER = re.compile(r"^(?:面试官|候选人|面试者|应聘者|考官|hr)\s*\d*$", re.IGNORECASE)

# 会议元信息、音效标记、分隔线、Markdown 标题，不参与发言归属
_META_PATTERNS = (
    re.compile(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?\s+\d{1,2}:\d{2}"),
    re.compile(r"^(?:会议主题|会议时间|会议号|会议密码|主持人|参会人|参会成员|录制文件|转写文件|智能纪要)\s*[：:]"),
    re.compile(r"^[\[(（【]\s*(?:音乐|掌声|笑声|静音|音频测试|无声|空白)\s*[\])）】]$"),
    re.compile(r"^\s*[-=_*~]{3,}\s*$"),
    re.compile(r"^#{1,6}\s+\S"),
)


@dataclass(frozen=True)
class Segment:
    """一段原始发言：转写里连续的一小段同一个人说的话。"""

    index: int
    speaker: str
    timestamp: str
    text: str


@dataclass
class Turn:
    """合并后的一轮发言：同一说话人连续说的若干段。"""

    index: int
    speaker: str
    segments: List[Segment] = field(default_factory=list)

    @property
    def start(self) -> str:
        return next((item.timestamp for item in self.segments if item.timestamp), "")

    @property
    def text(self) -> str:
        """本轮全部原文，段与段之间换行。"""
        return "\n".join(item.text for item in self.segments)

    @property
    def segment_indexes(self) -> List[int]:
        return [item.index for item in self.segments]


@dataclass
class SpeakerStat:
    speaker: str
    segment_count: int
    char_count: int


@dataclass
class Dialogue:
    """结构化后的整场对话。"""

    segments: List[Segment]
    turns: List[Turn]
    skipped: List[str] = field(default_factory=list)
    candidate_speaker: Optional[str] = None
    # 候选人标签的来源：manual（人工指定）/ name（姓名匹配）/ llm（模型兜底指认）/ 空（未定）
    candidate_source: str = ""
    candidate_confidence: str = ""
    candidate_evidence: str = ""

    @property
    def speakers(self) -> List[SpeakerStat]:
        return _speaker_stats(self.turns)

    @property
    def speaker_labels(self) -> List[str]:
        return [item.speaker for item in self.speakers]

    @property
    def is_structured(self) -> bool:
        """转写里是否认出了说话人；全未标注时下游只能按内容判断。"""
        return any(turn.speaker != UNKNOWN_SPEAKER for turn in self.turns)

    @property
    def text(self) -> str:
        return render_turns(self.turns)


def _speaker_key(name: str) -> str:
    """说话人标签的比对键：去掉空白与首尾标点后小写。"""
    text = re.sub(r"\s+", "", name or "")
    return text.strip("、,，.。:：;；").lower()


def _display_name(raw: str) -> str:
    return raw.strip().rstrip("、,，.。:：;；").strip()


def _is_meta_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in _META_PATTERNS)


def _collect_roster(lines: Sequence[str]) -> set:
    """先扫一遍强格式，得到说话人花名册；弱格式（纯冒号）靠它避免把正文当标题。"""
    roster = set()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        for pattern in (_RE_PAREN_TS, _RE_SPACE_DATE):
            match = pattern.match(line)
            if match and _valid_name(match.group("speaker")):
                roster.add(_speaker_key(match.group("speaker")))
        match = _RE_BRACKET.match(line)
        if match and _ASR_SPEAKER.match(match.group("speaker").strip()):
            roster.add(_speaker_key(match.group("speaker")))
    return roster


def _match_header(line: str, roster: set) -> Optional[Tuple[str, str, str]]:
    """识别说话人标题行，返回 (说话人, 时间戳, 行内剩余正文)。"""
    match = _RE_PAREN_TS.match(line)
    if match and _valid_name(match.group("speaker")):
        return (
            _display_name(match.group("speaker")),
            match.group("ts"),
            (match.group("rest") or "").strip(),
        )

    match = _RE_SPACE_DATE.match(line)
    if match and _valid_name(match.group("speaker")):
        stamp = match.group("ts")
        return _display_name(match.group("speaker")), stamp.split()[-1], ""

    match = _RE_BRACKET.match(line)
    if match:
        name = match.group("speaker").strip()
        if _ASR_SPEAKER.match(name) or _speaker_key(name) in roster:
            return _display_name(name), "", (match.group("rest") or "").strip()

    # 弱格式：有强格式时只认花名册里的名字，避免正文里的“他说：”被切成标题
    match = _RE_SPACE_TIME.match(line)
    if match and _valid_name(match.group("speaker")):
        key = _speaker_key(match.group("speaker"))
        if not roster or key in roster:
            return _display_name(match.group("speaker")), match.group("ts"), ""

    match = _RE_COLON.match(line)
    if match and _valid_name(match.group("speaker")):
        name = match.group("speaker").strip()
        key = _speaker_key(name)
        if not roster or key in roster or _ROLE_SPEAKER.match(name):
            return _display_name(name), "", (match.group("rest") or "").strip()
    return None


def _parse(text: str) -> Tuple[List[Segment], List[str]]:
    lines = (text or "").splitlines()
    roster = _collect_roster(lines)

    segments: List[Segment] = []
    skipped: List[str] = []
    state: Dict[str, object] = {"speaker": "", "timestamp": "", "buffer": []}

    def flush() -> None:
        body = "\n".join(state["buffer"]).strip()  # type: ignore[arg-type]
        state["buffer"] = []
        if not body:
            return
        speaker = state["speaker"] or UNKNOWN_SPEAKER  # type: ignore[assignment]
        segments.append(
            Segment(
                index=len(segments) + 1,
                speaker=speaker,
                timestamp=str(state["timestamp"] or ""),
                text=body,
            )
        )

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        if _is_meta_line(line):
            skipped.append(line)
            continue

        probe = line
        lead_ts = ""
        lead = _RE_LEAD_TS.match(probe)
        while lead:
            lead_ts = lead.group("ts")
            probe = probe[lead.end():]
            lead = _RE_LEAD_TS.match(probe)

        header = _match_header(probe.strip(), roster)
        if header:
            flush()
            speaker, timestamp, rest = header
            state["speaker"] = speaker
            state["timestamp"] = timestamp or lead_ts
            if rest:
                state["buffer"].append(rest)  # type: ignore[union-attr]
            continue

        state["buffer"].append(line)  # type: ignore[union-attr]
    flush()
    return segments, skipped


def parse_transcript(text: str) -> List[Segment]:
    """把转写文本拆成原始发言段，段号从 1 开始连续编号。"""
    return _parse(text)[0]


def merge_turns(segments: Sequence[Segment]) -> List[Turn]:
    """同一说话人连续出现的段合成一轮；中间夹了别人说话就另起一轮。"""
    turns: List[Turn] = []
    for segment in segments:
        if turns and _speaker_key(turns[-1].speaker) == _speaker_key(segment.speaker):
            turns[-1].segments.append(segment)
        else:
            turns.append(Turn(index=len(turns) + 1, speaker=segment.speaker, segments=[segment]))
    return turns


def _speaker_stats(turns: Sequence[Turn]) -> List[SpeakerStat]:
    stats: Dict[str, SpeakerStat] = {}
    order: List[str] = []
    for turn in turns:
        for segment in turn.segments:
            key = _speaker_key(segment.speaker)
            if key not in stats:
                stats[key] = SpeakerStat(speaker=segment.speaker, segment_count=0, char_count=0)
                order.append(key)
            stats[key].segment_count += 1
            stats[key].char_count += len(segment.text)
    return [stats[key] for key in order]


def resolve_candidate_speaker(
    speakers: Sequence[str], candidate_name: Optional[str]
) -> Optional[str]:
    """按人工填写的候选人姓名，找转写里对应的说话人标签。

    依次尝试完全一致、互相包含（“小夏”对“小夏ྀ”）、相似度兜底；都对不上返回 None。
    """
    target = _speaker_key(candidate_name or "")
    if not target:
        return None
    candidates = [item for item in speakers if item and item != UNKNOWN_SPEAKER]
    if not candidates:
        return None

    for speaker in candidates:
        if _speaker_key(speaker) == target:
            return speaker
    for speaker in candidates:
        key = _speaker_key(speaker)
        if key and (key in target or target in key):
            return speaker

    scored = [
        (SequenceMatcher(None, target, _speaker_key(item)).ratio(), item) for item in candidates
    ]
    best_ratio, best_speaker = max(scored, key=lambda item: item[0])
    return best_speaker if best_ratio >= 0.6 else None


def build_dialogue(
    text: str,
    candidate_name: Optional[str] = None,
    candidate_speaker: Optional[str] = None,
) -> Dialogue:
    """一行入口：解析 + 合并 + 确定候选人说话人标签。

    candidate_speaker 是人工从说话人列表里直接指定的标签，优先于姓名匹配；
    传入的标签不在转写里时视为无效，回落到按姓名匹配。
    """
    segments, skipped = _parse(text)
    turns = merge_turns(segments)
    labels = [item.speaker for item in _speaker_stats(turns)]
    source = ""
    if candidate_speaker and candidate_speaker in labels:
        resolved: Optional[str] = candidate_speaker
        source = "manual"
    else:
        resolved = resolve_candidate_speaker(labels, candidate_name)
        source = "name" if resolved else ""
    return Dialogue(
        segments=segments,
        turns=turns,
        skipped=skipped,
        candidate_speaker=resolved,
        candidate_source=source,
    )


def render_turns(turns: Sequence[Turn]) -> str:
    """渲染成喂给问答配对的文本：轮头沿用"说话人(起始时间):"，段内只保留原文。"""
    lines: List[str] = []
    for turn in turns:
        lines.append(f"{turn.speaker}({turn.start}):" if turn.start else f"{turn.speaker}:")
        lines.extend(segment.text for segment in turn.segments)
        lines.append("")
    return "\n".join(lines).strip()
