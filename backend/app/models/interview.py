"""面试记录模型：腾讯会议信息 + 面试材料 + AI 评价结果。"""
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class Interview(BaseModel):
    """一次面试（一场腾讯会议）的完整记录。"""

    __tablename__ = "interviews"

    # 归属与关联
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True, comment="创建用户ID")
    resume_evaluation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resume_evaluations.id"),
        nullable=False,
        index=True,
        comment="关联的简历评价ID（候选人）",
    )
    interview_plan_id = Column(String(64), nullable=True, comment="关联的远程面试方案ID")
    candidate_name = Column(String(100), nullable=True, comment="候选人姓名快照")
    candidate_position = Column(String(200), nullable=True, comment="应聘岗位快照")

    # 腾讯会议
    subject = Column(String(512), nullable=False, comment="会议主题")
    start_time = Column(String(64), nullable=False, comment="开始时间（ISO 8601，保留时区）")
    end_time = Column(String(64), nullable=False, comment="结束时间（ISO 8601，保留时区）")
    time_zone = Column(String(64), nullable=False, default="Asia/Shanghai", comment="会议时区")
    meeting_id = Column(String(64), nullable=True, unique=True, index=True, comment="腾讯会议 meeting_id")
    meeting_code = Column(String(32), nullable=True, comment="会议号")
    join_url = Column(Text, nullable=True, comment="候选人入会链接")
    password = Column(String(16), nullable=True, comment="会议密码")
    auto_in_waiting_room = Column(Boolean, nullable=False, default=True, comment="是否开启等候室")
    meeting_status = Column(String(20), nullable=False, default="scheduled", comment="scheduled/ongoing/cancelled/completed")

    # 面试材料与转写
    analysis_status = Column(
        String(20), nullable=False, default="not_started", comment="not_started/transcribing/transcript_ready/analyzing/completed/failed"
    )
    media_type = Column(String(20), nullable=True, comment="audio/video/document")
    media_path = Column(String(500), nullable=True, comment="上传文件存放路径")
    media_filename = Column(String(255), nullable=True, comment="原始文件名")
    media_size = Column(Integer, nullable=True, comment="文件大小（字节）")
    transcript_source = Column(String(20), nullable=True, comment="upload/tencent/document")
    transcript = Column(Text, nullable=True, comment="面试转写文本")
    transcript_meta = Column(JSON, nullable=True, comment="转写元信息（说话人、片段等）")

    # 评价依据快照与结果
    plan_content_snapshot = Column(Text, nullable=True, comment="发起面试时的面试方案内容快照")
    evaluation = Column(JSON, nullable=True, comment="AI 评价完整结果")
    total_score = Column(Float, nullable=True, comment="面试评价总分")
    error_message = Column(Text, nullable=True, comment="最近一次后台任务失败原因")

    def __repr__(self):
        return f"<Interview(id={self.id}, candidate='{self.candidate_name}', meeting_id='{self.meeting_id}')>"
