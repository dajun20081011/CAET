from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "not_ready"]
    version: str
    model_ready: bool


class WordSummary(BaseModel):
    id: str
    word: str
    translation: str
    category: str
    ipa: str
    focus_phones: list[str]


class ResolveWordsRequest(BaseModel):
    words: list[str] = Field(min_length=1, max_length=100)


class AssessmentMetrics(BaseModel):
    audio_seconds: float
    inference_ms: int
    target_error_count: int


class AssessmentResponse(BaseModel):
    request_id: str
    word: WordSummary
    score: int = Field(ge=0, le=100)
    verdict: Literal["excellent", "good", "needs_practice"]
    expected_phones: list[str]
    heard_phones: list[str]
    heard_phone_confidence: list[float]
    phonemes: list[dict[str, Any]]
    feedback: list[dict[str, Any]]
    metrics: AssessmentMetrics
    model: str = "wav2vec2-ljspeech-gruut-q4-onnx"

