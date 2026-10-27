from typing import Optional

from pydantic import BaseModel, Field

from schemas.catalog import LessonContent


class LessonCreate(BaseModel):
    course_id: int
    title: str = Field(min_length=1, max_length=200)
    sort_order: int = 0
    content: LessonContent


class LessonUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sort_order: Optional[int] = None
    content: Optional[LessonContent] = None
