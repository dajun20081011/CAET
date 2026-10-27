from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from ...integrations.oss import ObjectStorageAdapter, ObjectStorageError
from .learning_card_package import LearningCardPackageError, PackageLimits, parse_learning_card_package, _safe_path

logger = logging.getLogger(__name__)


@dataclass
class LearningCardService:
    store: Any
    storage: ObjectStorageAdapter
    limits: PackageLimits = PackageLimits()

    def import_package(self, body: bytes, filename: str, created_by: str) -> dict[str, Any]:
        if not filename.lower().endswith(".zip"):
            raise LearningCardPackageError("只支持 .zip 学习卡片课程包")
        package = parse_learning_card_package(body, self.limits)
        card_id = str(uuid4())
        storage_prefix = f"learning-cards/{card_id}"
        saved_refs: list[str] = []
        records: list[dict[str, Any]] = []
        try:
            for resource in package.resources:
                object_ref = self.storage.save(
                    f"{storage_prefix}/{resource.path}", resource.data, resource.mime_type,
                )
                saved_refs.append(object_ref)
                records.append({
                    "resource_path": resource.path, "object_ref": object_ref,
                    "mime_type": resource.mime_type, "byte_size": len(resource.data),
                    "sha256": resource.sha256,
                })
            return self.store.create_learning_card(
                card_id, package.manifest, storage_prefix, package.package_sha256, created_by, records,
            )
        except Exception:
            for object_ref in reversed(saved_refs):
                try:
                    self.storage.delete(object_ref)
                except Exception:
                    logger.warning('Learning card import cleanup incomplete: %s', card_id)
            raise

    def read_resource(self, card_id: str, resource_path: str):
        path = PurePosixPath(_safe_path(resource_path))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise LearningCardPackageError("课程资源路径不安全")
        resource = self.store.get_learning_card_resource(card_id, path.as_posix())
        if not resource:
            raise LearningCardPackageError("课程资源不存在")
        try:
            blob = self.storage.read(str(resource["object_ref"]))
            if sha256(blob.data).hexdigest() != resource['sha256']:
                raise LearningCardPackageError('课程资源校验失败')
            return resource, blob
        except ObjectStorageError as exc:
            raise LearningCardPackageError("课程资源不存在") from exc


def inject_viewer_bridge(html: bytes) -> bytes:
    """Add height reporting only; the original card DOM, styles and behavior remain intact."""
    bridge = b"""<script>(function(){var send=function(){try{parent.postMessage({type:'cabinlingo-learning-card-resize',height:Math.max(document.documentElement.scrollHeight,document.body?document.body.scrollHeight:0)},'*')}catch(e){}};addEventListener('load',send);addEventListener('resize',send);if(window.ResizeObserver)new ResizeObserver(send).observe(document.documentElement);setTimeout(send,120);setTimeout(send,600)})();</script>"""
    lowered = html.lower()
    marker = lowered.rfind(b"</body>")
    return html[:marker] + bridge + html[marker:] if marker >= 0 else html + bridge
