from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class KeyWord(BaseModel):
    word: str
    phonetic: Optional[str] = None
    meaning: Optional[str] = None
    audio_url: Optional[str] = None
    note: Optional[str] = None


class BroadcastContent(BaseModel):
    template_type: Literal["broadcast"] = "broadcast"
    chinese_text: str
    english_text: str
    standard_audio_url: Optional[str] = None
    slow_audio_url: Optional[str] = None
    key_words: List[KeyWord] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)


class CAET2Content(BaseModel):
    template_type: Literal["caet2"] = "caet2"
    scenario: Optional[str] = None
    chinese_prompt: str
    standard_english: str
    standard_audio_url: Optional[str] = None
    key_words: List[KeyWord] = Field(default_factory=list)
    expression_tips: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)


class CAET3Content(BaseModel):
    template_type: Literal["caet3"] = "caet3"
    scenario: Optional[str] = None
    chinese_task: str
    reference_english: Optional[str] = None
    standard_audio_url: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    key_words: List[KeyWord] = Field(default_factory=list)
    expression_logic: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
