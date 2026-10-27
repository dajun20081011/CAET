from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LearningCardOut(BaseModel):
    id: str
    title: str
    category: str
    package_format: Literal["cabinlingo-learning-card"]
    package_version: Literal["1.0"]
    entry_file: Literal["index.html"]
    metadata: dict[str, Any] = Field(default_factory=dict)
    resource_count: int
    status: Literal["active", "archived"]
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    course_count: int = 0


class LearningCardAddToCourse(BaseModel):
    course_id: str = Field(min_length=1, max_length=80)


class LearningCardCourseLinkOut(BaseModel):
    learning_card_id: str
    course_id: str
    course_version_id: str
    chapter_id: str
    content_item_id: str
    course_title: str
    version_status: str


class LearningCardViewerOut(BaseModel):
    learning_card_id: str
    title: str
    category: str
    viewer_url: str
    expires_in: int


class LearningCardContentMutationOut(BaseModel):
    content_item_id: str
    chapter_id: str
    removed: bool | None = None
    sequence_no: int | None = None
