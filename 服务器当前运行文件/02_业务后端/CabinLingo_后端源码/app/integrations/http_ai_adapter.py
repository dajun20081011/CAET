from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from .ai_gateway import AIResult, AudioLoader
from .http_client import HTTPClient, HTTPClientError


ResultParser = Callable[[dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True)
class ProviderConfig:
    adapter: str
    provider: str
    endpoint: str
    api_key: str
    version: str
    timeout_seconds: float = 15
    max_retries: int = 1
    backoff_seconds: float = 0.25
    audio_transport: str = "base64"
    audio_max_bytes: int = 15 * 1024 * 1024
    score_scale: float = 100


class HTTPAIAdapter:
    configured = True

    def __init__(self, config: ProviderConfig, parser: ResultParser,
                 audio_loader: AudioLoader, client: HTTPClient | None = None) -> None:
        self.config = config
        self.name = config.adapter
        self.provider = config.provider
        self.version = config.version
        self.parser = parser
        self.audio_loader = audio_loader
        self.client = client or HTTPClient(timeout_seconds=config.timeout_seconds,
                                           max_retries=config.max_retries,
                                           backoff_seconds=config.backoff_seconds)

    def analyze(self, *, reference_text: str, audio_ref: str) -> AIResult:
        request_id = uuid4().hex
        try:
            if self.config.audio_transport == "reference":
                audio: dict[str, Any] = {"reference": audio_ref}
            else:
                blob = self.audio_loader(audio_ref)
                if len(blob.data) > self.config.audio_max_bytes:
                    raise HTTPClientError("audio_too_large")
                audio = {"content_base64": base64.b64encode(blob.data).decode("ascii"),
                         "content_type": blob.content_type, "filename": blob.filename}
            headers = {"X-Request-ID": request_id}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            response_data, response = self.client.request_json("POST", self.config.endpoint, payload={
                "request_id": request_id, "adapter": self.name,
                "reference_text": reference_text, "audio": audio,
            }, headers=headers)
            if str(response_data.get("status", "completed")).lower() in {"failed", "error", "rejected"}:
                raise HTTPClientError("provider_rejected")
            normalized = self.parser(response_data, self.config.score_scale)
            normalized["provider_payload_version"] = str(response_data.get("version") or self.version)
            provider_request_id = str(response_data.get("request_id") or response.headers.get("x-request-id") or request_id)
            return AIResult(self.provider, self.name, self.version, "completed", normalized,
                            provider_request_id, response.latency_ms, response.attempts)
        except HTTPClientError as exc:
            return AIResult(self.provider, self.name, self.version, "failed", {
                "issues": [{"type": exc.code, "message": "AI 服务暂时不可用，请稍后重试", "severity": "error"}]
            }, request_id=request_id,
                attempts=self.config.max_retries + 1 if exc.retryable else 1, error_code=exc.code)

