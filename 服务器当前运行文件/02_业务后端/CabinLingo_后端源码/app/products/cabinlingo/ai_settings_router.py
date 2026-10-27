from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.rbac import Principal, assert_permission, get_principal
from ...integrations.provider_settings import PROVIDERS, ProviderSettingsError
from .ai_runtime import provider_settings


router = APIRouter(prefix="/api/v1/cabinlingo/admin/ai-providers", tags=["CabinLingo AI Settings"])


class ProviderSettingsUpdate(BaseModel):
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    api_key: str | None = Field(default=None, max_length=4096)
    api_secret: str | None = Field(default=None, max_length=4096)


def _admin(principal: Principal) -> None:
    assert_permission(principal, "cabinlingo", "cabinlingo:admin")


@router.get("")
def list_ai_provider_settings(principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        return provider_settings.public_list()
    except ProviderSettingsError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.put("/{provider_code}")
def update_ai_provider_settings(provider_code: str, data: ProviderSettingsUpdate,
                                principal: Principal = Depends(get_principal)):
    _admin(principal)
    if provider_code not in PROVIDERS:
        raise HTTPException(404, "AI 服务不存在")
    try:
        provider_settings.save(
            provider_code, data.enabled, data.config,
            {"api_key": data.api_key, "api_secret": data.api_secret}, principal.user_id,
        )
        return provider_settings.public_list()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ProviderSettingsError as exc:
        raise HTTPException(503, str(exc)) from exc
