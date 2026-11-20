"""面试问答配对：把合并后的发言轮次配成问答组。

纯代码规则，不调用模型、不判定质量，只确定"谁问、谁答、边界在哪"：
1. 非候选人（面试官一方）的连续发言轮累积成一个提问块；
2. 遇到候选人发言轮，即与当前提问块配成一组，提问块清空；
3. 候选人先开口、前面没有任何提问时，该轮记入 unprompted（开场自述），不成组；
4. 结尾有提问但没有候选人回应时，answer 留空，供下游判定为"未作答"。

每组带 question_turns / answer_turns 轮号，可逐条回溯到转写原文位置。
候选人说话人标签由人工填写的姓名匹配得到；匹配不到时无法配对，返回空结果。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.transcript_segmenter import Dialogue, Turn


@dataclass
class QAPair:
    """一组问答。question 可能由多个面试官轮累积而成，answer 为候选人一轮原文。"""

    index: int
    question: str
    answer: str
    question_turns: List[int] = field(default_factory=list)
    answer_turns: List[int] = field(default_factory=list)
    question_speakers: List[str] = field(default_factory=list)
    answer_speaker: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "question": self.question,
            "answer": self.answer,
            "question_turns": self.question_turns,
            "answer_turns": self.answer_turns,
            "question_speakers": self.question_speakers,
            "answer_speaker": self.answer_speaker,
        }


@dataclass
class PairingResult:
    """整场配对结果：问答组 + 候选人开场自述。

    unprompted 是候选人先开口、前面没有任何提问的轮次。它没有对应问题，
    因此不组成问答对、不参与问答判定；原文仍在转写全文里，轮号可回溯。
    """

    pairs: List[QAPair] = field(default_factory=list)
    unprompted: List[Turn] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pair_count": len(self.pairs),
            "pairs": [pair.to_dict() for pair in self.pairs],
            "unprompted_turns": [turn.index for turn in self.unprompted],
            "unprompted": [
                {"turn": turn.index, "speaker": turn.speaker, "text": turn.text}
                for turn in self.unprompted
            ],
        }


def _build(
    index: int,
    question_turns: List[Turn],
    answer_turn: Optional[Turn],
    candidate: str,
) -> QAPair:
    return QAPair(
        index=index,
        question="\n".join(turn.text for turn in question_turns),
        answer=answer_turn.text if answer_turn else "",
        question_turns=[turn.index for turn in question_turns],
        answer_turns=[answer_turn.index] if answer_turn else [],
        question_speakers=[turn.speaker for turn in question_turns],
        answer_speaker=candidate if answer_turn else "",
    )


def pair_qa_turns(dialogue: Dialogue) -> PairingResult:
    """按轮次配对出问答组；候选人标签缺失时返回空结果。

    规则只有一条：面试官轮攒起来当提问，遇到候选人轮就配成一组。
    候选人先开口（提问块为空）时记入 unprompted，不生成空提问的组；
    不做插话/打断的特殊处理，也不合并跨轮的回答。
    """
    candidate = dialogue.candidate_speaker
    if not candidate:
        return PairingResult()

    result = PairingResult()
    pending: List[Turn] = []
    for turn in dialogue.turns:
        if turn.speaker != candidate:
            pending.append(turn)
            continue
        if not pending:
            result.unprompted.append(turn)
            continue
        result.pairs.append(_build(len(result.pairs) + 1, pending, turn, candidate))
        pending = []
    if pending:
        result.pairs.append(_build(len(result.pairs) + 1, pending, None, candidate))
    return result


def pairs_to_json(result: PairingResult) -> Dict[str, Any]:
    """导出为可直接写文件的 JSON 结构（含问答组与开场自述）。"""
    return result.to_dict()
