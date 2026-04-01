from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MessageDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class TriggerMode(StrEnum):
    AT_ME = "at_me"
    KEYWORD = "keyword"
    BOTH = "both"
    ALL = "all"


class Message(BaseModel):
    msg_id: str
    contact_id: str
    group_id: str | None = None
    direction: MessageDirection
    content: str
    msg_type: str = "text"
    agent_model: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class Contact(BaseModel):
    wxid: str
    nickname: str | None = None
    remark: str | None = None
    relationship: str | None = None
    chat_prefs: dict | None = None
    is_whitelist: bool = False
    is_paused: bool = False
    last_interaction: datetime | None = None
    persona_summary: str | None = None
    style_summary: str | None = None
    interaction_style_summary: str | None = None
    my_alias_for: str | None = None
    last_analysis_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class Group(BaseModel):
    group_id: str
    group_name: str | None = None
    is_active: bool = False
    trigger_mode: TriggerMode = TriggerMode.AT_ME
    keywords: list[str] = Field(default_factory=list)
    group_profile: str | None = None
    reply_strategy: str | None = None
    last_analysis_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
