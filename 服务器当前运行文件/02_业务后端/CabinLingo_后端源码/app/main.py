from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .core.auth_router import router as auth_router
from .core.auth_repository import AuthRepository
from .core.admin_catalog import router as admin_catalog_router
from .core.config import settings
from .core.rbac import Principal, get_principal
from .core.security import hash_password
from .products.cabinlingo.router import ai_gateway, router as cabinlingo_router, store
from .products.cabinlingo.broadcast_router import router as broadcast_library_router
from .products.cabinlingo.learning_card_router import router as learning_card_router
from .products.cabinlingo.qwen_tts_router import router as qwen_tts_router
from .products.cabinlingo.ai_settings_router import router as ai_settings_router
from .products.cabinlingo.schemas import PasswordResetRequest, UserCreate, UserImportRequest, UserImportResult, UserOut


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Production candidate modular monolith API for CAET products.",
)


@app.middleware("http")
async def legacy_v1_path_bridge(request, call_next):
    """Accept the legacy Nginx-stripped /v1 path without changing old /api routes."""
    path = request.scope.get("path", "")
    if path.startswith("/v1/"):
        rewritten = "/api" + path
        request.scope["path"] = rewritten
        request.scope["raw_path"] = rewritten.encode("utf-8")
    return await call_next(request)

if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

core = APIRouter(prefix="/api/v1/core", tags=["Core"])


@core.get("/health")
async def health():
    try:
        database_ok = store.healthcheck()
    except Exception:
        database_ok = False
    payload = {
        "status": "ok" if database_ok else "error",
        "environment": settings.environment,
        "database": getattr(store, "backend", "in_memory") if database_ok else "unavailable",
    }
    return payload if database_ok else JSONResponse(status_code=503, content=payload)


@core.get("/products")
async def products(principal: Principal = Depends(get_principal)):
    return [
        {"code": "cabinlingo", "status": "implemented"},
        {"code": "caet2", "status": "reserved"},
        {"code": "caet3", "status": "reserved"},
    ]


@core.get("/me")
async def me(principal: Principal = Depends(get_principal)):
    return {
        "user_id": principal.user_id,
        "display_name": principal.display_name,
        "memberships": [
            {"product": m.product_code, "roles": sorted(m.roles), "permissions": sorted(m.permissions)}
            for m in principal.memberships
        ],
    }


@core.get("/users", response_model=list[UserOut])
async def list_users(principal: Principal = Depends(get_principal)):
    from .core.rbac import assert_permission
    assert_permission(principal, "cabinlingo", "cabinlingo:admin")
    if not settings.database_url:
        return []
    return AuthRepository(settings.database_url).list_users()


@core.post("/users", response_model=UserOut)
async def create_user(data: UserCreate, principal: Principal = Depends(get_principal)):
    from .core.rbac import assert_permission
    assert_permission(principal, "cabinlingo", "cabinlingo:admin")
    if not settings.database_url:
        raise HTTPException(503, "User management requires PostgreSQL")
    try:
        return AuthRepository(settings.database_url).create_user(data.account.strip(), data.display_name.strip(), data.email, hash_password(data.password), data.role, data.class_id, principal.user_id)
    except Exception as exc:
        raise HTTPException(409, "User could not be created") from exc


def assert_user_capability(principal: Principal, permission: str) -> None:
    """Allow the legacy admin capability while new granular permissions roll out."""
    from .core.rbac import assert_permission
    if principal.has_permission("cabinlingo", permission) or principal.has_permission("cabinlingo", "cabinlingo:admin"):
        return
    assert_permission(principal, "cabinlingo", permission)


@core.post("/users/import", response_model=UserImportResult)
async def import_users(data: UserImportRequest, principal: Principal = Depends(get_principal)):
    assert_user_capability(principal, "cabinlingo:user.import")
    if not settings.database_url:
        raise HTTPException(503, "User management requires PostgreSQL")
    repository = AuthRepository(settings.database_url)
    imported: list[dict] = []
    errors: list[dict] = []
    for row_number, row in enumerate(data.rows, start=2):
        account = row.account.strip()
        try:
            if not account or not row.display_name.strip():
                raise ValueError("账号和姓名不能为空")
            password = row.password.strip()
            if len(password) < 10:
                raise ValueError("密码至少需要 10 个字符")
            password_hash = hash_password(password)
            existing = repository.update_imported_user(
                account,
                row.display_name.strip(),
                password_hash,
                principal.user_id,
                email=row.email.strip() if row.email else None,
                role=row.role.strip().lower() or "learner",
                class_id=row.class_id.strip() if row.class_id else None,
            )
            if existing:
                imported.append(existing)
                continue
            imported.append(repository.create_user(
                account,
                row.display_name.strip(),
                row.email.strip() if row.email else None,
                password_hash,
                row.role.strip().lower() or "learner",
                row.class_id.strip() if row.class_id else None,
                principal.user_id,
            ))
        except ValueError as exc:
            errors.append({"row": row_number, "account": account, "message": str(exc)})
        except Exception:
            errors.append({"row": row_number, "account": account, "message": "账号或邮箱已存在，或班级/角色无效"})
    return {"imported": len(imported), "failed": len(errors), "users": imported, "errors": errors}


@core.delete("/users/{user_id}", response_model=UserOut)
async def deactivate_user(user_id: str, principal: Principal = Depends(get_principal)):
    assert_user_capability(principal, "cabinlingo:user.delete")
    if not settings.database_url:
        raise HTTPException(503, "User management requires PostgreSQL")
    try:
        return AuthRepository(settings.database_url).deactivate_user(user_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, "User not found") from exc


@core.post("/users/{user_id}/password-reset", response_model=UserOut)
async def reset_user_password(user_id: str, data: PasswordResetRequest, principal: Principal = Depends(get_principal)):
    assert_user_capability(principal, "cabinlingo:user.password_reset")
    if not settings.database_url:
        raise HTTPException(503, "User management requires PostgreSQL")
    try:
        return AuthRepository(settings.database_url).reset_user_password(user_id, hash_password(data.password), principal.user_id)
    except LookupError as exc:
        raise HTTPException(404, "User not found") from exc


@app.on_event("startup")
async def validate_runtime() -> None:
    settings.validate_runtime()


app.include_router(auth_router)
app.include_router(core)
app.include_router(admin_catalog_router)
app.include_router(cabinlingo_router)
app.include_router(broadcast_library_router)
app.include_router(learning_card_router)
app.include_router(qwen_tts_router)
app.include_router(ai_settings_router)

ai = APIRouter(prefix="/api/v1/ai", tags=["AI Gateway"])


@ai.get("/status")
async def ai_status(principal: Principal = Depends(get_principal)):
    if not (principal.has_permission("cabinlingo", "cabinlingo:admin") or
            principal.has_permission("cabinlingo", "cabinlingo:review")):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Permission denied")
    return {"enabled": ai_gateway.enabled, "adapters": ai_gateway.status(),
            "object_storage": settings.object_storage_mode}


@ai.post("/analyze")
async def analyze(
    reference_text: str,
    audio_ref: str,
    adapters: str | None = None,
    principal: Principal = Depends(get_principal),
):
    if not principal.has_permission("cabinlingo", "cabinlingo:admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Permission denied")
    requested = [item.strip() for item in adapters.split(",")] if adapters else None
    try:
        results = ai_gateway.analyze(
            reference_text=reference_text, audio_ref=audio_ref, requested_adapters=requested
        )
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "results": [
            result.__dict__
            for result in results
        ]
    }


app.include_router(ai)
