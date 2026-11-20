"""面试生命周期（会议 + 材料 + AI 评价）请求/响应模型。"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class InterviewStartRequest(BaseModel):
    """发起面试：创建腾讯会议并落库。"""

    resume_evaluation_id: UUID = Field(..., description="候选人简历评价ID")
    interview_plan_id: Optional[str] = Field(None, description="已保存的面试方案ID")
    interview_plan_content: Optional[str] = Field(None, description="未保存方案的正文快照")
    subject: Optional[str] = Field(None, description="会议主题，缺省为 候选人 - 岗位面试")
    start_time: str = Field(..., description="开始时间，ISO 8601，如 2026-11-10T14:00:00+08:00")
    end_time: str = Field(..., description="结束时间，ISO 8601")
    password: Optional[str] = Field(None, description="会议密码，4~6 位数字")
    auto_in_waiting_room: bool = Field(True, description="是否开启等候室")
    auto_record: bool = Field(True, description="是否自动开启云录制与转写（逐字稿）")
    time_zone: str = Field("Asia/Shanghai", description="会议时区")

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_iso(cls, value: str) -> str:
        try:
            _parse_iso(value)
        except ValueError as exc:
            raise ValueError("时间必须是 ISO 8601 格式") from exc
        return value

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: Optional[str]) -> Optional[str]:
        if value and (not value.isdigit() or not 4 <= len(value) <= 6):
            raise ValueError("会议密码必须是 4~6 位数字")
        return value

    @model_validator(mode="after")
    def _validate_range(self):
        if _parse_iso(self.end_time) <= _parse_iso(self.start_time):
            raise ValueError("结束时间必须晚于开始时间")
        return self


class InterviewUpdateRequest(BaseModel):
    """修改已创建的面试会议（仅 scheduled 状态允许）。"""

    subject: Optional[str] = Field(None, description="会议主题")
    start_time: Optional[str] = Field(None, description="开始时间，ISO 8601")
    end_time: Optional[str] = Field(None, description="结束时间，ISO 8601")
    password: Optional[str] = Field(None, description="会议密码，4~6 位数字")
    auto_in_waiting_room: Optional[bool] = Field(None, description="是否开启等候室")
    auto_record: Optional[bool] = Field(None, description="是否自动开启云录制与转写（逐字稿），不传则不修改")
    time_zone: Optional[str] = Field(None, description="会议时区")

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_update_iso(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            try:
                _parse_iso(value)
            except ValueError as exc:
                raise ValueError("时间必须是 ISO 8601 格式") from exc
        return value

    @field_validator("password")
    @classmethod
    def _validate_update_password(cls, value: Optional[str]) -> Optional[str]:
        if value and (not value.isdigit() or not 4 <= len(value) <= 6):
            raise ValueError("会议密码必须是 4~6 位数字")
        return value


class InterviewResponse(BaseModel):
    """面试记录响应。"""

    id: UUID
    user_id: UUID
    resume_evaluation_id: UUID
    interview_plan_id: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_position: Optional[str] = None

    subject: str
    start_time: str
    end_time: str
    time_zone: str = "Asia/Shanghai"
    meeting_id: Optional[str] = None
    meeting_code: Optional[str] = None
    join_url: Optional[str] = None
    password: Optional[str] = None
    auto_in_waiting_room: bool = True
    meeting_status: str = "scheduled"

    analysis_status: str = "not_started"
    media_type: Optional[str] = None
    media_filename: Optional[str] = None
    media_size: Optional[int] = None
    transcript_source: Optional[str] = None
    transcript: Optional[str] = None
    transcript_meta: Optional[Dict[str, Any]] = None
    plan_content_snapshot: Optional[str] = None
    evaluation: Optional[Dict[str, Any]] = None
    total_score: Optional[float] = None
    error_message: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InterviewListResponse(BaseModel):
    items: List[InterviewResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 20


class InterviewCandidateUpdateRequest(BaseModel):
    """指定候选人姓名。

    姓名用于在转写里匹配说话人标签，是判断"谁在回答"的唯一人工依据。
    传空字符串表示清空，回到自动匹配 + 模型兜底。
    """

    candidate_name: Optional[str] = Field(None, max_length=100, description="候选人姓名，传空表示清空")

    @field_validator("candidate_name")
    @classmethod
    def _strip_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class InterviewDimension(BaseModel):
    """应答质量维度（rubric 0-4）。status=insufficient 表示素材不足、不计入总分。

    manual 表示该维度被人工改过分，ai_score 是模型原始分（首次修订时留存）；
    未修订的维度 manual=False、ai_score 为空。
    """

    name: str
    score: float
    max: float = 4
    status: str = "scored"
    reason: str = ""
    evidence: Optional[str] = None
    derived: bool = False
    manual: bool = False
    ai_score: Optional[float] = None


class InterviewQAPair(BaseModel):
    """一个问题与对应候选人回答的配对，用于判定"答非所问"。

    question_turns / answer_turns 是代码配对时定下的轮号，可定位回结构化转写；
    由模型自行从头配对的兜底路径没有轮号锚点，这两项为空。
    """

    question: str = ""
    answer: str = ""
    question_turns: List[int] = Field(default_factory=list)
    answer_turns: List[int] = Field(default_factory=list)
    answer_speaker: str = ""
    # 漏判或非法取值留空，推导时剔除；不默认成某一档，否则异常输出会白拿分
    verdict: str = ""
    substance: str = ""
    followup: str = ""
    note: str = ""


class InterviewRiskSignal(BaseModel):
    """带原话支撑的风险信号。"""

    type: str = "其他"
    detail: str = ""
    quote: Optional[str] = None


class InterviewExecution(BaseModel):
    """面试执行质量：追问深度。只给面试官看，不计入候选人分数。

    候选人被追问后的表现已作为独立 qa_pairs 计入问答一致性/事实信息量，
    这里只回答"面试官有没有把问题压到细节"。
    """

    question_count: int = 0
    followup_count: int = 0
    deep_count: int = 0
    followup_rate: Optional[float] = None
    depth_score: Optional[float] = None
    depth_level: str = "未知"
    sufficient: bool = False
    note: str = ""


class InterviewEvaluation(BaseModel):
    total_score: float = 0
    score_basis: str = ""
    dimensions: List[InterviewDimension] = Field(default_factory=list)
    qa_pairs: List[InterviewQAPair] = Field(default_factory=list)
    risk_signals: List[InterviewRiskSignal] = Field(default_factory=list)
    execution: InterviewExecution = Field(default_factory=InterviewExecution)
    summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommendation: str = "待定"
    confidence: str = "中"
    insufficient: bool = False
    notes: List[str] = Field(default_factory=list)
    prompt_version: str = ""
    rule_version: str = ""
    # 人工修订留痕：original_total_score 是 AI 原总分，history 每次修订追加一条
    manual_override: Optional[Dict[str, Any]] = None


class InterviewDimensionUpdate(BaseModel):
    """单个维度的人工修订。分数沿用 rubric 的 0-4 整数档，与模型输出同一把尺子。"""

    name: str = Field(..., description="维度名，需与评价里的维度名一致")
    score: int = Field(..., ge=0, le=4, description="修订后的分数，0-4 整数")


class InterviewEvaluationUpdateRequest(BaseModel):
    """人工修订面试评分。dimensions 只传要改的维度，未传的保持原样。

    note 必填：修订会改变候选人结论，必须留下原因备查。
    recommendation 不传则沿用原结论；人工改分后总分与原结论可能不一致，需要时一并改。
    """

    dimensions: List[InterviewDimensionUpdate] = Field(default_factory=list)
    recommendation: Optional[str] = None
    note: str = Field(..., min_length=1, max_length=500, description="修订原因")

    @field_validator("note")
    @classmethod
    def _validate_note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("修订原因不能为空")
        return value.strip()

    @field_validator("recommendation")
    @classmethod
    def _validate_recommendation(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in ("推荐", "待定", "不推荐"):
            raise ValueError("recommendation 只能是：推荐、待定、不推荐")
        return value


class TencentTranscriptRequest(BaseModel):
    """从腾讯会议拉取录制转写。"""

    record_file_id: Optional[str] = Field(None, description="录制文件ID；为空时按会议ID自动查找")
    meeting_code: Optional[str] = Field(None, description="会议号，可作为查找录制记录的兜底")


class InterviewRecordSettings(BaseModel):
    """会议当前云录制/转写设置。"""

    auto_record: Optional[bool] = Field(None, description="是否已开启自动云录制与转写，未知时为 null")
