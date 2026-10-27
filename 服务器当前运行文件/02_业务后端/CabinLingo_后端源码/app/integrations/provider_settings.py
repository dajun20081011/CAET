from __future__ import annotations

from dataclasses import fields
import json
import logging
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from .ai_gateway import AIResult, AudioLoader
from .runtime import build_ai_gateway


logger = logging.getLogger(__name__)


PROVIDERS: dict[str, dict[str, Any]] = {
    "qwen_tts": {
        "label": "千问语音合成",
        "prefix": "qwen_tts",
        "config": ("endpoint", "workspace_id", "model", "voices", "voice_profiles"),
        "secrets": ("api_key",),
    },
    "asr_iat": {
        "label": "讯飞语音听写 IAT",
        "prefix": "asr_iat",
        "config": ("endpoint", "app_id", "provider", "version", "language", "domain", "accent"),
        "secrets": ("api_key", "api_secret"),
    },
    "suntone": {
        "label": "讯飞 Suntone 发音评测",
        "prefix": "suntone",
        "config": ("endpoint", "app_id", "provider", "version", "language", "core", "dialect"),
        "secrets": ("api_key", "api_secret"),
    },
    "ise": {
        "label": "讯飞 ISE 发音评测",
        "prefix": "ise",
        "config": ("endpoint", "app_id", "provider", "version", "ent", "category"),
        "secrets": ("api_key", "api_secret"),
    },
}


class ProviderSettingsError(RuntimeError):
    pass


class ProviderSettingsRepository:
    def __init__(self, database_url: str, master_key: str) -> None:
        self.database_url = database_url
        self.master_key = master_key

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def list(self) -> dict[str, dict[str, Any]]:
        if not self.database_url or not self.master_key:
            return {}
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT provider_code, enabled, config,
                          pgp_sym_decrypt(encrypted_secrets, %s)::text AS secrets_json,
                          updated_at
                   FROM cl_ai_provider_settings ORDER BY provider_code""",
                (self.master_key,),
            )
            return {
                row["provider_code"]: {
                    "enabled": row["enabled"],
                    "config": dict(row["config"] or {}),
                    "secrets": json.loads(row["secrets_json"] or "{}"),
                    "updated_at": row["updated_at"].isoformat(),
                }
                for row in cur.fetchall()
            }

    def save(self, provider_code: str, enabled: bool, config: dict[str, Any],
             secrets: dict[str, str], actor_id: str) -> None:
        encoded = json.dumps(secrets, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO cl_ai_provider_settings
                     (provider_code, enabled, config, encrypted_secrets, updated_by, updated_at)
                   VALUES (%s,%s,%s::jsonb,pgp_sym_encrypt(%s,%s,'cipher-algo=aes256'),%s,now())
                   ON CONFLICT(provider_code) DO UPDATE SET
                     enabled=EXCLUDED.enabled, config=EXCLUDED.config,
                     encrypted_secrets=EXCLUDED.encrypted_secrets,
                     updated_by=EXCLUDED.updated_by, updated_at=now()""",
                (provider_code, enabled, json.dumps(config), encoded, self.master_key, actor_id),
            )
            cur.execute(
                """INSERT INTO audit_logs(actor_id,product_code,action,resource_type,metadata)
                   VALUES (%s,'cabinlingo','ai_provider_settings.updated','ai_provider_settings',
                           jsonb_build_object('provider_code',%s::text,'enabled',%s::boolean))""",
                (actor_id, provider_code, enabled),
            )


