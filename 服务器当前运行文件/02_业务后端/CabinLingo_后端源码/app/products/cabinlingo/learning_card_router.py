from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ...core.config import settings
from ...core.rbac import Principal, assert_permission, get_principal
from ...integrations.oss import ObjectStorageError, build_object_storage
from .learning_card_package import LearningCardPackageError, PackageLimits
from .learning_card_schemas import (
    LearningCardAddToCourse, LearningCardContentMutationOut, LearningCardCourseLinkOut, LearningCardOut,
    LearningCardViewerOut,
)
from .learning_card_security import LearningCardAccessLogFilter, LearningCardTokenError, LearningCardViewerSigner
from .learning_card_service import LearningCardService, inject_viewer_bridge
from .storage import build_store


router = APIRouter(prefix="/api/v1/cabinlingo", tags=["CabinLingo Learning Cards"])
store = build_store()
object_storage = build_object_storage(settings)
service = LearningCardService(store, object_storage)
signer = LearningCardViewerSigner(settings.jwt_secret or "local-development-learning-card-viewer")
import_gate = asyncio.Semaphore(1)
logging.getLogger('uvicorn.access').addFilter(LearningCardAccessLogFilter())

def _admin(principal: Principal) -> None:
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")


def _viewer(card: dict, token: str) -> dict:
    return {
        "learning_card_id": card["id"], "title": card["title"], "category": card["category"],
        "viewer_url": f"/api/v1/cabinlingo/learning-card-view/{token}/{card['entry_file']}",
        "expires_in": signer.ttl_seconds,
    }


@router.post("/admin/learning-cards/import", response_model=LearningCardOut)
async def import_learning_card(file: UploadFile = File(...), principal: Principal = Depends(get_principal)):
    _admin(principal)
    filename = (file.filename or "").strip()
    body = bytearray()
    limit = PackageLimits().max_package_bytes
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, "课程包文件过大")
    try:
        async with import_gate:
            return await run_in_threadpool(service.import_package, bytes(body), filename, principal.user_id)
    except LearningCardPackageError as exc:
        status = 413 if "过大" in str(exc) or "解压炸弹" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    except ObjectStorageError as exc:
        raise HTTPException(503, "学习卡片资源存储不可用") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/admin/learning-cards", response_model=list[LearningCardOut])
async def list_learning_cards(include_archived: bool = Query(False), principal: Principal = Depends(get_principal)):
    _admin(principal)
    return store.list_learning_cards(include_archived)


