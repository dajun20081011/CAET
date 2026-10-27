"""PostgreSQL repository for CabinLingo.

The psycopg import is intentionally lazy so unit tests can run without a database driver.
Run migrations/0001_platform_cl_schema.sql before selecting this repository.
"""

from datetime import datetime, timezone
from html import escape
from typing import Any
from uuid import UUID, uuid4

from .domain import ExamAssignment, ExamTask, PracticeAssignment, PracticeAttempt, PracticeTask
from .practice_feedback import (
    collect_practice_feedback,
    instructor_review_issues,
    learner_visible_issues,
    suntone_evidence,
)


class PostgresStore:
    backend = "postgresql"

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgresStore")
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL persistence") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def healthcheck(self) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            return cur.fetchone()["ok"] == 1

    def seed_broadcast(self, code: str, title: str, segments: int = 0) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id::text AS id, code, title, language FROM cl_broadcasts WHERE code=%s", (code,))
                row = cur.fetchone()
                if row:
                    cur.execute("SELECT count(*) AS n FROM cl_segments WHERE broadcast_id=%s", (row["id"],))
                    row["segment_count"] = cur.fetchone()["n"]
                    return row
                cur.execute("INSERT INTO cl_broadcasts(code,title) VALUES (%s,%s) RETURNING id::text AS id, code, title, language", (code, title))
                row = cur.fetchone()
                for sequence in range(1, segments + 1):
                    cur.execute("INSERT INTO cl_segments(broadcast_id,sequence_no,reference_text) VALUES (%s,%s,%s)", (row["id"], sequence, f"{title} segment {sequence}"))
                row["segment_count"] = segments
                return row

    def list_broadcasts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT b.id::text AS id,b.code,b.title,b.language,b.status,count(s.id)::int AS segment_count
                              FROM cl_broadcasts b LEFT JOIN cl_segments s ON s.broadcast_id=b.id
                              GROUP BY b.id ORDER BY b.created_at""")
                return list(cur.fetchall())

    def create_broadcast(self, code: str, title: str, language: str, status: str, created_by: str | None = None) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO cl_broadcasts(code,title,language,status,created_by)
                          VALUES (%s,%s,%s,%s,%s)
                          RETURNING id::text AS id,code,title,language,status,0::int AS segment_count""", (code, title, language, status, created_by))
            return dict(cur.fetchone())

    def update_broadcast(self, broadcast_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {key: value for key, value in changes.items() if value is not None and key in {"title", "language", "status"}}
        if not allowed:
            return next((row for row in self.list_broadcasts() if row["id"] == broadcast_id), None)
        assignments = ", ".join(f"{key}=%s" for key in allowed)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE cl_broadcasts SET {assignments} WHERE id=%s RETURNING id::text AS id,code,title,language,status", (*allowed.values(), broadcast_id))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("SELECT count(*)::int AS segment_count FROM cl_segments WHERE broadcast_id=%s", (broadcast_id,))
            row["segment_count"] = cur.fetchone()["segment_count"]
            return dict(row)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT t.id::text AS id,t.title,t.broadcast_id::text AS broadcast_id,t.course_version_id::text AS course_version_id,
                          source_version.source_broadcast_script_id::text AS broadcast_script_id,
                          CASE WHEN source_course.category='broadcast_snapshot' THEN
                            (SELECT count(*)::int FROM cl_chapters ch WHERE ch.course_version_id=t.course_version_id)
                          ELSE 0 END AS broadcast_script_count,t.due_at,t.week_no,t.unlock_after_task_type,
                          t.unlock_after_task_id::text AS unlock_after_task_id,t.status,'practice' AS task_type,
                          (SELECT count(*)::int FROM cl_practice_assignments a WHERE a.task_id=t.id) AS assignment_count,
                          (SELECT count(*)::int FROM cl_practice_assignments a WHERE a.task_id=t.id AND a.status='completed') AS completed_count
                          FROM cl_practice_tasks t LEFT JOIN cl_course_versions source_version ON source_version.id=t.course_version_id
                          LEFT JOIN cl_courses source_course ON source_course.id=source_version.course_id
                          WHERE t.deleted_at IS NULL
                          UNION ALL
                          SELECT t.id::text AS id,t.title,t.broadcast_id::text AS broadcast_id,t.course_version_id::text AS course_version_id,
                          source_version.source_broadcast_script_id::text AS broadcast_script_id,
                          CASE WHEN source_course.category='broadcast_snapshot' THEN
                            (SELECT count(*)::int FROM cl_chapters ch WHERE ch.course_version_id=t.course_version_id)
                          ELSE 0 END AS broadcast_script_count,t.due_at,t.week_no,t.unlock_after_task_type,
                          t.unlock_after_task_id::text AS unlock_after_task_id,t.status,'exam' AS task_type,
                          (SELECT count(*)::int FROM cl_exam_assignments a WHERE a.exam_task_id=t.id) AS assignment_count,
                          (SELECT count(*)::int FROM cl_exam_assignments a WHERE a.exam_task_id=t.id AND a.status IN ('submitted','graded','published')) AS completed_count
                          FROM cl_exam_tasks t LEFT JOIN cl_course_versions source_version ON source_version.id=t.course_version_id
                          LEFT JOIN cl_courses source_course ON source_course.id=source_version.course_id
                          WHERE t.deleted_at IS NULL
                          ORDER BY due_at NULLS LAST""")
            return [dict(row) for row in cur.fetchall()]

    def set_task_status(self, task_type: str, task_id: str, status: str) -> dict[str, Any] | None:
        table = "cl_practice_tasks" if task_type == "practice" else "cl_exam_tasks"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE {table} SET status=%s WHERE id=%s AND deleted_at IS NULL RETURNING id", (status, task_id))
            if not cur.fetchone():
                return None
            cur.execute(f"""SELECT task.id::text AS id,task.title,task.broadcast_id::text AS broadcast_id,
                        task.course_version_id::text AS course_version_id,
                        source_version.source_broadcast_script_id::text AS broadcast_script_id,
                        CASE WHEN source_course.category='broadcast_snapshot' THEN
                          (SELECT count(*)::int FROM cl_chapters ch WHERE ch.course_version_id=task.course_version_id)
                        ELSE 0 END AS broadcast_script_count,
                        task.due_at,task.week_no,task.unlock_after_task_type,
                        task.unlock_after_task_id::text AS unlock_after_task_id,task.status FROM {table} task
                        LEFT JOIN cl_course_versions source_version ON source_version.id=task.course_version_id
                        LEFT JOIN cl_courses source_course ON source_course.id=source_version.course_id
                        WHERE task.id=%s AND task.deleted_at IS NULL""", (task_id,))
            row = dict(cur.fetchone()); row["task_type"] = task_type
            cur.execute(f"SELECT count(*)::int AS n FROM { 'cl_practice_assignments' if task_type == 'practice' else 'cl_exam_assignments' } WHERE { 'task_id' if task_type == 'practice' else 'exam_task_id' }=%s", (task_id,))
            row["assignment_count"] = cur.fetchone()["n"]; row["completed_count"] = 0
            return row

    def delete_task(self, task_type: str, task_id: str, deleted_by: str) -> bool:
        table = "cl_practice_tasks" if task_type == "practice" else "cl_exam_tasks"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET status='closed',deleted_at=now(),deleted_by=%s WHERE id=%s AND deleted_at IS NULL RETURNING id",
                (deleted_by, task_id),
            )
            return cur.fetchone() is not None

    def resolve_task_assignee_ids(self, user_ids: list[str], class_ids: list[str], task_type: str) -> list[str]:
        """Expand class targets into active learner IDs and enforce class type."""
        expected_class_type = "training" if task_type == "practice" else "assessment"
        targets = list(dict.fromkeys(user_ids))
        with self._connect() as conn, conn.cursor() as cur:
            if class_ids:
                cur.execute("SELECT id::text AS id,class_type,status FROM classes WHERE id = ANY(%s::uuid[])", (list(dict.fromkeys(class_ids)),))
                rows = [dict(row) for row in cur.fetchall()]
                found = {row["id"] for row in rows}
                missing = [item for item in class_ids if item not in found]
                if missing:
                    raise ValueError(f"Class not found: {', '.join(missing)}")
                wrong = [row["id"] for row in rows if row["status"] != "active" or row["class_type"] != expected_class_type]
                if wrong:
                    label = "练习" if task_type == "practice" else "考试"
                    raise ValueError(f"{label}任务只能发布给对应类型班级")
                cur.execute("""SELECT DISTINCT cm.user_id::text AS user_id
                               FROM class_memberships cm JOIN users u ON u.id=cm.user_id
                               WHERE cm.class_id=ANY(%s::uuid[]) AND cm.status='active' AND u.is_active=true
                                 AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                                            WHERE ur.user_id=u.id AND r.code='learner')""", (list(dict.fromkeys(class_ids)),))
                targets.extend(row["user_id"] for row in cur.fetchall())
            if not targets:
                raise ValueError("No active learner selected")
            cur.execute("""SELECT id::text AS id FROM users u
                           WHERE u.id=ANY(%s::uuid[]) AND u.is_active=true
                             AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                                        WHERE ur.user_id=u.id AND r.code='learner')""", (list(dict.fromkeys(targets)),))
            valid = {row["id"] for row in cur.fetchall()}
            invalid = [item for item in targets if item not in valid]
            if invalid:
                raise ValueError(f"Only active learner accounts can receive tasks: {', '.join(invalid)}")
        return list(dict.fromkeys(targets))

    def create_recording(self, assignment_id: str, purpose: str, audio_ref: str, duration_ms: int | None = None, content_item_id: str | None = None, mime_type: str | None = None, byte_size: int | None = None, checksum_sha256: str | None = None) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT assignment.user_id::text AS user_id FROM cl_practice_assignments assignment
                           JOIN cl_practice_tasks task ON task.id=assignment.task_id
                           WHERE assignment.id=%s AND task.deleted_at IS NULL
                           UNION ALL
                           SELECT assignment.user_id::text AS user_id FROM cl_exam_assignments assignment
                           JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                           WHERE assignment.id=%s AND task.deleted_at IS NULL""", (assignment_id, assignment_id))
            owner = cur.fetchone()
            if not owner:
                raise ValueError("Assignment not found")
            storage_provider = "oss" if audio_ref.startswith("oss://") else "local"
            object_key = audio_ref.removeprefix("/media/") if audio_ref.startswith("/media/") else audio_ref.split("/", 3)[-1]
            cur.execute("""INSERT INTO cl_recordings(user_id,purpose,duration_ms,audio_ref,processing_status,assignment_id,content_item_id,mime_type,byte_size,storage_provider,object_key,checksum_sha256)
                          VALUES (%s,%s,%s,%s,'uploaded',%s,%s,%s,%s,%s,%s,%s) RETURNING id::text AS id""",
                        (owner["user_id"], purpose, duration_ms, audio_ref, assignment_id, content_item_id, mime_type, byte_size, storage_provider, object_key, checksum_sha256))
            row = dict(cur.fetchone()); row.update({"assignment_id": assignment_id, "purpose": purpose, "audio_ref": audio_ref, "status": "uploaded", "content_item_id": content_item_id, "mime_type": mime_type, "byte_size": byte_size}); return row

    def get_recording_audio_ref(self, recording_id: str, assignment_id: str, user_id: str) -> str | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT recording.audio_ref FROM cl_recordings recording
                           WHERE recording.id=%s AND recording.assignment_id=%s AND recording.user_id=%s AND (
                             EXISTS (SELECT 1 FROM cl_practice_assignments assignment
                                     JOIN cl_practice_tasks task ON task.id=assignment.task_id
                                     WHERE assignment.id=recording.assignment_id AND task.deleted_at IS NULL)
                             OR EXISTS (SELECT 1 FROM cl_exam_assignments assignment
                                        JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                                        WHERE assignment.id=recording.assignment_id AND task.deleted_at IS NULL)
                           )""", (recording_id, assignment_id, user_id))
            row = cur.fetchone()
            return row["audio_ref"] if row else None

    def get_learner_recording(self, recording_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT recording.id::text AS id,recording.audio_ref,recording.mime_type,recording.byte_size
                           FROM cl_recordings recording WHERE recording.id=%s AND recording.user_id=%s AND (
                             EXISTS (SELECT 1 FROM cl_practice_assignments assignment
                                     JOIN cl_practice_tasks task ON task.id=assignment.task_id
                                     WHERE assignment.id=recording.assignment_id AND task.deleted_at IS NULL)
                             OR EXISTS (SELECT 1 FROM cl_exam_assignments assignment
                                        JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                                        WHERE assignment.id=recording.assignment_id AND task.deleted_at IS NULL)
                           )""", (recording_id, user_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_review_queue(self, instructor_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT a.id::text AS assignment_id,a.exam_task_id::text AS task_id,a.user_id::text AS user_id,a.status,a.submitted_at,
                          COALESCE((SELECT string_agg(DISTINCT r.status, ',') FROM cl_ai_results r JOIN cl_recordings rec ON rec.id=r.recording_id WHERE rec.user_id=a.user_id),'pending') AS ai_status,
                          COALESCE((SELECT mr.status FROM cl_manual_reviews mr WHERE mr.exam_assignment_id=a.id ORDER BY mr.id DESC LIMIT 1),'pending') AS manual_status
                          FROM cl_exam_assignments a JOIN cl_exam_tasks task ON task.id=a.exam_task_id
                          WHERE a.status IN ('submitted','graded') AND task.deleted_at IS NULL
                            AND (%s::uuid IS NULL OR EXISTS (
                              SELECT 1 FROM cl_evaluation_tasks evaluation
                              WHERE evaluation.exam_assignment_id=a.id
                                AND evaluation.instructor_id=%s::uuid
                                AND evaluation.status IN ('pending','in_progress','completed')
                            ))
                          ORDER BY a.submitted_at NULLS LAST""", (instructor_id, instructor_id))
            return [dict(row) for row in cur.fetchall()]

    def save_manual_review(self, assignment_id: str, reviewer_id: str, manual_score: float, comments: str, publish: bool) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cl_manual_reviews(exam_assignment_id,reviewer_id,status,comments,reviewed_at) VALUES (%s,%s,'completed',%s,now()) RETURNING id::text AS id", (assignment_id, reviewer_id, comments))
            review_id = cur.fetchone()["id"]
            cur.execute("INSERT INTO cl_scores(exam_assignment_id,manual_score,final_score,status,published_at) VALUES (%s,%s,%s,%s,CASE WHEN %s THEN now() ELSE NULL END)", (assignment_id, manual_score, manual_score, "published" if publish else "unpublished", publish))
            if publish:
                cur.execute("UPDATE cl_exam_assignments SET status='published' WHERE id=%s", (assignment_id,))
            return {"review_id": review_id, "assignment_id": assignment_id, "manual_score": manual_score, "status": "published" if publish else "completed"}

    def has_broadcast(self, broadcast_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM cl_broadcasts WHERE id=%s", (broadcast_id,))
                return cur.fetchone() is not None

    def has_course_version(self, course_version_id: str, published_only: bool = False) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM cl_course_versions WHERE id=%s", (course_version_id,))
            row = cur.fetchone()
            return bool(row and (not published_only or row["status"] == "published"))

    @staticmethod
    def _learning_card_record(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["metadata"] = dict(item.get("metadata") or {})
        return item

    def create_learning_card(self, card_id: str, manifest: dict[str, Any], storage_prefix: str,
                             package_sha256: str, created_by: str,
                             resources: list[dict[str, Any]]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO cl_learning_cards(
                          id,title,category,package_format,package_version,entry_file,storage_prefix,
                          package_sha256,metadata,resource_count,created_by)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          RETURNING id::text AS id,title,category,package_format,package_version,entry_file,
                          storage_prefix,package_sha256,metadata,resource_count,status,created_by::text AS created_by,
                          created_at,updated_at,archived_at,0::int AS course_count""",
                        (card_id, manifest["title"], manifest["category"], manifest["format"], manifest["version"],
                         manifest["entry"], storage_prefix, package_sha256, Jsonb(manifest), len(resources), created_by))
            card = self._learning_card_record(cur.fetchone())
            for resource in resources:
                cur.execute("""INSERT INTO cl_learning_card_resources(
                              learning_card_id,resource_path,object_ref,mime_type,byte_size,sha256)
                              VALUES (%s,%s,%s,%s,%s,%s)""",
                            (card_id, resource["resource_path"], resource["object_ref"], resource["mime_type"],
                             resource["byte_size"], resource["sha256"]))
            return card

    def list_learning_cards(self, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT card.id::text AS id,card.title,card.category,card.package_format,card.package_version,
                          card.entry_file,card.storage_prefix,card.package_sha256,card.metadata,card.resource_count,
                          card.status,card.created_by::text AS created_by,card.created_at,card.updated_at,card.archived_at,
                          count(DISTINCT version.course_id)::int AS course_count
                          FROM cl_learning_cards card
                          LEFT JOIN cl_content_items content ON content.learning_card_id=card.id
                          LEFT JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          LEFT JOIN cl_course_versions version ON version.id=chapter.course_version_id
                          WHERE (%s OR card.status<>'archived')
                          GROUP BY card.id ORDER BY card.created_at DESC""", (include_archived,))
            return [self._learning_card_record(row) for row in cur.fetchall()]

    def get_learning_card(self, card_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT card.id::text AS id,card.title,card.category,card.package_format,card.package_version,
                          card.entry_file,card.storage_prefix,card.package_sha256,card.metadata,card.resource_count,
                          card.status,card.created_by::text AS created_by,card.created_at,card.updated_at,card.archived_at,
                          count(DISTINCT version.course_id)::int AS course_count
                          FROM cl_learning_cards card
                          LEFT JOIN cl_content_items content ON content.learning_card_id=card.id
                          LEFT JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          LEFT JOIN cl_course_versions version ON version.id=chapter.course_version_id
                          WHERE card.id=%s GROUP BY card.id""", (card_id,))
            row = cur.fetchone()
            return self._learning_card_record(row) if row else None

    def get_learning_card_resource(self, card_id: str, resource_path: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id::text AS id,learning_card_id::text AS learning_card_id,resource_path,
                          object_ref,mime_type,byte_size,sha256
                          FROM cl_learning_card_resources WHERE learning_card_id=%s AND resource_path=%s""",
                        (card_id, resource_path))
            row = cur.fetchone()
            return dict(row) if row else None

    def archive_learning_card(self, card_id: str) -> dict[str, Any] | None:
        updated = False
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE cl_learning_cards SET status='archived',archived_at=COALESCE(archived_at,now()),updated_at=now()
                          WHERE id=%s RETURNING id::text AS id""", (card_id,))
            updated = bool(cur.fetchone())
        return self.get_learning_card(card_id) if updated else None

    def _clone_course_version_for_learning_card(self, cur: Any, course_id: str, source_version_id: str,
                                                created_by: str) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        cur.execute("SELECT COALESCE(max(version_no),0)+1 AS next_no FROM cl_course_versions WHERE course_id=%s", (course_id,))
        next_no = int(cur.fetchone()["next_no"])
        cur.execute("""INSERT INTO cl_course_versions(course_id,version_no,version_label,change_summary,created_by)
                      VALUES (%s,%s,%s,'加入学习卡片',%s)
                      RETURNING id::text AS id,course_id::text AS course_id,version_no,version_label,status""",
                    (course_id, next_no, f"V{next_no}.0-LC", created_by))
        version = dict(cur.fetchone())
        cur.execute("""SELECT id::text AS id,code,title,sequence_no,learning_objective
                      FROM cl_chapters WHERE course_version_id=%s ORDER BY sequence_no""", (source_version_id,))
        for source_chapter in cur.fetchall():
            cur.execute("""INSERT INTO cl_chapters(course_version_id,code,title,sequence_no,learning_objective)
                          VALUES (%s,%s,%s,%s,%s) RETURNING id::text AS id""",
                        (version["id"], source_chapter["code"], source_chapter["title"],
                         source_chapter["sequence_no"], source_chapter["learning_objective"]))
            chapter_id = cur.fetchone()["id"]
            cur.execute("""SELECT id::text AS id,content_type,title,sequence_no,source_filename,sanitized_html,
                          original_sha256,sanitized_sha256,validation_report,document_file_id,
                          document_page_no,document_page_count,learning_card_id
                          FROM cl_content_items WHERE chapter_id=%s ORDER BY sequence_no""", (source_chapter["id"],))
            for source_content in cur.fetchall():
                cur.execute("""INSERT INTO cl_content_items(
                              chapter_id,content_type,title,sequence_no,source_filename,sanitized_html,
                              original_sha256,sanitized_sha256,validation_report,document_file_id,
                              document_page_no,document_page_count,learning_card_id,created_by)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                              RETURNING id::text AS id""",
                            (chapter_id, source_content["content_type"], source_content["title"],
                             source_content["sequence_no"], source_content["source_filename"],
                             source_content["sanitized_html"], source_content["original_sha256"],
                             source_content["sanitized_sha256"], Jsonb(source_content["validation_report"] or {}),
                             source_content["document_file_id"], source_content["document_page_no"],
                             source_content["document_page_count"], source_content["learning_card_id"], created_by))
                content_id = cur.fetchone()["id"]
                cur.execute("""INSERT INTO cl_content_assets(content_item_id,file_id,asset_role,original_filename)
                              SELECT %s,file_id,asset_role,original_filename FROM cl_content_assets WHERE content_item_id=%s""",
                            (content_id, source_content["id"]))
                cur.execute("""INSERT INTO cl_course_standards(
                              content_item_id,standard_text,standard_audio_file_id,pronunciation_rules,prosody_rules,
                              expression_rules,rule_version,created_by,change_summary,standard_audio_filename,created_at)
                              SELECT %s,standard_text,standard_audio_file_id,pronunciation_rules,prosody_rules,
                              expression_rules,rule_version,%s,change_summary,standard_audio_filename,created_at
                              FROM cl_course_standards WHERE content_item_id=%s""",
                            (content_id, created_by, source_content["id"]))
                cur.execute("""INSERT INTO cl_content_interactions(
                              content_item_id,interaction_type,title,prompt,config,sequence_no,required,status,
                              version_no,created_by,created_at,updated_at)
                              SELECT %s,interaction_type,title,prompt,config,sequence_no,required,status,
                              version_no,%s,created_at,updated_at FROM cl_content_interactions WHERE content_item_id=%s""",
                            (content_id, created_by, source_content["id"]))
        return version

    def add_learning_card_to_course(self, card_id: str, course_id: str, created_by: str) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT id::text AS id,title,status,package_sha256,package_version FROM cl_learning_cards WHERE id=%s FOR UPDATE", (card_id,))
                card = cur.fetchone()
                if not card or card["status"] != "active":
                    raise ValueError("Learning Card 不存在或已归档")
                cur.execute("SELECT id::text AS id,title,status FROM cl_courses WHERE id=%s FOR UPDATE", (course_id,))
                course = cur.fetchone()
                if not course or course["status"] == "archived":
                    raise ValueError("课程不存在或已归档")
                cur.execute("""SELECT id::text AS id,course_id::text AS course_id,version_no,version_label,status
                              FROM cl_course_versions WHERE course_id=%s AND status='draft'
                              ORDER BY version_no DESC LIMIT 1""", (course_id,))
                version = cur.fetchone()
                if not version:
                    cur.execute("""SELECT id::text AS id FROM cl_course_versions
                                  WHERE course_id=%s AND status='published' ORDER BY version_no DESC LIMIT 1""", (course_id,))
                    published = cur.fetchone()
                    if published:
                        version = self._clone_course_version_for_learning_card(cur, course_id, published["id"], created_by)
                    else:
                        cur.execute("SELECT COALESCE(max(version_no),0)+1 AS next_no FROM cl_course_versions WHERE course_id=%s", (course_id,))
                        next_no = int(cur.fetchone()["next_no"])
                        cur.execute("""INSERT INTO cl_course_versions(course_id,version_no,version_label,change_summary,created_by)
                                      VALUES (%s,%s,%s,'加入学习卡片',%s)
                                      RETURNING id::text AS id,course_id::text AS course_id,version_no,version_label,status""",
                                    (course_id, next_no, f"V{next_no}.0-LC", created_by))
                        version = cur.fetchone()
                cur.execute("""SELECT 1 FROM cl_content_items content JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                              WHERE chapter.course_version_id=%s AND content.learning_card_id=%s""", (version["id"], card_id))
                if cur.fetchone():
                    raise ValueError("该学习卡片已加入当前课程草稿")
                cur.execute("SELECT COALESCE(max(sequence_no),0)+1 AS next_sequence FROM cl_chapters WHERE course_version_id=%s", (version["id"],))
                sequence = int(cur.fetchone()["next_sequence"])
                cur.execute("""INSERT INTO cl_chapters(course_version_id,code,title,sequence_no,learning_objective)
                              VALUES (%s,%s,%s,%s,'完成学习卡片内容') RETURNING id::text AS id""",
                            (version["id"], f"LC-{card_id[:8].upper()}", card["title"], sequence))
                chapter_id = cur.fetchone()["id"]
                placeholder = f"<p>{escape(str(card['title']))}</p>"
                cur.execute("""INSERT INTO cl_content_items(
                              chapter_id,content_type,title,sequence_no,source_filename,sanitized_html,
                              original_sha256,sanitized_sha256,validation_report,learning_card_id,created_by)
                              VALUES (%s,'html',%s,1,'learning-card.zip',%s,%s,%s,%s,%s,%s)
                              RETURNING id::text AS id""",
                            (chapter_id, card["title"], placeholder, card["package_sha256"], card["package_sha256"],
                             Jsonb({"source_type": "learning_card", "package_version": card["package_version"]}), card_id, created_by))
                content_id = cur.fetchone()["id"]
                return {
                    "learning_card_id": card_id, "course_id": course_id, "course_version_id": version["id"],
                    "chapter_id": chapter_id, "content_item_id": content_id,
                    "course_title": course["title"], "version_status": version["status"],
                }
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("学习卡片加入课程失败") from exc

    def remove_learning_card_from_course(self, content_id: str) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("""SELECT content.id::text AS content_item_id,content.learning_card_id,
                              chapter.id::text AS chapter_id,version.status
                              FROM cl_content_items content
                              JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                              JOIN cl_course_versions version ON version.id=chapter.course_version_id
                              WHERE content.id=%s FOR UPDATE""", (content_id,))
                item = cur.fetchone()
                if not item or not item["learning_card_id"]:
                    raise ValueError("课程中的学习卡片不存在")
                if item["status"] != "draft":
                    raise ValueError("已发布版本不可移除学习卡片，请先创建新版本")
                cur.execute("DELETE FROM cl_content_items WHERE id=%s", (content_id,))
                cur.execute("SELECT 1 FROM cl_content_items WHERE chapter_id=%s LIMIT 1", (item["chapter_id"],))
                if not cur.fetchone():
                    cur.execute("DELETE FROM cl_chapters WHERE id=%s", (item["chapter_id"],))
                return {"content_item_id": content_id, "chapter_id": item["chapter_id"], "removed": True}
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("学习卡片移除失败") from exc

    def move_learning_card_in_course(self, content_id: str, direction: str) -> dict[str, Any]:
        if direction not in {"up", "down"}:
            raise ValueError("课程顺序调整方向无效")
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("""SELECT content.id::text AS content_item_id,content.learning_card_id,
                              chapter.id::text AS chapter_id,chapter.course_version_id::text AS course_version_id,
                              chapter.sequence_no,version.status
                              FROM cl_content_items content
                              JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                              JOIN cl_course_versions version ON version.id=chapter.course_version_id
                              WHERE content.id=%s FOR UPDATE""", (content_id,))
                item = cur.fetchone()
                if not item or not item["learning_card_id"]:
                    raise ValueError("课程中的学习卡片不存在")
                if item["status"] != "draft":
                    raise ValueError("已发布版本不可调整顺序，请先创建新版本")
                operator, ordering = ("<", "DESC") if direction == "up" else (">", "ASC")
                cur.execute(f"""SELECT id::text AS chapter_id,sequence_no FROM cl_chapters
                              WHERE course_version_id=%s AND sequence_no {operator} %s
                              ORDER BY sequence_no {ordering},id LIMIT 1 FOR UPDATE""",
                            (item["course_version_id"], item["sequence_no"]))
                target = cur.fetchone()
                if target:
                    cur.execute("""UPDATE cl_chapters SET sequence_no=CASE
                                  WHEN id=%s THEN %s WHEN id=%s THEN %s ELSE sequence_no END
                                  WHERE id IN (%s,%s)""",
                                (item["chapter_id"], target["sequence_no"], target["chapter_id"], item["sequence_no"],
                                 item["chapter_id"], target["chapter_id"]))
                    item["sequence_no"] = target["sequence_no"]
                return {"content_item_id": content_id, "chapter_id": item["chapter_id"], "sequence_no": item["sequence_no"]}
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("学习卡片顺序调整失败") from exc

    def get_learner_learning_card(self, content_id: str, assignment_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT card.id::text AS id,card.title,card.category,card.package_format,card.package_version,
                          card.entry_file,card.storage_prefix,card.package_sha256,card.metadata,card.resource_count,
                          card.status,card.created_by::text AS created_by,card.created_at,card.updated_at,card.archived_at,
                          content.id::text AS content_item_id,%s::text AS assignment_id,1::int AS course_count
                          FROM cl_content_items content
                          JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          JOIN cl_learning_cards card ON card.id=content.learning_card_id
                          WHERE content.id=%s AND (
                            EXISTS (SELECT 1 FROM cl_practice_assignments assignment
                                    JOIN cl_practice_tasks task ON task.id=assignment.task_id
                                    WHERE assignment.id=%s AND assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                                      AND task.course_version_id=chapter.course_version_id)
                            OR EXISTS (SELECT 1 FROM cl_exam_assignments assignment
                                       JOIN cl_exam_tasks task ON task.id=assignment.task_id
                                       WHERE assignment.id=%s AND assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                                         AND task.course_version_id=chapter.course_version_id)
                          )""", (assignment_id, content_id, assignment_id, user_id, assignment_id, user_id))
            row = cur.fetchone()
            return self._learning_card_record(row) if row else None

    def list_assignment_learning_cards(self, assignment_id: str, user_id: str):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT task.course_version_id FROM cl_practice_assignments a
                           JOIN cl_practice_tasks task ON task.id=a.task_id
                           WHERE a.id=%s AND a.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                           UNION ALL SELECT task.course_version_id FROM cl_exam_assignments a
                           JOIN cl_exam_tasks task ON task.id=a.exam_task_id
                           WHERE a.id=%s AND a.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL""",
                        (assignment_id, user_id, assignment_id, user_id))
            task = cur.fetchone()
            if not task:
                return None
            cur.execute("""SELECT c.id::text AS id,c.title,c.learning_card_id::text AS learning_card_id
                           FROM cl_content_items c JOIN cl_chapters ch ON ch.id=c.chapter_id
                           WHERE ch.course_version_id=%s AND c.learning_card_id IS NOT NULL
                           ORDER BY ch.sequence_no,c.sequence_no""", (task['course_version_id'],))
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _practice_completion(cur, assignment_id, version_id, minimum):
        cur.execute("""SELECT count(*)::int AS total,count(*) FILTER (WHERE
            (CASE WHEN c.learning_card_id IS NOT NULL THEN EXISTS (
                SELECT 1 FROM cl_learning_card_reads r WHERE r.assignment_id=%s AND r.content_item_id=c.id)
             ELSE (SELECT count(*) FROM cl_practice_attempts p WHERE p.assignment_id=%s AND p.content_item_id=c.id)>=%s END)
            AND NOT EXISTS (SELECT 1 FROM cl_content_interactions i
                WHERE i.content_item_id=c.id AND i.status='published' AND i.required
                AND NOT EXISTS (SELECT 1 FROM cl_interaction_attempts a
                    WHERE a.assignment_id=%s AND a.interaction_id=i.id AND a.is_correct)))::int AS completed
            FROM cl_content_items c JOIN cl_chapters ch ON ch.id=c.chapter_id
            WHERE ch.course_version_id=%s""", (assignment_id, assignment_id, minimum, assignment_id, version_id))
        return dict(cur.fetchone())

    def mark_learning_card_read(self, content_id: str, assignment_id: str, user_id: str):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT t.course_version_id,t.completion_rule FROM cl_practice_assignments a
                JOIN cl_practice_tasks t ON t.id=a.task_id
                JOIN cl_chapters ch ON ch.course_version_id=t.course_version_id
                JOIN cl_content_items c ON c.chapter_id=ch.id
                WHERE a.id=%s AND a.user_id=%s AND t.status='published' AND t.deleted_at IS NULL
                  AND c.id=%s AND c.learning_card_id IS NOT NULL FOR UPDATE OF a""", (assignment_id, user_id, content_id))
            task = cur.fetchone()
            if not task:
                raise ValueError('学习卡片不属于当前已发布练习任务')
            cur.execute("""INSERT INTO cl_learning_card_reads(assignment_id,content_item_id,user_id)
                           VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""", (assignment_id, content_id, user_id))
            progress = self._practice_completion(cur, assignment_id, task['course_version_id'], int((task['completion_rule'] or {}).get('min_attempts', 1)))
            status = 'completed' if progress['total'] and progress['completed'] == progress['total'] else 'in_progress'
            cur.execute("""UPDATE cl_practice_assignments SET status=%s,
                           completed_at=CASE WHEN %s='completed' THEN COALESCE(completed_at,now()) ELSE NULL END WHERE id=%s""",
                        (status, status, assignment_id))
            return {'content_item_id': content_id, 'read': True, 'progress_percent': round(progress['completed'] / max(progress['total'], 1) * 100)}

    def materialize_broadcast_course(self, script: dict[str, Any], version: dict[str, Any], slices: list[dict[str, Any]], created_by: str) -> str:
        """Create a hidden immutable course snapshot for the existing learner loop."""
        if not script.get("enabled") or not script.get("ready") or not slices:
            raise ValueError("Broadcast script is not enabled or complete")
        if "".join(item["text"] for item in slices) != version["full_text"]:
            raise ValueError("Broadcast slices do not match the full text")
        from psycopg.types.json import Jsonb
        course_id, version_id, chapter_id = str(uuid4()), str(uuid4()), str(uuid4())
        code = f"BROADCAST-{uuid4().hex.upper()}"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO cl_courses(id,organization_id,code,title,description,category,status,created_by)
                          VALUES (%s,%s,%s,%s,%s,'broadcast_snapshot','published',%s)""",
                        (course_id, script.get("company_id"), code, script["title"], "Broadcast task snapshot", created_by))
            cur.execute("""INSERT INTO cl_course_versions(id,course_id,version_no,version_label,status,change_summary,
                          created_by,published_by,published_at,source_broadcast_script_id)
                          VALUES (%s,%s,1,%s,'published','Broadcast task snapshot',%s,%s,now(),%s)""",
                        (version_id, course_id, f"V{version['version']}", created_by, created_by, script["id"]))
            cur.execute("""INSERT INTO cl_chapters(id,course_version_id,code,title,sequence_no,learning_objective)
                          VALUES (%s,%s,'SCRIPT',%s,1,'Complete every broadcast slice')""",
                        (chapter_id, version_id, script["title"]))
            for number, item in enumerate(slices, start=1):
                content_id = str(uuid4())
                cur.execute("""INSERT INTO cl_content_items(id,chapter_id,content_type,title,sequence_no,sanitized_html,validation_report,created_by)
                              VALUES (%s,%s,'broadcast',%s,%s,%s,%s,%s)""",
                            (content_id, chapter_id, f"第 {number} 段", number, f"<p>{escape(item['text'])}</p>",
                             Jsonb({"source": "broadcast_library", "script_id": script["id"], "version_id": version["id"], "slice_id": item["id"]}), created_by))
                cur.execute("""INSERT INTO cl_course_standards(content_item_id,standard_text,rule_version)
                              VALUES (%s,%s,'1.0')""", (content_id, item["text"]))
        return version_id

    def materialize_broadcast_course_bundle(self, sources: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]], created_by: str) -> str:
        """Create one hidden immutable course version for a multi-script task."""
        if len(sources) < 2:
            raise ValueError("A broadcast bundle requires at least two scripts")
        for script, version, slices in sources:
            if not script.get("enabled") or not script.get("ready") or not slices:
                raise ValueError("Broadcast script is not enabled or complete")
            if "".join(item["text"] for item in slices) != version["full_text"]:
                raise ValueError("Broadcast slices do not match the full text")
        from psycopg.types.json import Jsonb
        course_id, version_id = str(uuid4()), str(uuid4())
        code = f"BROADCAST-BUNDLE-{uuid4().hex.upper()}"
        organization_ids = {script.get("company_id") for script, _, _ in sources}
        organization_id = next(iter(organization_ids)) if len(organization_ids) == 1 else None
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO cl_courses(id,organization_id,code,title,description,category,status,created_by)
                          VALUES (%s,%s,%s,%s,%s,'broadcast_snapshot','published',%s)""",
                        (course_id, organization_id, code, f"广播词组合（{len(sources)}篇）", "Broadcast task bundle snapshot", created_by))
            cur.execute("""INSERT INTO cl_course_versions(id,course_id,version_no,version_label,status,change_summary,
                          created_by,published_by,published_at,source_broadcast_script_id)
                          VALUES (%s,%s,1,'组合 V1','published','Broadcast task bundle snapshot',%s,%s,now(),NULL)""",
                        (version_id, course_id, created_by, created_by))
            for chapter_number, (script, version, slices) in enumerate(sources, start=1):
                chapter_id = str(uuid4())
                cur.execute("""INSERT INTO cl_chapters(id,course_version_id,code,title,sequence_no,learning_objective)
                              VALUES (%s,%s,%s,%s,%s,'Complete every broadcast slice')""",
                            (chapter_id, version_id, f"SCRIPT-{chapter_number}", script["title"], chapter_number))
                for slice_number, item in enumerate(slices, start=1):
                    content_id = str(uuid4())
                    title = script["title"] if len(slices) == 1 else f"第 {slice_number} 段"
                    cur.execute("""INSERT INTO cl_content_items(id,chapter_id,content_type,title,sequence_no,sanitized_html,validation_report,created_by)
                                  VALUES (%s,%s,'broadcast',%s,%s,%s,%s,%s)""",
                                (content_id, chapter_id, title, slice_number, f"<p>{escape(item['text'])}</p>",
                                 Jsonb({"source": "broadcast_library", "bundle": True, "script_id": script["id"],
                                        "version_id": version["id"], "slice_id": item["id"]}), created_by))
                    cur.execute("""INSERT INTO cl_course_standards(content_item_id,standard_text,rule_version)
                                  VALUES (%s,%s,'1.0')""", (content_id, item["text"]))
        return version_id

    def create_practice_task(self, task: PracticeTask) -> PracticeTask:
        from psycopg.types.json import Jsonb
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO cl_practice_tasks(id,broadcast_id,course_version_id,title,status,completion_rule,due_at,
                              week_no,unlock_after_task_type,unlock_after_task_id)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (task.id, task.broadcast_id, task.course_version_id,
                              task.title, task.status, Jsonb(task.completion_rule), task.due_at, task.week_no,
                              task.unlock_after_task_type, task.unlock_after_task_id))
        return task

    def get_practice_task(self, task_id: str) -> PracticeTask | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT task.id::text AS id,task.title,task.broadcast_id::text AS broadcast_id,task.due_at,
                            task.completion_rule,task.status,task.course_version_id::text AS course_version_id,task.week_no,
                            task.unlock_after_task_type,task.unlock_after_task_id::text AS unlock_after_task_id,
                            version.source_broadcast_script_id::text AS broadcast_script_id
                            FROM cl_practice_tasks task LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                            WHERE task.id=%s AND task.deleted_at IS NULL""", (task_id,))
                row = cur.fetchone()
                return PracticeTask(**row) if row else None

    def create_exam_task(self, task: ExamTask) -> ExamTask:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO cl_exam_tasks(id,broadcast_id,course_version_id,title,status,max_recordings,due_at,
                              week_no,unlock_after_task_type,unlock_after_task_id)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (task.id, task.broadcast_id, task.course_version_id,
                              task.title, task.status, task.max_recordings, task.due_at, task.week_no,
                              task.unlock_after_task_type, task.unlock_after_task_id))
        return task

    def get_exam_task(self, task_id: str) -> ExamTask | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT task.id::text AS id,task.title,task.broadcast_id::text AS broadcast_id,task.max_recordings,
                            task.due_at,task.status,task.course_version_id::text AS course_version_id,task.week_no,
                            task.unlock_after_task_type,task.unlock_after_task_id::text AS unlock_after_task_id,
                            version.source_broadcast_script_id::text AS broadcast_script_id
                            FROM cl_exam_tasks task LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                            WHERE task.id=%s AND task.deleted_at IS NULL""", (task_id,))
                row = cur.fetchone()
                return ExamTask(**row) if row else None

    def is_task_unlocked(self, task_type: str, task_id: str, user_id: str) -> bool:
        task_table = "cl_practice_tasks" if task_type == "practice" else "cl_exam_tasks"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"""SELECT unlock_after_task_type,unlock_after_task_id::text AS unlock_after_task_id
                          FROM {task_table} WHERE id=%s AND deleted_at IS NULL""", (task_id,))
            task = cur.fetchone()
            if not task:
                return False
            prerequisite_id = task["unlock_after_task_id"]
            if not prerequisite_id:
                return True
            if task["unlock_after_task_type"] == "practice":
                cur.execute("""SELECT EXISTS (SELECT 1 FROM cl_practice_assignments assignment
                            JOIN cl_practice_tasks prerequisite ON prerequisite.id=assignment.task_id
                            WHERE assignment.task_id=%s AND assignment.user_id=%s AND assignment.status='completed'
                              AND prerequisite.deleted_at IS NULL) AS completed""", (prerequisite_id, user_id))
            else:
                cur.execute("""SELECT EXISTS (SELECT 1 FROM cl_exam_assignments assignment
                            JOIN cl_exam_tasks prerequisite ON prerequisite.id=assignment.exam_task_id
                            WHERE assignment.exam_task_id=%s AND assignment.user_id=%s
                              AND assignment.status IN ('submitted','graded','published')
                              AND prerequisite.deleted_at IS NULL) AS completed""", (prerequisite_id, user_id))
            return bool(cur.fetchone()["completed"])

    def is_assignment_unlocked(self, task_type: str, assignment_id: str, user_id: str) -> bool:
        assignment_table = "cl_practice_assignments" if task_type == "practice" else "cl_exam_assignments"
        task_column = "task_id" if task_type == "practice" else "exam_task_id"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {task_column}::text AS task_id FROM {assignment_table} WHERE id=%s AND user_id=%s",
                        (assignment_id, user_id))
            assignment = cur.fetchone()
        return bool(assignment) and self.is_task_unlocked(task_type, assignment["task_id"], user_id)

    def get_practice_assignment(self, assignment_id: str, user_id: str) -> PracticeAssignment | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id::text AS id,task_id::text AS task_id,user_id::text AS user_id,status FROM cl_practice_assignments WHERE id=%s AND user_id=%s", (assignment_id, user_id))
                row = cur.fetchone()
                if not row:
                    return None
                cur.execute("SELECT id::text AS id FROM cl_practice_attempts WHERE assignment_id=%s ORDER BY attempt_no", (assignment_id,))
                row["attempt_ids"] = [item["id"] for item in cur.fetchall()]
                return PracticeAssignment(**row)

    def create_practice_assignment(self, task_id: str, user_id: str) -> PracticeAssignment:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO cl_practice_assignments(id,task_id,user_id)
                              VALUES (%s,%s,%s)
                              ON CONFLICT (task_id,user_id) DO UPDATE SET task_id=EXCLUDED.task_id
                              RETURNING id::text AS id,task_id::text AS task_id,user_id::text AS user_id,status""", (str(uuid4()), task_id, user_id))
                row = cur.fetchone()
                row["attempt_ids"] = []
                return PracticeAssignment(**row)

    def list_practice_assignments(self, user_id: str) -> list[PracticeAssignment]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT a.id::text AS id,a.task_id::text AS task_id,a.user_id::text AS user_id,a.status
                              FROM cl_practice_assignments a JOIN cl_practice_tasks task ON task.id=a.task_id
                              WHERE a.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL ORDER BY a.assigned_at DESC""", (user_id,))
                rows = cur.fetchall()
                return [PracticeAssignment(**dict(row), attempt_ids=[]) for row in rows]

    def practice_attempt_count(self, assignment_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM cl_practice_attempts WHERE assignment_id=%s", (assignment_id,))
                return int(cur.fetchone()["n"])

    def save_practice_attempt(self, attempt: PracticeAttempt, feedback: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO cl_practice_attempts(id,assignment_id,segment_id,attempt_no,feedback)
                              VALUES (%s,%s,%s,%s,%s)""", (attempt.id, attempt.assignment_id, attempt.segment_id, attempt.attempt_no, Jsonb(feedback)))
                cur.execute("UPDATE cl_practice_assignments SET status='in_progress' WHERE id=%s", (attempt.assignment_id,))

    def get_exam_assignment(self, assignment_id: str, user_id: str) -> ExamAssignment | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id::text AS id,exam_task_id::text AS task_id,user_id::text AS user_id,status,submitted_at FROM cl_exam_assignments WHERE id=%s AND user_id=%s", (assignment_id, user_id))
                row = cur.fetchone()
                if not row:
                    return None
                row["submitted_recordings"] = []
                return ExamAssignment(**row)

    def create_exam_assignment(self, task_id: str, user_id: str) -> ExamAssignment:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO cl_exam_assignments(id,exam_task_id,user_id)
                              VALUES (%s,%s,%s)
                              ON CONFLICT (exam_task_id,user_id) DO UPDATE SET exam_task_id=EXCLUDED.exam_task_id
                              RETURNING id::text AS id,exam_task_id::text AS task_id,user_id::text AS user_id,status,submitted_at""", (str(uuid4()), task_id, user_id))
                row = cur.fetchone()
                row["submitted_recordings"] = []
                return ExamAssignment(**row)

    def list_exam_assignments(self, user_id: str) -> list[ExamAssignment]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT a.id::text AS id,a.exam_task_id::text AS task_id,a.user_id::text AS user_id,a.status,a.submitted_at
                              FROM cl_exam_assignments a JOIN cl_exam_tasks task ON task.id=a.exam_task_id
                              WHERE a.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL ORDER BY a.id""", (user_id,))
                rows = cur.fetchall()
                return [ExamAssignment(**dict(row), submitted_recordings=[]) for row in rows]

    def list_practice_progress(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT a.user_id::text AS user_id,a.id::text AS assignment_id,a.task_id::text AS task_id,
                              count(p.id)::int AS attempts,a.status FROM cl_practice_assignments a
                              JOIN cl_practice_tasks task ON task.id=a.task_id
                              LEFT JOIN cl_practice_attempts p ON p.assignment_id=a.id
                              WHERE a.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                              GROUP BY a.user_id,a.id,a.task_id,a.status ORDER BY a.id""", (user_id,))
                return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _enqueue_evaluation_tasks(cur, review_type: str, learner_id: str, *, practice_attempt_id: str | None = None, exam_assignment_id: str | None = None) -> dict[str, Any]:
        """Create one independent evaluation task per active assigned instructor."""
        assignment_type = "training" if review_type == "practice" else "assessment"
        if review_type == "practice" and practice_attempt_id:
            cur.execute("""SELECT DISTINCT binding.instructor_id::text AS instructor_id
                           FROM student_instructor_assignments binding
                           JOIN cl_practice_assignments assignment ON assignment.user_id=binding.student_id
                           JOIN cl_practice_attempts attempt ON attempt.assignment_id=assignment.id
                           JOIN cl_practice_tasks task ON task.id=assignment.task_id
                           LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                           WHERE binding.student_id=%s AND attempt.id=%s AND binding.status='active'
                             AND binding.assignment_type IN (%s,'both')
                             AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                             AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                             AND (binding.course_id IS NULL OR binding.course_id=version.course_id)""",
                        (learner_id, practice_attempt_id, assignment_type))
        elif review_type == "exam" and exam_assignment_id:
            cur.execute("""SELECT DISTINCT binding.instructor_id::text AS instructor_id
                           FROM student_instructor_assignments binding
                           JOIN cl_exam_assignments assignment ON assignment.user_id=binding.student_id
                           JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                           LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                           WHERE binding.student_id=%s AND assignment.id=%s AND binding.status='active'
                             AND binding.assignment_type IN (%s,'both')
                             AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                             AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                             AND (binding.course_id IS NULL OR binding.course_id=version.course_id)""",
                        (learner_id, exam_assignment_id, assignment_type))
        else:
            raise ValueError("Evaluation task target does not match review type")
        instructors = [row["instructor_id"] for row in cur.fetchall()]
        if not instructors:
            cur.execute("""INSERT INTO cl_evaluation_tasks(review_type,practice_attempt_id,exam_assignment_id,learner_id,status)
                           VALUES (%s,%s,%s,%s,'waiting_assignment') ON CONFLICT DO NOTHING""", (review_type, practice_attempt_id, exam_assignment_id, learner_id))
            return {"created": 0, "waiting_assignment": True}
        created = 0
        for instructor_id in instructors:
            cur.execute("""INSERT INTO cl_evaluation_tasks(review_type,practice_attempt_id,exam_assignment_id,learner_id,instructor_id,status)
                           VALUES (%s,%s,%s,%s,%s,'pending') ON CONFLICT DO NOTHING RETURNING id""",
                        (review_type, practice_attempt_id, exam_assignment_id, learner_id, instructor_id))
            created += int(cur.fetchone() is not None)
        if practice_attempt_id:
            cur.execute("UPDATE cl_evaluation_tasks SET status='resolved',updated_at=now() WHERE practice_attempt_id=%s AND instructor_id IS NULL AND status='waiting_assignment'", (practice_attempt_id,))
        else:
            cur.execute("UPDATE cl_evaluation_tasks SET status='resolved',updated_at=now() WHERE exam_assignment_id=%s AND instructor_id IS NULL AND status='waiting_assignment'", (exam_assignment_id,))
        return {"created": created, "waiting_assignment": False}

    @staticmethod
    def _sync_instructor_evaluation_tasks(cur, instructor_id: str) -> dict[str, int]:
        """Idempotently repair missing review tasks for one instructor's active bindings."""
        cur.execute("""INSERT INTO cl_evaluation_tasks
                         (review_type,practice_attempt_id,learner_id,instructor_id,status)
                       SELECT 'practice',attempt.id,assignment.user_id,binding.instructor_id,'pending'
                       FROM student_instructor_assignments binding
                       JOIN cl_practice_assignments assignment ON assignment.user_id=binding.student_id
                       JOIN cl_practice_attempts attempt ON attempt.assignment_id=assignment.id
                       JOIN cl_practice_tasks task ON task.id=assignment.task_id
                       LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                       WHERE binding.instructor_id=%s AND binding.status='active'
                         AND binding.assignment_type IN ('training','both')
                         AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                         AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                         AND (binding.course_id IS NULL OR binding.course_id=version.course_id)
                         AND attempt.ai_status='completed'
                         AND task.deleted_at IS NULL
                       ON CONFLICT DO NOTHING RETURNING id""", (instructor_id,))
        practice_created = len(cur.fetchall())
        cur.execute("""INSERT INTO cl_evaluation_tasks
                         (review_type,exam_assignment_id,learner_id,instructor_id,status)
                       SELECT 'exam',assignment.id,assignment.user_id,binding.instructor_id,'pending'
                       FROM student_instructor_assignments binding
                       JOIN cl_exam_assignments assignment ON assignment.user_id=binding.student_id
                       JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                       LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                       WHERE binding.instructor_id=%s AND binding.status='active'
                         AND binding.assignment_type IN ('assessment','both')
                         AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                         AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                         AND (binding.course_id IS NULL OR binding.course_id=version.course_id)
                         AND assignment.status IN ('submitted','graded','published')
                         AND task.deleted_at IS NULL
                       ON CONFLICT DO NOTHING RETURNING id""", (instructor_id,))
        exam_created = len(cur.fetchall())
        cur.execute("""UPDATE cl_evaluation_tasks waiting SET status='resolved',updated_at=now()
                       WHERE waiting.instructor_id IS NULL AND waiting.status='waiting_assignment'
                         AND EXISTS (
                           SELECT 1 FROM cl_evaluation_tasks assigned
                           WHERE assigned.instructor_id=%s
                             AND assigned.status<>'cancelled'
                             AND (
                               (waiting.practice_attempt_id IS NOT NULL AND assigned.practice_attempt_id=waiting.practice_attempt_id) OR
                               (waiting.exam_assignment_id IS NOT NULL AND assigned.exam_assignment_id=waiting.exam_assignment_id)
                             )
                         )""", (instructor_id,))
        return {"practice_created": practice_created, "exam_created": exam_created,
                "created": practice_created + exam_created}

    def sync_instructor_evaluation_tasks(self, instructor_id: str) -> dict[str, int]:
        with self._connect() as conn, conn.cursor() as cur:
            return self._sync_instructor_evaluation_tasks(cur, instructor_id)

    def reassign_evaluation_tasks(self, learner_id: str) -> dict[str, Any]:
        """Re-run routing for historical unassigned submissions after a binding is added."""
        created = 0
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT attempt.id::text AS id,assignment.user_id::text AS learner_id
                           FROM cl_practice_attempts attempt JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                           JOIN cl_practice_tasks task ON task.id=assignment.task_id
                           WHERE assignment.user_id=%s AND task.deleted_at IS NULL""", (learner_id,))
            practice = [dict(row) for row in cur.fetchall()]
            cur.execute("""SELECT assignment.id::text AS id,assignment.user_id::text AS learner_id
                           FROM cl_exam_assignments assignment JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                           WHERE assignment.user_id=%s AND assignment.status IN ('submitted','graded','published')
                             AND task.deleted_at IS NULL""", (learner_id,))
            exams = [dict(row) for row in cur.fetchall()]
            for item in practice:
                result = self._enqueue_evaluation_tasks(cur, "practice", learner_id, practice_attempt_id=item["id"])
                created += result["created"]
            for item in exams:
                result = self._enqueue_evaluation_tasks(cur, "exam", learner_id, exam_assignment_id=item["id"])
                created += result["created"]
            cur.execute("""SELECT count(*)::int AS n FROM cl_evaluation_tasks
                           WHERE learner_id=%s AND instructor_id IS NULL AND status='waiting_assignment'""", (learner_id,))
            waiting = cur.fetchone()["n"]
        return {"learner_id": learner_id, "created": created, "waiting_assignment": waiting, "practice_targets": len(practice), "exam_targets": len(exams)}

    def list_unassigned_evaluation_tasks(self) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT task.id::text AS id,task.review_type,task.practice_attempt_id::text AS practice_attempt_id,
                           task.exam_assignment_id::text AS exam_assignment_id,task.learner_id::text AS learner_id,
                           learner.display_name AS learner_name,task.status,task.created_at
                           FROM cl_evaluation_tasks task JOIN users learner ON learner.id=task.learner_id
                           WHERE task.status='waiting_assignment' ORDER BY task.created_at""")
            return [dict(row) for row in cur.fetchall()]

    def submit_exam_assignment(self, assignment: ExamAssignment, recording_refs: list[str], submitted_at: datetime) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE cl_exam_assignments SET status='submitted',submitted_at=%s WHERE id=%s", (submitted_at, assignment.id))
                cur.execute("SELECT user_id::text AS learner_id FROM cl_exam_assignments WHERE id=%s", (assignment.id,))
                learner = cur.fetchone()
                if learner:
                    self._enqueue_evaluation_tasks(cur, "exam", learner["learner_id"], exam_assignment_id=assignment.id)

    def list_courses(self) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT c.id::text AS id,c.organization_id::text AS organization_id,c.code,c.title,c.description,c.category,c.status,
                          count(v.id)::int AS version_count,
                          (array_agg(v.id::text ORDER BY v.version_no DESC) FILTER (WHERE v.status='published'))[1] AS published_version_id
                          FROM cl_courses c LEFT JOIN cl_course_versions v ON v.course_id=c.id
                          WHERE c.category<>'broadcast_snapshot'
                          GROUP BY c.id ORDER BY c.updated_at DESC,c.title""")
            return [dict(row) for row in cur.fetchall()]

    def create_course(self, code: str, title: str, description: str, category: str, organization_id: str | None, created_by: str) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO cl_courses(organization_id,code,title,description,category,created_by)
                              VALUES (%s,%s,%s,%s,%s,%s)
                              RETURNING id::text AS id,organization_id::text AS organization_id,code,title,description,category,status,
                              0::int AS version_count,NULL::text AS published_version_id""",
                            (organization_id, code, title, description, category, created_by))
                return dict(cur.fetchone())
        except Exception as exc:
            raise ValueError("Course code already exists") from exc

    def list_course_versions(self, course_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT v.id::text AS id,v.course_id::text AS course_id,v.version_no,v.version_label,v.status,v.change_summary,v.published_at,
                          count(DISTINCT chapter.id)::int AS chapter_count,count(content.id)::int AS content_count
                          FROM cl_course_versions v
                          LEFT JOIN cl_chapters chapter ON chapter.course_version_id=v.id
                          LEFT JOIN cl_content_items content ON content.chapter_id=chapter.id
                          WHERE v.course_id=%s GROUP BY v.id ORDER BY v.version_no DESC""", (course_id,))
            return [dict(row) for row in cur.fetchall()]

    def create_course_version(self, course_id: str, version_label: str, change_summary: str, created_by: str) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM cl_courses WHERE id=%s", (course_id,))
                if not cur.fetchone():
                    raise ValueError("Course not found")
                cur.execute("""INSERT INTO cl_course_versions(course_id,version_no,version_label,change_summary,created_by)
                              SELECT %s,COALESCE(max(version_no),0)+1,%s,%s,%s FROM cl_course_versions WHERE course_id=%s
                              RETURNING id::text AS id,course_id::text AS course_id,version_no,version_label,status,change_summary,
                              0::int AS chapter_count,0::int AS content_count,published_at""",
                            (course_id, version_label, change_summary, created_by, course_id))
                return dict(cur.fetchone())
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Version label already exists") from exc

    def list_chapters(self, course_version_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT chapter.id::text AS id,chapter.course_version_id::text AS course_version_id,chapter.code,chapter.title,
                          chapter.sequence_no,chapter.learning_objective,count(content.id)::int AS content_count
                          FROM cl_chapters chapter LEFT JOIN cl_content_items content ON content.chapter_id=chapter.id
                          WHERE chapter.course_version_id=%s GROUP BY chapter.id ORDER BY chapter.sequence_no""", (course_version_id,))
            return [dict(row) for row in cur.fetchall()]

    def create_chapter(self, course_version_id: str, code: str, title: str, sequence_no: int, learning_objective: str) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT status FROM cl_course_versions WHERE id=%s", (course_version_id,))
                version = cur.fetchone()
                if not version or version["status"] != "draft":
                    raise ValueError("Only a draft course version can be edited")
                cur.execute("""INSERT INTO cl_chapters(course_version_id,code,title,sequence_no,learning_objective)
                              VALUES (%s,%s,%s,%s,%s)
                              RETURNING id::text AS id,course_version_id::text AS course_version_id,code,title,sequence_no,learning_objective,0::int AS content_count""",
                            (course_version_id, code, title, sequence_no, learning_objective))
                return dict(cur.fetchone())
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Chapter code or sequence already exists") from exc

    def list_content_items(self, chapter_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id::text AS id,chapter_id::text AS chapter_id,content_type,title,sequence_no,source_filename,
                          sanitized_html,original_sha256,sanitized_sha256,validation_report,learning_card_id::text AS learning_card_id,
                          (SELECT count(*)::int FROM cl_content_interactions interaction
                           WHERE interaction.content_item_id=cl_content_items.id AND interaction.status<>'archived') AS interaction_count
                          FROM cl_content_items WHERE chapter_id=%s ORDER BY sequence_no""", (chapter_id,))
            return [dict(row) for row in cur.fetchall()]

    def create_html_content(self, chapter_id: str, title: str, sequence_no: int, source_filename: str, sanitized_html: str, original_sha256: str, sanitized_sha256: str, validation_report: dict[str, Any], created_by: str) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("""SELECT version.status FROM cl_chapters chapter JOIN cl_course_versions version ON version.id=chapter.course_version_id
                              WHERE chapter.id=%s""", (chapter_id,))
                version = cur.fetchone()
                if not version or version["status"] != "draft":
                    raise ValueError("Only a draft course version can be edited")
                cur.execute("""INSERT INTO cl_content_items(chapter_id,content_type,title,sequence_no,source_filename,sanitized_html,
                              original_sha256,sanitized_sha256,validation_report,created_by)
                              VALUES (%s,'html',%s,%s,%s,%s,%s,%s,%s,%s)
                              RETURNING id::text AS id,chapter_id::text AS chapter_id,content_type,title,sequence_no,source_filename,
                              sanitized_html,original_sha256,sanitized_sha256,validation_report""",
                            (chapter_id, title, sequence_no, source_filename, sanitized_html, original_sha256, sanitized_sha256, Jsonb(validation_report), created_by))
                return dict(cur.fetchone())
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Content sequence already exists") from exc

    def import_ppt_course(self, course_version_id: str, chapter_code: str, chapter_title: str,
                          source_filename: str, slides: list[dict[str, Any]], created_by: str) -> dict[str, Any]:
        """Atomically create a chapter and one HTML item for every PPTX slide."""
        from psycopg.types.json import Jsonb

        if not slides:
            raise ValueError("PPTX 中没有可导入的幻灯片")
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT status FROM cl_course_versions WHERE id=%s FOR UPDATE", (course_version_id,))
                version = cur.fetchone()
                if not version or version["status"] != "draft":
                    raise ValueError("Only a draft course version can be edited")
                cur.execute("SELECT COALESCE(max(sequence_no),0)+1 AS next_sequence FROM cl_chapters WHERE course_version_id=%s", (course_version_id,))
                chapter_sequence = int(cur.fetchone()["next_sequence"])
                cur.execute("""INSERT INTO cl_chapters(course_version_id,code,title,sequence_no,learning_objective)
                              VALUES (%s,%s,%s,%s,%s)
                              RETURNING id::text AS id""",
                            (course_version_id, chapter_code, chapter_title, chapter_sequence, "按幻灯片顺序学习课程内容"))
                chapter_id = str(cur.fetchone()["id"])
                content_ids: list[str] = []
                for index, slide in enumerate(slides, start=1):
                    cur.execute("""INSERT INTO cl_content_items(chapter_id,content_type,title,sequence_no,source_filename,sanitized_html,
                                  original_sha256,sanitized_sha256,validation_report,created_by)
                                  VALUES (%s,'html',%s,%s,%s,%s,%s,%s,%s,%s)
                                  RETURNING id::text AS id""",
                                (chapter_id, slide["title"], index, source_filename, slide["html"],
                                 slide["original_sha256"], slide["sanitized_sha256"],
                                 Jsonb(slide["validation_report"]), created_by))
                    content_ids.append(str(cur.fetchone()["id"]))
                return {
                    "course_version_id": course_version_id,
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                    "slides_imported": len(content_ids),
                    "content_ids": content_ids,
                    "warnings": [],
                }
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("PPTX 导入失败，篇目编码或顺序可能重复") from exc

    def import_pdf_course(self, course_version_id: str, chapter_code: str, chapter_title: str,
                          source_filename: str, pdf_ref: str, pdf_byte_size: int,
                          page_count: int, pdf_sha256: str, created_by: str) -> dict[str, Any]:
        """Store one original PDF and expose one learner content item per page."""
        from psycopg.types.json import Jsonb

        if page_count < 1:
            raise ValueError("PDF 中没有可导入的页面")
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT status FROM cl_course_versions WHERE id=%s FOR UPDATE", (course_version_id,))
                version = cur.fetchone()
                if not version or version["status"] != "draft":
                    raise ValueError("Only a draft course version can be edited")
                cur.execute("SELECT COALESCE(max(sequence_no),0)+1 AS next_sequence FROM cl_chapters WHERE course_version_id=%s", (course_version_id,))
                chapter_sequence = int(cur.fetchone()["next_sequence"])
                cur.execute("""INSERT INTO cl_chapters(course_version_id,code,title,sequence_no,learning_objective)
                              VALUES (%s,%s,%s,%s,%s) RETURNING id::text AS id""",
                            (course_version_id, chapter_code, chapter_title, chapter_sequence, "按 PDF 页面顺序学习课程内容"))
                chapter_id = str(cur.fetchone()["id"])
                cur.execute("""INSERT INTO files(owner_id,object_key,mime_type,byte_size)
                              VALUES (%s,%s,'application/pdf',%s) RETURNING id::text AS id""",
                            (created_by, pdf_ref, pdf_byte_size))
                file_id = str(cur.fetchone()["id"])
                content_ids: list[str] = []
                for page_no in range(1, page_count + 1):
                    report = {
                        "source_type": "pdf",
                        "source_filename": source_filename[:255],
                        "page_no": page_no,
                        "page_count": page_count,
                        "original_mime_type": "application/pdf",
                        "original_byte_size": pdf_byte_size,
                    }
                    cur.execute("""INSERT INTO cl_content_items(
                                  chapter_id,content_type,title,sequence_no,source_filename,sanitized_html,
                                  original_sha256,sanitized_sha256,validation_report,created_by,
                                  document_file_id,document_page_no,document_page_count)
                                  VALUES (%s,'document',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                  RETURNING id::text AS id""",
                                (chapter_id, f"第 {page_no} 页", page_no, source_filename[:255],
                                 f"<p>PDF 第 {page_no} 页</p>", pdf_sha256, pdf_sha256,
                                 Jsonb(report), created_by, file_id, page_no, page_count))
                    content_ids.append(str(cur.fetchone()["id"]))
                return {
                    "course_version_id": course_version_id,
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                    "pages_imported": len(content_ids),
                    "content_ids": content_ids,
                    "warnings": [],
                }
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("PDF 导入失败，篇目编码或顺序可能重复") from exc

    def create_content_asset(self, content_id: str, asset_ref: str, mime_type: str,
                             byte_size: int, source_filename: str, asset_role: str,
                             created_by: str) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("""SELECT version.status FROM cl_content_items content
                              JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                              JOIN cl_course_versions version ON version.id=chapter.course_version_id
                              WHERE content.id=%s""", (content_id,))
                version = cur.fetchone()
                if not version or version["status"] != "draft":
                    raise ValueError("Only a draft course version can be edited")
                cur.execute("""INSERT INTO files(owner_id,object_key,mime_type,byte_size)
                              VALUES (%s,%s,%s,%s) RETURNING id::text AS id""",
                            (created_by, asset_ref, mime_type, byte_size))
                file_id = str(cur.fetchone()["id"])
                cur.execute("""INSERT INTO cl_content_assets(content_item_id,file_id,asset_role,original_filename)
                              VALUES (%s,%s,%s,%s)
                              RETURNING id::text AS id,content_item_id::text AS content_item_id,asset_role,original_filename""",
                            (content_id, file_id, asset_role, source_filename[:255]))
                row = dict(cur.fetchone())
                row.update({"mime_type": mime_type, "byte_size": byte_size, "file_id": file_id})
                return row
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("课程媒体保存失败") from exc

    def list_content_assets(self, content_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT asset.id::text AS id,asset.content_item_id::text AS content_item_id,
                          asset.asset_role,asset.original_filename,file.mime_type,file.byte_size,
                          file.object_key AS asset_ref
                          FROM cl_content_assets asset JOIN files file ON file.id=asset.file_id
                          WHERE asset.content_item_id=%s ORDER BY asset.created_at""", (content_id,))
            return [dict(row) for row in cur.fetchall()]

    def get_content_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT asset.id::text AS id,asset.content_item_id::text AS content_item_id,
                          asset.asset_role,asset.original_filename,file.object_key AS asset_ref,
                          file.mime_type,file.byte_size
                          FROM cl_content_assets asset JOIN files file ON file.id=asset.file_id
                          WHERE asset.id=%s""", (asset_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_learner_content_asset(self, asset_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT asset.id::text AS id,asset.content_item_id::text AS content_item_id,
                          asset.asset_role,asset.original_filename,file.object_key AS asset_ref,
                          file.mime_type,file.byte_size
                          FROM cl_content_assets asset
                          JOIN files file ON file.id=asset.file_id
                          JOIN cl_content_items content ON content.id=asset.content_item_id
                          JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          WHERE asset.id=%s AND EXISTS (
                            SELECT 1 FROM cl_practice_assignments assignment
                            JOIN cl_practice_tasks task ON task.id=assignment.task_id
                            WHERE assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                              AND task.course_version_id=chapter.course_version_id
                          )""", (asset_id, user_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_learner_document(self, content_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT content.id::text AS content_item_id,
                          file.object_key AS document_ref,file.mime_type,file.byte_size,
                          content.source_filename,content.document_page_no,content.document_page_count
                          FROM cl_content_items content
                          JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          JOIN files file ON file.id=content.document_file_id
                          WHERE content.id=%s AND content.content_type='document' AND EXISTS (
                            SELECT 1 FROM cl_practice_assignments assignment
                            JOIN cl_practice_tasks task ON task.id=assignment.task_id
                            WHERE assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                              AND task.course_version_id=chapter.course_version_id
                          )""", (content_id, user_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_content_item(self, content_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT content.id::text AS id,content.chapter_id::text AS chapter_id,content.content_type,content.title,
                          content.sequence_no,content.source_filename,content.sanitized_html,content.original_sha256,
                          content.sanitized_sha256,content.validation_report,content.learning_card_id::text AS learning_card_id
                          FROM cl_content_items content WHERE content.id=%s""", (content_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def _interaction_record(row: Any, include_answer: bool = True) -> dict[str, Any]:
        item = dict(row)
        config = item.pop("config") or {}
        item["options"] = list(config.get("options") or [])
        item["correct_answer"] = str(config.get("correct_answer") or "") if include_answer else ""
        item["accepted_answers"] = list(config.get("accepted_answers") or []) if include_answer else []
        item["feedback_correct"] = str(config.get("feedback_correct") or "回答正确，继续保持。")
        item["feedback_incorrect"] = str(config.get("feedback_incorrect") or "再看一下课程内容，再试一次。")
        return item

    def list_content_interactions(self, content_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id::text AS id,content_item_id::text AS content_item_id,interaction_type,title,prompt,
                          config,sequence_no,required,status,version_no,created_at,updated_at
                          FROM cl_content_interactions
                          WHERE content_item_id=%s AND (%s OR status<>'archived')
                          ORDER BY sequence_no,created_at""", (content_id, include_archived))
            return [self._interaction_record(row) for row in cur.fetchall()]

    def _assert_interaction_editable(self, cur: Any, content_id: str) -> None:
        cur.execute("""SELECT version.status FROM cl_content_items content
                      JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                      JOIN cl_course_versions version ON version.id=chapter.course_version_id
                      WHERE content.id=%s""", (content_id,))
        version = cur.fetchone()
        if not version or version["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")

    def create_content_interaction(self, content_id: str, data: dict[str, Any], created_by: str) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        if data["interaction_type"] in {"choice", "hotspot"} and (len(data.get("options", [])) < 2 or data.get("correct_answer") not in data.get("options", [])):
            raise ValueError("选择或点击互动至少需要两个选项，且正确答案必须是选项之一")
        if data["interaction_type"] == "fill_blank" and not (data.get("accepted_answers") or str(data.get("correct_answer", "")).strip()):
            raise ValueError("填空互动至少需要一个可接受答案")
        config = {"options": data.get("options", []), "correct_answer": data.get("correct_answer", ""), "accepted_answers": data.get("accepted_answers", []), "feedback_correct": data.get("feedback_correct", "回答正确，继续保持。"), "feedback_incorrect": data.get("feedback_incorrect", "再看一下课程内容，再试一次。")}
        try:
            with self._connect() as conn, conn.cursor() as cur:
                self._assert_interaction_editable(cur, content_id)
                cur.execute("""INSERT INTO cl_content_interactions(content_item_id,interaction_type,title,prompt,config,sequence_no,required,created_by)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                              RETURNING id::text AS id,content_item_id::text AS content_item_id,interaction_type,title,prompt,config,sequence_no,required,status,version_no,created_at,updated_at""",
                            (content_id, data["interaction_type"], data.get("title", "互动练习"), data["prompt"], Jsonb(config), data.get("sequence_no", 1), data.get("required", True), created_by))
                return self._interaction_record(cur.fetchone())
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("互动保存失败，顺序可能重复") from exc

    def update_content_interaction(self, interaction_id: str, data: dict[str, Any], updated_by: str) -> dict[str, Any] | None:
        from psycopg.types.json import Jsonb
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id::text AS id,content_item_id::text AS content_item_id,interaction_type,title,prompt,config,
                          sequence_no,required,status,version_no,created_at,updated_at
                          FROM cl_content_interactions WHERE id=%s""", (interaction_id,))
            current = cur.fetchone()
            if not current:
                return None
            self._assert_interaction_editable(cur, current["content_item_id"])
            old = self._interaction_record(current)
            merged = {**old, **data}
            if merged["interaction_type"] in {"choice", "hotspot"} and (len(merged.get("options", [])) < 2 or merged.get("correct_answer") not in merged.get("options", [])):
                raise ValueError("选择或点击互动至少需要两个选项，且正确答案必须是选项之一")
            if merged["interaction_type"] == "fill_blank" and not (merged.get("accepted_answers") or str(merged.get("correct_answer", "")).strip()):
                raise ValueError("填空互动至少需要一个可接受答案")
            config = {"options": merged.get("options", []), "correct_answer": merged.get("correct_answer", ""), "accepted_answers": merged.get("accepted_answers", []), "feedback_correct": merged.get("feedback_correct", "回答正确，继续保持。"), "feedback_incorrect": merged.get("feedback_incorrect", "再看一下课程内容，再试一次。")}
            cur.execute("""UPDATE cl_content_interactions SET interaction_type=%s,title=%s,prompt=%s,config=%s,sequence_no=%s,required=%s,version_no=version_no+1,updated_at=now()
                          WHERE id=%s
                          RETURNING id::text AS id,content_item_id::text AS content_item_id,interaction_type,title,prompt,config,sequence_no,required,status,version_no,created_at,updated_at""",
                        (merged["interaction_type"], merged["title"], merged["prompt"], Jsonb(config), merged["sequence_no"], merged["required"], interaction_id))
            return self._interaction_record(cur.fetchone())

    def archive_content_interaction(self, interaction_id: str, archived_by: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT content_item_id::text AS content_item_id FROM cl_content_interactions WHERE id=%s", (interaction_id,))
            current = cur.fetchone()
            if not current:
                return None
            self._assert_interaction_editable(cur, current["content_item_id"])
            cur.execute("""UPDATE cl_content_interactions SET status='archived',updated_at=now()
                          WHERE id=%s
                          RETURNING id::text AS id,content_item_id::text AS content_item_id,interaction_type,title,prompt,config,sequence_no,required,status,version_no,created_at,updated_at""", (interaction_id,))
            return self._interaction_record(cur.fetchone())

    def submit_interaction_answer(self, assignment_id: str, user_id: str, content_item_id: str, interaction_id: str, answer: str) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT interaction.id::text AS interaction_id,interaction.content_item_id::text AS content_item_id,
                          interaction.interaction_type,interaction.config,interaction.feedback_correct,interaction.feedback_incorrect
                          FROM cl_content_interactions interaction
                          JOIN cl_practice_assignments assignment ON assignment.id=%s AND assignment.user_id=%s
                          JOIN cl_practice_tasks task ON task.id=assignment.task_id AND task.status<>'draft' AND task.deleted_at IS NULL
                          JOIN cl_chapters chapter ON chapter.course_version_id=task.course_version_id
                          JOIN cl_content_items content ON content.id=interaction.content_item_id AND content.chapter_id=chapter.id
                          WHERE interaction.id=%s AND interaction.content_item_id=%s AND interaction.status='published'""", (assignment_id, user_id, interaction_id, content_item_id))
            interaction = cur.fetchone()
            if not interaction:
                raise ValueError("互动内容不存在或不属于当前练习")
            config = interaction["config"] or {}
            normalized = str(answer or "").strip().casefold()
            correct = str(config.get("correct_answer") or "").strip().casefold()
            accepted = [str(value).strip().casefold() for value in (config.get("accepted_answers") or [])]
            is_correct = normalized == correct if interaction["interaction_type"] in {"choice", "hotspot"} else normalized in set(accepted + ([correct] if correct else []))
            feedback = interaction["feedback_correct"] if is_correct else interaction["feedback_incorrect"]
            cur.execute("""INSERT INTO cl_interaction_attempts(assignment_id,user_id,content_item_id,interaction_id,answer,is_correct,score,feedback)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (assignment_id, user_id, content_item_id, interaction_id, Jsonb({"value": answer}), is_correct, 1 if is_correct else 0, feedback))
            cur.execute("""SELECT count(*)::int AS attempt_count,coalesce(bool_or(is_correct),false) AS completed
                          FROM cl_interaction_attempts WHERE assignment_id=%s AND interaction_id=%s""", (assignment_id, interaction_id))
            result = cur.fetchone()
            return {"interaction_id": interaction_id, "assignment_id": assignment_id, "content_item_id": content_item_id, "is_correct": is_correct, "score": 1.0 if is_correct else 0.0, "feedback": feedback, "completed": bool(result["completed"]), "attempt_count": result["attempt_count"], "answer": answer}

    @staticmethod
    def _course_standard_record(row: Any) -> dict[str, Any]:
        item = dict(row)
        pronunciation = item.pop("pronunciation_rules") or {}
        prosody = item.pop("prosody_rules") or {}
        expression = item.pop("expression_rules") or {}
        audio_ref = item.pop("standard_audio_ref", None)
        item.update({
            "stress_rules": str(pronunciation.get("stress", "")),
            "pronunciation_notes": str(pronunciation.get("notes", "")),
            "pause_rules": str(prosody.get("pause", "")),
            "tone_requirements": str(expression.get("tone", "")),
            "standard_audio_filename": item.get("standard_audio_filename") or (str(audio_ref).rsplit("/", 1)[-1] if audio_ref else None),
            "standard_audio_url": (
                f"/api/v1/cabinlingo/course-standard-audio/{item['standard_audio_file_id']}"
                if item.get("standard_audio_file_id") else None
            ),
        })
        return item

    def get_course_standard(self, content_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT s.id::text AS id,s.content_item_id::text AS content_item_id,s.standard_text,
                          s.pronunciation_rules,s.prosody_rules,s.expression_rules,s.rule_version,s.change_summary,s.standard_audio_filename,
                          s.standard_audio_file_id::text AS standard_audio_file_id,file.object_key AS standard_audio_ref,s.created_at
                          FROM cl_course_standards s LEFT JOIN files file ON file.id=s.standard_audio_file_id
                          WHERE s.content_item_id=%s ORDER BY s.created_at DESC,s.id DESC LIMIT 1""", (content_id,))
            row = cur.fetchone()
            return self._course_standard_record(row) if row else None

    def save_course_standard(self, content_id: str, data: dict[str, Any], created_by: str) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT version.status FROM cl_content_items content
                          JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          JOIN cl_course_versions version ON version.id=chapter.course_version_id
                          WHERE content.id=%s""", (content_id,))
            version = cur.fetchone()
            if not version or version["status"] != "draft":
                raise ValueError("Only a draft course version can be edited")
            cur.execute("""SELECT standard_audio_file_id,standard_audio_filename FROM cl_course_standards
                          WHERE content_item_id=%s ORDER BY created_at DESC,id DESC LIMIT 1""", (content_id,))
            previous = cur.fetchone()
            cur.execute("""INSERT INTO cl_course_standards(
                            content_item_id,standard_text,standard_audio_file_id,standard_audio_filename,pronunciation_rules,prosody_rules,
                            expression_rules,rule_version,created_by,change_summary)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          RETURNING id::text AS id,content_item_id::text AS content_item_id,standard_text,
                            pronunciation_rules,prosody_rules,expression_rules,rule_version,change_summary,
                            standard_audio_file_id::text AS standard_audio_file_id,standard_audio_filename,NULL::text AS standard_audio_ref,created_at""",
                        (content_id, data["standard_text"], previous["standard_audio_file_id"] if previous else None,
                         previous["standard_audio_filename"] if previous else None,
                         Jsonb({"stress": data.get("stress_rules", ""), "notes": data.get("pronunciation_notes", "")}),
                         Jsonb({"pause": data.get("pause_rules", "")}),
                         Jsonb({"tone": data.get("tone_requirements", "")}), data.get("rule_version", "1.0"),
                         created_by, data.get("change_summary", "")))
            item = self._course_standard_record(cur.fetchone())
            if item.get("standard_audio_file_id") and not item.get("standard_audio_filename"):
                cur.execute("SELECT object_key FROM files WHERE id=%s", (item["standard_audio_file_id"],))
                file_row = cur.fetchone()
                if file_row:
                    item["standard_audio_filename"] = str(file_row["object_key"]).rsplit("/", 1)[-1]
            return item

    def attach_course_standard_audio(self, content_id: str, standard_id: str, audio_ref: str,
                                     mime_type: str, byte_size: int, source_filename: str,
                                     created_by: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT version.status FROM cl_course_standards s
                          JOIN cl_content_items content ON content.id=s.content_item_id
                          JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          JOIN cl_course_versions version ON version.id=chapter.course_version_id
                          WHERE s.id=%s AND s.content_item_id=%s""", (standard_id, content_id))
            version = cur.fetchone()
            if not version:
                raise ValueError("Course standard not found")
            if version["status"] != "draft":
                raise ValueError("Only a draft course version can be edited")
            cur.execute("""INSERT INTO files(owner_id,object_key,mime_type,byte_size)
                          VALUES (%s,%s,%s,%s) RETURNING id::text AS id""",
                        (created_by, audio_ref, mime_type, byte_size))
            file_id = cur.fetchone()["id"]
            cur.execute("UPDATE cl_course_standards SET standard_audio_file_id=%s,standard_audio_filename=%s WHERE id=%s",
                        (file_id, source_filename, standard_id))
            cur.execute("""SELECT s.id::text AS id,s.content_item_id::text AS content_item_id,s.standard_text,
                          s.pronunciation_rules,s.prosody_rules,s.expression_rules,s.rule_version,s.change_summary,s.standard_audio_filename,
                          s.standard_audio_file_id::text AS standard_audio_file_id,file.object_key AS standard_audio_ref,s.created_at
                          FROM cl_course_standards s LEFT JOIN files file ON file.id=s.standard_audio_file_id
                          WHERE s.id=%s""", (standard_id,))
            return self._course_standard_record(cur.fetchone())

    def get_course_standard_audio(self, file_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT file.object_key AS audio_ref,file.mime_type,file.byte_size,s.standard_audio_filename AS source_filename
                          FROM files file JOIN cl_course_standards s ON s.standard_audio_file_id=file.id
                          WHERE file.id=%s LIMIT 1""", (file_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def publish_course_version(self, course_version_id: str, published_by: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT course_id::text AS course_id FROM cl_course_versions WHERE id=%s", (course_version_id,))
            version = cur.fetchone()
            if not version:
                raise ValueError("Course version not found")
            course_id = version["course_id"]
            cur.execute("SELECT id FROM cl_courses WHERE id=%s FOR UPDATE", (course_id,))
            if not cur.fetchone():
                raise ValueError("Course not found")
            cur.execute("SELECT status FROM cl_course_versions WHERE id=%s AND course_id=%s FOR UPDATE",
                        (course_version_id, course_id))
            version_status = cur.fetchone()
            if not version_status:
                raise ValueError("Course version not found")
            if version_status["status"] not in {"draft", "published"}:
                raise ValueError("Only a draft course version can be published")
            cur.execute("""SELECT count(DISTINCT chapter.id)::int AS chapter_count,count(content.id)::int AS content_count
                          FROM cl_chapters chapter LEFT JOIN cl_content_items content ON content.chapter_id=chapter.id
                          WHERE chapter.course_version_id=%s""", (course_version_id,))
            counts = cur.fetchone()
            version = {**dict(version_status), **dict(counts), "course_id": course_id}
            if version["chapter_count"] < 1 or version["content_count"] < 1:
                raise ValueError("A course version needs at least one chapter and one content item")
            if version_status["status"] == "draft":
                cur.execute("UPDATE cl_course_versions SET status='archived' WHERE course_id=%s AND status='published' AND id<>%s", (course_id, course_version_id))
                cur.execute("UPDATE cl_course_versions SET status='published',published_by=%s,published_at=now() WHERE id=%s", (published_by, course_version_id))
                cur.execute("UPDATE cl_courses SET status='published',updated_at=now() WHERE id=%s", (course_id,))
                cur.execute("""UPDATE cl_content_interactions SET status='published',updated_at=now()
                              WHERE content_item_id IN (
                                SELECT content.id FROM cl_content_items content
                                JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                                WHERE chapter.course_version_id=%s
                              ) AND status='draft'""", (course_version_id,))
            cur.execute("""SELECT id::text AS id,course_id::text AS course_id,version_no,version_label,status,change_summary,
                          %s::int AS chapter_count,%s::int AS content_count,published_at FROM cl_course_versions WHERE id=%s""",
                        (version["chapter_count"], version["content_count"], course_version_id))
            return dict(cur.fetchone())

    @staticmethod
    def _course_v23_record(row: Any) -> dict[str, Any]:
        item = dict(row)
        for role in ("cover", "video"):
            file_id = item.pop(f"{role}_file_id", None)
            item[f"{role}_url"] = f"/api/v1/cabinlingo/course-v23-media/{file_id}" if file_id else None
        legacy_audio: dict[str, tuple[str | None, str]] = {}
        for role in ("audio", "audio_zh", "audio_en"):
            file_id = item.pop(f"{role}_file_id", None)
            legacy_audio[role] = (file_id, item.get(f"{role}_filename") or "")
            item[f"{role}_url"] = f"/api/v1/cabinlingo/course-v23-media/{file_id}" if file_id else None
        tracks = []
        for track in item.pop("stored_audio_tracks", None) or []:
            language = str(track.get("language") or "bilingual")
            sequence = int(track.get("sequence_no") or 1)
            role = "audio" if language == "bilingual" else f"audio_{language}" if sequence == 1 else f"audio_{language}_{sequence}"
            tracks.append({
                "file_id": str(track.get("file_id") or ""),
                "role": role,
                "label": str(track.get("label") or ""),
                "language": language,
                "sequence_no": sequence,
                "filename": str(track.get("filename") or ""),
                "url": f"/api/v1/cabinlingo/course-v23-media/{track['file_id']}",
                "alignment": dict(track.get("alignment") or {}),
            })
        if not tracks:
            for role, label, language in (
                ("audio", "完整示范音频", "bilingual"),
                ("audio_zh", "中文标准音频 1", "zh"),
                ("audio_en", "英文标准音频 1", "en"),
            ):
                file_id, filename = legacy_audio[role]
                if file_id:
                    tracks.append({"role": role, "label": label, "language": language, "sequence_no": 1, "filename": filename, "url": item[f"{role}_url"]})
        item["audio_tracks"] = tracks
        errors: list[str] = []
        is_expression_video = item.get("course_kind") == "expression_skill" and item.get("content_mode") == "video"
        required_fields = (("title_zh", "课程名称"),) if is_expression_video else (("title_zh", "课程名称"), ("delivery_pace", "播音速度"))
        for field, label in required_fields:
            if not str(item.get(field) or "").strip():
                errors.append(f"{label}不能为空")
        if not is_expression_video:
            expected = {"zh", "en"} if item.get("language") == "bilingual" else {item.get("language")}
            annotated = item.get("annotated_scripts") or {}
            for language in expected:
                if language and not str(annotated.get(language) or "").strip():
                    errors.append(f"缺少 {language} 专业标注原文")
            has_complete_audio = bool(item.get("audio_url"))
            has_zh_audio = bool(item.get("audio_zh_url"))
            has_en_audio = bool(item.get("audio_en_url"))
            if item.get("language") == "bilingual" and not has_complete_audio and not (has_zh_audio and has_en_audio):
                errors.append("双语课程需上传完整示范音频，或同时上传中文和英文标准音频")
            elif item.get("language") == "zh" and not (has_complete_audio or has_zh_audio):
                errors.append("缺少中文标准音频")
            elif item.get("language") == "en" and not (has_complete_audio or has_en_audio):
                errors.append("缺少英文标准音频")
            if not item.get("mistake_words"):
                errors.append("至少需要一条易错词")
        if item.get("content_mode") == "video" and not (item.get("video_url") or item.get("cos_video_key")):
            errors.append("缺少课程视频")
        if item.get("publish_scope") == "classes" and not item.get("publish_class_ids"):
            errors.append("指定班级发布时至少选择一个班级")
        item["validation_errors"] = errors
        return item

    def _course_v23_query(self, where: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"""SELECT course.id::text AS id,course.code AS course_id,version.id::text AS course_version_id,
                          content.id::text AS content_item_id,course.code,course.title AS title_zh,detail.title_en,
                          course.category,detail.summary,detail.language_code AS language,version.version_label,version.status,
                          course.status AS course_status,
                          EXISTS(SELECT 1 FROM cl_course_versions published WHERE published.course_id=course.id AND published.status='published') AS has_published_version,
                          (SELECT count(*)::int FROM (
                            SELECT task.id FROM cl_practice_tasks task JOIN cl_course_versions task_version ON task_version.id=task.course_version_id
                              WHERE task_version.course_id=course.id AND task.deleted_at IS NULL
                            UNION ALL
                            SELECT task.id FROM cl_exam_tasks task JOIN cl_course_versions task_version ON task_version.id=task.course_version_id
                              WHERE task_version.course_id=course.id AND task.deleted_at IS NULL
                          ) all_tasks) AS task_count,
                          (SELECT count(*)::int FROM (
                            SELECT task.id FROM cl_practice_tasks task JOIN cl_course_versions task_version ON task_version.id=task.course_version_id
                              WHERE task_version.course_id=course.id AND task.deleted_at IS NULL AND task.status<>'closed'
                            UNION ALL
                            SELECT task.id FROM cl_exam_tasks task JOIN cl_course_versions task_version ON task_version.id=task.course_version_id
                              WHERE task_version.course_id=course.id AND task.deleted_at IS NULL AND task.status<>'closed'
                          ) active_tasks) AS active_task_count,
                          detail.course_kind,detail.content_mode,detail.training_enabled,detail.content_config,
                          detail.explanation,detail.annotated_scripts,detail.delivery_tone,detail.delivery_pace,
                          detail.delivery_rhythm,COALESCE(standard.pronunciation_rules->>'notes','') AS pronunciation_notes,
                          detail.mistake_words,detail.cover_filename,detail.cover_file_id::text AS cover_file_id,
                          detail.video_filename,detail.video_file_id::text AS video_file_id,
                          detail.standard_audio_filename AS audio_filename,detail.standard_audio_file_id::text AS audio_file_id,
                          detail.zh_audio_filename AS audio_zh_filename,detail.zh_audio_file_id::text AS audio_zh_file_id,
                          detail.en_audio_filename AS audio_en_filename,detail.en_audio_file_id::text AS audio_en_file_id,
                          detail.cos_video_key,detail.cos_video_filename,detail.cos_video_size,detail.cos_video_etag,
                          detail.sort_order,detail.publish_scope,
                          COALESCE(ARRAY(SELECT class_id::text FROM unnest(detail.publish_class_ids) class_id),'{{}}'::text[]) AS publish_class_ids,
                          tracks.audio_tracks AS stored_audio_tracks,version.published_at,detail.updated_at
                          FROM cl_course_details detail
                          JOIN cl_course_versions version ON version.id=detail.course_version_id
                          JOIN cl_courses course ON course.id=version.course_id
                          JOIN cl_chapters chapter ON chapter.course_version_id=version.id AND chapter.code='COURSE-V23'
                          JOIN cl_content_items content ON content.chapter_id=chapter.id AND content.sequence_no=1
                          LEFT JOIN LATERAL (SELECT pronunciation_rules FROM cl_course_standards item
                            WHERE item.content_item_id=content.id ORDER BY item.created_at DESC,item.id DESC LIMIT 1) standard ON true
                          LEFT JOIN LATERAL (
                            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                              'file_id',track.file_id::text,'language',track.language_code,'sequence_no',track.sequence_no,
                              'label',track.label,'filename',track.filename,'alignment',track.alignment
                            ) ORDER BY CASE track.language_code WHEN 'bilingual' THEN 0 WHEN 'zh' THEN 1 ELSE 2 END,track.sequence_no),'[]'::jsonb) AS audio_tracks
                            FROM cl_course_audio_tracks track WHERE track.course_version_id=version.id
                          ) tracks ON true
                          WHERE {where} ORDER BY detail.sort_order ASC,detail.updated_at DESC""", params)
            return [self._course_v23_record(row) for row in cur.fetchall()]

    def list_course_v23(self) -> list[dict[str, Any]]:
        return self._course_v23_query("course.category<>'broadcast_snapshot'", ())

    def list_published_course_v23(self, user_id: str) -> list[dict[str, Any]]:
        return self._course_v23_query(
            "version.status='published' AND course.status='published' AND course.category<>'broadcast_snapshot' "
            "AND (course.organization_id IS NULL OR course.organization_id=(SELECT organization_id FROM users WHERE id=%s)) "
            "AND (detail.publish_scope='all_authorized' OR EXISTS (SELECT 1 FROM class_memberships membership "
            "WHERE membership.user_id=%s AND membership.status='active' AND membership.class_id=ANY(detail.publish_class_ids)))",
            (user_id, user_id),
        )

    def get_published_course_v23_for_user(self, version_id: str, user_id: str) -> dict[str, Any] | None:
        rows = self._course_v23_query(
            "version.id=%s AND version.status='published' AND course.status='published' "
            "AND (course.organization_id IS NULL OR course.organization_id=(SELECT organization_id FROM users WHERE id=%s)) "
            "AND (detail.publish_scope='all_authorized' OR EXISTS (SELECT 1 FROM class_memberships membership "
            "WHERE membership.user_id=%s AND membership.status='active' AND membership.class_id=ANY(detail.publish_class_ids)))",
            (version_id, user_id, user_id),
        )
        return rows[0] if rows else None

    def get_course_v23(self, version_id: str, published_only: bool = False) -> dict[str, Any] | None:
        where = "version.id=%s" + (" AND version.status='published' AND course.status='published'" if published_only else "")
        rows = self._course_v23_query(where, (version_id,))
        return rows[0] if rows else None

    def get_course_v23_by_course(self, course_id: str) -> dict[str, Any] | None:
        rows = self._course_v23_query("course.id=%s", (course_id,))
        if not rows:
            return None
        return next((item for item in rows if item.get("status") == "draft"), rows[0])

    def set_course_v23_status(self, course_id: str, status: str) -> dict[str, Any]:
        if status not in {"draft", "published", "archived"}:
            raise ValueError("课程状态无效")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id,status FROM cl_courses WHERE id=%s FOR UPDATE", (course_id,))
            course = cur.fetchone()
            if not course:
                raise ValueError("课程不存在")
            if status == "published":
                cur.execute("SELECT 1 FROM cl_course_versions WHERE course_id=%s AND status='published' LIMIT 1", (course_id,))
                if not cur.fetchone():
                    raise ValueError("课程尚无已发布版本，请先发布课程")
            if status == "archived":
                cur.execute("""SELECT count(*)::int AS count FROM (
                              SELECT task.id FROM cl_practice_tasks task JOIN cl_course_versions version ON version.id=task.course_version_id
                                WHERE version.course_id=%s AND task.deleted_at IS NULL AND task.status<>'closed'
                              UNION ALL
                              SELECT task.id FROM cl_exam_tasks task JOIN cl_course_versions version ON version.id=task.course_version_id
                                WHERE version.course_id=%s AND task.deleted_at IS NULL AND task.status<>'closed'
                              ) active""", (course_id, course_id))
                if int(cur.fetchone()["count"] or 0):
                    raise ValueError("课程存在进行中任务，不能删除")
            cur.execute("UPDATE cl_courses SET status=%s,updated_at=now() WHERE id=%s", (status, course_id))
        item = self.get_course_v23_by_course(course_id)
        if not item:
            raise ValueError("课程详情不存在")
        return item

    def create_course_v23_revision(self, source_version_id: str, created_by: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT course_id::text AS course_id,status FROM cl_course_versions WHERE id=%s FOR UPDATE", (source_version_id,))
            source = cur.fetchone()
            if not source:
                raise ValueError("课程版本不存在")
            cur.execute("SELECT id::text AS id FROM cl_course_versions WHERE course_id=%s AND status='draft' ORDER BY created_at DESC LIMIT 1", (source["course_id"],))
            existing = cur.fetchone()
            if existing:
                draft_id = str(existing["id"])
            else:
                cur.execute("SELECT COALESCE(max(version_no),0)+1 AS version_no FROM cl_course_versions WHERE course_id=%s", (source["course_id"],))
                version_no = int(cur.fetchone()["version_no"])
                cur.execute("""INSERT INTO cl_course_versions(course_id,version_no,version_label,status,change_summary,created_by)
                              VALUES (%s,%s,%s,'draft','Created from published course',%s) RETURNING id::text AS id""",
                            (source["course_id"], version_no, f"V{version_no}.0", created_by))
                draft_id = str(cur.fetchone()["id"])
                cur.execute("""INSERT INTO cl_chapters(course_version_id,code,title,sequence_no,learning_objective)
                              SELECT %s,code,title,sequence_no,learning_objective FROM cl_chapters WHERE course_version_id=%s
                              RETURNING id::text AS id""", (draft_id, source_version_id))
                new_chapter_id = str(cur.fetchone()["id"])
                cur.execute("""INSERT INTO cl_content_items(chapter_id,content_type,title,sequence_no,source_filename,sanitized_html,
                              original_sha256,sanitized_sha256,validation_report,created_by)
                              SELECT %s,content_type,title,sequence_no,source_filename,sanitized_html,original_sha256,sanitized_sha256,
                                     validation_report,%s FROM cl_content_items
                              WHERE chapter_id=(SELECT id FROM cl_chapters WHERE course_version_id=%s AND code='COURSE-V23') AND sequence_no=1
                              RETURNING id::text AS id""", (new_chapter_id, created_by, source_version_id))
                new_content_id = str(cur.fetchone()["id"])
                cur.execute("""INSERT INTO cl_course_standards(content_item_id,standard_text,standard_audio_file_id,pronunciation_rules,
                              prosody_rules,expression_rules,rule_version,created_by,change_summary,standard_audio_filename)
                              SELECT %s,standard_text,standard_audio_file_id,pronunciation_rules,prosody_rules,expression_rules,rule_version,
                                     %s,'Created from published course',standard_audio_filename
                              FROM cl_course_standards WHERE content_item_id=(
                                SELECT content.id FROM cl_content_items content JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                                WHERE chapter.course_version_id=%s AND content.sequence_no=1
                              ) ORDER BY created_at DESC,id DESC LIMIT 1""", (new_content_id, created_by, source_version_id))
                cur.execute("""INSERT INTO cl_course_details(course_version_id,title_en,summary,language_code,delivery_tone,delivery_pace,
                              delivery_rhythm,explanation,annotated_scripts,mistake_words,cover_file_id,cover_filename,video_file_id,
                              video_filename,standard_audio_file_id,standard_audio_filename,created_by,course_kind,content_mode,
                              training_enabled,content_config,zh_audio_file_id,zh_audio_filename,en_audio_file_id,en_audio_filename,
                              cos_video_key,cos_video_filename,cos_video_size,cos_video_etag,sort_order,publish_scope,publish_class_ids)
                              SELECT %s,title_en,summary,language_code,delivery_tone,delivery_pace,delivery_rhythm,explanation,
                                     annotated_scripts,mistake_words,cover_file_id,cover_filename,video_file_id,video_filename,
                                     standard_audio_file_id,standard_audio_filename,%s,course_kind,content_mode,training_enabled,
                                     content_config,zh_audio_file_id,zh_audio_filename,en_audio_file_id,en_audio_filename,
                                     cos_video_key,cos_video_filename,cos_video_size,cos_video_etag,sort_order,publish_scope,publish_class_ids
                              FROM cl_course_details WHERE course_version_id=%s""", (draft_id, created_by, source_version_id))
                cur.execute("""INSERT INTO cl_course_audio_tracks(course_version_id,file_id,language_code,sequence_no,label,filename,created_by)
                              SELECT %s,file_id,language_code,sequence_no,label,filename,%s FROM cl_course_audio_tracks
                              WHERE course_version_id=%s ON CONFLICT DO NOTHING""", (draft_id, created_by, source_version_id))
        item = self.get_course_v23(draft_id)
        if not item:
            raise ValueError("课程草稿创建失败")
        return item

    def update_course_v23_mistake_words(self, version_id: str, mistake_words: list[dict[str, Any]]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM cl_course_versions WHERE id=%s FOR UPDATE", (version_id,))
            version = cur.fetchone()
            if not version:
                raise ValueError("课程草稿不存在")
            if version["status"] != "draft":
                raise ValueError("已发布课程不可直接修改，请先创建新版本")
            cur.execute("UPDATE cl_course_details SET mistake_words=%s,updated_at=now() WHERE course_version_id=%s", (Jsonb(mistake_words), version_id))
        item = self.get_course_v23(version_id)
        if not item:
            raise ValueError("易错词保存失败")
        return item

    def next_available_course_code(self, requested: str, organization_id: str | None) -> str:
        base = requested.strip()[:72]
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT lower(code) AS code FROM cl_courses WHERE organization_id IS NOT DISTINCT FROM %s",
                (organization_id,),
            )
            existing = {row["code"] for row in cur.fetchall()}
        if base.lower() not in existing:
            return base
        suffix = 2
        while f"{base}-{suffix}".lower() in existing:
            suffix += 1
        return f"{base}-{suffix}"

    @staticmethod
    def _course_audio_track_spec(role: str) -> tuple[str, int, str] | None:
        specs = {
            "audio": ("bilingual", 1, "完整示范音频"),
            "audio_zh": ("zh", 1, "中文标准音频 1"),
            "audio_zh_1": ("zh", 1, "中文标准音频 1"),
            "audio_zh_2": ("zh", 2, "中文标准音频 2"),
            "audio_en": ("en", 1, "英文标准音频 1"),
            "audio_en_1": ("en", 1, "英文标准音频 1"),
            "audio_en_2": ("en", 2, "英文标准音频 2"),
        }
        return specs.get(role)

    def create_course_v23_draft(self, data: dict[str, Any], media_records: list[dict[str, Any]],
                                created_by: str, batch_id: str | None = None) -> dict[str, Any]:
        from html import escape
        from psycopg.types.json import Jsonb
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM cl_courses WHERE lower(code)=lower(%s) AND organization_id IS NOT DISTINCT FROM %s", (data["course_id"], data.get("organization_id")))
                if cur.fetchone():
                    raise ValueError("Course code already exists")
                cur.execute("""INSERT INTO cl_courses(organization_id,code,title,description,category,created_by)
                              VALUES (%s,%s,%s,%s,%s,%s) RETURNING id::text AS id""",
                            (data.get("organization_id"), data["course_id"], data["title_zh"], data["summary"], data["category"], created_by))
                course_id = str(cur.fetchone()["id"])
                cur.execute("""INSERT INTO cl_course_versions(course_id,version_no,version_label,change_summary,created_by)
                              VALUES (%s,1,%s,'Course V2.3 draft',%s) RETURNING id::text AS id""",
                            (course_id, data.get("version_label", "V1.0"), created_by))
                version_id = str(cur.fetchone()["id"])
                cur.execute("""INSERT INTO cl_chapters(course_version_id,code,title,sequence_no,learning_objective)
                              VALUES (%s,'COURSE-V23',%s,1,%s) RETURNING id::text AS id""",
                            (version_id, data["title_zh"], data.get("explanation", "")))
                chapter_id = str(cur.fetchone()["id"])
                standard_text = str((data.get("annotated_scripts") or {}).get("zh") or (data.get("annotated_scripts") or {}).get("en") or "")
                cur.execute("""INSERT INTO cl_content_items(chapter_id,content_type,title,sequence_no,source_filename,sanitized_html,
                              validation_report,created_by) VALUES (%s,'html',%s,1,%s,%s,%s,%s) RETURNING id::text AS id""",
                            (chapter_id, data["title_zh"], f"{data['course_id']}.html", f"<p>{escape(standard_text)}</p>", Jsonb({"source": "course_v23"}), created_by))
                content_id = str(cur.fetchone()["id"])
                file_ids: dict[str, str] = {}
                filenames: dict[str, str] = {}
                for media in media_records:
                    cur.execute("INSERT INTO files(owner_id,object_key,mime_type,byte_size) VALUES (%s,%s,%s,%s) RETURNING id::text AS id",
                                (created_by, media["asset_ref"], media["mime_type"], media["byte_size"]))
                    file_ids[media["role"]] = str(cur.fetchone()["id"])
                    filenames[media["role"]] = media["filename"][:255]
                    spec = self._course_audio_track_spec(media["role"])
                    if spec:
                        language, sequence, label = spec
                        cur.execute("""INSERT INTO cl_course_audio_tracks(course_version_id,file_id,language_code,sequence_no,label,filename,created_by)
                                      VALUES (%s,%s,%s,%s,%s,%s,%s)
                                      ON CONFLICT(course_version_id,language_code,sequence_no) DO UPDATE SET
                                        file_id=EXCLUDED.file_id,label=EXCLUDED.label,filename=EXCLUDED.filename,created_by=EXCLUDED.created_by,created_at=now()""",
                                    (version_id, file_ids[media["role"]], language, sequence, label, filenames[media["role"]], created_by))
                if file_ids.get("audio_zh_1"):
                    file_ids["audio_zh"], filenames["audio_zh"] = file_ids["audio_zh_1"], filenames["audio_zh_1"]
                if file_ids.get("audio_en_1"):
                    file_ids["audio_en"], filenames["audio_en"] = file_ids["audio_en_1"], filenames["audio_en_1"]
                preferred_role = "audio_en" if data.get("language") == "en" else "audio_zh" if data.get("language") == "zh" else "audio"
                selected_role = preferred_role if file_ids.get(preferred_role) else "audio" if file_ids.get("audio") else "audio_zh" if file_ids.get("audio_zh") else "audio_en"
                cur.execute("""INSERT INTO cl_course_standards(content_item_id,standard_text,standard_audio_file_id,
                              standard_audio_filename,pronunciation_rules,prosody_rules,expression_rules,rule_version,
                              created_by,change_summary) VALUES (%s,%s,%s,%s,%s,%s,%s,'2.3',%s,'Course V2.3 structured draft')""",
                            (content_id, standard_text, file_ids.get(selected_role), filenames.get(selected_role),
                             Jsonb({"stress": "按专业标注原文中的强调标记朗读", "notes": data.get("pronunciation_notes", "")}),
                             Jsonb({"pause": "短停 /；长停 //"}), Jsonb({"tone": "、".join(data.get("delivery_tone") or [])}), created_by))
                cur.execute("""INSERT INTO cl_course_details(course_version_id,title_en,summary,language_code,course_kind,
                              content_mode,training_enabled,content_config,delivery_tone,
                              delivery_pace,delivery_rhythm,explanation,annotated_scripts,mistake_words,cover_file_id,
                              cover_filename,video_file_id,video_filename,standard_audio_file_id,standard_audio_filename,
                              zh_audio_file_id,zh_audio_filename,en_audio_file_id,en_audio_filename,
                              source_import_batch_id,created_by,cos_video_key,cos_video_filename,cos_video_size,
                              cos_video_etag,sort_order,publish_scope,publish_class_ids)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (version_id, data.get("title_en", ""), data["summary"], data.get("language", "bilingual"),
                             data.get("course_kind", "lesson"), data.get("content_mode", "audio_text"),
                             bool(data.get("training_enabled", True)), Jsonb(data.get("content_config") or {}),
                             Jsonb(data.get("delivery_tone") or []), data.get("delivery_pace", ""),
                             Jsonb(data.get("delivery_rhythm") or []), data.get("explanation", ""),
                             Jsonb(data.get("annotated_scripts") or {}), Jsonb(data.get("mistake_words") or []),
                             file_ids.get("cover"), filenames.get("cover"), file_ids.get("video"), filenames.get("video"),
                             file_ids.get("audio"), filenames.get("audio"), file_ids.get("audio_zh"), filenames.get("audio_zh"),
                             file_ids.get("audio_en"), filenames.get("audio_en"), batch_id, created_by,
                             data.get("cos_video_key"), data.get("cos_video_filename"), data.get("cos_video_size"),
                             data.get("cos_video_etag"), int(data.get("sort_order") or 0),
                             data.get("publish_scope", "all_authorized"), data.get("publish_class_ids") or []))
            return self.get_course_v23(version_id) or {}
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Course V2.3 draft could not be created") from exc

    def update_course_v23_draft(self, version_id: str, data: dict[str, Any], media_records: list[dict[str, Any]],
                                updated_by: str, expected_updated_at: str | None = None) -> dict[str, Any]:
        from html import escape
        from psycopg.types.json import Jsonb
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("""SELECT version.status,version.course_id::text AS course_id,course.code,
                              detail.cover_file_id::text AS cover_file_id,detail.video_file_id::text AS video_file_id,
                              detail.standard_audio_file_id::text AS audio_file_id,detail.cover_filename,
                              detail.video_filename,detail.standard_audio_filename AS audio_filename,
                              detail.zh_audio_file_id::text AS audio_zh_file_id,detail.zh_audio_filename AS audio_zh_filename,
                              detail.en_audio_file_id::text AS audio_en_file_id,detail.en_audio_filename AS audio_en_filename,
                              detail.updated_at::text AS updated_at,content.id::text AS content_id
                              FROM cl_course_versions version
                              JOIN cl_courses course ON course.id=version.course_id
                              JOIN cl_course_details detail ON detail.course_version_id=version.id
                              JOIN cl_chapters chapter ON chapter.course_version_id=version.id AND chapter.code='COURSE-V23'
                              JOIN cl_content_items content ON content.chapter_id=chapter.id AND content.sequence_no=1
                              WHERE version.id=%s FOR UPDATE""", (version_id,))
                current = cur.fetchone()
                if not current:
                    raise ValueError("Course V2.3 draft not found")
                if current["status"] != "draft":
                    raise ValueError("已发布课程不可直接修改，请创建新版本")
                if expected_updated_at:
                    cur.execute("SELECT %s::timestamptz=%s::timestamptz AS matches",
                                (expected_updated_at, current["updated_at"]))
                    if not cur.fetchone()["matches"]:
                        raise ValueError("课程草稿已被其他管理员修改，请刷新后重试")
                if data["course_id"].lower() != str(current["code"]).lower():
                    raise ValueError("课程 ID 创建后不可修改")

                cur.execute("""UPDATE cl_courses SET organization_id=%s,title=%s,description=%s,category=%s,updated_at=now()
                              WHERE id=%s""", (data.get("organization_id"), data["title_zh"], data["summary"], data["category"], current["course_id"]))
                cur.execute("UPDATE cl_course_versions SET version_label=%s,change_summary='Course content draft updated' WHERE id=%s",
                            (data.get("version_label", "V1.0"), version_id))
                cur.execute("UPDATE cl_chapters SET title=%s,learning_objective=%s WHERE course_version_id=%s AND code='COURSE-V23'",
                            (data["title_zh"], data.get("explanation", ""), version_id))
                standard_text = str((data.get("annotated_scripts") or {}).get("zh") or (data.get("annotated_scripts") or {}).get("en") or "")
                cur.execute("UPDATE cl_content_items SET title=%s,sanitized_html=%s,updated_at=now() WHERE id=%s",
                            (data["title_zh"], f"<p>{escape(standard_text)}</p>", current["content_id"]))

                file_ids = {role: current[f"{role}_file_id"] for role in ("cover", "video", "audio", "audio_zh", "audio_en")}
                filenames = {role: current[f"{role}_filename"] for role in ("cover", "video", "audio", "audio_zh", "audio_en")}
                for media in media_records:
                    cur.execute("INSERT INTO files(owner_id,object_key,mime_type,byte_size) VALUES (%s,%s,%s,%s) RETURNING id::text AS id",
                                (updated_by, media["asset_ref"], media["mime_type"], media["byte_size"]))
                    file_ids[media["role"]] = str(cur.fetchone()["id"])
                    filenames[media["role"]] = media["filename"][:255]
                    spec = self._course_audio_track_spec(media["role"])
                    if spec:
                        language, sequence, label = spec
                        cur.execute("""INSERT INTO cl_course_audio_tracks(course_version_id,file_id,language_code,sequence_no,label,filename,created_by)
                                      VALUES (%s,%s,%s,%s,%s,%s,%s)
                                      ON CONFLICT(course_version_id,language_code,sequence_no) DO UPDATE SET
                                        file_id=EXCLUDED.file_id,label=EXCLUDED.label,filename=EXCLUDED.filename,created_by=EXCLUDED.created_by,created_at=now()""",
                                    (version_id, file_ids[media["role"]], language, sequence, label, filenames[media["role"]], updated_by))
                if file_ids.get("audio_zh_1"):
                    file_ids["audio_zh"], filenames["audio_zh"] = file_ids["audio_zh_1"], filenames["audio_zh_1"]
                if file_ids.get("audio_en_1"):
                    file_ids["audio_en"], filenames["audio_en"] = file_ids["audio_en_1"], filenames["audio_en_1"]

                cur.execute("""UPDATE cl_course_details SET title_en=%s,summary=%s,language_code=%s,course_kind=%s,
                              content_mode=%s,training_enabled=%s,content_config=%s,delivery_tone=%s,delivery_pace=%s,
                              delivery_rhythm=%s,explanation=%s,annotated_scripts=%s,mistake_words=%s,
                              cover_file_id=%s,cover_filename=COALESCE(%s,cover_filename),
                              video_file_id=%s,video_filename=COALESCE(%s,video_filename),
                              standard_audio_file_id=%s,standard_audio_filename=COALESCE(%s,standard_audio_filename),
                              zh_audio_file_id=%s,zh_audio_filename=COALESCE(%s,zh_audio_filename),
                              en_audio_file_id=%s,en_audio_filename=COALESCE(%s,en_audio_filename),
                              cos_video_key=%s,cos_video_filename=%s,cos_video_size=%s,cos_video_etag=%s,
                              sort_order=%s,publish_scope=%s,publish_class_ids=%s,updated_at=now()
                              WHERE course_version_id=%s""",
                            (data.get("title_en", ""), data["summary"], data.get("language", "bilingual"),
                             data.get("course_kind", "lesson"), data.get("content_mode", "audio_text"),
                             bool(data.get("training_enabled", True)), Jsonb(data.get("content_config") or {}),
                             Jsonb(data.get("delivery_tone") or []), data.get("delivery_pace", ""),
                             Jsonb(data.get("delivery_rhythm") or []), data.get("explanation", ""),
                             Jsonb(data.get("annotated_scripts") or {}), Jsonb(data.get("mistake_words") or []),
                             file_ids["cover"], filenames.get("cover"), file_ids["video"], filenames.get("video"),
                             file_ids["audio"], filenames.get("audio"), file_ids["audio_zh"], filenames.get("audio_zh"),
                             file_ids["audio_en"], filenames.get("audio_en"), data.get("cos_video_key"),
                             data.get("cos_video_filename"), data.get("cos_video_size"), data.get("cos_video_etag"),
                             int(data.get("sort_order") or 0), data.get("publish_scope", "all_authorized"),
                             data.get("publish_class_ids") or [], version_id))
                preferred_role = "audio_en" if data.get("language") == "en" else "audio_zh" if data.get("language") == "zh" else "audio"
                selected_role = preferred_role if file_ids.get(preferred_role) else "audio" if file_ids.get("audio") else "audio_zh" if file_ids.get("audio_zh") else "audio_en"
                cur.execute("""INSERT INTO cl_course_standards(content_item_id,standard_text,standard_audio_file_id,
                              standard_audio_filename,pronunciation_rules,prosody_rules,expression_rules,rule_version,
                              created_by,change_summary) VALUES (%s,%s,%s,%s,%s,%s,%s,'2.3',%s,'Course content draft updated')
                              ON CONFLICT(content_item_id,rule_version) DO UPDATE SET
                                standard_text=EXCLUDED.standard_text,
                                standard_audio_file_id=EXCLUDED.standard_audio_file_id,
                                standard_audio_filename=EXCLUDED.standard_audio_filename,
                                pronunciation_rules=EXCLUDED.pronunciation_rules,
                                prosody_rules=EXCLUDED.prosody_rules,
                                expression_rules=EXCLUDED.expression_rules,
                                created_by=EXCLUDED.created_by,
                                change_summary=EXCLUDED.change_summary""",
                            (current["content_id"], standard_text, file_ids.get(selected_role), filenames.get(selected_role),
                             Jsonb({"stress": "按专业标注原文中的强调标记朗读", "notes": data.get("pronunciation_notes", "")}),
                             Jsonb({"pause": "短停 /；长停 //"}), Jsonb({"tone": "、".join(data.get("delivery_tone") or [])}), updated_by))
            return self.get_course_v23(version_id) or {}
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Course V2.3 draft could not be updated") from exc

    def get_course_v23_media(self, file_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT file.object_key AS asset_ref,file.mime_type,file.byte_size,
                          COALESCE(track.filename,
                            CASE WHEN file.id=detail.cover_file_id THEN detail.cover_filename
                                 WHEN file.id=detail.video_file_id THEN detail.video_filename
                                 WHEN file.id=detail.zh_audio_file_id THEN detail.zh_audio_filename
                                 WHEN file.id=detail.en_audio_file_id THEN detail.en_audio_filename
                                 ELSE detail.standard_audio_filename END) AS filename
                          FROM files file
                          LEFT JOIN cl_course_audio_tracks track ON track.file_id=file.id
                          LEFT JOIN cl_course_details detail ON file.id IN
                            (detail.cover_file_id,detail.video_file_id,detail.standard_audio_file_id,
                             detail.zh_audio_file_id,detail.en_audio_file_id)
                          WHERE file.id=%s AND (track.file_id IS NOT NULL OR detail.course_version_id IS NOT NULL)
                          LIMIT 1""", (file_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def user_can_access_course_v23_media(self, file_id: str, user_id: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT EXISTS(
                          SELECT 1 FROM cl_course_details detail
                          JOIN cl_course_versions version ON version.id=detail.course_version_id
                          JOIN cl_courses course ON course.id=version.course_id
                          WHERE version.status='published' AND course.status='published'
                            AND (%s::uuid IN (detail.cover_file_id,detail.video_file_id,detail.standard_audio_file_id,detail.zh_audio_file_id,detail.en_audio_file_id)
                              OR EXISTS (SELECT 1 FROM cl_course_audio_tracks track WHERE track.course_version_id=version.id AND track.file_id=%s::uuid))
                            AND (course.organization_id IS NULL OR course.organization_id=(SELECT organization_id FROM users WHERE id=%s))
                            AND (detail.publish_scope='all_authorized' OR EXISTS (
                              SELECT 1 FROM class_memberships membership WHERE membership.user_id=%s
                                AND membership.status='active' AND membership.class_id=ANY(detail.publish_class_ids)
                            ))
                          ) AS allowed""", (file_id, file_id, user_id, user_id))
            row = cur.fetchone()
            return bool(row and row["allowed"])

    def get_course_v23_audio_track(self, version_id: str, file_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT track.id::text AS id,track.course_version_id::text AS course_version_id,
                          track.file_id::text AS file_id,track.language_code AS language,track.alignment,
                          track.alignment_updated_at,file.object_key AS asset_ref,file.mime_type,file.byte_size,
                          COALESCE(NULLIF(track.filename,''),'course-standard') AS filename
                          FROM cl_course_audio_tracks track
                          JOIN files file ON file.id=track.file_id
                          WHERE track.course_version_id=%s AND track.file_id=%s""", (version_id, file_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def save_course_v23_audio_alignment(self, track_id: str, language: str, alignment: dict[str, Any]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE cl_course_audio_tracks
                          SET alignment=COALESCE(alignment,'{}'::jsonb) || %s,alignment_updated_at=now()
                          WHERE id=%s RETURNING alignment""", (Jsonb({language: alignment}), track_id))
            row = cur.fetchone()
            if not row:
                raise LookupError("Course audio track not found")
            return dict(row["alignment"] or {})

    def start_course_import_batch(self, excel_filename: str, media_zip_filename: str | None, created_by: str) -> str:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO cl_course_import_batches(excel_filename,media_zip_filename,created_by)
                          VALUES (%s,%s,%s) RETURNING id::text AS id""", (excel_filename[:255], (media_zip_filename or "")[:255] or None, created_by))
            return str(cur.fetchone()["id"])

    def finish_course_import_batch(self, batch_id: str, total: int, created: int, errors: list[dict[str, Any]]) -> None:
        from psycopg.types.json import Jsonb
        status = "completed" if not errors else "completed_with_errors" if created else "failed"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE cl_course_import_batches SET status=%s,row_count=%s,draft_count=%s,error_count=%s,
                          errors=%s,completed_at=now() WHERE id=%s""", (status, total, created, len(errors), Jsonb(errors), batch_id))

    def publish_course_v23(self, version_id: str, published_by: str) -> dict[str, Any]:
        item = self.get_course_v23(version_id)
        if not item:
            raise ValueError("Course V2.3 draft not found")
        if item["validation_errors"]:
            raise ValueError("；".join(item["validation_errors"]))
        self.publish_course_version(version_id, published_by)
        return self.get_course_v23(version_id) or {}

    def list_task_roster(self, task_type: str, task_id: str) -> dict[str, Any] | None:
        if task_type not in {"practice", "exam"}:
            return None
        learners: list[dict[str, Any]] = []
        with self._connect() as conn, conn.cursor() as cur:
            task_table = "cl_practice_tasks" if task_type == "practice" else "cl_exam_tasks"
            cur.execute(
                f"SELECT id::text AS task_id,title AS task_title,status AS task_status,course_version_id::text AS course_version_id"
                f"{',completion_rule' if task_type == 'practice' else ''} FROM {task_table} WHERE id=%s AND deleted_at IS NULL",
                (task_id,),
            )
            task = cur.fetchone()
            if not task:
                return None
            task = dict(task)
            if task_type == "practice":
                cur.execute("""SELECT assignment.id::text AS assignment_id,assignment.user_id::text AS learner_id,
                              learner.display_name,learner.external_ref,class.name AS class_name,assignment.status AS assignment_status,
                              EXISTS (SELECT 1 FROM cl_evaluation_tasks evaluation
                                      JOIN cl_practice_attempts attempt ON attempt.id=evaluation.practice_attempt_id
                                      WHERE attempt.assignment_id=assignment.id
                                        AND evaluation.status IN ('waiting_assignment','pending','in_progress')) AS pending_review,
                              EXISTS (SELECT 1 FROM cl_remediation_requests remediation
                                      WHERE remediation.practice_assignment_id=assignment.id
                                        AND remediation.status IN ('open','in_progress')) AS needs_retraining
                              FROM cl_practice_assignments assignment
                              JOIN users learner ON learner.id=assignment.user_id
                              LEFT JOIN LATERAL (SELECT membership.class_id FROM class_memberships membership
                                                 WHERE membership.user_id=learner.id AND membership.status='active'
                                                 ORDER BY membership.joined_at DESC LIMIT 1) membership ON true
                              LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                              WHERE assignment.task_id=%s
                              ORDER BY learner.display_name,learner.external_ref NULLS LAST""", (task_id,))
                rows = [dict(row) for row in cur.fetchall()]
                assignment_ids = [row["assignment_id"] for row in rows]
                course_version_id = task.get("course_version_id")
                minimum = int((task.get("completion_rule") or {}).get("min_attempts", 1))
                if course_version_id:
                    cur.execute("""SELECT content.id::text AS content_id,content.learning_card_id IS NOT NULL AS is_card
                                  FROM cl_content_items content JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                                  WHERE chapter.course_version_id=%s ORDER BY chapter.sequence_no,content.sequence_no""", (course_version_id,))
                    contents = [dict(row) for row in cur.fetchall()]
                else:
                    contents = []
                attempts: dict[tuple[str, str], int] = {}
                read_items: set[tuple[str, str]] = set()
                required_interactions: dict[str, int] = {}
                completed_interactions: dict[tuple[str, str], int] = {}
                if assignment_ids and contents:
                    cur.execute("""SELECT assignment_id::text AS assignment_id,content_item_id::text AS content_id,count(*)::int AS attempts
                                  FROM cl_practice_attempts WHERE assignment_id=ANY(%s::uuid[]) AND content_item_id IS NOT NULL
                                  GROUP BY assignment_id,content_item_id""", (assignment_ids,))
                    attempts = {(row["assignment_id"], row["content_id"]): row["attempts"] for row in cur.fetchall()}
                    cur.execute("""SELECT assignment_id::text AS assignment_id,content_item_id::text AS content_id
                                  FROM cl_learning_card_reads WHERE assignment_id=ANY(%s::uuid[])""", (assignment_ids,))
                    read_items = {(row["assignment_id"], row["content_id"]) for row in cur.fetchall()}
                    cur.execute("""SELECT interaction.content_item_id::text AS content_id,count(*)::int AS required_count
                                  FROM cl_content_interactions interaction
                                  WHERE interaction.content_item_id=ANY(%s::uuid[]) AND interaction.status='published' AND interaction.required
                                  GROUP BY interaction.content_item_id""", ([item["content_id"] for item in contents],))
                    required_interactions = {row["content_id"]: row["required_count"] for row in cur.fetchall()}
                    cur.execute("""SELECT answer.assignment_id::text AS assignment_id,interaction.content_item_id::text AS content_id,
                                  count(DISTINCT interaction.id)::int AS completed_count
                                  FROM cl_interaction_attempts answer JOIN cl_content_interactions interaction ON interaction.id=answer.interaction_id
                                  WHERE answer.assignment_id=ANY(%s::uuid[]) AND answer.is_correct
                                    AND interaction.status='published' AND interaction.required
                                  GROUP BY answer.assignment_id,interaction.content_item_id""", (assignment_ids,))
                    completed_interactions = {(row["assignment_id"], row["content_id"]): row["completed_count"] for row in cur.fetchall()}
                for row in rows:
                    if course_version_id:
                        def is_completed(content: dict[str, Any]) -> bool:
                            key = (row["assignment_id"], content["content_id"])
                            activity_done = key in read_items if content["is_card"] else attempts.get(key, 0) >= minimum
                            return activity_done and completed_interactions.get(key, 0) >= required_interactions.get(content["content_id"], 0)
                        total_items = len(contents)
                        completed_items = sum(is_completed(content) for content in contents)
                        attempt_count = sum(attempts.get((row["assignment_id"], content["content_id"]), 0) for content in contents)
                        progress_percent = round(completed_items / max(total_items, 1) * 100)
                    else:
                        cur.execute("SELECT count(*)::int AS attempts FROM cl_practice_attempts WHERE assignment_id=%s", (row["assignment_id"],))
                        attempt_count = cur.fetchone()["attempts"]
                        total_items = 1
                        completed_items = 1 if row["assignment_status"] == "completed" else 0
                        progress_percent = 100 if completed_items else 0
                    row.update(total_items=total_items, completed_items=completed_items,
                               attempt_count=attempt_count, progress_percent=progress_percent)
                    learners.append(row)
            else:
                cur.execute("""SELECT assignment.id::text AS assignment_id,assignment.user_id::text AS learner_id,
                              learner.display_name,learner.external_ref,class.name AS class_name,assignment.status AS assignment_status,
                              1::int AS total_items,
                              CASE WHEN assignment.status IN ('submitted','graded','published') THEN 1 ELSE 0 END::int AS completed_items,
                              CASE WHEN assignment.submitted_at IS NULL THEN 0 ELSE 1 END::int AS attempt_count,
                              CASE WHEN assignment.status IN ('submitted','graded','published') THEN 100 ELSE 0 END::int AS progress_percent,
                              EXISTS (SELECT 1 FROM cl_evaluation_tasks evaluation
                                      WHERE evaluation.exam_assignment_id=assignment.id
                                        AND evaluation.status IN ('waiting_assignment','pending','in_progress')) AS pending_review,
                              EXISTS (SELECT 1 FROM cl_remediation_requests remediation
                                      WHERE remediation.exam_assignment_id=assignment.id
                                        AND remediation.status IN ('open','in_progress')) AS needs_retraining
                              FROM cl_exam_assignments assignment
                              JOIN users learner ON learner.id=assignment.user_id
                              LEFT JOIN LATERAL (SELECT membership.class_id FROM class_memberships membership
                                                 WHERE membership.user_id=learner.id AND membership.status='active'
                                                 ORDER BY membership.joined_at DESC LIMIT 1) membership ON true
                              LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                              WHERE assignment.exam_task_id=%s
                              ORDER BY learner.display_name,learner.external_ref NULLS LAST""", (task_id,))
                learners = [dict(row) for row in cur.fetchall()]
        for learner in learners:
            progress = learner["progress_percent"]
            learner["progress_status"] = "completed" if progress >= 100 else "in_progress" if learner["attempt_count"] > 0 or learner["completed_items"] > 0 else "not_started"
            learner["final_status"] = "pending_review" if learner["pending_review"] else "passed" if progress >= 100 and not learner["needs_retraining"] else "not_passed"
        return {
            "task_id": task["task_id"], "task_type": task_type, "task_title": task["task_title"], "task_status": task["task_status"],
            "total_count": len(learners),
            "passed_count": sum(item["final_status"] == "passed" for item in learners),
            "pending_review_count": sum(item["final_status"] == "pending_review" for item in learners),
            "not_passed_count": sum(item["final_status"] == "not_passed" for item in learners),
            "not_started_count": sum(item["progress_status"] == "not_started" for item in learners),
            "in_progress_count": sum(item["progress_status"] == "in_progress" for item in learners),
            "completed_count": sum(item["progress_status"] == "completed" for item in learners),
            "learners": learners,
        }

    def list_learner_tasks(self, user_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT assignment.id::text AS assignment_id,task.id::text AS task_id,'practice' AS task_type,
                          task.title,assignment.status,task.due_at,task.week_no,task.course_version_id::text AS course_version_id,
                          COALESCE(course.title,broadcast.title,'广播词练习') AS course_title,version.version_label,task.completion_rule
                          FROM cl_practice_assignments assignment
                          JOIN cl_practice_tasks task ON task.id=assignment.task_id
                          LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                          LEFT JOIN cl_courses course ON course.id=version.course_id
                          LEFT JOIN cl_broadcasts broadcast ON broadcast.id=task.broadcast_id
                          WHERE assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                          ORDER BY task.due_at NULLS LAST,assignment.assigned_at DESC""", (user_id,))
            practice_rows = [dict(row) for row in cur.fetchall()]
            for row in practice_rows:
                minimum = int((row.pop("completion_rule") or {}).get("min_attempts", 1))
                if row["course_version_id"]:
                    cur.execute("""SELECT content.id::text AS id,content.learning_card_id FROM cl_content_items content
                                  JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                                  WHERE chapter.course_version_id=%s ORDER BY chapter.sequence_no,content.sequence_no""", (row["course_version_id"],))
                    content_rows = list(cur.fetchall())
                    content_ids = [item['id'] for item in content_rows]
                    card_ids = {item['id'] for item in content_rows if item['learning_card_id']}
                    cur.execute('SELECT content_item_id::text AS id FROM cl_learning_card_reads WHERE assignment_id=%s', (row['assignment_id'],))
                    read_ids = {item['id'] for item in cur.fetchall()}
                    cur.execute("""SELECT content_item_id::text AS id,count(*)::int AS attempts FROM cl_practice_attempts
                                  WHERE assignment_id=%s AND content_item_id IS NOT NULL GROUP BY content_item_id""", (row["assignment_id"],))
                    counts = {item["id"]: item["attempts"] for item in cur.fetchall()}
                    cur.execute("""SELECT interaction.content_item_id::text AS id,count(*)::int AS required_count,
                                  count(*) FILTER (WHERE EXISTS (
                                    SELECT 1 FROM cl_interaction_attempts answer
                                    WHERE answer.assignment_id=%s AND answer.interaction_id=interaction.id AND answer.is_correct
                                  ))::int AS completed_count
                                  FROM cl_content_interactions interaction
                                  JOIN cl_content_items content ON content.id=interaction.content_item_id
                                  JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                                  WHERE chapter.course_version_id=%s AND interaction.status='published' AND interaction.required
                                  GROUP BY interaction.content_item_id""", (row["assignment_id"], row["course_version_id"]))
                    interaction_status = {item["id"]: item for item in cur.fetchall()}
                    def content_completed(content_id: str) -> bool:
                        interaction = interaction_status.get(content_id, {"required_count": 0, "completed_count": 0})
                        return (content_id in read_ids if content_id in card_ids else counts.get(content_id, 0) >= minimum) and interaction["completed_count"] >= interaction["required_count"]
                    row["total_items"] = len(content_ids)
                    row["completed_items"] = sum(content_completed(item) for item in content_ids)
                    row["attempt_count"] = sum(counts.values())
                    row["progress_percent"] = round(row["completed_items"] / max(row["total_items"], 1) * 100)
                    row["next_content_item_id"] = next((item for item in content_ids if not content_completed(item)), None)
                else:
                    cur.execute("SELECT count(*)::int AS n FROM cl_practice_attempts WHERE assignment_id=%s", (row["assignment_id"],))
                    row.update({"total_items": 1, "completed_items": 1 if row["status"] == "completed" else 0, "attempt_count": cur.fetchone()["n"], "progress_percent": 100 if row["status"] == "completed" else 0, "next_content_item_id": None})
                rows.append(row)
            cur.execute("""SELECT assignment.id::text AS assignment_id,task.id::text AS task_id,'exam' AS task_type,
                          task.title,assignment.status,task.due_at,task.week_no,task.course_version_id::text AS course_version_id,
                          COALESCE(course.title,broadcast.title,'广播词考试') AS course_title,version.version_label,
                          1::int AS total_items,CASE WHEN assignment.status IN ('submitted','graded','published') THEN 1 ELSE 0 END::int AS completed_items,
                          CASE WHEN assignment.submitted_at IS NULL THEN 0 ELSE 1 END::int AS attempt_count,
                          CASE WHEN assignment.status IN ('submitted','graded','published') THEN 100 ELSE 0 END::int AS progress_percent,
                          NULL::text AS next_content_item_id
                          FROM cl_exam_assignments assignment JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                          LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                          LEFT JOIN cl_courses course ON course.id=version.course_id
                          LEFT JOIN cl_broadcasts broadcast ON broadcast.id=task.broadcast_id
                          WHERE assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                          ORDER BY task.due_at NULLS LAST""", (user_id,))
            rows.extend(dict(row) for row in cur.fetchall())
        for row in rows:
            row["locked"] = not self.is_task_unlocked(row["task_type"], row["task_id"], user_id)
            row["unlock_reason"] = "完成上一周任务后自动解锁" if row["locked"] else None
        return rows

    def list_admin_learner_broadcast_progress(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT assignment.id::text AS assignment_id,task.id::text AS task_id,task.title AS task_title,
                          content.id::text AS content_item_id,content.title AS content_title,
                          chapter.title AS chapter_title,chapter.sequence_no AS chapter_sequence,content.sequence_no,
                          COALESCE(attempts.attempt_count,0)::int AS attempt_count,
                          GREATEST(COALESCE((task.completion_rule->>'min_attempts')::int,1),1)::int AS required_attempts,
                          COALESCE(interactions.completed_count,0)::int AS completed_interactions,
                          COALESCE(interactions.required_count,0)::int AS required_interactions,
                          attempts.latest_attempt_id,attempts.latest_attempt_at,attempts.latest_ai_status,
                          attempts.latest_score,
                          CASE WHEN review.status='published' THEN 'published'
                               WHEN review.status='draft' THEN 'draft'
                               WHEN attempts.latest_attempt_id IS NOT NULL AND EXISTS (
                                 SELECT 1 FROM cl_evaluation_tasks evaluation
                                 WHERE evaluation.practice_attempt_id=attempts.latest_attempt_id::uuid
                                   AND evaluation.status IN ('pending','in_progress','completed')
                               ) THEN 'pending_review'
                               ELSE 'not_submitted' END AS review_status
                          FROM cl_practice_assignments assignment
                          JOIN cl_practice_tasks task ON task.id=assignment.task_id
                          JOIN cl_chapters chapter ON chapter.course_version_id=task.course_version_id
                          JOIN cl_content_items content ON content.chapter_id=chapter.id AND content.content_type='broadcast'
                          LEFT JOIN LATERAL (
                            SELECT count(*)::int AS attempt_count,
                              (array_agg(attempt.id::text ORDER BY attempt.created_at DESC,attempt.id DESC))[1] AS latest_attempt_id,
                              max(attempt.created_at) AS latest_attempt_at,
                              (array_agg(attempt.ai_status ORDER BY attempt.created_at DESC,attempt.id DESC))[1] AS latest_ai_status,
                              (array_agg(COALESCE(NULLIF(attempt.score_summary->>'overall',''),NULLIF(attempt.score_summary->>'overall_score',''))::float8 ORDER BY attempt.created_at DESC,attempt.id DESC))[1] AS latest_score
                            FROM cl_practice_attempts attempt
                            WHERE attempt.assignment_id=assignment.id AND attempt.content_item_id=content.id
                          ) attempts ON true
                          LEFT JOIN LATERAL (
                            SELECT count(*) FILTER (WHERE interaction.required)::int AS required_count,
                              count(*) FILTER (WHERE interaction.required AND EXISTS (
                                SELECT 1 FROM cl_interaction_attempts answer
                                WHERE answer.assignment_id=assignment.id AND answer.interaction_id=interaction.id AND answer.is_correct
                              ))::int AS completed_count
                            FROM cl_content_interactions interaction
                            WHERE interaction.content_item_id=content.id AND interaction.status='published'
                          ) interactions ON true
                          LEFT JOIN LATERAL (
                            SELECT item.status FROM cl_instructor_reviews item
                            WHERE item.practice_attempt_id=attempts.latest_attempt_id::uuid AND item.status IN ('draft','published')
                            ORDER BY item.revision_no DESC LIMIT 1
                          ) review ON true
                          WHERE assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL
                          ORDER BY task.due_at NULLS LAST,task.created_at DESC,chapter.sequence_no,content.sequence_no""", (user_id,))
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            completed = (
                row["attempt_count"] >= row["required_attempts"]
                and row["completed_interactions"] >= row["required_interactions"]
            )
            row["progress_status"] = (
                "completed" if completed
                else "in_progress" if row["attempt_count"] > 0 or row["completed_interactions"] > 0
                else "not_started"
            )
        return rows

    def learner_home(self, user_id: str) -> dict[str, Any]:
        tasks = self.list_learner_tasks(user_id)
        active = [item for item in tasks if item["progress_percent"] < 100 and item["status"] != "closed" and not item["locked"]]
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT count(*)::int AS n FROM cl_teacher_feedback feedback
                           LEFT JOIN cl_practice_attempts attempt ON attempt.id=feedback.practice_attempt_id
                           LEFT JOIN cl_practice_assignments practice_assignment ON practice_assignment.id=attempt.assignment_id
                           LEFT JOIN cl_practice_tasks practice_task ON practice_task.id=practice_assignment.task_id
                           LEFT JOIN cl_exam_assignments exam_assignment ON exam_assignment.id=feedback.exam_assignment_id
                           LEFT JOIN cl_exam_tasks exam_task ON exam_task.id=exam_assignment.exam_task_id
                           WHERE feedback.learner_id=%s AND feedback.status='published'
                             AND ((feedback.practice_attempt_id IS NOT NULL AND practice_task.deleted_at IS NULL)
                               OR (feedback.exam_assignment_id IS NOT NULL AND exam_task.deleted_at IS NULL))""", (user_id,))
            pending_feedback = cur.fetchone()["n"]
        return {"practice_count": sum(item["task_type"] == "practice" and item["progress_percent"] < 100 for item in tasks), "exam_count": sum(item["task_type"] == "exam" and item["progress_percent"] < 100 for item in tasks), "completed_count": sum(item["progress_percent"] == 100 for item in tasks), "total_attempts": sum(item["attempt_count"] for item in tasks), "pending_feedback": pending_feedback, "next_task": active[0] if active else None}

    def learner_practice_workspace(self, assignment_id: str, user_id: str) -> dict[str, Any] | None:
        from .html_sanitizer import extract_text
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT assignment.id::text AS assignment_id,assignment.status AS assignment_status,
                          task.id::text AS task_id,task.title AS task_title,task.completion_rule,
                          version.id::text AS course_version_id,version.version_label,course.title AS course_title
                          FROM cl_practice_assignments assignment JOIN cl_practice_tasks task ON task.id=assignment.task_id
                          JOIN cl_course_versions version ON version.id=task.course_version_id
                          JOIN cl_courses course ON course.id=version.course_id
                          WHERE assignment.id=%s AND assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL""", (assignment_id, user_id))
            workspace = cur.fetchone()
            if not workspace:
                return None
            result = dict(workspace)
            minimum = int((result.pop("completion_rule") or {}).get("min_attempts", 1))
            cur.execute("""SELECT content.id::text AS id,content.chapter_id::text AS chapter_id,chapter.title AS chapter_title,
                          chapter.sequence_no AS chapter_sequence,content.content_type,content.title,content.sequence_no,content.sanitized_html,
                          content.document_page_no,content.document_page_count,content.learning_card_id::text AS learning_card_id,
                          standard.standard_text,
                          COALESCE(standard.pronunciation_rules->>'stress','') AS stress_rules,
                          COALESCE(standard.pronunciation_rules->>'notes','') AS pronunciation_notes,
                          COALESCE(standard.prosody_rules->>'pause','') AS pause_rules,
                          COALESCE(standard.expression_rules->>'tone','') AS tone_requirements,
                          standard.rule_version,standard.standard_audio_file_id::text AS standard_audio_file_id
                          FROM cl_content_items content JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          LEFT JOIN LATERAL (SELECT * FROM cl_course_standards s WHERE s.content_item_id=content.id ORDER BY s.created_at DESC LIMIT 1) standard ON true
                          WHERE chapter.course_version_id=%s ORDER BY chapter.sequence_no,content.sequence_no""", (result["course_version_id"],))
            contents = []
            for content in cur.fetchall():
                item = dict(content)
                cur.execute("""SELECT id::text AS id,ai_status FROM cl_practice_attempts
                              WHERE assignment_id=%s AND content_item_id=%s ORDER BY created_at DESC LIMIT 1""", (assignment_id, item["id"]))
                latest = cur.fetchone()
                cur.execute("SELECT count(*)::int AS n FROM cl_practice_attempts WHERE assignment_id=%s AND content_item_id=%s", (assignment_id, item["id"]))
                attempt_count = cur.fetchone()["n"]
                item["reference_text"] = (item.pop("standard_text") or "").strip() or extract_text(item.get("sanitized_html") or "")
                audio_file_id = item.pop("standard_audio_file_id")
                item["standard_audio_url"] = f"/api/v1/cabinlingo/course-standard-audio/{audio_file_id}" if audio_file_id else None
                item["document_url"] = f"/api/v1/cabinlingo/learner/course-documents/{item['id']}" if item.get("content_type") == "document" else None
                asset_rows = []
                cur.execute("""SELECT asset.id::text AS id,asset.content_item_id::text AS content_item_id,
                              asset.asset_role,asset.original_filename,file.mime_type,file.byte_size
                              FROM cl_content_assets asset JOIN files file ON file.id=asset.file_id
                              WHERE asset.content_item_id=%s ORDER BY asset.created_at""", (item["id"],))
                for asset in cur.fetchall():
                    asset_item = dict(asset)
                    asset_item["url"] = f"/api/v1/cabinlingo/learner/content-assets/{asset_item['id']}"
                    asset_rows.append(asset_item)
                item["assets"] = asset_rows
                item["attempt_count"] = attempt_count
                item["latest_attempt_id"] = latest["id"] if latest else None
                item["latest_ai_status"] = latest["ai_status"] if latest else None
                cur.execute("""SELECT id::text AS id,content_item_id::text AS content_item_id,interaction_type,title,prompt,config,
                              sequence_no,required,status,version_no,created_at,updated_at
                              FROM cl_content_interactions
                              WHERE content_item_id=%s AND status='published' ORDER BY sequence_no,created_at""", (item["id"],))
                interactions = []
                for interaction_row in cur.fetchall():
                    interaction = self._interaction_record(interaction_row, include_answer=False)
                    cur.execute("""SELECT count(*)::int AS attempt_count,coalesce(bool_or(is_correct),false) AS completed
                                  FROM cl_interaction_attempts WHERE assignment_id=%s AND interaction_id=%s""", (assignment_id, interaction["id"]))
                    interaction_result = cur.fetchone()
                    interaction["attempt_count"] = interaction_result["attempt_count"]
                    interaction["completed"] = bool(interaction_result["completed"])
                    interactions.append(interaction)
                item["interactions"] = interactions
                item["required_interactions"] = sum(bool(interaction["required"]) for interaction in interactions)
                item["completed_interactions"] = sum(bool(interaction["completed"]) for interaction in interactions if interaction["required"])
                if item.get('learning_card_id'):
                    cur.execute('SELECT 1 FROM cl_learning_card_reads WHERE assignment_id=%s AND content_item_id=%s', (assignment_id, item['id']))
                    base_completed = cur.fetchone() is not None
                else:
                    base_completed = attempt_count >= minimum
                item["completed"] = base_completed and item["completed_interactions"] >= item["required_interactions"]
                contents.append(item)
            result["minimum_attempts"] = minimum
            result["progress_percent"] = round(sum(item["completed"] for item in contents) / max(len(contents), 1) * 100)
            result["contents"] = contents
            return result

    def save_learner_practice_attempt(
        self,
        assignment_id: str,
        user_id: str,
        content_item_id: str,
        recording_id: str,
        correction_of_attempt_id: str | None,
        ai_results: list[dict[str, Any]],
        recognized_text: str | None = None,
        reference_text: str | None = None,
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT task.completion_rule,task.course_version_id FROM cl_practice_assignments assignment
                          JOIN cl_practice_tasks task ON task.id=assignment.task_id
                          WHERE assignment.id=%s AND assignment.user_id=%s AND task.status<>'draft' AND task.deleted_at IS NULL""", (assignment_id, user_id))
            task = cur.fetchone()
            if not task:
                raise ValueError("Assignment not found")
            cur.execute("""SELECT content.title,content.sanitized_html FROM cl_content_items content JOIN cl_chapters chapter ON chapter.id=content.chapter_id
                          WHERE content.id=%s AND chapter.course_version_id=%s""", (content_item_id, task["course_version_id"]))
            content = cur.fetchone()
            cur.execute("SELECT audio_ref FROM cl_recordings WHERE id=%s AND user_id=%s AND assignment_id=%s", (recording_id, user_id, assignment_id))
            recording = cur.fetchone()
            if not content or not recording:
                raise ValueError("Content or recording not found")
            cur.execute("SELECT count(*)::int + 1 AS n FROM cl_practice_attempts WHERE assignment_id=%s", (assignment_id,))
            attempt_no = cur.fetchone()["n"]
            if reference_text is None:
                from .html_sanitizer import extract_text
                reference_text = extract_text(content["sanitized_html"] or "")
            practice_feedback = collect_practice_feedback(ai_results, reference_text or "", recognized_text)
            issues = practice_feedback["issues"]
            scores = practice_feedback["score_summary"]
            ai_status = practice_feedback["ai_status"]
            cur.execute("""INSERT INTO cl_practice_attempts(assignment_id,content_item_id,recording_id,attempt_no,correction_of_attempt_id,transcript,ai_status,score_summary,issues,feedback)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           RETURNING id::text AS id,created_at""", (
                               assignment_id,
                               content_item_id,
                               recording_id,
                               attempt_no,
                               correction_of_attempt_id,
                               practice_feedback["recognized_text"],
                               ai_status,
                               Jsonb(scores),
                               Jsonb(issues),
                               Jsonb({
                                   "next_action": "review_feedback_and_retry" if issues else "continue_next_content",
                                   "browser_transcript": practice_feedback.get("browser_transcript"),
                                   "iat_transcript": practice_feedback.get("iat_transcript"),
                                   "transcript_source": practice_feedback.get("transcript_source"),
                                   "alignment": practice_feedback.get("alignment", []),
                                   "alignment_source": practice_feedback.get("alignment_source"),
                                   "alignment_provider": practice_feedback.get("alignment_provider"),
                                   "normalized_transcript": practice_feedback.get("normalized_transcript"),
                                   "normalized_reference_text": practice_feedback.get("normalized_reference_text"),
                                   "text_diagnosis": practice_feedback.get("text_diagnosis"),
                                   "pause_diagnosis": practice_feedback.get("pause_diagnosis"),
                                   "pending_review_issues": practice_feedback.get("pending_review_issues", []),
                                   "filtered_issues": practice_feedback.get("filtered_issues", []),
                                   "system_issues": practice_feedback.get("system_issues", []),
                               }),
                           ))
            attempt = cur.fetchone()
            routing = self._enqueue_evaluation_tasks(cur, "practice", user_id, practice_attempt_id=attempt["id"])
            for item in ai_results:
                cur.execute("""INSERT INTO cl_ai_results(recording_id,adapter,provider,provider_version,status,payload,
                              provider_request_id,latency_ms,attempt_count,error_code,updated_at)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())""",
                            (recording_id, item["adapter"], item["provider"], item["version"], item["status"],
                             Jsonb(item.get("payload", {})), item.get("request_id"), item.get("latency_ms"),
                             item.get("attempts", 0), item.get("error_code")))
            event_type = "practice_corrected" if correction_of_attempt_id else "practice_submitted"
            cur.execute("""INSERT INTO cl_growth_events(learner_id,event_type,assignment_id,practice_attempt_id,content_item_id,metrics)
                          VALUES (%s,%s,%s,%s,%s,%s)""", (user_id, event_type, assignment_id, attempt["id"], content_item_id, Jsonb({"ai_status": ai_status, "scores": scores})))
            minimum = int((task["completion_rule"] or {}).get("min_attempts", 1))
            progress = self._practice_completion(cur, assignment_id, task['course_version_id'], minimum)
            total, completed = progress['total'], progress['completed']
            assignment_status = "completed" if total > 0 and completed == total else "in_progress"
            cur.execute("UPDATE cl_practice_assignments SET status=%s,completed_at=CASE WHEN %s='completed' THEN now() ELSE NULL END WHERE id=%s", (assignment_status, assignment_status, assignment_id))
            return {"attempt_id": attempt["id"], "assignment_id": assignment_id, "content_item_id": content_item_id, "content_title": content["title"], "attempt_no": attempt_no, **practice_feedback, "next_action": "review_feedback_and_retry" if issues else "continue_next_content", "recording_url": f"/api/v1/cabinlingo/learner/audio/{recording_id}", "correction_of_attempt_id": correction_of_attempt_id, "teacher_feedback": None, "created_at": attempt["created_at"], "evaluation_tasks_created": routing["created"], "waiting_assignment": routing["waiting_assignment"]}

    def list_learner_attempts(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT attempt.id::text AS attempt_id,attempt.assignment_id::text AS assignment_id,
                          attempt.content_item_id::text AS content_item_id,COALESCE(content.title,'历史广播词练习') AS content_title,attempt.attempt_no,
                          attempt.ai_status,attempt.score_summary,attempt.issues,attempt.feedback AS feedback_payload,
                          attempt.transcript AS recognized_text,suntone.payload AS suntone_payload,iat.payload AS iat_payload,
                          recording.id::text AS recording_id,attempt.correction_of_attempt_id::text AS correction_of_attempt_id,attempt.created_at
                          FROM cl_practice_attempts attempt JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                          JOIN cl_practice_tasks task ON task.id=assignment.task_id
                          LEFT JOIN cl_content_items content ON content.id=attempt.content_item_id
                          LEFT JOIN cl_recordings recording ON recording.id=attempt.recording_id
                          LEFT JOIN LATERAL (
                            SELECT result.payload FROM cl_ai_results result
                            WHERE result.recording_id=recording.id AND result.adapter='suntone' AND result.status='completed'
                            ORDER BY result.updated_at DESC,result.created_at DESC LIMIT 1
                          ) suntone ON true
                          LEFT JOIN LATERAL (
                            SELECT result.payload FROM cl_ai_results result
                            WHERE result.recording_id=recording.id AND result.adapter='asr_iat' AND result.status='completed'
                            ORDER BY result.updated_at DESC,result.created_at DESC LIMIT 1
                          ) iat ON true
                          WHERE assignment.user_id=%s AND task.deleted_at IS NULL ORDER BY attempt.created_at DESC""", (user_id,))
            result = []
            for row in cur.fetchall():
                item = dict(row)
                item["issues"] = learner_visible_issues(item.get("issues"))
                recording_id = item.pop("recording_id")
                item.update(suntone_evidence(item.pop("suntone_payload", None)))
                feedback_payload = item.pop("feedback_payload", None)
                feedback_payload = feedback_payload if isinstance(feedback_payload, dict) else {}
                iat_payload = item.pop("iat_payload", None)
                iat_payload = iat_payload if isinstance(iat_payload, dict) else {}
                item["browser_transcript"] = feedback_payload.get("browser_transcript")
                item["iat_transcript"] = feedback_payload.get("iat_transcript")
                if item["iat_transcript"] is None and isinstance(iat_payload.get("transcript"), str):
                    item["iat_transcript"] = iat_payload["transcript"]
                item["transcript_source"] = feedback_payload.get("transcript_source")
                if item["transcript_source"] is None and item["iat_transcript"] is not None:
                    item["transcript_source"] = "iat"
                alignment = feedback_payload.get("alignment")
                if not isinstance(alignment, list):
                    alignment = iat_payload.get("alignment")
                item["alignment"] = alignment if isinstance(alignment, list) else []
                item["alignment_source"] = (
                    feedback_payload.get("alignment_source")
                    or iat_payload.get("alignment_source")
                )
                item["alignment_provider"] = feedback_payload.get("alignment_provider")
                item["recording_url"] = f"/api/v1/cabinlingo/learner/audio/{recording_id}" if recording_id else None
                cur.execute("""SELECT feedback.id::text AS id,feedback.summary,feedback.correction_advice,feedback.required_retraining,
                              feedback.status,feedback.published_at,teacher.display_name AS teacher_name
                              FROM cl_teacher_feedback feedback JOIN users teacher ON teacher.id=feedback.teacher_id
                              WHERE feedback.practice_attempt_id=%s AND feedback.status IN ('published','acknowledged')
                              ORDER BY feedback.created_at DESC LIMIT 1""", (item["attempt_id"],))
                feedback = cur.fetchone()
                item["teacher_feedback"] = dict(feedback) if feedback else None
                item["next_action"] = feedback_payload.get("next_action") or "review_feedback_and_retry"
                result.append(item)
            return result

    def get_learner_attempt(self, attempt_id: str, user_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_learner_attempts(user_id) if item["attempt_id"] == attempt_id), None)

    def get_learner_attempt_reanalysis_context(self, attempt_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT recording.audio_ref,attempt.transcript,attempt.feedback,
                                  COALESCE(standard.standard_text,'') AS standard_text,content.sanitized_html
                           FROM cl_practice_attempts attempt
                           JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                           JOIN cl_practice_tasks task ON task.id=assignment.task_id
                           JOIN cl_recordings recording ON recording.id=attempt.recording_id
                           JOIN cl_content_items content ON content.id=attempt.content_item_id
                           LEFT JOIN LATERAL (
                             SELECT standard_text FROM cl_course_standards s
                             WHERE s.content_item_id=content.id ORDER BY created_at DESC LIMIT 1
                           ) standard ON true
                           WHERE attempt.id=%s AND assignment.user_id=%s AND task.deleted_at IS NULL""",
                        (attempt_id, user_id))
            row = cur.fetchone()
        if not row:
            return None
        from .html_sanitizer import extract_text
        feedback = row.get("feedback") if isinstance(row.get("feedback"), dict) else {}
        reference_text = (row.get("standard_text") or "").strip() or extract_text(row.get("sanitized_html") or "")
        if not reference_text or not row.get("audio_ref"):
            return None
        return {
            "audio_ref": row["audio_ref"],
            "reference_text": reference_text,
            "recognized_text": feedback.get("browser_transcript") or row.get("transcript"),
        }

    def replace_learner_practice_analysis(
        self,
        attempt_id: str,
        user_id: str,
        ai_results: list[dict[str, Any]],
        recognized_text: str | None,
        reference_text: str,
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        practice_feedback = collect_practice_feedback(ai_results, reference_text, recognized_text)
        issues = practice_feedback["issues"]
        feedback_payload = {
            "next_action": "review_feedback_and_retry" if issues else "continue_next_content",
            "browser_transcript": practice_feedback.get("browser_transcript"),
            "iat_transcript": practice_feedback.get("iat_transcript"),
            "transcript_source": practice_feedback.get("transcript_source"),
            "alignment": practice_feedback.get("alignment", []),
            "alignment_source": practice_feedback.get("alignment_source"),
            "alignment_provider": practice_feedback.get("alignment_provider"),
            "normalized_transcript": practice_feedback.get("normalized_transcript"),
            "normalized_reference_text": practice_feedback.get("normalized_reference_text"),
            "text_diagnosis": practice_feedback.get("text_diagnosis"),
            "pause_diagnosis": practice_feedback.get("pause_diagnosis"),
            "pending_review_issues": practice_feedback.get("pending_review_issues", []),
            "filtered_issues": practice_feedback.get("filtered_issues", []),
            "system_issues": practice_feedback.get("system_issues", []),
            "reanalyzed": True,
        }
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT attempt.recording_id::text AS recording_id
                           FROM cl_practice_attempts attempt
                           JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                           JOIN cl_practice_tasks task ON task.id=assignment.task_id
                           WHERE attempt.id=%s AND assignment.user_id=%s AND task.deleted_at IS NULL
                           FOR UPDATE OF attempt""", (attempt_id, user_id))
            owned = cur.fetchone()
            if not owned:
                raise ValueError("Practice attempt or recording not found")
            cur.execute("""UPDATE cl_practice_attempts
                           SET transcript=%s,ai_status=%s,score_summary=%s,issues=%s,feedback=%s
                           WHERE id=%s""", (
                               practice_feedback.get("recognized_text"),
                               practice_feedback["ai_status"],
                               Jsonb(practice_feedback["score_summary"]),
                               Jsonb(issues),
                               Jsonb(feedback_payload),
                               attempt_id,
                           ))
            for item in ai_results:
                cur.execute("""INSERT INTO cl_ai_results(recording_id,adapter,provider,provider_version,status,payload,
                              provider_request_id,latency_ms,attempt_count,error_code,updated_at)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())""", (
                                  owned["recording_id"], item["adapter"], item["provider"], item["version"],
                                  item["status"], Jsonb(item.get("payload", {})), item.get("request_id"),
                                  item.get("latency_ms"), item.get("attempts", 0), item.get("error_code"),
                              ))
        item = self.get_learner_attempt(attempt_id, user_id)
        if not item:
            raise ValueError("Practice attempt not found after reanalysis")
        return item

    def list_learner_feedback(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT feedback.id::text AS id,feedback.practice_attempt_id::text AS practice_attempt_id,
                          feedback.exam_assignment_id::text AS exam_assignment_id,teacher.display_name AS teacher_name,
                          feedback.summary,feedback.correction_advice,feedback.required_retraining,feedback.status,feedback.published_at
                          FROM cl_teacher_feedback feedback JOIN users teacher ON teacher.id=feedback.teacher_id
                          LEFT JOIN cl_practice_attempts attempt ON attempt.id=feedback.practice_attempt_id
                          LEFT JOIN cl_practice_assignments practice_assignment ON practice_assignment.id=attempt.assignment_id
                          LEFT JOIN cl_practice_tasks practice_task ON practice_task.id=practice_assignment.task_id
                          LEFT JOIN cl_exam_assignments exam_assignment ON exam_assignment.id=feedback.exam_assignment_id
                          LEFT JOIN cl_exam_tasks exam_task ON exam_task.id=exam_assignment.exam_task_id
                          WHERE feedback.learner_id=%s AND feedback.status IN ('published','acknowledged')
                            AND ((feedback.practice_attempt_id IS NOT NULL AND practice_task.deleted_at IS NULL)
                              OR (feedback.exam_assignment_id IS NOT NULL AND exam_task.deleted_at IS NULL))
                          ORDER BY feedback.created_at DESC""", (user_id,))
            return [dict(row) for row in cur.fetchall()]

    def learner_growth_profile(self, user_id: str) -> dict[str, Any]:
        attempts = self.list_learner_attempts(user_id)
        tasks = self.list_learner_tasks(user_id)
        feedback = self.list_learner_feedback(user_id)
        issue_counts: dict[str, int] = {}
        points: dict[str, dict[str, Any]] = {}
        for item in attempts:
            day = item["created_at"].date().isoformat()
            point = points.setdefault(day, {"date": day, "attempts": 0, "completed_tasks": 0, "scores": []})
            point["attempts"] += 1
            numeric = [float(value) for value in (item["score_summary"] or {}).values() if isinstance(value, (int, float))]
            if numeric:
                point["scores"].append(sum(numeric) / len(numeric))
            for issue in item["issues"] or []:
                key = issue.get("dimension", "other")
                issue_counts[key] = issue_counts.get(key, 0) + 1
        completed_count = sum(item["progress_percent"] == 100 for item in tasks)
        trend = []
        for point in points.values():
            scores = point.pop("scores")
            point["completed_tasks"] = completed_count
            point["average_score"] = round(sum(scores) / len(scores), 1) if scores else None
            trend.append(point)
        return {"total_attempts": len(attempts), "completed_tasks": completed_count, "corrected_attempts": sum(bool(item["correction_of_attempt_id"]) for item in attempts), "feedback_count": len(feedback), "issue_counts": issue_counts, "trend": trend}

    def list_instructor_queue(self, review_type: str | None = None, review_status: str | None = None, class_id: str | None = None, instructor_id: str | None = None) -> list[dict[str, Any]]:
        """Return only evaluation tasks assigned to the current instructor."""
        with self._connect() as conn, conn.cursor() as cur:
            if instructor_id:
                self._sync_instructor_evaluation_tasks(cur, instructor_id)
            cur.execute("""WITH practice_queue AS (
                            SELECT DISTINCT ON (assignment.id,COALESCE(attempt.content_item_id,attempt.id))
                              'practice'::text AS review_type,attempt.id::text AS target_id,
                              assignment.id::text AS assignment_id,task.id::text AS task_id,task.title AS task_title,
                              learner.id::text AS learner_id,learner.display_name AS learner_name,
                              class.id::text AS class_id,class.name AS class_name,content.title AS content_title,
                              attempt.created_at AS submitted_at,attempt.ai_status,
                              COALESCE(review.status,'pending') AS review_status,
                              CASE WHEN remediation.status IN ('open','in_progress') THEN 'retraining'
                                   WHEN task.due_at IS NOT NULL AND task.due_at < now() THEN 'overdue' ELSE 'normal' END AS priority
                            FROM cl_evaluation_tasks evaluation
                            JOIN cl_practice_attempts attempt ON attempt.id=evaluation.practice_attempt_id
                            JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                            JOIN cl_practice_tasks task ON task.id=assignment.task_id
                            JOIN users learner ON learner.id=assignment.user_id
                            LEFT JOIN LATERAL (SELECT cm.class_id FROM class_memberships cm WHERE cm.user_id=learner.id AND cm.status='active' ORDER BY cm.joined_at DESC LIMIT 1) membership ON true
                            LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                            LEFT JOIN cl_content_items content ON content.id=attempt.content_item_id
                            LEFT JOIN LATERAL (SELECT id,status FROM cl_instructor_reviews r WHERE r.practice_attempt_id=attempt.id AND r.reviewer_id=evaluation.instructor_id AND r.status IN ('draft','published') ORDER BY revision_no DESC LIMIT 1) review ON true
                            LEFT JOIN cl_remediation_requests remediation ON remediation.review_id=review.id
                            WHERE evaluation.review_type='practice' AND evaluation.instructor_id=%s AND evaluation.status IN ('pending','in_progress','completed')
                              AND attempt.ai_status='completed'
                              AND task.deleted_at IS NULL
                              AND EXISTS (
                                SELECT 1 FROM student_instructor_assignments binding
                                LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                                WHERE binding.student_id=assignment.user_id
                                  AND binding.instructor_id=evaluation.instructor_id
                                  AND binding.status='active'
                                  AND binding.assignment_type IN ('training','both')
                                  AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                                  AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                                  AND (binding.course_id IS NULL OR binding.course_id=version.course_id)
                              )
                            ORDER BY assignment.id,COALESCE(attempt.content_item_id,attempt.id),attempt.created_at DESC,attempt.id DESC
                          ), exam_queue AS (
                            SELECT 'exam'::text AS review_type,assignment.id::text AS target_id,
                              assignment.id::text AS assignment_id,task.id::text AS task_id,task.title AS task_title,
                              learner.id::text AS learner_id,learner.display_name AS learner_name,
                              class.id::text AS class_id,class.name AS class_name,NULL::text AS content_title,
                              COALESCE(assignment.submitted_at,now()) AS submitted_at,COALESCE(ai.status,'pending') AS ai_status,
                              COALESCE(review.status,'pending') AS review_status,
                              CASE WHEN remediation.status IN ('open','in_progress') THEN 'retraining'
                                   WHEN task.due_at IS NOT NULL AND task.due_at < now() THEN 'overdue' ELSE 'normal' END AS priority
                            FROM cl_evaluation_tasks evaluation
                            JOIN cl_exam_assignments assignment ON assignment.id=evaluation.exam_assignment_id
                            JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                            JOIN users learner ON learner.id=assignment.user_id
                            LEFT JOIN LATERAL (SELECT cm.class_id FROM class_memberships cm WHERE cm.user_id=learner.id AND cm.status='active' ORDER BY cm.joined_at DESC LIMIT 1) membership ON true
                            LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                            LEFT JOIN LATERAL (SELECT string_agg(DISTINCT result.status,',') AS status FROM cl_ai_results result JOIN cl_recordings recording ON recording.id=result.recording_id WHERE recording.assignment_id=assignment.id) ai ON true
                            LEFT JOIN LATERAL (SELECT id,status FROM cl_instructor_reviews r WHERE r.exam_assignment_id=assignment.id AND r.reviewer_id=evaluation.instructor_id AND r.status IN ('draft','published') ORDER BY revision_no DESC LIMIT 1) review ON true
                            LEFT JOIN cl_remediation_requests remediation ON remediation.review_id=review.id
                            WHERE evaluation.review_type='exam' AND evaluation.instructor_id=%s AND evaluation.status IN ('pending','in_progress','completed')
                              AND task.deleted_at IS NULL
                              AND assignment.status IN ('submitted','graded','published')
                              AND EXISTS (
                                SELECT 1 FROM student_instructor_assignments binding
                                LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                                WHERE binding.student_id=assignment.user_id
                                  AND binding.instructor_id=evaluation.instructor_id
                                  AND binding.status='active'
                                  AND binding.assignment_type IN ('assessment','both')
                                  AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                                  AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                                  AND (binding.course_id IS NULL OR binding.course_id=version.course_id)
                              )
                          )
                          SELECT * FROM (SELECT * FROM practice_queue UNION ALL SELECT * FROM exam_queue) queue
                          WHERE (%s::text IS NULL OR review_type=%s) AND (%s::text IS NULL OR review_status=%s)
                            AND (%s::text IS NULL OR class_id=%s)
                          ORDER BY CASE review_status WHEN 'pending' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END,
                            CASE priority WHEN 'retraining' THEN 0 WHEN 'overdue' THEN 1 ELSE 2 END,submitted_at""",
                        (instructor_id, instructor_id, review_type, review_type, review_status, review_status, class_id, class_id))
            return [dict(row) for row in cur.fetchall()]

    def list_instructor_learners(self, instructor_id: str) -> list[dict[str, Any]]:
        """List only learners with a currently active binding to this instructor."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""WITH active_bindings AS (
                            SELECT binding.student_id,
                              array_agg(DISTINCT binding.assignment_type ORDER BY binding.assignment_type) AS assignment_types,
                              min(binding.created_at) AS assigned_at
                            FROM student_instructor_assignments binding
                            WHERE binding.instructor_id=%s::uuid AND binding.status='active'
                              AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                              AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                            GROUP BY binding.student_id
                          ), review_stats AS (
                            SELECT evaluation.learner_id,
                              count(DISTINCT evaluation.id)::int AS submitted_count,
                              count(DISTINCT evaluation.id) FILTER (WHERE COALESCE(review.status,'pending')<>'published')::int AS pending_review_count,
                              count(DISTINCT evaluation.id) FILTER (WHERE review.status='published')::int AS published_review_count,
                              count(DISTINCT evaluation.id) FILTER (WHERE remediation.status IN ('open','in_progress'))::int AS retraining_count,
                              max(COALESCE(attempt.created_at,exam.submitted_at,evaluation.created_at)) AS latest_submitted_at
                            FROM cl_evaluation_tasks evaluation
                            LEFT JOIN cl_practice_attempts attempt ON attempt.id=evaluation.practice_attempt_id
                            LEFT JOIN cl_exam_assignments exam ON exam.id=evaluation.exam_assignment_id
                            LEFT JOIN LATERAL (
                              SELECT item.id,item.status
                              FROM cl_instructor_reviews item
                              WHERE item.reviewer_id=evaluation.instructor_id
                                AND ((evaluation.review_type='practice' AND item.practice_attempt_id=evaluation.practice_attempt_id)
                                  OR (evaluation.review_type='exam' AND item.exam_assignment_id=evaluation.exam_assignment_id))
                                AND item.status IN ('draft','published')
                              ORDER BY item.revision_no DESC LIMIT 1
                            ) review ON true
                            LEFT JOIN cl_remediation_requests remediation ON remediation.review_id=review.id
                            WHERE evaluation.instructor_id=%s::uuid
                              AND evaluation.status IN ('pending','in_progress','completed')
                            GROUP BY evaluation.learner_id
                          )
                          SELECT learner.id::text AS learner_id,learner.display_name AS learner_name,
                            learner.external_ref,class.id::text AS class_id,class.name AS class_name,
                            binding.assignment_types,binding.assigned_at,
                            COALESCE(stats.submitted_count,0)::int AS submitted_count,
                            COALESCE(stats.pending_review_count,0)::int AS pending_review_count,
                            COALESCE(stats.published_review_count,0)::int AS published_review_count,
                            COALESCE(stats.retraining_count,0)::int AS retraining_count,
                            stats.latest_submitted_at
                          FROM active_bindings binding
                          JOIN users learner ON learner.id=binding.student_id AND learner.is_active=true
                          LEFT JOIN LATERAL (
                            SELECT membership.class_id FROM class_memberships membership
                            WHERE membership.user_id=learner.id AND membership.status='active'
                            ORDER BY membership.joined_at DESC LIMIT 1
                          ) membership ON true
                          LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                          LEFT JOIN review_stats stats ON stats.learner_id=learner.id
                          ORDER BY learner.display_name,learner.external_ref NULLS LAST""", (instructor_id, instructor_id))
            return [dict(row) for row in cur.fetchall()]

    def list_instructor_learner_submissions(self, instructor_id: str, learner_id: str) -> list[dict[str, Any]]:
        """Return submissions visible through this instructor's current learner binding."""
        with self._connect() as conn, conn.cursor() as cur:
            self._sync_instructor_evaluation_tasks(cur, instructor_id)
            cur.execute("""WITH practice_submissions AS (
                            SELECT 'practice'::text AS review_type,attempt.id::text AS target_id,
                              assignment.id::text AS assignment_id,task.id::text AS task_id,task.title AS task_title,
                              learner.id::text AS learner_id,learner.display_name AS learner_name,
                              class.id::text AS class_id,class.name AS class_name,content.title AS content_title,
                              attempt.created_at AS submitted_at,attempt.ai_status,
                              COALESCE(review.status,'pending') AS review_status,
                              CASE WHEN remediation.status IN ('open','in_progress') THEN 'retraining'
                                   WHEN task.due_at IS NOT NULL AND task.due_at<now() THEN 'overdue' ELSE 'normal' END AS priority
                            FROM cl_evaluation_tasks evaluation
                            JOIN cl_practice_attempts attempt ON attempt.id=evaluation.practice_attempt_id
                            JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                            JOIN cl_practice_tasks task ON task.id=assignment.task_id
                            JOIN users learner ON learner.id=assignment.user_id
                            LEFT JOIN LATERAL (SELECT membership.class_id FROM class_memberships membership WHERE membership.user_id=learner.id AND membership.status='active' ORDER BY membership.joined_at DESC LIMIT 1) membership ON true
                            LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                            LEFT JOIN cl_content_items content ON content.id=attempt.content_item_id
                            LEFT JOIN LATERAL (SELECT item.id,item.status FROM cl_instructor_reviews item WHERE item.practice_attempt_id=attempt.id AND item.reviewer_id=evaluation.instructor_id AND item.status IN ('draft','published') ORDER BY item.revision_no DESC LIMIT 1) review ON true
                            LEFT JOIN cl_remediation_requests remediation ON remediation.review_id=review.id
                            WHERE evaluation.review_type='practice' AND evaluation.instructor_id=%s::uuid
                              AND evaluation.learner_id=%s::uuid AND evaluation.status IN ('pending','in_progress','completed')
                              AND EXISTS (SELECT 1 FROM student_instructor_assignments binding
                                LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                                WHERE binding.student_id=assignment.user_id AND binding.instructor_id=evaluation.instructor_id
                                  AND binding.status='active' AND binding.assignment_type IN ('training','both')
                                  AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                                  AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                                  AND (binding.course_id IS NULL OR binding.course_id=version.course_id))
                          ), exam_submissions AS (
                            SELECT 'exam'::text AS review_type,assignment.id::text AS target_id,
                              assignment.id::text AS assignment_id,task.id::text AS task_id,task.title AS task_title,
                              learner.id::text AS learner_id,learner.display_name AS learner_name,
                              class.id::text AS class_id,class.name AS class_name,NULL::text AS content_title,
                              COALESCE(assignment.submitted_at,evaluation.created_at) AS submitted_at,COALESCE(ai.status,'pending') AS ai_status,
                              COALESCE(review.status,'pending') AS review_status,
                              CASE WHEN remediation.status IN ('open','in_progress') THEN 'retraining'
                                   WHEN task.due_at IS NOT NULL AND task.due_at<now() THEN 'overdue' ELSE 'normal' END AS priority
                            FROM cl_evaluation_tasks evaluation
                            JOIN cl_exam_assignments assignment ON assignment.id=evaluation.exam_assignment_id
                            JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                            JOIN users learner ON learner.id=assignment.user_id
                            LEFT JOIN LATERAL (SELECT membership.class_id FROM class_memberships membership WHERE membership.user_id=learner.id AND membership.status='active' ORDER BY membership.joined_at DESC LIMIT 1) membership ON true
                            LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                            LEFT JOIN LATERAL (SELECT string_agg(DISTINCT result.status,',') AS status FROM cl_ai_results result JOIN cl_recordings recording ON recording.id=result.recording_id WHERE recording.assignment_id=assignment.id) ai ON true
                            LEFT JOIN LATERAL (SELECT item.id,item.status FROM cl_instructor_reviews item WHERE item.exam_assignment_id=assignment.id AND item.reviewer_id=evaluation.instructor_id AND item.status IN ('draft','published') ORDER BY item.revision_no DESC LIMIT 1) review ON true
                            LEFT JOIN cl_remediation_requests remediation ON remediation.review_id=review.id
                            WHERE evaluation.review_type='exam' AND evaluation.instructor_id=%s::uuid
                              AND evaluation.learner_id=%s::uuid AND evaluation.status IN ('pending','in_progress','completed')
                              AND assignment.status IN ('submitted','graded','published')
                              AND EXISTS (SELECT 1 FROM student_instructor_assignments binding
                                LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
                                WHERE binding.student_id=assignment.user_id AND binding.instructor_id=evaluation.instructor_id
                                  AND binding.status='active' AND binding.assignment_type IN ('assessment','both')
                                  AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                                  AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                                  AND (binding.course_id IS NULL OR binding.course_id=version.course_id))
                          )
                          SELECT * FROM practice_submissions UNION ALL SELECT * FROM exam_submissions
                          ORDER BY submitted_at DESC""", (instructor_id, learner_id, instructor_id, learner_id))
            return [dict(row) for row in cur.fetchall()]

    def instructor_dashboard(self, instructor_id: str) -> dict[str, Any]:
        """Return instructor work/profile metrics from persisted review and assignment history."""
        params = {"instructor_id": instructor_id}
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""WITH active_bindings AS (
                            SELECT DISTINCT binding.student_id
                            FROM student_instructor_assignments binding
                            WHERE binding.instructor_id=%(instructor_id)s::uuid
                              AND binding.status='active'
                              AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                              AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                          ), published_reviews AS (
                            SELECT review.id,review.evaluation_task_id,review.practice_attempt_id,review.exam_assignment_id,
                              review.published_at,review.required_retraining
                            FROM cl_instructor_reviews review
                            WHERE review.reviewer_id=%(instructor_id)s::uuid
                              AND review.status='published' AND review.published_at IS NOT NULL
                          ), passed_learners AS (
                            SELECT binding.student_id,max(review.published_at) AS passed_at
                            FROM active_bindings binding
                            JOIN cl_evaluation_tasks evaluation
                              ON evaluation.learner_id=binding.student_id
                             AND evaluation.instructor_id=%(instructor_id)s::uuid
                            JOIN published_reviews review ON review.evaluation_task_id=evaluation.id
                              OR (evaluation.review_type='practice' AND review.practice_attempt_id=evaluation.practice_attempt_id)
                              OR (evaluation.review_type='exam' AND review.exam_assignment_id=evaluation.exam_assignment_id)
                            WHERE review.required_retraining=false
                              AND NOT EXISTS (
                                SELECT 1 FROM cl_remediation_requests remediation
                                WHERE remediation.learner_id=binding.student_id
                                  AND remediation.status IN ('open','in_progress')
                              )
                            GROUP BY binding.student_id
                          )
                          SELECT
                            (SELECT count(*)::int FROM published_reviews) AS total_evaluations,
                            (SELECT count(*)::int FROM published_reviews
                              WHERE published_at AT TIME ZONE 'Asia/Shanghai' >= date_trunc('month',now() AT TIME ZONE 'Asia/Shanghai')) AS month_evaluations,
                            (SELECT count(*)::int FROM published_reviews
                              WHERE (published_at AT TIME ZONE 'Asia/Shanghai')::date=(now() AT TIME ZONE 'Asia/Shanghai')::date) AS today_completed,
                            (SELECT count(*)::int FROM cl_evaluation_tasks evaluation
                              WHERE evaluation.instructor_id=%(instructor_id)s::uuid
                                AND evaluation.status='completed'
                                AND evaluation.completed_at AT TIME ZONE 'Asia/Shanghai' >= date_trunc('week',now() AT TIME ZONE 'Asia/Shanghai')) AS week_completed,
                            (SELECT count(*)::int FROM cl_evaluation_tasks evaluation
                              WHERE evaluation.instructor_id=%(instructor_id)s::uuid
                                AND evaluation.status NOT IN ('cancelled','resolved','waiting_assignment')
                                AND evaluation.created_at AT TIME ZONE 'Asia/Shanghai' >= date_trunc('week',now() AT TIME ZONE 'Asia/Shanghai')) AS week_total,
                            (SELECT count(*)::int FROM cl_remediation_requests remediation
                              JOIN cl_instructor_reviews review ON review.id=remediation.review_id
                              WHERE review.reviewer_id=%(instructor_id)s::uuid
                                AND remediation.status='completed'
                                AND remediation.completed_at AT TIME ZONE 'Asia/Shanghai' >= date_trunc('week',now() AT TIME ZONE 'Asia/Shanghai')) AS week_retraining_completed,
                            (SELECT count(DISTINCT binding.student_id)::int FROM student_instructor_assignments binding
                              WHERE binding.instructor_id=%(instructor_id)s::uuid) AS total_mentored,
                            (SELECT count(*)::int FROM active_bindings) AS current_mentoring,
                            (SELECT count(*)::int FROM passed_learners) AS passed_mentoring""", params)
            result = dict(cur.fetchone())
            cur.execute("""WITH active_bindings AS (
                            SELECT DISTINCT binding.student_id
                            FROM student_instructor_assignments binding
                            WHERE binding.instructor_id=%(instructor_id)s::uuid
                              AND binding.status='active'
                              AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                              AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
                          ), passed_learners AS (
                            SELECT binding.student_id,max(review.published_at) AS passed_at
                            FROM active_bindings binding
                            JOIN cl_evaluation_tasks evaluation
                              ON evaluation.learner_id=binding.student_id
                             AND evaluation.instructor_id=%(instructor_id)s::uuid
                            JOIN cl_instructor_reviews review
                              ON (review.evaluation_task_id=evaluation.id
                                OR (evaluation.review_type='practice' AND review.practice_attempt_id=evaluation.practice_attempt_id)
                                OR (evaluation.review_type='exam' AND review.exam_assignment_id=evaluation.exam_assignment_id))
                             AND review.reviewer_id=%(instructor_id)s::uuid
                             AND review.status='published'
                             AND review.required_retraining=false
                            WHERE NOT EXISTS (
                              SELECT 1 FROM cl_remediation_requests remediation
                              WHERE remediation.learner_id=binding.student_id
                                AND remediation.status IN ('open','in_progress')
                            )
                            GROUP BY binding.student_id
                          )
                          SELECT learner.id::text AS learner_id,learner.display_name AS learner_name,passed.passed_at
                          FROM passed_learners passed
                          JOIN users learner ON learner.id=passed.student_id
                          ORDER BY passed.passed_at DESC,learner.display_name
                          LIMIT 3""", params)
            result["recent_passed"] = [dict(row) for row in cur.fetchall()]
            cur.execute("""SELECT count(*)::int AS retraining_followups
                          FROM cl_remediation_requests remediation
                          JOIN cl_instructor_reviews review ON review.id=remediation.review_id
                          WHERE review.reviewer_id=%(instructor_id)s::uuid
                            AND remediation.status IN ('open','in_progress')""", params)
            result.update(dict(cur.fetchone()))
        queue = self.list_instructor_queue(instructor_id=instructor_id)
        result["pending_reviews"] = sum(item["review_status"] != "published" for item in queue)
        result["retraining_followups"] = max(
            result["retraining_followups"],
            sum(item["review_status"] != "published" and item["priority"] == "retraining" for item in queue),
        )
        result["active_mentoring"] = max(0, result["current_mentoring"] - result["passed_mentoring"])
        return result

    def get_instructor_review_detail(self, review_type: str, target_id: str, instructor_id: str | None = None) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            if review_type == "practice":
                cur.execute("""SELECT 'practice'::text AS review_type,attempt.id::text AS target_id,
                              assignment.id::text AS assignment_id,task.id::text AS task_id,task.title AS task_title,
                              learner.id::text AS learner_id,learner.display_name AS learner_name,class.name AS class_name,
                              content.title AS content_title,COALESCE(standard.standard_text,'') AS reference_text,content.sanitized_html,
                              recording.id::text AS recording_id,attempt.created_at AS submitted_at,attempt.ai_status,attempt.transcript AS saved_transcript,
                              attempt.score_summary AS ai_scores,attempt.issues AS ai_issues,attempt.feedback AS diagnosis_feedback
                              FROM cl_practice_attempts attempt
                              JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                              JOIN cl_practice_tasks task ON task.id=assignment.task_id
                              JOIN users learner ON learner.id=assignment.user_id
                              LEFT JOIN LATERAL (SELECT cm.class_id FROM class_memberships cm WHERE cm.user_id=learner.id AND cm.status='active' ORDER BY cm.joined_at DESC LIMIT 1) membership ON true
                              LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                              LEFT JOIN cl_content_items content ON content.id=attempt.content_item_id
                              LEFT JOIN LATERAL (SELECT standard_text FROM cl_course_standards s WHERE s.content_item_id=content.id ORDER BY created_at DESC LIMIT 1) standard ON true
                              LEFT JOIN cl_recordings recording ON recording.id=attempt.recording_id
                              WHERE attempt.id=%s
                                AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM cl_evaluation_tasks evaluation
                                                                 WHERE evaluation.practice_attempt_id=attempt.id
                                                                   AND evaluation.instructor_id=%s::uuid
                                                                   AND evaluation.status IN ('pending','in_progress','completed')))""", (target_id, instructor_id, instructor_id))
            else:
                cur.execute("""SELECT 'exam'::text AS review_type,assignment.id::text AS target_id,
                              assignment.id::text AS assignment_id,task.id::text AS task_id,task.title AS task_title,
                              learner.id::text AS learner_id,learner.display_name AS learner_name,class.name AS class_name,
                              NULL::text AS content_title,''::text AS reference_text,NULL::text AS recording_id,
                              COALESCE(assignment.submitted_at,now()) AS submitted_at,COALESCE(ai.status,'pending') AS ai_status,
                              '{}'::jsonb AS ai_scores,'[]'::jsonb AS ai_issues
                              FROM cl_exam_assignments assignment
                              JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
                              JOIN users learner ON learner.id=assignment.user_id
                              LEFT JOIN LATERAL (SELECT cm.class_id FROM class_memberships cm WHERE cm.user_id=learner.id AND cm.status='active' ORDER BY cm.joined_at DESC LIMIT 1) membership ON true
                              LEFT JOIN classes class ON class.id=COALESCE(learner.class_id,membership.class_id)
                              LEFT JOIN LATERAL (SELECT string_agg(DISTINCT result.status,',') AS status FROM cl_ai_results result JOIN cl_recordings recording ON recording.id=result.recording_id WHERE recording.assignment_id=assignment.id) ai ON true
                               WHERE assignment.id=%s
                                 AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM cl_evaluation_tasks evaluation
                                                                  WHERE evaluation.exam_assignment_id=assignment.id
                                                                    AND evaluation.instructor_id=%s::uuid
                                                                    AND evaluation.status IN ('pending','in_progress','completed')))""", (target_id, instructor_id, instructor_id))
            row = cur.fetchone()
            if not row:
                return None
            detail = dict(row)
            diagnosis_feedback: dict[str, Any] | None = None
            saved_transcript = detail.pop("saved_transcript", None)
            if review_type == "practice":
                from .html_sanitizer import extract_text
                detail["reference_text"] = (detail.get("reference_text") or "").strip() or extract_text(detail.pop("sanitized_html") or "")
                detail["ai_issues"] = instructor_review_issues(detail.get("ai_issues"))
                diagnosis_feedback = detail.pop("diagnosis_feedback", None)
                pending = diagnosis_feedback.get("pending_review_issues") if isinstance(diagnosis_feedback, dict) else None
                if isinstance(pending, list):
                    if not isinstance(detail.get("ai_issues"), list):
                        detail["ai_issues"] = []
                    detail["ai_issues"].extend(
                        issue for issue in pending
                        if isinstance(issue, dict) and issue.get("issue_status") == "pending_review"
                    )
            cur.execute("""SELECT id::text AS id,mime_type,duration_ms,created_at FROM cl_recordings
                          WHERE assignment_id=%s AND purpose=%s
                            AND (%s::text='exam' OR id=%s::uuid)
                          ORDER BY created_at""", (detail["assignment_id"], review_type, review_type, detail.get("recording_id")))
            recordings = [dict(item) for item in cur.fetchall()]
            for item in recordings:
                item["audio_url"] = f"/api/v1/cabinlingo/instructor/audio/{item['id']}"
            detail["recordings"] = recordings
            if recordings and not detail.get("recording_id"):
                detail["recording_id"] = recordings[0]["id"]
            detail["recording_url"] = f"/api/v1/cabinlingo/instructor/audio/{detail['recording_id']}" if detail.get("recording_id") else None
            detail.update(suntone_evidence(None))
            detail["recognized_text"] = saved_transcript if isinstance(saved_transcript, str) else None
            detail["alignment"] = (
                diagnosis_feedback.get("alignment", [])
                if isinstance(diagnosis_feedback, dict) and isinstance(diagnosis_feedback.get("alignment"), list)
                else []
            )
            detail["alignment_source"] = diagnosis_feedback.get("alignment_source") if isinstance(diagnosis_feedback, dict) else None
            detail["alignment_provider"] = diagnosis_feedback.get("alignment_provider") if isinstance(diagnosis_feedback, dict) else None
            cur.execute("""SELECT result.adapter,result.provider,result.provider_version,result.status,result.payload,result.created_at
                          FROM cl_ai_results result
                          JOIN cl_recordings recording ON recording.id=result.recording_id
                          WHERE recording.assignment_id=%s AND recording.purpose=%s
                            AND (%s::text='exam' OR recording.id=%s::uuid)
                          ORDER BY result.created_at""", (detail["assignment_id"], review_type, review_type, detail.get("recording_id")))
            evidence: dict[str, Any] = {}
            for result in cur.fetchall():
                evidence[result["adapter"]] = {"provider": result["provider"], "version": result["provider_version"], "status": result["status"], "payload": result["payload"]}
                if result["status"] == "completed" and isinstance(result["payload"], dict):
                    payload = result["payload"]
                    if result["adapter"] == "suntone":
                        detail.update(suntone_evidence(payload))
                        scores = payload.get("scores")
                        if isinstance(scores, dict):
                            detail["ai_scores"].update(scores)
                    if result["adapter"] == "asr_iat":
                        transcript = payload.get("transcript")
                        if isinstance(transcript, str):
                            detail["recognized_text"] = transcript
                        alignment = payload.get("alignment")
                        if isinstance(alignment, list):
                            detail["alignment"] = alignment
                            detail["alignment_source"] = payload.get("alignment_source")
                            detail["alignment_provider"] = result["provider"]
                if review_type == "practice" and isinstance(result["payload"], dict):
                    diagnosis = result["payload"].get("text_diagnosis")
                    pending = diagnosis.get("pending_review_issues") if isinstance(diagnosis, dict) else None
                    if isinstance(pending, list):
                        detail["ai_issues"].extend(
                            item for item in pending
                            if isinstance(item, dict) and item.get("issue_status") == "pending_review"
                        )
                if review_type == "exam" and isinstance(result["payload"], dict):
                    scores = result["payload"].get("scores")
                    issues = result["payload"].get("issues")
                    if isinstance(scores, dict): detail["ai_scores"].update(scores)
                    if isinstance(issues, list): detail["ai_issues"].extend(issues)
            if review_type == "practice":
                unique: list[dict[str, Any]] = []
                seen: set[tuple[Any, ...]] = set()
                for issue in detail["ai_issues"]:
                    if not isinstance(issue, dict):
                        continue
                    key = (
                        issue.get("type"), issue.get("reference_index"), issue.get("start_ms"),
                        issue.get("expected"), issue.get("actual"), issue.get("issue_status"),
                    )
                    if key not in seen:
                        seen.add(key)
                        unique.append(issue)
                detail["ai_issues"] = unique
            detail["ai_evidence"] = evidence
            target_column = "practice_attempt_id" if review_type == "practice" else "exam_assignment_id"
            cur.execute(f"""SELECT id::text AS id,reviewer_id::text AS reviewer_id,revision_no,status,
                          completeness_score::float8 AS completeness_score,pronunciation_score::float8 AS pronunciation_score,
                          fluency_score::float8 AS fluency_score,expression_score::float8 AS expression_score,
                          final_score::float8 AS final_score,evidence,summary,correction_advice,required_retraining,reviewed_at,published_at
                           FROM cl_instructor_reviews WHERE {target_column}=%s AND status IN ('draft','published')
                             AND (%s::uuid IS NULL OR reviewer_id=%s::uuid)
                           ORDER BY revision_no DESC LIMIT 1""", (target_id, instructor_id, instructor_id))
            review = cur.fetchone()
            detail["review"] = dict(review) if review else None
            return detail

    def get_instructor_recording(self, recording_id: str, instructor_id: str | None = None) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT recording.id::text AS id,recording.audio_ref,recording.mime_type,recording.byte_size
                          FROM cl_recordings recording
                          WHERE recording.id=%s
                            AND (%s::uuid IS NULL OR EXISTS (
                              SELECT 1 FROM cl_evaluation_tasks evaluation
                              WHERE evaluation.instructor_id=%s::uuid
                                AND evaluation.status IN ('pending','in_progress','completed')
                                AND ((evaluation.review_type='practice' AND evaluation.practice_attempt_id IN (
                                  SELECT attempt.id FROM cl_practice_attempts attempt WHERE attempt.recording_id=recording.id
                                )) OR (evaluation.review_type='exam' AND evaluation.exam_assignment_id=recording.assignment_id))
                            ))""", (recording_id, instructor_id, instructor_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_admin_learner_recording(self, recording_id: str, learner_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT recording.id::text AS id,recording.audio_ref,recording.mime_type,recording.byte_size
                          FROM cl_recordings recording
                          JOIN cl_practice_assignments assignment ON assignment.id=recording.assignment_id
                          JOIN cl_practice_tasks task ON task.id=assignment.task_id
                          WHERE recording.id=%s AND assignment.user_id=%s AND recording.purpose='practice'
                            AND task.deleted_at IS NULL""", (recording_id, learner_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def save_instructor_review(self, review_type: str, target_id: str, reviewer_id: str, data: dict[str, Any], publish: bool) -> dict[str, Any]:
        from psycopg.types.json import Jsonb
        data = dict(data)
        data["summary"] = str(data.get("summary") or "").strip() or "教员整改建议"
        data["correction_advice"] = str(data.get("correction_advice") or "").strip()
        if not data["correction_advice"]:
            data["correction_advice"] = data["summary"]
        target_column = "practice_attempt_id" if review_type == "practice" else "exam_assignment_id"
        target_table = "cl_practice_attempts" if review_type == "practice" else "cl_exam_assignments"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM {target_table} WHERE id=%s", (target_id,))
            if not cur.fetchone():
                raise ValueError("Review target not found")
            cur.execute(f"""SELECT id::text AS id,status FROM cl_evaluation_tasks
                           WHERE review_type=%s AND {target_column}=%s AND instructor_id=%s
                             AND status IN ('pending','in_progress','completed')""", (review_type, target_id, reviewer_id))
            evaluation_task = cur.fetchone()
            if not evaluation_task:
                raise ValueError("Review target is not assigned to this instructor")
            cur.execute(f"SELECT id::text AS id,status FROM cl_instructor_reviews WHERE {target_column}=%s AND reviewer_id=%s AND status IN ('draft','published') ORDER BY revision_no DESC LIMIT 1", (target_id, reviewer_id))
            current = cur.fetchone()
            if current and current["status"] == "published":
                raise ValueError("Published review is immutable")
            values = (data.get("completeness_score"), data.get("pronunciation_score"), data.get("fluency_score"), data.get("expression_score"), data.get("final_score"), Jsonb(data.get("evidence", {})), data["summary"], data["correction_advice"], bool(data.get("required_retraining")))
            if current:
                cur.execute("""UPDATE cl_instructor_reviews SET reviewer_id=%s,evaluation_task_id=%s,completeness_score=%s,pronunciation_score=%s,
                              fluency_score=%s,expression_score=%s,final_score=%s,evidence=%s,summary=%s,correction_advice=%s,
                              required_retraining=%s,reviewed_at=now(),updated_at=now() WHERE id=%s RETURNING id::text AS id,revision_no""",
                            (reviewer_id, evaluation_task["id"], *values, current["id"]))
            else:
                cur.execute(f"""INSERT INTO cl_instructor_reviews(review_type,{target_column},reviewer_id,evaluation_task_id,completeness_score,
                               pronunciation_score,fluency_score,expression_score,final_score,evidence,summary,correction_advice,
                               required_retraining,reviewed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                               RETURNING id::text AS id,revision_no""", (review_type, target_id, reviewer_id, evaluation_task["id"], *values))
            review = dict(cur.fetchone())
            cur.execute("UPDATE cl_evaluation_tasks SET status=%s,claimed_at=COALESCE(claimed_at,now()),completed_at=CASE WHEN %s THEN now() ELSE completed_at END,updated_at=now() WHERE id=%s", ("completed" if publish else "in_progress", publish, evaluation_task["id"]))
            if publish:
                cur.execute("UPDATE cl_instructor_reviews SET status='published',published_at=now(),updated_at=now() WHERE id=%s", (review["id"],))
                if review_type == "practice":
                    cur.execute("SELECT assignment.user_id::text AS learner_id,assignment.id::text AS assignment_id,attempt.content_item_id::text AS content_item_id FROM cl_practice_attempts attempt JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id WHERE attempt.id=%s", (target_id,))
                    target = cur.fetchone()
                    cur.execute("""INSERT INTO cl_teacher_feedback(learner_id,practice_attempt_id,teacher_id,summary,correction_advice,required_retraining,status,published_at)
                                  VALUES (%s,%s,%s,%s,%s,%s,'published',now())""", (target["learner_id"], target_id, reviewer_id, data["summary"], data.get("correction_advice", ""), bool(data.get("required_retraining"))))
                    remediation_assignment = target["assignment_id"]
                    remediation_content = target["content_item_id"]
                else:
                    cur.execute("SELECT user_id::text AS learner_id,id::text AS assignment_id FROM cl_exam_assignments WHERE id=%s", (target_id,))
                    target = cur.fetchone()
                    cur.execute("""INSERT INTO cl_manual_reviews(exam_assignment_id,evaluation_task_id,reviewer_id,status,comments,reviewed_at) VALUES (%s,%s,%s,'completed',%s,now())""", (target_id, evaluation_task["id"], reviewer_id, data["summary"]))
                    cur.execute("""INSERT INTO cl_scores(exam_assignment_id,evaluation_task_id,reviewer_id,manual_score,final_score,status,published_at) VALUES (%s,%s,%s,%s,%s,'published',now())""", (target_id, evaluation_task["id"], reviewer_id, data.get("final_score"), data.get("final_score")))
                    cur.execute("""SELECT count(*)::int AS pending FROM cl_evaluation_tasks
                                   WHERE exam_assignment_id=%s AND status IN ('pending','in_progress')""", (target_id,))
                    if cur.fetchone()["pending"] == 0:
                        cur.execute("UPDATE cl_exam_assignments SET status='published' WHERE id=%s", (target_id,))
                    cur.execute("""INSERT INTO cl_teacher_feedback(learner_id,exam_assignment_id,teacher_id,summary,correction_advice,required_retraining,status,published_at)
                                  VALUES (%s,%s,%s,%s,%s,%s,'published',now())""", (target["learner_id"], target_id, reviewer_id, data["summary"], data.get("correction_advice", ""), bool(data.get("required_retraining"))))
                    remediation_assignment = target["assignment_id"]
                    remediation_content = None
                if data.get("required_retraining"):
                    cur.execute("""INSERT INTO cl_remediation_requests(review_id,learner_id,practice_assignment_id,exam_assignment_id,content_item_id,instructions,due_at)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(review_id) DO NOTHING""",
                                (review["id"], target["learner_id"], remediation_assignment if review_type == "practice" else None,
                                 remediation_assignment if review_type == "exam" else None, remediation_content,
                                 data.get("correction_advice") or data["summary"], data.get("remediation_due_at")))
                cur.execute("""INSERT INTO cl_growth_events(learner_id,event_type,assignment_id,practice_attempt_id,content_item_id,metrics)
                              VALUES (%s,'feedback_received',%s,%s,%s,%s)""", (target["learner_id"], remediation_assignment,
                              target_id if review_type == "practice" else None, remediation_content, Jsonb({"review_type": review_type, "final_score": data.get("final_score"), "required_retraining": bool(data.get("required_retraining"))})))
            status = "published" if publish else "draft"
            return {"id": review["id"], "review_type": review_type, "target_id": target_id, "reviewer_id": reviewer_id,
                    "revision_no": review["revision_no"], "status": status, **data,
                    "reviewed_at": self.now(), "published_at": self.now() if publish else None}

    def class_review_analytics(self, instructor_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""WITH class_users AS (
                            SELECT training_class.id AS class_id,training_class.name AS class_name,learner_user.id AS user_id
                            FROM classes training_class JOIN class_memberships membership ON membership.class_id=training_class.id AND membership.status='active'
                            JOIN users learner_user ON learner_user.id=membership.user_id
                            WHERE (%s::uuid IS NULL OR EXISTS (
                              SELECT 1 FROM student_instructor_assignments binding
                              WHERE binding.student_id=learner_user.id AND binding.instructor_id=%s::uuid
                                AND binding.status='active'
                                AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
                                AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)))
                          ), submitted AS (
                            SELECT assignment.user_id,attempt.id AS target_id,'practice'::text AS review_type FROM cl_practice_attempts attempt JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                            WHERE (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM cl_evaluation_tasks evaluation WHERE evaluation.practice_attempt_id=attempt.id AND evaluation.instructor_id=%s::uuid AND evaluation.status IN ('pending','in_progress','completed')))
                            UNION ALL
                            SELECT assignment.user_id,assignment.id,'exam'::text FROM cl_exam_assignments assignment WHERE assignment.status IN ('submitted','graded','published')
                              AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM cl_evaluation_tasks evaluation WHERE evaluation.exam_assignment_id=assignment.id AND evaluation.instructor_id=%s::uuid AND evaluation.status IN ('pending','in_progress','completed')))
                          ), reviews AS (
                            SELECT COALESCE(practice_assignment.user_id,exam_assignment.user_id) AS user_id,
                              review.review_type,COALESCE(review.practice_attempt_id,review.exam_assignment_id) AS target_id,
                              review.status,review.final_score,review.required_retraining
                            FROM cl_instructor_reviews review
                            LEFT JOIN cl_practice_attempts attempt ON attempt.id=review.practice_attempt_id
                            LEFT JOIN cl_practice_assignments practice_assignment ON practice_assignment.id=attempt.assignment_id
                            LEFT JOIN cl_exam_assignments exam_assignment ON exam_assignment.id=review.exam_assignment_id
                            WHERE review.status IN ('draft','published')
                              AND (%s::uuid IS NULL OR review.reviewer_id=%s::uuid)
                          )
                          SELECT class_users.class_id::text AS class_id,class_users.class_name,
                            count(DISTINCT class_users.user_id)::int AS learner_count,
                            count(DISTINCT (submitted.review_type,submitted.target_id))::int AS submitted_count,
                            (count(DISTINCT (submitted.review_type,submitted.target_id)) FILTER (WHERE reviews.status IS NULL))::int AS pending_review_count,
                            (count(*) FILTER (WHERE reviews.status='published'))::int AS published_review_count,
                            (count(*) FILTER (WHERE reviews.required_retraining))::int AS remediation_count,
                            round(avg(reviews.final_score) FILTER (WHERE reviews.status='published'),1)::float8 AS average_score
                          FROM class_users LEFT JOIN submitted ON submitted.user_id=class_users.user_id
                          LEFT JOIN reviews ON reviews.user_id=class_users.user_id AND reviews.review_type=submitted.review_type AND reviews.target_id=submitted.target_id
                          GROUP BY class_users.class_id,class_users.class_name ORDER BY class_users.class_name""",
                        (instructor_id, instructor_id, instructor_id, instructor_id,
                         instructor_id, instructor_id, instructor_id, instructor_id))
            return [dict(row) for row in cur.fetchall()]
