from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ...core.config import settings
from .broadcast_service import (
    BroadcastLibraryError,
    broadcast_script_type_filter_values,
    split_broadcast_text,
    validate_version_for_freeze,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryBroadcastRepository:
    """Local/test repository. Production selects PostgreSQL through the factory below."""

    def __init__(self) -> None:
        self.scripts: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, dict[str, Any]] = {}
        self.slices: dict[str, dict[str, Any]] = {}

    def _require_script(self, script_id: str) -> dict[str, Any]:
        item = self.scripts.get(script_id)
        if not item:
            raise BroadcastLibraryError("Broadcast script not found", 404)
        return item

    def _require_version(self, version_id: str) -> dict[str, Any]:
        item = self.versions.get(version_id)
        if not item:
            raise BroadcastLibraryError("Broadcast script version not found", 404)
        return item

    def _editable(self, version_id: str) -> dict[str, Any]:
        version = self._require_version(version_id)
        if version["frozen"]:
            raise BroadcastLibraryError("Frozen versions are read-only")
        return version

    def _version_slices(self, version_id: str) -> list[dict[str, Any]]:
        return sorted(
            (item for item in self.slices.values() if item["version_id"] == version_id),
            key=lambda item: item["slice_no"],
        )

    def _version_out(self, version: dict[str, Any]) -> dict[str, Any]:
        return {**version, "slice_count": len(self._version_slices(version["id"]))}

    def _version_ready(self, version: dict[str, Any]) -> bool:
        slices = self._version_slices(version["id"])
        return bool(
            version["full_text"].strip()
            and slices
            and not version["slices_stale"]
            and "".join(item["text"] for item in slices) == version["full_text"]
        )

    def _script_out(self, script: dict[str, Any]) -> dict[str, Any]:
        versions = sorted(
            (item for item in self.versions.values() if item["script_id"] == script["id"]),
            key=lambda item: item["version"],
            reverse=True,
        )
        latest = versions[0]
        return {
            **script,
            "company_name": None,
            "latest_version_id": latest["id"],
            "latest_version": latest["version"],
            "frozen": latest["frozen"],
            "slice_count": len(self._version_slices(latest["id"])),
            "ready": self._version_ready(latest),
        }

    def _sync_positions(self, version_id: str) -> None:
        version = self._require_version(version_id)
        position = 0
        joined: list[str] = []
        now = _now()
        for number, item in enumerate(self._version_slices(version_id), start=1):
            item["slice_no"] = number
            item["start_char"] = position
            position += len(item["text"])
            item["end_char"] = position
            item["updated_at"] = now
            joined.append(item["text"])
        version["slices_stale"] = "".join(joined) != version["full_text"]
        version["updated_at"] = now
        self.scripts[version["script_id"]]["enabled"] = False
        self.scripts[version["script_id"]]["updated_at"] = now

    def list_scripts(self, **filters: Any) -> dict[str, Any]:
        items = [self._script_out(item) for item in self.scripts.values()]
        keyword = str(filters.get("keyword") or "").lower()
        if keyword:
            items = [item for item in items if keyword in f"{item['title']} {item['script_type']} {item.get('category') or ''}".lower()]
        for key in ("language", "company_id", "frozen", "enabled"):
            value = filters.get(key)
            if value is not None:
                items = [item for item in items if item.get(key) == value]
        if filters.get("script_type") is not None:
            allowed_types = broadcast_script_type_filter_values(str(filters["script_type"]))
            items = [item for item in items if item.get("script_type") in allowed_types]
        archived = bool(filters.get("archived", False))
        items = [item for item in items if (item["status"] == "archived") == archived]
        items.sort(key=lambda item: (item["updated_at"], item["title"]), reverse=True)
        total = len(items)
        page = int(filters.get("page", 1))
        page_size = int(filters.get("page_size", 20))
        start = (page - 1) * page_size
        return {"items": items[start:start + page_size], "total": total, "page": page, "page_size": page_size}

    def create_script(self, data: dict[str, Any], created_by: str) -> dict[str, Any]:
        now = _now()
        script_id = str(uuid4())
        version_id = str(uuid4())
        script = {
            "id": script_id, "title": data["title"], "language": data["language"],
            "script_type": data["script_type"], "category": data.get("category"),
            "company_id": data.get("company_id"), "status": "draft", "enabled": False, "created_by": created_by,
            "created_at": now, "updated_at": now, "archived_at": None,
        }
        version = {
            "id": version_id, "script_id": script_id, "version": 1,
            "full_text": data.get("full_text", ""), "frozen": False, "slices_stale": False,
            "created_by": created_by, "created_at": now, "updated_at": now, "frozen_at": None,
        }
        self.scripts[script_id] = script
        self.versions[version_id] = version
        return self._script_out(script)

    def get_script(self, script_id: str) -> dict[str, Any]:
        return self._script_out(self._require_script(script_id))

    def update_script(self, script_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        script = self._require_script(script_id)
        if script["status"] == "archived":
            raise BroadcastLibraryError("Archived scripts cannot be edited")
        if changes.get("enabled") is True:
            latest = max(
                (item for item in self.versions.values() if item["script_id"] == script_id),
                key=lambda item: item["version"],
            )
            if not self._version_ready(latest):
                raise BroadcastLibraryError("Complete the text and matching slices before enabling", 409)
        for key in ("title", "language", "script_type", "category", "company_id", "enabled"):
            if key in changes:
                script[key] = changes[key]
        script["updated_at"] = _now()
        return self._script_out(script)

    def archive_script(self, script_id: str) -> dict[str, Any]:
        script = self._require_script(script_id)
        script["status"] = "archived"
        script["enabled"] = False
        script["archived_at"] = script["archived_at"] or _now()
        script["updated_at"] = _now()
        return self._script_out(script)

    def list_versions(self, script_id: str) -> list[dict[str, Any]]:
        self._require_script(script_id)
        return [self._version_out(item) for item in sorted(
            (version for version in self.versions.values() if version["script_id"] == script_id),
            key=lambda version: version["version"], reverse=True,
        )]

    def create_version(self, script_id: str, full_text: str | None, created_by: str) -> dict[str, Any]:
        script = self._require_script(script_id)
        if script["status"] == "archived":
            raise BroadcastLibraryError("Archived scripts cannot receive new versions")
        existing = self.list_versions(script_id)
        latest = existing[0]
        now = _now()
        version = {
            "id": str(uuid4()), "script_id": script_id, "version": latest["version"] + 1,
            "full_text": latest["full_text"] if full_text is None else full_text,
            "frozen": False, "slices_stale": False, "created_by": created_by,
            "created_at": now, "updated_at": now, "frozen_at": None,
        }
        self.versions[version["id"]] = version
        script["updated_at"] = now
        return self._version_out(version)

    def get_version(self, version_id: str) -> dict[str, Any]:
        return self._version_out(self._require_version(version_id))

    def update_full_text(self, version_id: str, full_text: str) -> dict[str, Any]:
        version = self._editable(version_id)
        count = len(self._version_slices(version_id))
        changed = version["full_text"] != full_text
        version["full_text"] = full_text
        version["slices_stale"] = version["slices_stale"] or (changed and count > 0)
        version["updated_at"] = _now()
        self.scripts[version["script_id"]]["enabled"] = False
        self.scripts[version["script_id"]]["updated_at"] = version["updated_at"]
        return {"status": "updated", "slice_count": count, "requires_slice_regeneration": version["slices_stale"], "version": self._version_out(version)}

    def list_slices(self, version_id: str) -> list[dict[str, Any]]:
        self._require_version(version_id)
        return [dict(item) for item in self._version_slices(version_id)]

    def generate_slices(self, version_id: str, max_chars: int) -> list[dict[str, Any]]:
        version = self._editable(version_id)
        generated = split_broadcast_text(version["full_text"], max_chars=max_chars)
        for item_id in [item["id"] for item in self._version_slices(version_id)]:
            del self.slices[item_id]
        now = _now()
        for number, generated_slice in enumerate(generated, start=1):
            item = {
                "id": str(uuid4()), "version_id": version_id, "slice_no": number,
                "text": generated_slice.text, "start_char": generated_slice.start_char,
                "end_char": generated_slice.end_char, "verified": False,
                "created_at": now, "updated_at": now,
            }
            self.slices[item["id"]] = item
        version["slices_stale"] = False
        version["updated_at"] = now
        self.scripts[version["script_id"]]["enabled"] = False
        self.scripts[version["script_id"]]["updated_at"] = now
        return self.list_slices(version_id)

    def create_slice(self, version_id: str, text: str, position: int | None, verified: bool) -> dict[str, Any]:
        self._editable(version_id)
        rows = self._version_slices(version_id)
        insert_at = len(rows) + 1 if position is None else position
        if insert_at < 1 or insert_at > len(rows) + 1:
            raise BroadcastLibraryError("Slice position is outside the valid range", 422)
        for item in rows[insert_at - 1:]:
            item["slice_no"] += 1
        now = _now()
        created = {
            "id": str(uuid4()), "version_id": version_id, "slice_no": insert_at,
            "text": text, "start_char": 0, "end_char": len(text), "verified": verified,
            "created_at": now, "updated_at": now,
        }
        self.slices[created["id"]] = created
        self._sync_positions(version_id)
        return dict(created)

    def update_slice(self, slice_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        item = self.slices.get(slice_id)
        if not item:
            raise BroadcastLibraryError("Broadcast slice not found", 404)
        self._editable(item["version_id"])
        for key in ("text", "verified"):
            if key in changes:
                item[key] = changes[key]
        item["updated_at"] = _now()
        self._sync_positions(item["version_id"])
        return dict(item)

    def delete_slice(self, slice_id: str) -> dict[str, Any]:
        item = self.slices.get(slice_id)
        if not item:
            raise BroadcastLibraryError("Broadcast slice not found", 404)
        self._editable(item["version_id"])
        deleted = dict(item)
        del self.slices[slice_id]
        self._sync_positions(item["version_id"])
        return deleted

    def reorder_slices(self, version_id: str, slice_ids: list[str]) -> list[dict[str, Any]]:
        self._editable(version_id)
        current = self._version_slices(version_id)
        current_ids = [item["id"] for item in current]
        if len(slice_ids) != len(set(slice_ids)):
            raise BroadcastLibraryError("slice_ids cannot contain duplicates", 422)
        if len(slice_ids) != len(current_ids) or set(slice_ids) != set(current_ids):
            raise BroadcastLibraryError("slice_ids must contain every slice from this version exactly once", 422)
        for number, slice_id in enumerate(slice_ids, start=1):
            self.slices[slice_id]["slice_no"] = number
        self._sync_positions(version_id)
        return self.list_slices(version_id)

    def freeze_version(self, version_id: str) -> dict[str, Any]:
        version = self._require_version(version_id)
        slices = self._version_slices(version_id)
        validate_version_for_freeze(version, slices)
        version["frozen"] = True
        version["frozen_at"] = _now()
        version["updated_at"] = version["frozen_at"]
        self.scripts[version["script_id"]]["updated_at"] = version["updated_at"]
        return self._version_out(version)


class PostgresBroadcastRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL persistence") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _script_select(where: str = "s.id=%s") -> str:
        return f"""SELECT s.id::text AS id,s.title,s.language,s.script_type,s.category,
                  s.company_id::text AS company_id,o.name AS company_name,s.status,s.enabled,
                  latest.id::text AS latest_version_id,latest.version AS latest_version,
                  latest.frozen,COALESCE(latest.slice_count,0)::int AS slice_count,latest.ready,
                  s.created_by::text AS created_by,s.created_at,s.updated_at,s.archived_at
                  FROM cl_broadcast_scripts s
                  LEFT JOIN organizations o ON o.id=s.company_id
                  JOIN LATERAL (
                    SELECT v.id,v.version,v.frozen,
                           (SELECT count(*) FROM cl_broadcast_script_slices sl WHERE sl.version_id=v.id) AS slice_count,
                           (length(btrim(v.full_text))>0 AND NOT v.slices_stale
                            AND (SELECT count(*) FROM cl_broadcast_script_slices sl WHERE sl.version_id=v.id)>0
                            AND COALESCE((SELECT string_agg(sl.text,'' ORDER BY sl.slice_no)
                                          FROM cl_broadcast_script_slices sl WHERE sl.version_id=v.id),'')=v.full_text) AS ready
                    FROM cl_broadcast_script_versions v WHERE v.script_id=s.id
                    ORDER BY v.version DESC LIMIT 1
                  ) latest ON true WHERE {where}"""

    @staticmethod
    def _version_select(where: str = "v.id=%s") -> str:
        return f"""SELECT v.id::text AS id,v.script_id::text AS script_id,v.version,v.full_text,
                  v.frozen,v.slices_stale,v.created_by::text AS created_by,v.created_at,
                  v.updated_at,v.frozen_at,count(sl.id)::int AS slice_count
                  FROM cl_broadcast_script_versions v
                  LEFT JOIN cl_broadcast_script_slices sl ON sl.version_id=v.id
                  WHERE {where} GROUP BY v.id"""

    def list_scripts(self, **filters: Any) -> dict[str, Any]:
        clauses = ["s.status=%s"]
        params: list[Any] = ["archived" if filters.get("archived") else "draft"]
        if filters.get("keyword"):
            clauses.append("(s.title ILIKE %s OR s.script_type ILIKE %s OR COALESCE(s.category,'') ILIKE %s)")
            keyword = f"%{filters['keyword']}%"
            params.extend([keyword, keyword, keyword])
        for key, column in (("language", "s.language"), ("company_id", "s.company_id")):
            if filters.get(key) is not None:
                clauses.append(f"{column}=%s")
                params.append(filters[key])
        if filters.get("script_type") is not None:
            clauses.append("s.script_type=ANY(%s)")
            params.append(list(broadcast_script_type_filter_values(str(filters["script_type"]))))
        if filters.get("frozen") is not None:
            clauses.append("latest.frozen=%s")
            params.append(filters["frozen"])
        if filters.get("enabled") is not None:
            clauses.append("s.enabled=%s")
            params.append(filters["enabled"])
        where = " AND ".join(clauses)
        page = int(filters.get("page", 1))
        page_size = int(filters.get("page_size", 20))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"""SELECT count(*)::int AS total FROM cl_broadcast_scripts s
                         JOIN LATERAL (SELECT v.frozen FROM cl_broadcast_script_versions v
                           WHERE v.script_id=s.id ORDER BY v.version DESC LIMIT 1) latest ON true
                         WHERE {where}""", params)
            total = cur.fetchone()["total"]
            cur.execute(self._script_select(where) + " ORDER BY s.updated_at DESC,s.title LIMIT %s OFFSET %s", (*params, page_size, (page - 1) * page_size))
            items = [dict(row) for row in cur.fetchall()]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def create_script(self, data: dict[str, Any], created_by: str) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO cl_broadcast_scripts(title,language,script_type,category,company_id,created_by)
                               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id::text AS id""",
                            (data["title"], data["language"], data["script_type"], data.get("category"), data.get("company_id"), created_by))
                script_id = cur.fetchone()["id"]
                cur.execute("""INSERT INTO cl_broadcast_script_versions(script_id,version,full_text,created_by)
                               VALUES (%s,1,%s,%s)""", (script_id, data.get("full_text", ""), created_by))
            return self.get_script(script_id)
        except BroadcastLibraryError:
            raise
        except Exception as exc:
            raise BroadcastLibraryError("Broadcast script could not be created", 422) from exc

    def get_script(self, script_id: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._script_select(), (script_id,))
            row = cur.fetchone()
        if not row:
            raise BroadcastLibraryError("Broadcast script not found", 404)
        return dict(row)

    def update_script(self, script_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        allowed = {key: changes[key] for key in ("title", "language", "script_type", "category", "company_id", "enabled") if key in changes}
        if not allowed:
            return self.get_script(script_id)
        assignments = ",".join(f"{key}=%s" for key in allowed)
        try:
            with self._connect() as conn, conn.cursor() as cur:
                if allowed.get("enabled") is True:
                    cur.execute("""SELECT v.full_text,v.slices_stale,
                                  count(sl.id)::int AS slice_count,
                                  COALESCE(string_agg(sl.text,'' ORDER BY sl.slice_no),'') AS joined_text
                                  FROM cl_broadcast_script_versions v
                                  LEFT JOIN cl_broadcast_script_slices sl ON sl.version_id=v.id
                                  WHERE v.script_id=%s
                                  GROUP BY v.id ORDER BY v.version DESC LIMIT 1""", (script_id,))
                    latest = cur.fetchone()
                    if not latest or not latest["full_text"].strip() or latest["slices_stale"] or latest["slice_count"] < 1 or latest["joined_text"] != latest["full_text"]:
                        raise BroadcastLibraryError("Complete the text and matching slices before enabling", 409)
                cur.execute(f"""UPDATE cl_broadcast_scripts SET {assignments},updated_at=now()
                               WHERE id=%s AND status<>'archived' RETURNING id""", (*allowed.values(), script_id))
                if not cur.fetchone():
                    cur.execute("SELECT status FROM cl_broadcast_scripts WHERE id=%s", (script_id,))
                    row = cur.fetchone()
                    if not row:
                        raise BroadcastLibraryError("Broadcast script not found", 404)
                    raise BroadcastLibraryError("Archived scripts cannot be edited")
            return self.get_script(script_id)
        except BroadcastLibraryError:
            raise
        except Exception as exc:
            raise BroadcastLibraryError("Broadcast script could not be updated", 422) from exc

    def archive_script(self, script_id: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE cl_broadcast_scripts SET status='archived',enabled=false,archived_at=COALESCE(archived_at,now()),updated_at=now()
                           WHERE id=%s RETURNING id""", (script_id,))
            if not cur.fetchone():
                raise BroadcastLibraryError("Broadcast script not found", 404)
        return self.get_script(script_id)

    def list_versions(self, script_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM cl_broadcast_scripts WHERE id=%s", (script_id,))
            if not cur.fetchone():
                raise BroadcastLibraryError("Broadcast script not found", 404)
            cur.execute(self._version_select("v.script_id=%s") + " ORDER BY v.version DESC", (script_id,))
            return [dict(row) for row in cur.fetchall()]

    def create_version(self, script_id: str, full_text: str | None, created_by: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM cl_broadcast_scripts WHERE id=%s FOR UPDATE", (script_id,))
            script = cur.fetchone()
            if not script:
                raise BroadcastLibraryError("Broadcast script not found", 404)
            if script["status"] == "archived":
                raise BroadcastLibraryError("Archived scripts cannot receive new versions")
            cur.execute("""SELECT version,full_text FROM cl_broadcast_script_versions
                           WHERE script_id=%s ORDER BY version DESC LIMIT 1 FOR UPDATE""", (script_id,))
            latest = cur.fetchone()
            cur.execute("""INSERT INTO cl_broadcast_script_versions(script_id,version,full_text,created_by)
                           VALUES (%s,%s,%s,%s) RETURNING id::text AS id""",
                        (script_id, latest["version"] + 1, latest["full_text"] if full_text is None else full_text, created_by))
            version_id = cur.fetchone()["id"]
            cur.execute("UPDATE cl_broadcast_scripts SET enabled=false,updated_at=now() WHERE id=%s", (script_id,))
        return self.get_version(version_id)

    def get_version(self, version_id: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._version_select(), (version_id,))
            row = cur.fetchone()
        if not row:
            raise BroadcastLibraryError("Broadcast script version not found", 404)
        return dict(row)

    @staticmethod
    def _lock_editable_version(cur: Any, version_id: str) -> dict[str, Any]:
        cur.execute("""SELECT id::text AS id,script_id::text AS script_id,full_text,frozen,slices_stale
                       FROM cl_broadcast_script_versions WHERE id=%s FOR UPDATE""", (version_id,))
        version = cur.fetchone()
        if not version:
            raise BroadcastLibraryError("Broadcast script version not found", 404)
        if version["frozen"]:
            raise BroadcastLibraryError("Frozen versions are read-only")
        return dict(version)

    @staticmethod
    def _fetch_slices(cur: Any, version_id: str) -> list[dict[str, Any]]:
        cur.execute("""SELECT id::text AS id,version_id::text AS version_id,slice_no,text,start_char,end_char,
                       verified,created_at,updated_at FROM cl_broadcast_script_slices
                       WHERE version_id=%s ORDER BY slice_no FOR UPDATE""", (version_id,))
        return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _renumber(cur: Any, version_id: str, ordered_ids: list[str]) -> None:
        cur.execute("UPDATE cl_broadcast_script_slices SET slice_no=slice_no+1000000 WHERE version_id=%s", (version_id,))
        for number, slice_id in enumerate(ordered_ids, start=1):
            cur.execute("UPDATE cl_broadcast_script_slices SET slice_no=%s,updated_at=now() WHERE id=%s AND version_id=%s", (number, slice_id, version_id))

    @classmethod
    def _sync_positions(cls, cur: Any, version_id: str) -> None:
        rows = cls._fetch_slices(cur, version_id)
        position = 0
        joined: list[str] = []
        for number, row in enumerate(rows, start=1):
            end = position + len(row["text"])
            cur.execute("""UPDATE cl_broadcast_script_slices SET slice_no=%s,start_char=%s,end_char=%s,updated_at=now()
                           WHERE id=%s""", (number, position, end, row["id"]))
            position = end
            joined.append(row["text"])
        cur.execute("""UPDATE cl_broadcast_script_versions SET slices_stale=(full_text<>%s),updated_at=now()
                       WHERE id=%s RETURNING script_id""", ("".join(joined), version_id))
        version = cur.fetchone()
        cur.execute("UPDATE cl_broadcast_scripts SET enabled=false,updated_at=now() WHERE id=%s", (version["script_id"],))

    def update_full_text(self, version_id: str, full_text: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            version = self._lock_editable_version(cur, version_id)
            cur.execute("SELECT count(*)::int AS count FROM cl_broadcast_script_slices WHERE version_id=%s", (version_id,))
            count = cur.fetchone()["count"]
            stale = bool(version["slices_stale"] or (version["full_text"] != full_text and count > 0))
            cur.execute("""UPDATE cl_broadcast_script_versions SET full_text=%s,slices_stale=%s,updated_at=now()
                           WHERE id=%s""", (full_text, stale, version_id))
            cur.execute("UPDATE cl_broadcast_scripts SET enabled=false,updated_at=now() WHERE id=%s", (version["script_id"],))
        return {"status": "updated", "slice_count": count, "requires_slice_regeneration": stale, "version": self.get_version(version_id)}

    def list_slices(self, version_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM cl_broadcast_script_versions WHERE id=%s", (version_id,))
            if not cur.fetchone():
                raise BroadcastLibraryError("Broadcast script version not found", 404)
            cur.execute("""SELECT id::text AS id,version_id::text AS version_id,slice_no,text,start_char,end_char,
                           verified,created_at,updated_at FROM cl_broadcast_script_slices
                           WHERE version_id=%s ORDER BY slice_no""", (version_id,))
            return [dict(row) for row in cur.fetchall()]

    def generate_slices(self, version_id: str, max_chars: int) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            version = self._lock_editable_version(cur, version_id)
            generated = split_broadcast_text(version["full_text"], max_chars=max_chars)
            cur.execute("DELETE FROM cl_broadcast_script_slices WHERE version_id=%s", (version_id,))
            for number, item in enumerate(generated, start=1):
                cur.execute("""INSERT INTO cl_broadcast_script_slices(version_id,slice_no,text,start_char,end_char,verified)
                               VALUES (%s,%s,%s,%s,%s,false)""",
                            (version_id, number, item.text, item.start_char, item.end_char))
            cur.execute("UPDATE cl_broadcast_script_versions SET slices_stale=false,updated_at=now() WHERE id=%s", (version_id,))
            cur.execute("UPDATE cl_broadcast_scripts SET enabled=false,updated_at=now() WHERE id=%s", (version["script_id"],))
        return self.list_slices(version_id)

    def create_slice(self, version_id: str, text: str, position: int | None, verified: bool) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            self._lock_editable_version(cur, version_id)
            rows = self._fetch_slices(cur, version_id)
            insert_at = len(rows) + 1 if position is None else position
            if insert_at < 1 or insert_at > len(rows) + 1:
                raise BroadcastLibraryError("Slice position is outside the valid range", 422)
            cur.execute("UPDATE cl_broadcast_script_slices SET slice_no=slice_no+1000000 WHERE version_id=%s", (version_id,))
            cur.execute("""INSERT INTO cl_broadcast_script_slices(version_id,slice_no,text,start_char,end_char,verified)
                           VALUES (%s,2000000000,%s,0,%s,%s) RETURNING id::text AS id""", (version_id, text, len(text), verified))
            created_id = cur.fetchone()["id"]
            ordered = [row["id"] for row in rows]
            ordered.insert(insert_at - 1, created_id)
            for number, ordered_id in enumerate(ordered, start=1):
                cur.execute("""UPDATE cl_broadcast_script_slices SET slice_no=%s,updated_at=now()
                               WHERE id=%s AND version_id=%s""", (number, ordered_id, version_id))
            self._sync_positions(cur, version_id)
            cur.execute("""SELECT id::text AS id,version_id::text AS version_id,slice_no,text,start_char,end_char,
                           verified,created_at,updated_at FROM cl_broadcast_script_slices WHERE id=%s""", (created_id,))
            return dict(cur.fetchone())

    def update_slice(self, slice_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT version_id::text AS version_id FROM cl_broadcast_script_slices WHERE id=%s", (slice_id,))
            item = cur.fetchone()
            if not item:
                raise BroadcastLibraryError("Broadcast slice not found", 404)
            self._lock_editable_version(cur, item["version_id"])
            allowed = {key: changes[key] for key in ("text", "verified") if key in changes}
            if allowed:
                assignments = ",".join(f"{key}=%s" for key in allowed)
                cur.execute(f"UPDATE cl_broadcast_script_slices SET {assignments},updated_at=now() WHERE id=%s", (*allowed.values(), slice_id))
            self._sync_positions(cur, item["version_id"])
            cur.execute("""SELECT id::text AS id,version_id::text AS version_id,slice_no,text,start_char,end_char,
                           verified,created_at,updated_at FROM cl_broadcast_script_slices WHERE id=%s""", (slice_id,))
            return dict(cur.fetchone())

    def delete_slice(self, slice_id: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id::text AS id,version_id::text AS version_id,slice_no,text,start_char,end_char,
                           verified,created_at,updated_at FROM cl_broadcast_script_slices WHERE id=%s""", (slice_id,))
            item = cur.fetchone()
            if not item:
                raise BroadcastLibraryError("Broadcast slice not found", 404)
            self._lock_editable_version(cur, item["version_id"])
            cur.execute("DELETE FROM cl_broadcast_script_slices WHERE id=%s", (slice_id,))
            rows = self._fetch_slices(cur, item["version_id"])
            self._renumber(cur, item["version_id"], [row["id"] for row in rows])
            self._sync_positions(cur, item["version_id"])
            return dict(item)

    def reorder_slices(self, version_id: str, slice_ids: list[str]) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            self._lock_editable_version(cur, version_id)
            rows = self._fetch_slices(cur, version_id)
            current_ids = [row["id"] for row in rows]
            if len(slice_ids) != len(set(slice_ids)):
                raise BroadcastLibraryError("slice_ids cannot contain duplicates", 422)
            if len(slice_ids) != len(current_ids) or set(slice_ids) != set(current_ids):
                raise BroadcastLibraryError("slice_ids must contain every slice from this version exactly once", 422)
            self._renumber(cur, version_id, slice_ids)
            self._sync_positions(cur, version_id)
        return self.list_slices(version_id)

    def freeze_version(self, version_id: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id::text AS id,script_id::text AS script_id,full_text,frozen,slices_stale
                           FROM cl_broadcast_script_versions WHERE id=%s FOR UPDATE""", (version_id,))
            version = cur.fetchone()
            if not version:
                raise BroadcastLibraryError("Broadcast script version not found", 404)
            slices = self._fetch_slices(cur, version_id)
            validate_version_for_freeze(dict(version), slices)
            cur.execute("""UPDATE cl_broadcast_script_versions SET frozen=true,frozen_at=now(),updated_at=now()
                           WHERE id=%s""", (version_id,))
            cur.execute("UPDATE cl_broadcast_scripts SET updated_at=now() WHERE id=%s", (version["script_id"],))
        return self.get_version(version_id)


def build_broadcast_repository():
    if settings.database_url:
        return PostgresBroadcastRepository(settings.database_url)
    if settings.is_production:
        raise RuntimeError("Production cannot use the in-memory broadcast repository")
    return InMemoryBroadcastRepository()
