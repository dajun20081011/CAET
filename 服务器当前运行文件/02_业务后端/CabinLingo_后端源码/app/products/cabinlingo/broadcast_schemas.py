from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BroadcastScriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    language: str = Field(default="zh_cn", min_length=2, max_length=20)
    script_type: str = Field(default="general", min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=60)
    company_id: str | None = None
    full_text: str = Field(default="", max_length=500_000)


class BroadcastScriptUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    language: str | None = Field(default=None, min_length=2, max_length=20)
    script_type: str | None = Field(default=None, min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=60)
    company_id: str | None = None
    enabled: bool | None = None


class BroadcastScriptItem(BaseModel):
    id: str
    title: str
    language: str
    script_type: str
    category: str | None = None
    company_id: str | None = None
    company_name: str | None = None
    status: Literal["draft", "archived"]
    latest_version_id: str
    latest_version: int
    frozen: bool
    slice_count: int
    ready: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class BroadcastScriptDetail(BroadcastScriptItem):
    created_by: str | None = None


class BroadcastScriptPage(BaseModel):
    items: list[BroadcastScriptItem]
    total: int
    page: int
    page_size: int


class BroadcastVersionCreate(BaseModel):
    full_text: str | None = Field(default=None, max_length=500_000)


class BroadcastVersionOut(BaseModel):
    id: str
    script_id: str
    version: int
    full_text: str
    frozen: bool
    slices_stale: bool
    slice_count: int
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    frozen_at: datetime | None = None


class FullTextUpdate(BaseModel):
    full_text: str = Field(max_length=500_000)


class FullTextUpdateResult(BaseModel):
    status: Literal["updated"] = "updated"
    slice_count: int
    requires_slice_regeneration: bool
    version: BroadcastVersionOut


class BroadcastSliceCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1024)
    position: int | None = Field(default=None, ge=1)
    verified: bool = False


class BroadcastSliceUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1024)
    verified: bool | None = None


class BroadcastSliceOut(BaseModel):
    id: str
    version_id: str
    slice_no: int
    text: str
    start_char: int
    end_char: int
    verified: bool
    created_at: datetime
    updated_at: datetime


class SliceGenerateRequest(BaseModel):
    max_chars: int = Field(default=900, ge=1, le=1024)


class SliceOrderRequest(BaseModel):
    slice_ids: list[str] = Field(min_length=1)
