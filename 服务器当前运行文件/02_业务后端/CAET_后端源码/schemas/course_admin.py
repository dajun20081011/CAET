from typing import Optional

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    project_code: str
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    sort_order: int = 0


class CourseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    sort_order: Optional[int] = None
