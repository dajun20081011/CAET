from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from schemas.course import BroadcastContent, CAET2Content, CAET3Content


ProjectType = Literal["broadcast", "caet2", "caet3"]

LessonContent = Annotated[
    Union[BroadcastContent, CAET2Content, CAET3Content],
    Field(discriminator="template_type"),
]


class Lesson(BaseModel):
    title: str
    order: int = 1
    content: LessonContent


class Course(BaseModel):
    project_type: ProjectType
    title: str
    description: Optional[str] = None
    lessons: List[Lesson] = Field(default_factory=list)
