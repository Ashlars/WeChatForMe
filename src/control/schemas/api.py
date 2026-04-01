from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.schemas import TriggerMode


class PaginatedResponse(BaseModel):
    items: list[dict]
    page: int = 1
    page_size: int = 20
    total: int


class ContactPatch(BaseModel):
    nickname: str | None = None
    remark: str | None = None
    relationship: str | None = None
    is_whitelist: bool | None = None
    is_paused: bool | None = None
    persona_summary: str | None = None
    style_summary: str | None = None
    interaction_style_summary: str | None = None
    my_alias_for: str | None = None


class GroupPatch(BaseModel):
    group_name: str | None = None
    is_active: bool | None = None
    trigger_mode: TriggerMode | None = None
    keywords: list[str] | None = Field(default=None)
    group_profile: str | None = None
    reply_strategy: str | None = None