class ProviderSettingsManager:
    def __init__(self, base_settings: Any, repository: ProviderSettingsRepository | None = None) -> None:
        self.base = base_settings
        self.repository = repository or ProviderSettingsRepository(
            getattr(base_settings, "database_url", ""), getattr(base_settings, "ai_settings_master_key", "")
        )

    @property
    def writable(self) -> bool:
        return bool(getattr(self.base, "database_url", "") and getattr(self.base, "ai_settings_master_key", ""))

    def _records(self) -> dict[str, dict[str, Any]]:
        try:
            return self.repository.list()
        except Exception as exc:
            raise ProviderSettingsError("AI 服务配置读取失败") from exc

    def _environment_provider(self, code: str) -> dict[str, Any]:
        spec = PROVIDERS[code]
        prefix = spec["prefix"]
        required = tuple(getattr(self.base, "ai_required_adapters", ()))
        enabled = (getattr(self.base, "qwen_tts_enabled", False) if code == "qwen_tts"
                   else getattr(self.base, "ai_gateway_enabled", False) and code in required)
        config = {name: getattr(self.base, f"{prefix}_{name}", "") for name in spec["config"]}
        secrets = {name: getattr(self.base, f"{prefix}_{name}", "") for name in spec["secrets"]}
        return {"enabled": enabled, "config": config, "secrets": secrets, "source": "environment", "updated_at": None}

    def effective_records(self) -> dict[str, dict[str, Any]]:
        saved = self._records()
        result = {}
        for code in PROVIDERS:
            item = self._environment_provider(code)
            if code in saved:
                item = {**saved[code], "source": "database"}
            result[code] = item
        return result

    def public_list(self) -> dict[str, Any]:
        records = self.effective_records()
        providers = []
        for code, spec in PROVIDERS.items():
            item = records[code]
            providers.append({
                "code": code,
                "label": spec["label"],
                "enabled": bool(item["enabled"]),
                "source": item["source"],
                "config": item["config"],
                "secret_status": {name: bool(item["secrets"].get(name)) for name in spec["secrets"]},
                "updated_at": item.get("updated_at"),
            })
        return {"writable": self.writable, "providers": providers}

    def save(self, code: str, enabled: bool, config: dict[str, Any], incoming_secrets: dict[str, str | None], actor_id: str) -> None:
        if code not in PROVIDERS:
            raise ValueError("不支持的 AI 服务")
        if not self.writable:
            raise ProviderSettingsError("服务器尚未配置 AI_SETTINGS_MASTER_KEY")
        spec = PROVIDERS[code]
        unknown = set(config) - set(spec["config"])
        if unknown:
            raise ValueError(f"不支持的配置字段: {', '.join(sorted(unknown))}")
        clean_config: dict[str, Any] = {}
        for name in spec["config"]:
            value = config.get(name, "")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"配置字段 {name} 格式错误")
            clean_config[name] = value.strip() if isinstance(value, str) else value
            if isinstance(clean_config[name], str) and len(clean_config[name]) > 12000:
                raise ValueError(f"配置字段 {name} 过长")
        records = self.effective_records()
        secrets = dict(records[code]["secrets"])
        for name in spec["secrets"]:
            value = incoming_secrets.get(name)
            if value is not None and value.strip():
                secrets[name] = value.strip()
        if enabled:
            required = ["endpoint", "api_key"] + ([] if code == "qwen_tts" else ["app_id", "api_secret"])
            missing = [name for name in required if not (clean_config.get(name) or secrets.get(name))]
            if missing:
                raise ValueError(f"启用前请填写: {', '.join(missing)}")
            endpoint = str(clean_config.get("endpoint", ""))
            parsed = urlparse(endpoint)
            allowed_schemes = {"https"} if code == "qwen_tts" else {"https", "wss"}
            if parsed.scheme not in allowed_schemes or not parsed.hostname:
                raise ValueError("接口地址必须使用有效的 HTTPS/WSS 地址")
            if code == "qwen_tts" and "/compatible-mode/" in parsed.path:
                raise ValueError("该地址是兼容模型接口，请填写千问语音合成 SpeechSynthesizer 接口")
        try:
            self.repository.save(code, enabled, clean_config, secrets, actor_id)
        except Exception as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            logger.exception("AI provider settings save failed: provider=%s sqlstate=%s", code, sqlstate or "unknown")
            suffix = f"（数据库错误 {sqlstate}）" if sqlstate else ""
            raise ProviderSettingsError(f"AI 服务配置保存失败{suffix}") from exc

    def effective_settings(self) -> Any:
        values = {item.name: getattr(self.base, item.name) for item in fields(self.base)}
        required = list(values.get("ai_required_adapters", ())) if values.get("ai_gateway_enabled") else []
        for code, item in self.effective_records().items():
            spec = PROVIDERS[code]
            prefix = spec["prefix"]
            for name, value in item["config"].items():
                values[f"{prefix}_{name}"] = value
            for name, value in item["secrets"].items():
                values[f"{prefix}_{name}"] = value
            if code == "qwen_tts":
                values["qwen_tts_enabled"] = bool(item["enabled"])
            elif item["source"] == "database":
                if item["enabled"] and code not in required:
                    required.append(code)
                if not item["enabled"] and code in required:
                    required.remove(code)
        values["ai_required_adapters"] = tuple(required)
        values["ai_gateway_enabled"] = bool(required)
        return SimpleNamespace(**values)


class DynamicAIGateway:
    def __init__(self, manager: ProviderSettingsManager, audio_loader: AudioLoader) -> None:
        self.manager = manager
        self.audio_loader = audio_loader

    @property
    def enabled(self) -> bool:
        return bool(self.manager.effective_settings().ai_gateway_enabled)

    def status(self) -> list[dict[str, Any]]:
        return build_ai_gateway(self.manager.effective_settings(), self.audio_loader).status()

    def analyze(self, *, reference_text: str, audio_ref: str,
                requested_adapters: list[str] | None = None) -> list[AIResult]:
        gateway = build_ai_gateway(self.manager.effective_settings(), self.audio_loader)
        return gateway.analyze(reference_text=reference_text, audio_ref=audio_ref,
                               requested_adapters=requested_adapters)