@router.get("/admin/learning-cards/{card_id}", response_model=LearningCardOut)
async def get_learning_card(card_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    card = store.get_learning_card(card_id)
    if not card:
        raise HTTPException(404, "学习卡片不存在")
    return card


@router.get("/admin/learning-cards/{card_id}/preview", response_model=LearningCardViewerOut)
async def preview_learning_card(card_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    card = store.get_learning_card(card_id)
    if not card:
        raise HTTPException(404, "学习卡片不存在")
    return _viewer(card, signer.issue(card_id, principal.user_id, "admin_preview"))


@router.post("/admin/learning-cards/{card_id}/add-to-course", response_model=LearningCardCourseLinkOut)
async def add_learning_card_to_course(card_id: str, data: LearningCardAddToCourse,
                                      principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        return store.add_learning_card_to_course(card_id, data.course_id, principal.user_id)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if "不存在" in message else 409, message) from exc


@router.delete("/admin/learning-cards/{card_id}", response_model=LearningCardOut)
async def archive_learning_card(card_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    card = store.archive_learning_card(card_id)
    if not card:
        raise HTTPException(404, "学习卡片不存在")
    return card


@router.delete("/admin/learning-card-contents/{content_id}", response_model=LearningCardContentMutationOut)
async def remove_learning_card_from_course(content_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        return store.remove_learning_card_from_course(content_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/admin/learning-card-contents/{content_id}/move", response_model=LearningCardContentMutationOut)
async def move_learning_card_in_course(content_id: str, direction: str = Query(..., pattern="^(up|down)$"),
                                       principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        return store.move_learning_card_in_course(content_id, direction)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/learner/learning-cards/{content_id}", response_model=LearningCardViewerOut)
async def learner_learning_card(
    content_id: str,
    assignment_id: str | None = Query(None),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")

    if assignment_id:
        card = store.get_learner_learning_card(
            content_id,
            assignment_id,
            principal.user_id,
        )
        if not card:
            raise HTTPException(404, "学习卡片不存在或不属于当前任务")

        return _viewer(
            card,
            signer.issue(
                card["id"],
                principal.user_id,
                "learner_view",
                content_id=content_id,
                assignment_id=assignment_id,
            ),
        )

    card = store.get_learner_catalog_learning_card(
        content_id,
        principal.user_id,
    )
    if not card:
        raise HTTPException(404, "学习卡片不存在或不属于当前已发布课程")

    return _viewer(
        card,
        signer.issue(
            card["id"],
            principal.user_id,
            "learner_catalog",
            content_id=content_id,
        ),
    )


@router.get('/learner/assignments/{assignment_id}/learning-cards')
async def assignment_learning_cards(assignment_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, 'cabinlingo', 'cabinlingo:learn')
    cards = store.list_assignment_learning_cards(assignment_id, principal.user_id)
    if cards is None:
        raise HTTPException(404, '任务不存在或未分配给当前学员')
    return cards


@router.post('/learner/learning-cards/{content_id}/read')
async def mark_learning_card_read(content_id: str, assignment_id: str = Query(...), principal: Principal = Depends(get_principal)):
    assert_permission(principal, 'cabinlingo', 'cabinlingo:learn')
    try:
        return store.mark_learning_card_read(content_id, assignment_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/learning-card-view/{token}/{resource_path:path}")
async def learning_card_resource(token: str, resource_path: str, request: Request):
    try:
        claims = signer.verify(token)
        if claims['scope'] == 'learner_view':
            card = store.get_learner_learning_card(
                claims.get('content_id', ''),
                claims.get('assignment_id', ''),
                claims['sub'],
            )
            if not card or card['id'] != claims['card_id']:
                raise LearningCardTokenError('revoked grant')
        elif claims['scope'] == 'learner_catalog':
            card = store.get_learner_catalog_learning_card(
                claims.get('content_id', ''),
                claims['sub'],
            )
            if not card or card['id'] != claims['card_id']:
                raise LearningCardTokenError('revoked grant')
        resource, blob = service.read_resource(str(claims["card_id"]), resource_path)
    except LearningCardTokenError as exc:
        raise HTTPException(401, "学习卡片访问地址已失效，请刷新页面") from exc
    except LearningCardPackageError as exc:
        raise HTTPException(404, str(exc)) from exc
    data = inject_viewer_bridge(blob.data) if resource_path == "index.html" else blob.data
    resource_base = str(request.base_url).rstrip('/') + f'/api/v1/cabinlingo/learning-card-view/{token}/'
    csp = (
        "sandbox allow-scripts; default-src 'none'; base-uri 'none'; object-src 'none'; "
        "frame-src 'none'; child-src 'none'; worker-src 'none'; manifest-src 'none'; "
        "form-action 'none'; frame-ancestors 'self'; "
        f"script-src {resource_base} 'unsafe-inline'; style-src {resource_base} 'unsafe-inline'; "
        f"img-src {resource_base} data: blob:; font-src {resource_base} data:; "
        f"media-src {resource_base} data: blob:; connect-src {resource_base}"
    )
    headers = {
        "Content-Security-Policy": csp,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Disposition": "inline",
        "Access-Control-Allow-Origin": "null",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    }
    return Response(data, media_type=resource.get("mime_type") or blob.content_type, headers=headers)
