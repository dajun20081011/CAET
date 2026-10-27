from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Protocol


@dataclass(frozen=True)
class AudioBlob:
    data: bytes
    content_type: str
    filename: str = "recording"


AudioLoader = Callable[[str], AudioBlob]


@dataclass(frozen=True)
class AIResult:
    provider: str
    adapter: str
    version: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    latency_ms: int | None = None
    attempts: int = 0
    error_code: str | None = None

    def as_record(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "adapter": self.adapter, "version": self.version,
            "status": self.status, "payload": self.payload, "request_id": self.request_id,
            "latency_ms": self.latency_ms, "attempts": self.attempts, "error_code": self.error_code,
        }


class AIAdapter(Protocol):
    name: str
    provider: str
    version: str
    configured: bool

    def analyze(self, *, reference_text: str, audio_ref: str) -> AIResult: ...


class PendingAdapter:
    provider = "unconfigured"
    configured = False

    def __init__(self, name: str, version: str = "unconfigured") -> None:
        self.name, self.version = name, version

    def analyze(self, *, reference_text: str, audio_ref: str) -> AIResult:
        return AIResult(
            provider=self.provider,
            adapter=self.name,
            version=self.version,
            status="pending_adapter",
            payload={"issues": [{"type": "provider_unconfigured", "message": "AI 服务尚未配置", "severity": "info"}]},
        )


def aggregate_status(results: list[AIResult]) -> str:
    if not results:
        return "pending_adapter"
    statuses = {item.status for item in results}
    if statuses == {"completed"}:
        return "completed"
    if "completed" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    return "pending_adapter"


class AIGateway:
    """Provider-neutral port. No Cabin Voice production endpoint or credential is used."""

    def __init__(self, adapters: Iterable[AIAdapter] | None = None) -> None:
        self.adapters = {a.name: a for a in (adapters or [PendingAdapter("asr_iat"), PendingAdapter("ise"), PendingAdapter("suntone")])}

    def status(self) -> list[dict[str, Any]]:
        return [{"adapter": item.name, "provider": item.provider, "version": item.version,
                 "configured": item.configured} for item in self.adapters.values()]

    def analyze(self, *, reference_text: str, audio_ref: str, requested_adapters: list[str] | None = None) -> list[AIResult]:
        names = requested_adapters or list(self.adapters)
        unknown = [name for name in names if name not in self.adapters]
        if unknown:
            raise ValueError(f"Unsupported AI adapters: {', '.join(unknown)}")
        results: list[AIResult] = []
        for name in names:
            adapter = self.adapters[name]
            try:
                results.append(adapter.analyze(reference_text=reference_text, audio_ref=audio_ref))
            except Exception:
                results.append(AIResult(adapter.provider, adapter.name, adapter.version, "failed", {
                    "issues": [{"type": "adapter_internal_error", "message": "AI 服务处理失败", "severity": "error"}]
                }, attempts=1, error_code="adapter_internal_error"))
        return results
