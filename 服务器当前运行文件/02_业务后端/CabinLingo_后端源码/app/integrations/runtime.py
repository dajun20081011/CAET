from __future__ import annotations

from typing import Any

from .ai_gateway import AIGateway, AudioLoader, PendingAdapter
from .asr import ASRIATAdapter
from .http_ai_adapter import ProviderConfig
from .ise import ISEAdapter
from .suntone import SuntoneAdapter
from .xfyun_iat import XfyunIATAdapter, XfyunIATConfig
from .xfyun_ise import XfyunISEAdapter, XfyunISEConfig
from .xfyun_suntone import XfyunSuntoneAdapter, XfyunSuntoneConfig


def _config(settings: Any, adapter: str) -> ProviderConfig | None:
    prefix = adapter.upper()
    endpoint = getattr(settings, f"{adapter}_endpoint")
    if not settings.ai_gateway_enabled or not endpoint:
        return None
    return ProviderConfig(
        adapter=adapter,
        provider=getattr(settings, f"{adapter}_provider") or prefix,
        endpoint=endpoint,
        api_key=getattr(settings, f"{adapter}_api_key"),
        version=getattr(settings, f"{adapter}_version"),
        timeout_seconds=settings.ai_timeout_seconds,
        max_retries=settings.ai_max_retries,
        backoff_seconds=settings.ai_backoff_seconds,
        audio_transport=settings.ai_audio_transport,
        audio_max_bytes=settings.ai_audio_max_bytes,
        score_scale=getattr(settings, f"{adapter}_score_scale"),
    )


def build_ai_gateway(settings: Any, audio_loader: AudioLoader) -> AIGateway:
    adapters = []
    implementations = {"asr_iat": ASRIATAdapter, "ise": ISEAdapter, "suntone": SuntoneAdapter}
    required = tuple(getattr(settings, "ai_required_adapters", tuple(implementations)))
    for name in required:
        implementation = implementations[name]
        config = _config(settings, name)
        if name == "asr_iat" and config and config.endpoint.lower().startswith(("ws://", "wss://")):
            xfyun_config = XfyunIATConfig(
                endpoint=config.endpoint,
                app_id=getattr(settings, "asr_iat_app_id", ""),
                api_key=config.api_key,
                api_secret=getattr(settings, "asr_iat_api_secret", ""),
                provider=config.provider,
                version=config.version,
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
                backoff_seconds=config.backoff_seconds,
                audio_max_bytes=config.audio_max_bytes,
                language=getattr(settings, "asr_iat_language", "en_us"),
                domain=getattr(settings, "asr_iat_domain", "iat"),
                accent=getattr(settings, "asr_iat_accent", "mandarin"),
                sample_rate=getattr(settings, "asr_iat_sample_rate", 16000),
            )
            adapters.append(XfyunIATAdapter(xfyun_config, audio_loader)
                            if xfyun_config.configured else PendingAdapter(name, "xfyun-unconfigured"))
        elif name == "ise" and config and config.endpoint.lower().startswith(("ws://", "wss://")):
            xfyun_config = XfyunISEConfig(
                endpoint=config.endpoint,
                app_id=getattr(settings, "ise_app_id", ""),
                api_key=config.api_key,
                api_secret=getattr(settings, "ise_api_secret", ""),
                provider=config.provider,
                version=config.version,
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
                backoff_seconds=config.backoff_seconds,
                audio_max_bytes=config.audio_max_bytes,
                ent=getattr(settings, "ise_ent", "en_vip"),
                category=getattr(settings, "ise_category", "read_chapter"),
                sample_rate=getattr(settings, "ise_sample_rate", 16000),
                score_scale=config.score_scale,
            )
            adapters.append(XfyunISEAdapter(xfyun_config, audio_loader)
                            if xfyun_config.configured else PendingAdapter(name, "xfyun-ise-unconfigured"))
        elif name == "suntone" and config and config.endpoint.lower().startswith(("ws://", "wss://")):
            xfyun_config = XfyunSuntoneConfig(
                endpoint=config.endpoint,
                app_id=getattr(settings, "suntone_app_id", ""),
                api_key=config.api_key,
                api_secret=getattr(settings, "suntone_api_secret", ""),
                provider=config.provider,
                version=config.version,
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
                backoff_seconds=config.backoff_seconds,
                audio_max_bytes=config.audio_max_bytes,
                encoded_audio_max_bytes=getattr(settings, "suntone_encoded_audio_max_bytes", 7 * 1024 * 1024),
                language=getattr(settings, "suntone_language", "en"),
                core=getattr(settings, "suntone_core", "para"),
                dialect=getattr(settings, "suntone_dialect", "en_us"),
                score_scale=int(config.score_scale),
                ffmpeg_binary=getattr(settings, "audio_transcode_binary", "ffmpeg"),
                transcode_timeout_seconds=getattr(settings, "audio_transcode_timeout_seconds", 30),
                transcode_max_seconds=getattr(settings, "audio_transcode_max_seconds", 300),
            )
            adapters.append(XfyunSuntoneAdapter(xfyun_config, audio_loader)
                            if xfyun_config.configured else PendingAdapter(name, "xfyun-suntone-unconfigured"))
        else:
            adapters.append(implementation(config, audio_loader) if config else PendingAdapter(name))
    return AIGateway(adapters)
