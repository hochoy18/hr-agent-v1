"""腾讯会议（MCP）相关请求/响应模型。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MeetingCreateRequest(BaseModel):
    """创建会议（面试）请求。时间使用 ISO 8601 字符串，带 +08:00 时区。"""

    subject: str = Field(..., description="会议主题")
    start_time: str = Field(..., description="开始时间，如 2026-11-10T10:00:00+08:00")
    end_time: str = Field(..., description="结束时间，如 2026-11-10T11:00:00+08:00")
    password: Optional[str] = Field(None, description="会议密码，4~6 位数字")
    auto_in_waiting_room: bool = Field(True, description="是否开启等候室（面试建议开启）")
    auto_record_type: Optional[str] = Field(
        None, description="自动录制类型：none/local/cloud"
    )
    auto_asr: Optional[bool] = Field(
        None, description="是否开启自动文字转写（逐字稿）"
    )
    only_user_join_type: Optional[int] = Field(
        None, description="入会限制：1 所有人 / 2 仅受邀 / 3 仅企业内部"
    )
    invitees: List[str] = Field(default_factory=list, description="受邀成员 open_id 列表")
    time_zone: str = Field("Asia/Shanghai", description="会议时区")


class MeetingInfo(BaseModel):
    """创建/查询会议返回的关键信息。"""

    meeting_id: str = Field(..., description="会议唯一标识，取消/查询用")
    meeting_code: str = Field("", description="会议号")
    join_url: str = Field("", description="入会链接")
    subject: str = Field("", description="会议主题")
    start_time: str = Field("", description="开始时间")
    end_time: str = Field("", description="结束时间")
    password: Optional[str] = Field(None, description="会议密码")
    raw: Dict[str, Any] = Field(default_factory=dict, description="接口原始返回")


class MeetingCreateResponse(BaseModel):
    meetings: List[MeetingInfo] = Field(default_factory=list, description="创建的会议列表")


class MeetingCancelResponse(BaseModel):
    meeting_id: str
    cancelled: bool = True
