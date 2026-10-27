from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from typing import Any
from uuid import uuid4

from .practice_feedback import collect_practice_feedback, instructor_review_issues, learner_visible_issues


def new_id(prefix: str) -> str:
    # UUID strings work with PostgreSQL UUID columns and remain opaque to clients.
    return str(uuid4())


@dataclass
class PracticeTask:
    id: str
    title: str
    broadcast_id: str | None
    due_at: datetime | None
    completion_rule: dict[str, Any]
    status: str = "draft"
    course_version_id: str | None = None
    broadcast_script_id: str | None = None
    week_no: int | None = None
    unlock_after_task_type: str | None = None
    unlock_after_task_id: str | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None


@dataclass
class PracticeAssignment:
    id: str
    task_id: str
    user_id: str
    status: str = "not_started"
    attempt_ids: list[str] = field(default_factory=list)


@dataclass
class PracticeAttempt:
    id: str
    assignment_id: str
    segment_id: str
    audio_ref: str
    attempt_no: int
    created_at: datetime
    ai_status: str = "pending_adapter"


@dataclass
class ExamTask:
    id: str
    title: str
    broadcast_id: str | None
    max_recordings: int
    due_at: datetime | None
    status: str = "draft"
    course_version_id: str | None = None
    broadcast_script_id: str | None = None
    week_no: int | None = None
    unlock_after_task_type: str | None = None
    unlock_after_task_id: str | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None


@dataclass
class ExamAssignment:
    id: str
    task_id: str
    user_id: str
    status: str = "not_started"
    submitted_recordings: list[str] = field(default_factory=list)
    submitted_at: datetime | None = None


class TrainingStore:
    """In-memory repository for unit tests and local development only."""

    def __init__(self) -> None:
        self.broadcasts: dict[str, dict[str, Any]] = {}
        self.practice_tasks: dict[str, PracticeTask] = {}
        self.practice_assignments: dict[str, PracticeAssignment] = {}
        self.practice_attempts: dict[str, PracticeAttempt] = {}
        self.exam_tasks: dict[str, ExamTask] = {}
        self.exam_assignments: dict[str, ExamAssignment] = {}
        self.courses: dict[str, dict[str, Any]] = {}
        self.course_versions: dict[str, dict[str, Any]] = {}
        self.chapters: dict[str, dict[str, Any]] = {}
        self.content_items: dict[str, dict[str, Any]] = {}
        self.content_interactions: dict[str, dict[str, Any]] = {}
        self.interaction_attempts: list[dict[str, Any]] = []
        self.course_standards: dict[str, list[dict[str, Any]]] = {}
        self.standard_audio_files: dict[str, dict[str, Any]] = {}
        self.course_details: dict[str, dict[str, Any]] = {}
        self.course_v23_files: dict[str, dict[str, Any]] = {}
        self.course_import_batches: dict[str, dict[str, Any]] = {}
        self.content_assets: dict[str, dict[str, Any]] = {}
        self.content_documents: dict[str, dict[str, Any]] = {}
        self.learning_cards: dict[str, dict[str, Any]] = {}
        self.learning_card_resources: dict[str, dict[str, dict[str, Any]]] = {}
        self.learning_card_reads: set[tuple[str, str]] = set()
        self.recordings: dict[str, dict[str, Any]] = {}
        self.learner_attempt_details: dict[str, dict[str, Any]] = {}
        self.teacher_feedback: list[dict[str, Any]] = []
        self.growth_events: list[dict[str, Any]] = []
        self.instructor_reviews: dict[tuple[str, str], dict[str, Any]] = {}
        self.remediation_requests: list[dict[str, Any]] = []

    def seed_broadcast(self, code: str, title: str, segments: int = 0) -> dict[str, Any]:
        item = {"id": new_id("bc"), "code": code, "title": title, "language": "en-US", "segment_count": segments}
        self.broadcasts[item["id"]] = item
        return item

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def healthcheck(self) -> bool:
        return True

    def list_broadcasts(self) -> list[dict[str, Any]]:
        return list(self.broadcasts.values())

    def create_broadcast(self, code: str, title: str, language: str, status: str, created_by: str | None = None) -> dict[str, Any]:
        if any(item["code"] == code for item in self.broadcasts.values()):
            raise ValueError("Broadcast code already exists")
        item = {"id": new_id("bc"), "code": code, "title": title, "language": language, "status": status, "segment_count": 0}
        self.broadcasts[item["id"]] = item
        return item

    def update_broadcast(self, broadcast_id: str, **changes: Any) -> dict[str, Any] | None:
        item = self.broadcasts.get(broadcast_id)
        if not item:
            return None
        item.update({key: value for key, value in changes.items() if value is not None})
        return item

    def list_tasks(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        def broadcast_script_count(task: PracticeTask | ExamTask) -> int:
            version = self.course_versions.get(task.course_version_id or "")
            course = self.courses.get(version["course_id"]) if version else None
            if not course or course.get("category") != "broadcast_snapshot":
                return 0
            return sum(chapter["course_version_id"] == task.course_version_id for chapter in self.chapters.values())
        for task in self.practice_tasks.values():
            if task.deleted_at:
                continue
            assignments = [a for a in self.practice_assignments.values() if a.task_id == task.id]
            rows.append({"id": task.id, "title": task.title, "broadcast_id": task.broadcast_id, "course_version_id": task.course_version_id, "broadcast_script_id": task.broadcast_script_id, "broadcast_script_count": broadcast_script_count(task), "due_at": task.due_at, "week_no": task.week_no, "unlock_after_task_type": task.unlock_after_task_type, "unlock_after_task_id": task.unlock_after_task_id, "status": task.status, "task_type": "practice", "assignment_count": len(assignments), "completed_count": sum(a.status == "completed" for a in assignments)})
        for task in self.exam_tasks.values():
            if task.deleted_at:
                continue
            assignments = [a for a in self.exam_assignments.values() if a.task_id == task.id]
            rows.append({"id": task.id, "title": task.title, "broadcast_id": task.broadcast_id, "course_version_id": task.course_version_id, "broadcast_script_id": task.broadcast_script_id, "broadcast_script_count": broadcast_script_count(task), "due_at": task.due_at, "week_no": task.week_no, "unlock_after_task_type": task.unlock_after_task_type, "unlock_after_task_id": task.unlock_after_task_id, "status": task.status, "task_type": "exam", "assignment_count": len(assignments), "completed_count": sum(a.status in {"submitted", "graded", "published"} for a in assignments)})
        return rows

    def set_task_status(self, task_type: str, task_id: str, status: str) -> dict[str, Any] | None:
        task = (self.practice_tasks if task_type == "practice" else self.exam_tasks).get(task_id)
        if not task or task.deleted_at:
            return None
        task.status = status
        version = self.course_versions.get(task.course_version_id or "")
        course = self.courses.get(version["course_id"]) if version else None
        broadcast_script_count = sum(chapter["course_version_id"] == task.course_version_id for chapter in self.chapters.values()) if course and course.get("category") == "broadcast_snapshot" else 0
        return {"id": task.id, "title": task.title, "broadcast_id": task.broadcast_id, "course_version_id": task.course_version_id, "broadcast_script_id": task.broadcast_script_id, "broadcast_script_count": broadcast_script_count, "due_at": task.due_at, "week_no": task.week_no, "unlock_after_task_type": task.unlock_after_task_type, "unlock_after_task_id": task.unlock_after_task_id, "status": task.status, "task_type": task_type, "assignment_count": 0, "completed_count": 0}

    def delete_task(self, task_type: str, task_id: str, deleted_by: str) -> bool:
        task = (self.practice_tasks if task_type == "practice" else self.exam_tasks).get(task_id)
        if not task or task.deleted_at:
            return False
        task.status = "closed"
        task.deleted_at = self.now()
        task.deleted_by = deleted_by
        return True

    def resolve_task_assignee_ids(self, user_ids: list[str], class_ids: list[str], task_type: str) -> list[str]:
        if class_ids:
            raise ValueError("Class-based assignment requires PostgreSQL")
        if not user_ids:
            raise ValueError("No active learner selected")
        return list(dict.fromkeys(user_ids))

    def reassign_evaluation_tasks(self, learner_id: str) -> dict[str, Any]:
        return {"learner_id": learner_id, "created": 0, "waiting_assignment": 0, "practice_targets": 0, "exam_targets": 0}

    def list_unassigned_evaluation_tasks(self) -> list[dict[str, Any]]:
        return []

    def create_recording(self, assignment_id: str, purpose: str, audio_ref: str, duration_ms: int | None = None, content_item_id: str | None = None, mime_type: str | None = None, byte_size: int | None = None, checksum_sha256: str | None = None) -> dict[str, Any]:
        practice = self.practice_assignments.get(assignment_id)
        exam = self.exam_assignments.get(assignment_id)
        task = self.get_practice_task(practice.task_id) if practice else self.get_exam_task(exam.task_id) if exam else None
        if not task:
            raise ValueError("Assignment not found")
        item = {"id": new_id("rec"), "assignment_id": assignment_id, "purpose": purpose, "audio_ref": audio_ref, "status": "uploaded", "content_item_id": content_item_id, "mime_type": mime_type, "byte_size": byte_size, "checksum_sha256": checksum_sha256}
        self.recordings[item["id"]] = item
        return item

    def get_recording_audio_ref(self, recording_id: str, assignment_id: str, user_id: str) -> str | None:
        item = self.recordings.get(recording_id)
        practice = self.practice_assignments.get(assignment_id)
        exam = self.exam_assignments.get(assignment_id)
        task = self.get_practice_task(practice.task_id) if practice else self.get_exam_task(exam.task_id) if exam else None
        return item["audio_ref"] if item and task and item["assignment_id"] == assignment_id else None

    def get_learner_recording(self, recording_id: str, user_id: str) -> dict[str, Any] | None:
        item = self.recordings.get(recording_id)
        if not item:
            return None
        practice = self.practice_assignments.get(item["assignment_id"])
        exam = self.exam_assignments.get(item["assignment_id"])
        task = self.get_practice_task(practice.task_id) if practice else self.get_exam_task(exam.task_id) if exam else None
        owned = bool(task) and any(a.id == item["assignment_id"] and a.user_id == user_id for a in [*self.practice_assignments.values(), *self.exam_assignments.values()])
        return dict(item) if owned else None

    def list_review_queue(self, instructor_id: str | None = None) -> list[dict[str, Any]]:
        return [{"assignment_id": a.id, "task_id": a.task_id, "user_id": a.user_id, "status": a.status, "submitted_at": a.submitted_at, "ai_status": "pending", "manual_status": "pending"} for a in self.exam_assignments.values() if a.status == "submitted"]

    def save_manual_review(self, assignment_id: str, reviewer_id: str, manual_score: float, comments: str, publish: bool) -> dict[str, Any]:
        assignment = self.exam_assignments.get(assignment_id)
        if not assignment:
            raise ValueError("Review assignment not found")
        if publish:
            assignment.status = "published"
        return {"assignment_id": assignment_id, "manual_score": manual_score, "status": "published" if publish else "completed"}

    def has_broadcast(self, broadcast_id: str) -> bool:
        return broadcast_id in self.broadcasts

    def has_course_version(self, course_version_id: str, published_only: bool = False) -> bool:
        item = self.course_versions.get(course_version_id)
        return bool(item and (not published_only or item["status"] == "published"))

    def create_learning_card(self, card_id: str, manifest: dict[str, Any], storage_prefix: str,
                             package_sha256: str, created_by: str,
                             resources: list[dict[str, Any]]) -> dict[str, Any]:
        now = self.now()
        item = {
            "id": card_id, "title": manifest["title"], "category": manifest["category"],
            "package_format": manifest["format"], "package_version": manifest["version"],
            "entry_file": manifest["entry"], "storage_prefix": storage_prefix,
            "package_sha256": package_sha256, "metadata": dict(manifest),
            "resource_count": len(resources), "status": "active", "created_by": created_by,
            "created_at": now, "updated_at": now, "archived_at": None,
        }
        self.learning_cards[card_id] = item
        self.learning_card_resources[card_id] = {resource["resource_path"]: dict(resource) for resource in resources}
        return dict(item)

    def list_learning_cards(self, include_archived: bool = False) -> list[dict[str, Any]]:
        rows = []
        for card in self.learning_cards.values():
            if card["status"] == "archived" and not include_archived:
                continue
            rows.append({
                **card,
                "course_count": sum(item.get("learning_card_id") == card["id"] for item in self.content_items.values()),
            })
        return sorted(rows, key=lambda item: item["created_at"], reverse=True)

    def get_learning_card(self, card_id: str) -> dict[str, Any] | None:
        card = self.learning_cards.get(card_id)
        if not card:
            return None
        return {
            **card,
            "course_count": sum(item.get("learning_card_id") == card_id for item in self.content_items.values()),
        }

    def get_learning_card_resource(self, card_id: str, resource_path: str) -> dict[str, Any] | None:
        item = self.learning_card_resources.get(card_id, {}).get(resource_path)
        return dict(item) if item else None

    def archive_learning_card(self, card_id: str) -> dict[str, Any] | None:
        card = self.learning_cards.get(card_id)
        if not card:
            return None
        card.update({"status": "archived", "archived_at": self.now(), "updated_at": self.now()})
        return self.get_learning_card(card_id)

    def _clone_course_version(self, source_version_id: str, course_id: str, created_by: str) -> dict[str, Any]:
        existing = [item for item in self.course_versions.values() if item["course_id"] == course_id]
        next_no = max((item["version_no"] for item in existing), default=0) + 1
        version = self.create_course_version(course_id, f"V{next_no}.0-LC", "加入学习卡片", created_by)
        for source_chapter in self.list_chapters(source_version_id):
            chapter = self.create_chapter(
                version["id"], source_chapter["code"], source_chapter["title"],
                source_chapter["sequence_no"], source_chapter.get("learning_objective", ""),
            )
            for source_content in self.list_content_items(source_chapter["id"]):
                content_id = new_id("content")
                copied = {key: value for key, value in source_content.items() if key != "interaction_count"}
                copied.update({"id": content_id, "chapter_id": chapter["id"]})
                self.content_items[content_id] = copied
                if source_content["id"] in self.course_standards:
                    self.course_standards[content_id] = [
                        {**standard, "id": new_id("standard"), "content_item_id": content_id}
                        for standard in self.course_standards[source_content["id"]]
                    ]
                for asset in list(self.content_assets.values()):
                    if asset["content_item_id"] == source_content["id"]:
                        asset_id = new_id("asset")
                        self.content_assets[asset_id] = {**asset, "id": asset_id, "content_item_id": content_id}
                for interaction in list(self.content_interactions.values()):
                    if interaction["content_item_id"] == source_content["id"]:
                        interaction_id = new_id("interaction")
                        self.content_interactions[interaction_id] = {
                            **interaction, "id": interaction_id, "content_item_id": content_id,
                            "created_by": created_by, "created_at": self.now(), "updated_at": self.now(),
                        }
        return version

    def add_learning_card_to_course(self, card_id: str, course_id: str, created_by: str) -> dict[str, Any]:
        card = self.learning_cards.get(card_id)
        course = self.courses.get(course_id)
        if not card or card["status"] != "active":
            raise ValueError("Learning Card 不存在或已归档")
        if not course or course.get("status") == "archived":
            raise ValueError("课程不存在或已归档")
        drafts = [item for item in self.course_versions.values() if item["course_id"] == course_id and item["status"] == "draft"]
        if drafts:
            version = max(drafts, key=lambda item: item["version_no"])
        else:
            published = [item for item in self.course_versions.values() if item["course_id"] == course_id and item["status"] == "published"]
            if published:
                version = self._clone_course_version(max(published, key=lambda item: item["version_no"])["id"], course_id, created_by)
            else:
                next_no = max((item["version_no"] for item in self.course_versions.values() if item["course_id"] == course_id), default=0) + 1
                version = self.create_course_version(course_id, f"V{next_no}.0-LC", "加入学习卡片", created_by)
        if any(item.get("learning_card_id") == card_id for chapter in self.list_chapters(version["id"])
               for item in self.list_content_items(chapter["id"])):
            raise ValueError("该学习卡片已加入当前课程草稿")
        sequence = max((item["sequence_no"] for item in self.list_chapters(version["id"])), default=0) + 1
        chapter = self.create_chapter(version["id"], f"LC-{card_id[:8].upper()}", card["title"], sequence, "完成学习卡片内容")
        content_id = new_id("content")
        content = {
            "id": content_id, "chapter_id": chapter["id"], "content_type": "html",
            "title": card["title"], "sequence_no": 1, "source_filename": "learning-card.zip",
            "sanitized_html": f"<p>{escape(card['title'])}</p>",
            "original_sha256": card["package_sha256"], "sanitized_sha256": card["package_sha256"],
            "validation_report": {"source_type": "learning_card", "package_version": card["package_version"]},
            "learning_card_id": card_id,
        }
        self.content_items[content_id] = content
        return {
            "learning_card_id": card_id, "course_id": course_id, "course_version_id": version["id"],
            "chapter_id": chapter["id"], "content_item_id": content_id,
            "course_title": course["title"], "version_status": version["status"],
        }

    def remove_learning_card_from_course(self, content_id: str) -> dict[str, Any]:
        content = self.content_items.get(content_id)
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        version = self.course_versions.get(chapter["course_version_id"]) if chapter else None
        if not content or not content.get("learning_card_id") or not chapter or not version:
            raise ValueError("课程中的学习卡片不存在")
        if version["status"] != "draft":
            raise ValueError("已发布版本不可移除学习卡片，请先创建新版本")
        chapter_id = chapter["id"]
        self.content_items.pop(content_id, None)
        self.course_standards.pop(content_id, None)
        for asset_id in [key for key, item in self.content_assets.items() if item["content_item_id"] == content_id]:
            self.content_assets.pop(asset_id, None)
        for interaction_id in [key for key, item in self.content_interactions.items() if item["content_item_id"] == content_id]:
            self.content_interactions.pop(interaction_id, None)
        if not any(item["chapter_id"] == chapter_id for item in self.content_items.values()):
            self.chapters.pop(chapter_id, None)
        return {"content_item_id": content_id, "chapter_id": chapter_id, "removed": True}

    def move_learning_card_in_course(self, content_id: str, direction: str) -> dict[str, Any]:
        if direction not in {"up", "down"}:
            raise ValueError("课程顺序调整方向无效")
        content = self.content_items.get(content_id)
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        version = self.course_versions.get(chapter["course_version_id"]) if chapter else None
        if not content or not content.get("learning_card_id") or not chapter or not version:
            raise ValueError("课程中的学习卡片不存在")
        if version["status"] != "draft":
            raise ValueError("已发布版本不可调整顺序，请先创建新版本")
        chapters = self.list_chapters(version["id"])
        current_index = next(index for index, item in enumerate(chapters) if item["id"] == chapter["id"])
        target_index = current_index - 1 if direction == "up" else current_index + 1
        if target_index < 0 or target_index >= len(chapters):
            return {"content_item_id": content_id, "chapter_id": chapter["id"], "sequence_no": chapter["sequence_no"]}
        target = self.chapters[chapters[target_index]["id"]]
        chapter["sequence_no"], target["sequence_no"] = target["sequence_no"], chapter["sequence_no"]
        return {"content_item_id": content_id, "chapter_id": chapter["id"], "sequence_no": chapter["sequence_no"]}

    def get_learner_learning_card(self, content_id: str, assignment_id: str, user_id: str) -> dict[str, Any] | None:
        content = self.content_items.get(content_id)
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        card = self.learning_cards.get(content.get("learning_card_id", "")) if content else None
        if not content or not chapter or not card:
            return None
        practice = self.practice_assignments.get(assignment_id)
        exam = self.exam_assignments.get(assignment_id)
        assignment = practice if practice and practice.user_id == user_id else exam if exam and exam.user_id == user_id else None
        task = self.practice_tasks.get(assignment.task_id) if practice and assignment else self.exam_tasks.get(assignment.task_id) if assignment else None
        if not task or task.deleted_at or task.status == "draft" or task.course_version_id != chapter["course_version_id"]:
            return None
        return {**self.get_learning_card(card["id"]), "content_item_id": content_id, "assignment_id": assignment_id}

    def list_courses(self) -> list[dict[str, Any]]:
        result = []
        for course in self.courses.values():
            if course.get("category") == "broadcast_snapshot":
                continue
            versions = [item for item in self.course_versions.values() if item["course_id"] == course["id"]]
            published = next((item for item in versions if item["status"] == "published"), None)
            result.append({**course, "version_count": len(versions), "published_version_id": published["id"] if published else None})
        return result

    def materialize_broadcast_course(self, script: dict[str, Any], version: dict[str, Any], slices: list[dict[str, Any]], created_by: str) -> str:
        if not script.get("enabled") or not script.get("ready"):
            raise ValueError("Broadcast script is not enabled or complete")
        course_id = new_id("course")
        version_id = new_id("version")
        chapter_id = new_id("chapter")
        self.courses[course_id] = {
            "id": course_id, "organization_id": script.get("company_id"),
            "code": f"BROADCAST-{course_id[:8]}", "title": script["title"],
            "description": "Broadcast task snapshot", "category": "broadcast_snapshot",
            "status": "published", "version_count": 1, "published_version_id": version_id,
        }
        self.course_versions[version_id] = {
            "id": version_id, "course_id": course_id, "version_no": 1,
            "version_label": f"V{version['version']}", "status": "published",
            "change_summary": "Broadcast task snapshot", "chapter_count": 1,
            "content_count": len(slices), "published_at": self.now(),
            "source_broadcast_script_id": script["id"],
        }
        self.chapters[chapter_id] = {
            "id": chapter_id, "course_version_id": version_id, "code": "SCRIPT",
            "title": script["title"], "sequence_no": 1,
            "learning_objective": "Complete every broadcast slice", "content_count": len(slices),
        }
        for index, item in enumerate(slices, start=1):
            content_id = new_id("content")
            self.content_items[content_id] = {
                "id": content_id, "chapter_id": chapter_id, "content_type": "broadcast",
                "title": f"第 {index} 段", "sequence_no": index, "source_filename": None,
                "sanitized_html": f"<p>{item['text']}</p>", "original_sha256": None,
                "sanitized_sha256": None, "validation_report": {"source": "broadcast_library"},
            }
            self.course_standards[content_id] = [{
                "id": new_id("standard"), "content_item_id": content_id,
                "standard_text": item["text"], "stress_rules": "", "pronunciation_notes": "",
                "pause_rules": "", "tone_requirements": "", "rule_version": "1.0",
                "change_summary": "", "created_at": self.now(),
            }]
        return version_id

    def materialize_broadcast_course_bundle(self, sources: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]], created_by: str) -> str:
        """Create one immutable course version containing several broadcast scripts."""
        if len(sources) < 2:
            raise ValueError("A broadcast bundle requires at least two scripts")
        for script, version, slices in sources:
            if not script.get("enabled") or not script.get("ready") or not slices:
                raise ValueError("Broadcast script is not enabled or complete")
            if "".join(item["text"] for item in slices) != version["full_text"]:
                raise ValueError("Broadcast slices do not match the full text")
        course_id = new_id("course")
        version_id = new_id("version")
        organization_ids = {script.get("company_id") for script, _, _ in sources}
        organization_id = next(iter(organization_ids)) if len(organization_ids) == 1 else None
        self.courses[course_id] = {
            "id": course_id, "organization_id": organization_id,
            "code": f"BROADCAST-BUNDLE-{course_id[:8]}", "title": f"广播词组合（{len(sources)}篇）",
            "description": "Broadcast task bundle snapshot", "category": "broadcast_snapshot",
            "status": "published", "version_count": 1, "published_version_id": version_id,
        }
        self.course_versions[version_id] = {
            "id": version_id, "course_id": course_id, "version_no": 1,
            "version_label": "组合 V1", "status": "published",
            "change_summary": "Broadcast task bundle snapshot", "chapter_count": len(sources),
            "content_count": sum(len(slices) for _, _, slices in sources), "published_at": self.now(),
            "source_broadcast_script_id": None,
        }
        for chapter_number, (script, version, slices) in enumerate(sources, start=1):
            chapter_id = new_id("chapter")
            self.chapters[chapter_id] = {
                "id": chapter_id, "course_version_id": version_id, "code": f"SCRIPT-{chapter_number}",
                "title": script["title"], "sequence_no": chapter_number,
                "learning_objective": "Complete every broadcast slice", "content_count": len(slices),
            }
            for slice_number, item in enumerate(slices, start=1):
                content_id = new_id("content")
                self.content_items[content_id] = {
                    "id": content_id, "chapter_id": chapter_id, "content_type": "broadcast",
                    "title": script["title"] if len(slices) == 1 else f"第 {slice_number} 段",
                    "sequence_no": slice_number, "source_filename": None,
                    "sanitized_html": f"<p>{escape(item['text'])}</p>", "original_sha256": None,
                    "sanitized_sha256": None,
                    "validation_report": {"source": "broadcast_library", "bundle": True,
                                          "script_id": script["id"], "version_id": version["id"], "slice_id": item["id"]},
                }
                self.course_standards[content_id] = [{
                    "id": new_id("standard"), "content_item_id": content_id,
                    "standard_text": item["text"], "stress_rules": "", "pronunciation_notes": "",
                    "pause_rules": "", "tone_requirements": "", "rule_version": "1.0",
                    "change_summary": "", "created_at": self.now(),
                }]
        return version_id

    def create_course(self, code: str, title: str, description: str, category: str, organization_id: str | None, created_by: str) -> dict[str, Any]:
        if any(item["code"].lower() == code.lower() and item.get("organization_id") == organization_id for item in self.courses.values()):
            raise ValueError("Course code already exists")
        item = {"id": new_id("course"), "code": code, "title": title, "description": description, "category": category, "organization_id": organization_id, "status": "draft", "version_count": 0, "published_version_id": None}
        self.courses[item["id"]] = item
        return item

    def list_course_versions(self, course_id: str) -> list[dict[str, Any]]:
        result = []
        for version in self.course_versions.values():
            if version["course_id"] != course_id:
                continue
            chapters = [item for item in self.chapters.values() if item["course_version_id"] == version["id"]]
            content_count = sum(1 for item in self.content_items.values() if item["chapter_id"] in {chapter["id"] for chapter in chapters})
            result.append({**version, "chapter_count": len(chapters), "content_count": content_count})
        return sorted(result, key=lambda item: item["version_no"], reverse=True)

    def create_course_version(self, course_id: str, version_label: str, change_summary: str, created_by: str) -> dict[str, Any]:
        if course_id not in self.courses:
            raise ValueError("Course not found")
        existing = [item for item in self.course_versions.values() if item["course_id"] == course_id]
        if any(item["version_label"] == version_label for item in existing):
            raise ValueError("Version label already exists")
        item = {"id": new_id("version"), "course_id": course_id, "version_no": max([item["version_no"] for item in existing], default=0) + 1, "version_label": version_label, "status": "draft", "change_summary": change_summary, "chapter_count": 0, "content_count": 0, "published_at": None}
        self.course_versions[item["id"]] = item
        return item

    def list_chapters(self, course_version_id: str) -> list[dict[str, Any]]:
        result = []
        for chapter in self.chapters.values():
            if chapter["course_version_id"] == course_version_id:
                result.append({**chapter, "content_count": sum(item["chapter_id"] == chapter["id"] for item in self.content_items.values())})
        return sorted(result, key=lambda item: item["sequence_no"])

    def create_chapter(self, course_version_id: str, code: str, title: str, sequence_no: int, learning_objective: str) -> dict[str, Any]:
        version = self.course_versions.get(course_version_id)
        if not version or version["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")
        if any(item["course_version_id"] == course_version_id and (item["code"] == code or item["sequence_no"] == sequence_no) for item in self.chapters.values()):
            raise ValueError("Chapter code or sequence already exists")
        item = {"id": new_id("chapter"), "course_version_id": course_version_id, "code": code, "title": title, "sequence_no": sequence_no, "learning_objective": learning_objective, "content_count": 0}
        self.chapters[item["id"]] = item
        return item

    def list_content_items(self, chapter_id: str) -> list[dict[str, Any]]:
        return sorted([{**item, "interaction_count": sum(1 for interaction in self.content_interactions.values() if interaction["content_item_id"] == item["id"] and interaction["status"] != "archived")} for item in self.content_items.values() if item["chapter_id"] == chapter_id], key=lambda item: item["sequence_no"])

    def create_html_content(self, chapter_id: str, title: str, sequence_no: int, source_filename: str, sanitized_html: str, original_sha256: str, sanitized_sha256: str, validation_report: dict[str, Any], created_by: str) -> dict[str, Any]:
        chapter = self.chapters.get(chapter_id)
        if not chapter or self.course_versions[chapter["course_version_id"]]["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")
        if any(item["chapter_id"] == chapter_id and item["sequence_no"] == sequence_no for item in self.content_items.values()):
            raise ValueError("Content sequence already exists")
        item = {"id": new_id("content"), "chapter_id": chapter_id, "content_type": "html", "title": title, "sequence_no": sequence_no, "source_filename": source_filename, "sanitized_html": sanitized_html, "original_sha256": original_sha256, "sanitized_sha256": sanitized_sha256, "validation_report": validation_report}
        self.content_items[item["id"]] = item
        return item

    def import_ppt_course(self, course_version_id: str, chapter_code: str, chapter_title: str,
                          source_filename: str, slides: list[dict[str, Any]], created_by: str) -> dict[str, Any]:
        """Create one chapter and one HTML learning item per imported slide."""
        version = self.course_versions.get(course_version_id)
        if not version or version["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")
        sequence_no = max((item["sequence_no"] for item in self.list_chapters(course_version_id)), default=0) + 1
        chapter = self.create_chapter(course_version_id, chapter_code, chapter_title, sequence_no, "按幻灯片顺序学习课程内容")
        created: list[dict[str, Any]] = []
        try:
            for index, slide in enumerate(slides, start=1):
                created.append(self.create_html_content(
                    chapter["id"], slide["title"], index, source_filename,
                    slide["html"], slide["original_sha256"], slide["sanitized_sha256"],
                    slide["validation_report"], created_by,
                ))
        except Exception:
            # The in-memory store is only a test repository; avoid leaving a
            # half-imported chapter when a fixture is intentionally invalid.
            self.chapters.pop(chapter["id"], None)
            for item in created:
                self.content_items.pop(item["id"], None)
            raise
        return {
            "course_version_id": course_version_id,
            "chapter_id": chapter["id"],
            "chapter_title": chapter_title,
            "slides_imported": len(created),
            "content_ids": [item["id"] for item in created],
            "warnings": [],
        }

    def import_pdf_course(self, course_version_id: str, chapter_code: str, chapter_title: str,
                          source_filename: str, pdf_ref: str, pdf_byte_size: int,
                          page_count: int, pdf_sha256: str, created_by: str) -> dict[str, Any]:
        version = self.course_versions.get(course_version_id)
        if not version or version["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")
        chapter_sequence = max((item["sequence_no"] for item in self.list_chapters(course_version_id)), default=0) + 1
        chapter = self.create_chapter(course_version_id, chapter_code, chapter_title, chapter_sequence, "按 PDF 页面顺序学习课程内容")
        file_id = new_id("file")
        self.content_documents[file_id] = {"id": file_id, "document_ref": pdf_ref, "mime_type": "application/pdf", "byte_size": pdf_byte_size, "source_filename": source_filename, "owner_id": created_by}
        content_ids: list[str] = []
        for page_no in range(1, page_count + 1):
            content = {"id": new_id("content"), "chapter_id": chapter["id"], "content_type": "document", "title": f"第 {page_no} 页", "sequence_no": page_no, "source_filename": source_filename, "sanitized_html": f"<p>PDF 第 {page_no} 页</p>", "original_sha256": pdf_sha256, "sanitized_sha256": pdf_sha256, "validation_report": {"source_type": "pdf", "page_no": page_no, "page_count": page_count}, "document_file_id": file_id, "document_page_no": page_no, "document_page_count": page_count}
            if any(item["chapter_id"] == chapter["id"] and item["sequence_no"] == page_no for item in self.content_items.values()):
                raise ValueError("Content sequence already exists")
            self.content_items[content["id"]] = content
            content_ids.append(content["id"])
        return {"course_version_id": course_version_id, "chapter_id": chapter["id"], "chapter_title": chapter_title, "pages_imported": len(content_ids), "content_ids": content_ids, "warnings": []}

    def create_content_asset(self, content_id: str, asset_ref: str, mime_type: str,
                             byte_size: int, source_filename: str, asset_role: str,
                             created_by: str) -> dict[str, Any]:
        content = self.content_items.get(content_id)
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        version = self.course_versions.get(chapter["course_version_id"]) if chapter else None
        if not content or not version or version["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")
        item = {"id": new_id("asset"), "content_item_id": content_id, "asset_role": asset_role, "original_filename": source_filename, "asset_ref": asset_ref, "mime_type": mime_type, "byte_size": byte_size, "owner_id": created_by}
        self.content_assets[item["id"]] = item
        return dict(item)

    def list_content_assets(self, content_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.content_assets.values() if item["content_item_id"] == content_id]

    def get_content_asset(self, asset_id: str) -> dict[str, Any] | None:
        item = self.content_assets.get(asset_id)
        return dict(item) if item else None

    def get_learner_content_asset(self, asset_id: str, user_id: str) -> dict[str, Any] | None:
        item = self.content_assets.get(asset_id)
        if not item:
            return None
        content = self.content_items.get(item["content_item_id"])
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        if not chapter:
            return None
        allowed = any((task := self.get_practice_task(assignment.task_id)) and task.course_version_id == self.chapters[chapter["id"]]["course_version_id"] and task.status != "draft" for assignment in self.practice_assignments.values() if assignment.user_id == user_id)
        return dict(item) if allowed else None

    def get_learner_document(self, content_id: str, user_id: str) -> dict[str, Any] | None:
        content = self.content_items.get(content_id)
        if not content or content.get("content_type") != "document":
            return None
        asset = self.content_documents.get(content.get("document_file_id"))
        if not asset:
            return None
        chapter = self.chapters.get(content["chapter_id"])
        allowed = any((task := self.get_practice_task(assignment.task_id)) and task.course_version_id == chapter["course_version_id"] and task.status != "draft" for assignment in self.practice_assignments.values() if assignment.user_id == user_id)
        if not allowed:
            return None
        return {**asset, "content_item_id": content_id, "document_page_no": content.get("document_page_no"), "document_page_count": content.get("document_page_count")}

    def get_content_item(self, content_id: str) -> dict[str, Any] | None:
        item = self.content_items.get(content_id)
        return dict(item) if item else None

    def list_content_interactions(self, content_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        items = [dict(item) for item in self.content_interactions.values() if item["content_item_id"] == content_id and (include_archived or item["status"] != "archived")]
        return sorted(items, key=lambda item: (item["sequence_no"], item["created_at"]))

    def _content_is_draft(self, content_id: str) -> bool:
        content = self.content_items.get(content_id)
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        version = self.course_versions.get(chapter["course_version_id"]) if chapter else None
        return bool(version and version["status"] == "draft")

    def create_content_interaction(self, content_id: str, data: dict[str, Any], created_by: str) -> dict[str, Any]:
        if content_id not in self.content_items or not self._content_is_draft(content_id):
            raise ValueError("Only a draft course version can be edited")
        if data["interaction_type"] in {"choice", "hotspot"} and (len(data.get("options", [])) < 2 or data.get("correct_answer") not in data.get("options", [])):
            raise ValueError("选择或点击互动至少需要两个选项，且正确答案必须是选项之一")
        if data["interaction_type"] == "fill_blank" and not (data.get("accepted_answers") or str(data.get("correct_answer", "")).strip()):
            raise ValueError("填空互动至少需要一个可接受答案")
        now = self.now()
        item = {"id": new_id("interaction"), "content_item_id": content_id, "interaction_type": data["interaction_type"], "title": data.get("title", "互动练习"), "prompt": data["prompt"], "options": list(data.get("options", [])), "correct_answer": data.get("correct_answer", ""), "accepted_answers": list(data.get("accepted_answers", [])), "feedback_correct": data.get("feedback_correct", "回答正确，继续保持。"), "feedback_incorrect": data.get("feedback_incorrect", "再看一下课程内容，再试一次。"), "required": bool(data.get("required", True)), "sequence_no": int(data.get("sequence_no", 1)), "status": "draft", "version_no": 1, "created_by": created_by, "created_at": now, "updated_at": now}
        self.content_interactions[item["id"]] = item
        return dict(item)

    def update_content_interaction(self, interaction_id: str, data: dict[str, Any], updated_by: str) -> dict[str, Any] | None:
        item = self.content_interactions.get(interaction_id)
        if not item:
            return None
        if not self._content_is_draft(item["content_item_id"]):
            raise ValueError("Only a draft course version can be edited")
        merged = {**item, **data}
        if merged["interaction_type"] in {"choice", "hotspot"} and (len(merged.get("options", [])) < 2 or merged.get("correct_answer") not in merged.get("options", [])):
            raise ValueError("选择或点击互动至少需要两个选项，且正确答案必须是选项之一")
        if merged["interaction_type"] == "fill_blank" and not (merged.get("accepted_answers") or str(merged.get("correct_answer", "")).strip()):
            raise ValueError("填空互动至少需要一个可接受答案")
        for key in ("interaction_type", "title", "prompt", "options", "correct_answer", "accepted_answers", "feedback_correct", "feedback_incorrect", "required", "sequence_no"):
            if key in data:
                item[key] = data[key]
        item["version_no"] += 1
        item["updated_at"] = self.now()
        item["updated_by"] = updated_by
        return dict(item)

    def archive_content_interaction(self, interaction_id: str, archived_by: str) -> dict[str, Any] | None:
        item = self.content_interactions.get(interaction_id)
        if not item:
            return None
        if not self._content_is_draft(item["content_item_id"]):
            raise ValueError("Only a draft course version can be edited")
        item["status"] = "archived"
        item["updated_at"] = self.now()
        item["updated_by"] = archived_by
        return dict(item)

    def _learner_interaction(self, item: dict[str, Any], assignment_id: str) -> dict[str, Any]:
        attempts = [attempt for attempt in self.interaction_attempts if attempt["assignment_id"] == assignment_id and attempt["interaction_id"] == item["id"]]
        return {key: item[key] for key in ("id", "content_item_id", "interaction_type", "title", "prompt", "options", "required", "sequence_no")} | {"completed": any(attempt["is_correct"] for attempt in attempts), "attempt_count": len(attempts)}

    def submit_interaction_answer(self, assignment_id: str, user_id: str, content_item_id: str, interaction_id: str, answer: str) -> dict[str, Any]:
        assignment = self.get_practice_assignment(assignment_id, user_id)
        interaction = self.content_interactions.get(interaction_id)
        if not assignment or not interaction or interaction["content_item_id"] != content_item_id or interaction["status"] != "published":
            raise ValueError("互动内容不存在或不属于当前练习")
        workspace = self.learner_practice_workspace(assignment_id, user_id)
        if not workspace or content_item_id not in {item["id"] for item in workspace["contents"]}:
            raise ValueError("Content does not belong to this assignment")
        normalized = str(answer or "").strip().casefold()
        accepted = [str(value).strip().casefold() for value in interaction.get("accepted_answers", [])]
        correct = str(interaction.get("correct_answer", "")).strip().casefold()
        is_correct = normalized == correct if interaction["interaction_type"] in {"choice", "hotspot"} else normalized in set(accepted + ([correct] if correct else []))
        feedback = interaction["feedback_correct"] if is_correct else interaction["feedback_incorrect"]
        self.interaction_attempts.append({"id": new_id("ia"), "assignment_id": assignment_id, "user_id": user_id, "content_item_id": content_item_id, "interaction_id": interaction_id, "answer": answer, "is_correct": is_correct, "score": 1.0 if is_correct else 0.0, "feedback": feedback, "created_at": self.now()})
        attempts = [attempt for attempt in self.interaction_attempts if attempt["assignment_id"] == assignment_id and attempt["interaction_id"] == interaction_id]
        return {"interaction_id": interaction_id, "assignment_id": assignment_id, "content_item_id": content_item_id, "is_correct": is_correct, "score": 1.0 if is_correct else 0.0, "feedback": feedback, "completed": any(attempt["is_correct"] for attempt in attempts), "attempt_count": len(attempts), "answer": answer}

    def get_course_standard(self, content_id: str) -> dict[str, Any] | None:
        history = self.course_standards.get(content_id, [])
        return dict(history[-1]) if history else None

    def save_course_standard(self, content_id: str, data: dict[str, Any], created_by: str) -> dict[str, Any]:
        content = self.content_items.get(content_id)
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        version = self.course_versions.get(chapter["course_version_id"]) if chapter else None
        if not content or not version or version["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")
        previous = self.get_course_standard(content_id)
        item = {
            "id": new_id("standard"), "content_item_id": content_id,
            "standard_text": data["standard_text"],
            "stress_rules": data.get("stress_rules", ""),
            "pronunciation_notes": data.get("pronunciation_notes", ""),
            "pause_rules": data.get("pause_rules", ""),
            "tone_requirements": data.get("tone_requirements", ""),
            "rule_version": data.get("rule_version", "1.0"),
            "change_summary": data.get("change_summary", ""),
            "standard_audio_file_id": previous.get("standard_audio_file_id") if previous else None,
            "standard_audio_filename": previous.get("standard_audio_filename") if previous else None,
            "standard_audio_url": previous.get("standard_audio_url") if previous else None,
            "created_at": self.now(), "created_by": created_by,
        }
        self.course_standards.setdefault(content_id, []).append(item)
        return dict(item)

    def attach_course_standard_audio(self, content_id: str, standard_id: str, audio_ref: str,
                                     mime_type: str, byte_size: int, source_filename: str,
                                     created_by: str) -> dict[str, Any]:
        standard = next((item for item in self.course_standards.get(content_id, []) if item["id"] == standard_id), None)
        if not standard:
            raise ValueError("Course standard not found")
        content = self.content_items.get(content_id)
        chapter = self.chapters.get(content["chapter_id"]) if content else None
        version = self.course_versions.get(chapter["course_version_id"]) if chapter else None
        if not version or version["status"] != "draft":
            raise ValueError("Only a draft course version can be edited")
        file_id = new_id("file")
        self.standard_audio_files[file_id] = {
            "id": file_id, "audio_ref": audio_ref, "mime_type": mime_type,
            "byte_size": byte_size, "owner_id": created_by, "source_filename": source_filename,
        }
        standard.update({
            "standard_audio_file_id": file_id,
            "standard_audio_filename": source_filename,
            "standard_audio_url": f"/api/v1/cabinlingo/course-standard-audio/{file_id}",
        })
        return dict(standard)

    def get_course_standard_audio(self, file_id: str) -> dict[str, Any] | None:
        item = self.standard_audio_files.get(file_id)
        return dict(item) if item else None

    def publish_course_version(self, course_version_id: str, published_by: str) -> dict[str, Any]:
        version = self.course_versions.get(course_version_id)
        if not version:
            raise ValueError("Course version not found")
        if version["status"] == "published":
            return next(item for item in self.list_course_versions(version["course_id"]) if item["id"] == course_version_id)
        if version["status"] != "draft":
            raise ValueError("Only a draft course version can be published")
        chapters = self.list_chapters(course_version_id)
        if not chapters or not any(self.list_content_items(chapter["id"]) for chapter in chapters):
            raise ValueError("A course version needs at least one chapter and one content item")
        for item in self.course_versions.values():
            if item["course_id"] == version["course_id"] and item["status"] == "published":
                item["status"] = "archived"
        version["status"] = "published"
        version["published_at"] = self.now()
        self.courses[version["course_id"]]["status"] = "published"
        for chapter in chapters:
            for content in self.list_content_items(chapter["id"]):
                for interaction in self.content_interactions.values():
                    if interaction["content_item_id"] == content["id"] and interaction["status"] == "draft":
                        interaction["status"] = "published"
                        interaction["updated_at"] = self.now()
        return next(item for item in self.list_course_versions(version["course_id"]) if item["id"] == course_version_id)

    @staticmethod
    def _course_v23_validation(item: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        is_expression_video = item.get("course_kind") == "expression_skill" and item.get("content_mode") == "video"
        fields = (("title_zh", "课程名称"),) if is_expression_video else (("title_zh", "课程名称"), ("summary", "课程摘要"), ("delivery_pace", "播音速度"))
        for field, label in fields:
            if not str(item.get(field) or "").strip():
                errors.append(f"{label}不能为空")
        if not is_expression_video:
            expected = {"zh", "en"} if item.get("language") == "bilingual" else {item.get("language")}
            annotated = item.get("annotated_scripts") or {}
            for language in expected:
                if language and not str(annotated.get(language) or "").strip():
                    errors.append(f"缺少 {language} 专业标注原文")
            has_complete_audio = bool(item.get("audio_file_id"))
            has_zh_audio = bool(item.get("audio_zh_file_id"))
            has_en_audio = bool(item.get("audio_en_file_id"))
            language = item.get("language")
            if language == "bilingual" and not has_complete_audio and not (has_zh_audio and has_en_audio):
                errors.append("双语课程需上传完整示范音频，或同时上传中文和英文标准音频")
            elif language == "zh" and not (has_complete_audio or has_zh_audio):
                errors.append("缺少中文标准音频")
            elif language == "en" and not (has_complete_audio or has_en_audio):
                errors.append("缺少英文标准音频")
            if not item.get("mistake_words"):
                errors.append("至少需要一条易错词")
        if item.get("content_mode") == "video" and not (item.get("video_file_id") or item.get("cos_video_key")):
            errors.append("缺少课程视频")
        if item.get("publish_scope") == "classes" and not item.get("publish_class_ids"):
            errors.append("指定班级发布时至少选择一个班级")
        return errors

    def _course_v23_record(self, version_id: str) -> dict[str, Any] | None:
        detail = self.course_details.get(version_id)
        version = self.course_versions.get(version_id)
        course = self.courses.get(version["course_id"]) if version else None
        if not detail or not version or not course:
            return None
        item = {
            "id": course["id"], "course_id": course["code"], "course_version_id": version_id,
            "content_item_id": detail["content_item_id"], "code": course["code"],
            "title_zh": course["title"], "title_en": detail.get("title_en", ""),
            "category": course["category"], "summary": detail.get("summary", ""),
            "language": detail.get("language", "bilingual"), "version_label": version["version_label"],
            "status": version["status"],
            "updated_at": detail.get("updated_at"),
            "course_kind": detail.get("course_kind", "lesson"),
            "content_mode": detail.get("content_mode", "audio_text"),
            "training_enabled": bool(detail.get("training_enabled", True)),
            "content_config": dict(detail.get("content_config") or {}),
            "explanation": detail.get("explanation", ""),
            "annotated_scripts": dict(detail.get("annotated_scripts") or {}),
            "delivery_tone": list(detail.get("delivery_tone") or []),
            "delivery_pace": detail.get("delivery_pace", ""),
            "delivery_rhythm": list(detail.get("delivery_rhythm") or []),
            "pronunciation_notes": detail.get("pronunciation_notes", ""),
            "mistake_words": list(detail.get("mistake_words") or []),
            "cover_filename": detail.get("cover_filename"),
            "video_filename": detail.get("video_filename"),
            "cos_video_key": detail.get("cos_video_key"),
            "cos_video_filename": detail.get("cos_video_filename"),
            "cos_video_size": detail.get("cos_video_size"),
            "cos_video_etag": detail.get("cos_video_etag"),
            "sort_order": int(detail.get("sort_order") or 0),
            "publish_scope": detail.get("publish_scope", "all_authorized"),
            "publish_class_ids": list(detail.get("publish_class_ids") or []),
            "audio_filename": detail.get("audio_filename"),
            "published_at": version.get("published_at"),
        }
        for role in ("cover", "video", "audio", "audio_zh", "audio_en"):
            file_id = detail.get(f"{role}_file_id")
            item[f"{role}_url"] = f"/api/v1/cabinlingo/course-v23-media/{file_id}" if file_id else None
            item[f"{role}_filename"] = detail.get(f"{role}_filename")
        item["audio_tracks"] = [
            {"role": role, "label": label, "language": language, "filename": item.get(f"{role}_filename") or "", "url": item[f"{role}_url"]}
            for role, label, language in (
                ("audio", "完整示范音频", "bilingual"),
                ("audio_zh", "中文标准音频", "zh"),
                ("audio_en", "英文标准音频", "en"),
            ) if item.get(f"{role}_url")
        ]
        item["validation_errors"] = self._course_v23_validation(item | {
            "audio_file_id": detail.get("audio_file_id"),
            "audio_zh_file_id": detail.get("audio_zh_file_id"),
            "audio_en_file_id": detail.get("audio_en_file_id"),
            "video_file_id": detail.get("video_file_id"),
        })
        return item

    def create_course_v23_draft(self, data: dict[str, Any], media_records: list[dict[str, Any]],
                                created_by: str, batch_id: str | None = None) -> dict[str, Any]:
        course = self.create_course(data["course_id"], data["title_zh"], data["summary"], data["category"], data.get("organization_id"), created_by)
        try:
            version = self.create_course_version(course["id"], data.get("version_label", "V1.0"), "Course V2.3 draft", created_by)
            chapter = self.create_chapter(version["id"], "COURSE-V23", data["title_zh"], 1, data.get("explanation", ""))
            standard_text = str((data.get("annotated_scripts") or {}).get("zh") or (data.get("annotated_scripts") or {}).get("en") or "")
            content = self.create_html_content(chapter["id"], data["title_zh"], 1, f"{data['course_id']}.html", f"<p>{escape(standard_text)}</p>", "", "", {"source": "course_v23"}, created_by)
            self.save_course_standard(content["id"], {
                "standard_text": standard_text, "stress_rules": "按专业标注原文中的强调标记朗读",
                "pronunciation_notes": data.get("pronunciation_notes", ""), "pause_rules": "短停 /；长停 //",
                "tone_requirements": "、".join(data.get("delivery_tone") or []), "rule_version": "2.3",
                "change_summary": "Course V2.3 structured draft",
            }, created_by)
            detail = {**data, "content_item_id": content["id"], "source_import_batch_id": batch_id, "updated_at": self.now()}
            for media in media_records:
                file_id = new_id("file")
                self.course_v23_files[file_id] = {"id": file_id, **media, "owner_id": created_by}
                detail[f"{media['role']}_file_id"] = file_id
                detail[f"{media['role']}_filename"] = media["filename"]
            preferred_role = "audio_en" if data.get("language") == "en" else "audio_zh" if data.get("language") == "zh" else "audio"
            selected_role = preferred_role if detail.get(f"{preferred_role}_file_id") else "audio" if detail.get("audio_file_id") else "audio_zh" if detail.get("audio_zh_file_id") else "audio_en"
            selected_file_id = detail.get(f"{selected_role}_file_id")
            standard = self.get_course_standard(content["id"])
            if standard and selected_file_id:
                standard.update({"standard_audio_file_id": selected_file_id, "standard_audio_filename": detail.get(f"{selected_role}_filename"), "standard_audio_url": f"/api/v1/cabinlingo/course-v23-media/{selected_file_id}"})
            self.course_details[version["id"]] = detail
            return self._course_v23_record(version["id"]) or {}
        except Exception:
            self.courses.pop(course["id"], None)
            raise

    def update_course_v23_draft(self, version_id: str, data: dict[str, Any], media_records: list[dict[str, Any]],
                                updated_by: str, expected_updated_at: str | None = None) -> dict[str, Any]:
        detail = self.course_details.get(version_id)
        version = self.course_versions.get(version_id)
        course = self.courses.get(version["course_id"]) if version else None
        if not detail or not version or not course:
            raise ValueError("Course V2.3 draft not found")
        if version["status"] != "draft":
            raise ValueError("已发布课程不可直接修改，请创建新版本")
        if expected_updated_at and detail.get("updated_at"):
            try:
                expected_timestamp = datetime.fromisoformat(expected_updated_at.replace("Z", "+00:00"))
            except (AttributeError, ValueError) as exc:
                raise ValueError("课程草稿时间戳无效，请刷新后重试") from exc
            if detail["updated_at"] != expected_timestamp:
                raise ValueError("课程草稿已被其他管理员修改，请刷新后重试")
        if data["course_id"].lower() != str(course["code"]).lower():
            raise ValueError("课程 ID 创建后不可修改")

        course.update({
            "title": data["title_zh"], "description": data["summary"],
            "category": data["category"], "organization_id": data.get("organization_id"),
        })
        version["version_label"] = data.get("version_label", version["version_label"])
        detail.update({**data, "content_item_id": detail["content_item_id"], "updated_at": self.now()})
        content = self.content_items.get(detail["content_item_id"])
        if content:
            standard_text = str((data.get("annotated_scripts") or {}).get("zh") or (data.get("annotated_scripts") or {}).get("en") or "")
            content.update({"title": data["title_zh"], "sanitized_html": f"<p>{escape(standard_text)}</p>"})
            self.save_course_standard(content["id"], {
                "standard_text": standard_text, "stress_rules": "按专业标注原文中的强调标记朗读",
                "pronunciation_notes": data.get("pronunciation_notes", ""), "pause_rules": "短停 /；长停 //",
                "tone_requirements": "、".join(data.get("delivery_tone") or []), "rule_version": "2.3",
                "change_summary": "Course content draft updated",
            }, updated_by)
        for media in media_records:
            role = media["role"]
            file_id = new_id("file")
            self.course_v23_files[file_id] = {"id": file_id, **media, "owner_id": updated_by}
            detail[f"{role}_file_id"] = file_id
            detail[f"{role}_filename"] = media["filename"]
        preferred_role = "audio_en" if data.get("language") == "en" else "audio_zh" if data.get("language") == "zh" else "audio"
        selected_role = preferred_role if detail.get(f"{preferred_role}_file_id") else "audio" if detail.get("audio_file_id") else "audio_zh" if detail.get("audio_zh_file_id") else "audio_en"
        selected_file_id = detail.get(f"{selected_role}_file_id")
        standard = self.get_course_standard(content["id"]) if content else None
        if standard and selected_file_id:
            standard.update({"standard_audio_file_id": selected_file_id, "standard_audio_filename": detail.get(f"{selected_role}_filename"), "standard_audio_url": f"/api/v1/cabinlingo/course-v23-media/{selected_file_id}"})
        return self._course_v23_record(version_id) or {}

    def list_course_v23(self) -> list[dict[str, Any]]:
        items = [self._course_v23_record(version_id) for version_id in self.course_details]
        return [item for item in items if item]

    def list_published_course_v23(self, user_id: str | None = None) -> list[dict[str, Any]]:
        return [item for item in self.list_course_v23() if item["status"] == "published"]

    def get_course_v23(self, version_id: str, published_only: bool = False) -> dict[str, Any] | None:
        item = self._course_v23_record(version_id)
        if not item or (published_only and item["status"] != "published"):
            return None
        return item

    def get_published_course_v23_for_user(self, version_id: str, user_id: str) -> dict[str, Any] | None:
        item = self.get_course_v23(version_id, published_only=True)
        if not item or item.get("course_status", "published") != "published":
            return None
        if item.get("publish_scope") == "classes":
            memberships = getattr(self, "class_memberships", {})
            allowed = {str(value) for value in item.get("publish_class_ids") or []}
            if not any(str(getattr(member, "class_id", member.get("class_id") if isinstance(member, dict) else "")) in allowed
                       and str(getattr(member, "user_id", member.get("user_id") if isinstance(member, dict) else "")) == user_id
                       for member in memberships.values()):
                return None
        return item

    def next_available_course_code(self, requested: str, organization_id: str | None) -> str:
        base = requested.strip()[:72]
        existing = {
            course.code.lower()
            for course in self.courses.values()
            if course.organization_id == organization_id
        }
        if base.lower() not in existing:
            return base
        suffix = 2
        while f"{base}-{suffix}".lower() in existing:
            suffix += 1
        return f"{base}-{suffix}"

    def get_course_v23_media(self, file_id: str) -> dict[str, Any] | None:
        item = self.course_v23_files.get(file_id)
        return dict(item) if item else None

    def user_can_access_course_v23_media(self, file_id: str, user_id: str) -> bool:
        for version_id, detail in self.course_details.items():
            if file_id not in {detail.get(f"{role}_file_id") for role in ("cover", "video", "audio", "audio_zh", "audio_zh_2", "audio_en", "audio_en_2")}:
                continue
            if self.get_published_course_v23_for_user(version_id, user_id):
                return True
        return False

    def start_course_import_batch(self, excel_filename: str, media_zip_filename: str | None, created_by: str) -> str:
        batch_id = new_id("course-import")
        self.course_import_batches[batch_id] = {
            "id": batch_id, "excel_filename": excel_filename, "media_zip_filename": media_zip_filename,
            "status": "processing", "created_by": created_by, "created_at": self.now(),
        }
        return batch_id

    def finish_course_import_batch(self, batch_id: str, total: int, created: int, errors: list[dict[str, Any]]) -> None:
        batch = self.course_import_batches.get(batch_id)
        if not batch:
            return
        batch.update({
            "status": "completed" if not errors else "completed_with_errors" if created else "failed",
            "row_count": total, "draft_count": created, "error_count": len(errors),
            "errors": list(errors), "completed_at": self.now(),
        })

    def publish_course_v23(self, version_id: str, published_by: str) -> dict[str, Any]:
        item = self._course_v23_record(version_id)
        if not item:
            raise ValueError("Course V2.3 draft not found")
        if item["validation_errors"]:
            raise ValueError("；".join(item["validation_errors"]))
        self.publish_course_version(version_id, published_by)
        return self._course_v23_record(version_id) or {}

    def list_learner_tasks(self, user_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for assignment in self.list_practice_assignments(user_id):
            task = self.practice_tasks.get(assignment.task_id)
            if not task or task.deleted_at or task.status == "draft":
                continue
            version = self.course_versions.get(task.course_version_id or "")
            course = self.courses.get(version["course_id"]) if version else None
            chapter_ids = {item["id"] for item in self.chapters.values() if version and item["course_version_id"] == version["id"]}
            content_ids = [item["id"] for item in self.content_items.values() if item["chapter_id"] in chapter_ids]
            details = [item for item in self.learner_attempt_details.values() if item["assignment_id"] == assignment.id]
            minimum = int(task.completion_rule.get("min_attempts", 1))
            def content_completed(content_id: str) -> bool:
                is_card = bool(self.content_items[content_id].get('learning_card_id'))
                if is_card and (assignment.id, content_id) not in self.learning_card_reads:
                    return False
                if not is_card and sum(item["content_item_id"] == content_id for item in details) < minimum:
                    return False
                required = [interaction for interaction in self.content_interactions.values() if interaction["content_item_id"] == content_id and interaction["status"] == "published" and interaction["required"]]
                return all(any(attempt["interaction_id"] == interaction["id"] and attempt["is_correct"] for attempt in self.interaction_attempts if attempt["assignment_id"] == assignment.id) for interaction in required)
            completed = sum(content_completed(content_id) for content_id in content_ids)
            locked = not self.is_task_unlocked("practice", task.id, user_id)
            rows.append({"assignment_id": assignment.id, "task_id": task.id, "task_type": "practice", "title": task.title, "status": assignment.status, "due_at": task.due_at, "week_no": task.week_no, "locked": locked, "unlock_reason": "完成上一周任务后自动解锁" if locked else None, "course_version_id": task.course_version_id, "course_title": course["title"] if course else "广播词练习", "version_label": version["version_label"] if version else None, "total_items": len(content_ids), "completed_items": completed, "attempt_count": len(details), "progress_percent": round(completed / max(len(content_ids), 1) * 100), "next_content_item_id": next((content_id for content_id in content_ids if not content_completed(content_id)), None)})
        for assignment in self.list_exam_assignments(user_id):
            task = self.exam_tasks.get(assignment.task_id)
            if not task or task.deleted_at or task.status == "draft":
                continue
            version = self.course_versions.get(task.course_version_id or "")
            course = self.courses.get(version["course_id"]) if version else None
            locked = not self.is_task_unlocked("exam", task.id, user_id)
            rows.append({"assignment_id": assignment.id, "task_id": task.id, "task_type": "exam", "title": task.title, "status": assignment.status, "due_at": task.due_at, "week_no": task.week_no, "locked": locked, "unlock_reason": "完成上一周任务后自动解锁" if locked else None, "course_version_id": task.course_version_id, "course_title": course["title"] if course else "广播词考试", "version_label": version["version_label"] if version else None, "total_items": 1, "completed_items": 1 if assignment.status in {"submitted", "graded", "published"} else 0, "attempt_count": len(assignment.submitted_recordings), "progress_percent": 100 if assignment.status in {"submitted", "graded", "published"} else 0, "next_content_item_id": None})
        return rows

    def list_assignment_learning_cards(self, assignment_id: str, user_id: str):
        assignment = self.get_practice_assignment(assignment_id, user_id)
        task = self.get_practice_task(assignment.task_id) if assignment else None
        if not assignment:
            assignment = self.get_exam_assignment(assignment_id, user_id)
            task = self.get_exam_task(assignment.task_id) if assignment else None
        if not task or task.status == 'draft':
            return None
        return [dict(item) for chapter in self.list_chapters(task.course_version_id or '')
                for item in self.list_content_items(chapter['id']) if item.get('learning_card_id')]

    def mark_learning_card_read(self, content_id: str, assignment_id: str, user_id: str):
        assignment = self.get_practice_assignment(assignment_id, user_id)
        task = self.get_practice_task(assignment.task_id) if assignment else None
        if not task or task.status != 'published' or not self.get_learner_learning_card(content_id, assignment_id, user_id):
            raise ValueError('学习卡片不属于当前已发布练习任务')
        self.learning_card_reads.add((assignment_id, content_id))
        progress = next(row for row in self.list_learner_tasks(user_id) if row['assignment_id'] == assignment_id)
        assignment.status = 'completed' if progress['progress_percent'] == 100 else 'in_progress'
        return {'content_item_id': content_id, 'read': True, 'progress_percent': progress['progress_percent']}

    def learner_home(self, user_id: str) -> dict[str, Any]:
        tasks = self.list_learner_tasks(user_id)
        active = [item for item in tasks if item["status"] not in {"completed", "published", "closed"} and not item["locked"]]
        return {"practice_count": sum(item["task_type"] == "practice" and item["status"] != "completed" for item in tasks), "exam_count": sum(item["task_type"] == "exam" and item["status"] not in {"submitted", "graded", "published"} for item in tasks), "completed_count": sum(item["progress_percent"] == 100 for item in tasks), "total_attempts": sum(item["attempt_count"] for item in tasks), "pending_feedback": sum(item["status"] == "published" for item in self.teacher_feedback), "next_task": active[0] if active else None}

    def learner_practice_workspace(self, assignment_id: str, user_id: str) -> dict[str, Any] | None:
        assignment = self.get_practice_assignment(assignment_id, user_id)
        if not assignment:
            return None
        task = self.get_practice_task(assignment.task_id)
        if not task or task.status == "draft" or not task.course_version_id:
            return None
        version = self.course_versions.get(task.course_version_id)
        if not version:
            return None
        course = self.courses[version["course_id"]]
        minimum = int(task.completion_rule.get("min_attempts", 1))
        contents: list[dict[str, Any]] = []
        for chapter in self.list_chapters(version["id"]):
            for item in self.list_content_items(chapter["id"]):
                attempts = [detail for detail in self.learner_attempt_details.values() if detail["assignment_id"] == assignment_id and detail["content_item_id"] == item["id"]]
                latest = attempts[-1] if attempts else None
                from .html_sanitizer import extract_text
                standard = self.get_course_standard(item["id"]) or {}
                interactions = [self._learner_interaction(interaction, assignment_id) for interaction in self.list_content_interactions(item["id"]) if interaction["status"] == "published"]
                required_interactions = sum(interaction["required"] for interaction in interactions)
                completed_interactions = sum(interaction["completed"] for interaction in interactions if interaction["required"])
                assets = [{**asset, "url": f"/api/v1/cabinlingo/learner/content-assets/{asset['id']}"} for asset in self.list_content_assets(item["id"])]
                document_url = f"/api/v1/cabinlingo/learner/course-documents/{item['id']}" if item.get("content_type") == "document" else None
                contents.append({"id": item["id"], "chapter_id": chapter["id"], "chapter_title": chapter["title"], "chapter_sequence": chapter["sequence_no"], "title": item["title"], "sequence_no": item["sequence_no"], "content_type": item.get("content_type", "html"), "learning_card_id": item.get("learning_card_id"), "sanitized_html": item.get("sanitized_html") or "", "reference_text": standard.get("standard_text") or extract_text(item.get("sanitized_html") or ""), "document_url": document_url, "document_page_no": item.get("document_page_no"), "document_page_count": item.get("document_page_count"), "assets": assets, "standard_audio_url": standard.get("standard_audio_url"), "stress_rules": standard.get("stress_rules", ""), "pronunciation_notes": standard.get("pronunciation_notes", ""), "pause_rules": standard.get("pause_rules", ""), "tone_requirements": standard.get("tone_requirements", ""), "rule_version": standard.get("rule_version"), "attempt_count": len(attempts), "latest_attempt_id": latest["attempt_id"] if latest else None, "latest_ai_status": latest["ai_status"] if latest else None, "interactions": interactions, "required_interactions": required_interactions, "completed_interactions": completed_interactions, "completed": (((assignment.id, item["id"]) in self.learning_card_reads) if item.get("learning_card_id") else len(attempts) >= minimum) and completed_interactions >= required_interactions})
        completed = sum(item["completed"] for item in contents)
        return {"assignment_id": assignment.id, "task_id": task.id, "task_title": task.title, "assignment_status": assignment.status, "course_title": course["title"], "version_label": version["version_label"], "minimum_attempts": minimum, "progress_percent": round(completed / max(len(contents), 1) * 100), "contents": contents}

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
        assignment = self.get_practice_assignment(assignment_id, user_id)
        recording = self.recordings.get(recording_id)
        if not assignment or not recording or recording["assignment_id"] != assignment_id:
            raise ValueError("Assignment or recording not found")
        workspace = self.learner_practice_workspace(assignment_id, user_id)
        if not workspace or content_item_id not in {item["id"] for item in workspace["contents"]}:
            raise ValueError("Content does not belong to this assignment")
        attempt_no = self.practice_attempt_count(assignment_id) + 1
        attempt = PracticeAttempt(new_id("pat"), assignment_id, content_item_id, recording["audio_ref"], attempt_no, self.now())
        self.practice_attempts[attempt.id] = attempt
        assignment.attempt_ids.append(attempt.id)
        if reference_text is None:
            from .html_sanitizer import extract_text
            standard = self.get_course_standard(content_item_id) or {}
            reference_text = standard.get("standard_text") or extract_text(self.content_items[content_item_id].get("sanitized_html") or "")
        feedback = collect_practice_feedback(ai_results, reference_text or "", recognized_text)
        detail = {
            "attempt_id": attempt.id,
            "assignment_id": assignment_id,
            "content_item_id": content_item_id,
            "content_title": self.content_items[content_item_id]["title"],
            "attempt_no": attempt_no,
            **feedback,
            "next_action": "review_feedback_and_retry" if feedback["issues"] else "continue_next_content",
            "recording_url": f"/api/v1/cabinlingo/learner/audio/{recording_id}",
            "correction_of_attempt_id": correction_of_attempt_id,
            "teacher_feedback": None,
            "created_at": attempt.created_at,
        }
        self.learner_attempt_details[attempt.id] = detail
        workspace = self.learner_practice_workspace(assignment_id, user_id)
        assignment.status = "completed" if workspace and workspace["progress_percent"] == 100 else "in_progress"
        self.growth_events.append({"learner_id": user_id, "event_type": "practice_corrected" if correction_of_attempt_id else "practice_submitted", "attempt_id": attempt.id, "created_at": attempt.created_at})
        return detail

    def list_learner_attempts(self, user_id: str) -> list[dict[str, Any]]:
        assignment_ids = {item.id for item in self.list_practice_assignments(user_id)}
        attempts = [dict(item) for item in self.learner_attempt_details.values() if item["assignment_id"] in assignment_ids]
        for item in attempts:
            item["issues"] = learner_visible_issues(item.get("issues"))
        return sorted(attempts, key=lambda item: item["created_at"], reverse=True)

    def get_learner_attempt(self, attempt_id: str, user_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_learner_attempts(user_id) if item["attempt_id"] == attempt_id), None)

    def get_learner_attempt_reanalysis_context(self, attempt_id: str, user_id: str) -> dict[str, Any] | None:
        detail = self.learner_attempt_details.get(attempt_id)
        attempt = self.practice_attempts.get(attempt_id)
        assignment = self.practice_assignments.get(attempt.assignment_id) if attempt else None
        if not detail or not attempt or not assignment or assignment.user_id != user_id:
            return None
        task = self.get_practice_task(assignment.task_id)
        if not task:
            return None
        content_id = detail["content_item_id"]
        content = self.content_items.get(content_id)
        if not content:
            return None
        from .html_sanitizer import extract_text
        standard = self.get_course_standard(content_id) or {}
        reference_text = standard.get("standard_text") or extract_text(content.get("sanitized_html") or "")
        if not reference_text:
            return None
        return {
            "audio_ref": attempt.audio_ref,
            "reference_text": reference_text,
            "recognized_text": detail.get("browser_transcript") or detail.get("recognized_text"),
        }

    def replace_learner_practice_analysis(
        self,
        attempt_id: str,
        user_id: str,
        ai_results: list[dict[str, Any]],
        recognized_text: str | None,
        reference_text: str,
    ) -> dict[str, Any]:
        context = self.get_learner_attempt_reanalysis_context(attempt_id, user_id)
        detail = self.learner_attempt_details.get(attempt_id)
        if not context or not detail:
            raise ValueError("Practice attempt or recording not found")
        feedback = collect_practice_feedback(ai_results, reference_text, recognized_text)
        detail.update({
            **feedback,
            "next_action": "review_feedback_and_retry" if feedback["issues"] else "continue_next_content",
        })
        attempt = self.practice_attempts.get(attempt_id)
        if attempt:
            attempt.ai_status = feedback["ai_status"]
        return dict(detail)

    def list_learner_feedback(self, user_id: str) -> list[dict[str, Any]]:
        def visible(item: dict[str, Any]) -> bool:
            if item.get("practice_attempt_id"):
                attempt = self.learner_attempt_details.get(item["practice_attempt_id"])
                assignment = self.practice_assignments.get(attempt["assignment_id"]) if attempt else None
                return bool(assignment and self.get_practice_task(assignment.task_id))
            assignment = self.exam_assignments.get(item.get("exam_assignment_id", ""))
            return bool(assignment and self.get_exam_task(assignment.task_id))
        return [dict(item) for item in self.teacher_feedback if item["learner_id"] == user_id and item["status"] in {"published", "acknowledged"} and visible(item)]

    def learner_growth_profile(self, user_id: str) -> dict[str, Any]:
        attempts = self.list_learner_attempts(user_id)
        tasks = self.list_learner_tasks(user_id)
        by_date: dict[str, dict[str, Any]] = {}
        issue_counts: dict[str, int] = {}
        for item in attempts:
            day = item["created_at"].date().isoformat()
            point = by_date.setdefault(day, {"date": day, "attempts": 0, "completed_tasks": 0, "average_score": None})
            point["attempts"] += 1
            for issue in item["issues"]:
                key = issue.get("dimension", "other")
                issue_counts[key] = issue_counts.get(key, 0) + 1
        return {"total_attempts": len(attempts), "completed_tasks": sum(item["progress_percent"] == 100 for item in tasks), "corrected_attempts": sum(bool(item["correction_of_attempt_id"]) for item in attempts), "feedback_count": len(self.list_learner_feedback(user_id)), "issue_counts": issue_counts, "trend": list(by_date.values())}

    def list_instructor_queue(self, review_type: str | None = None, review_status: str | None = None, class_id: str | None = None, instructor_id: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for attempt in self.learner_attempt_details.values():
            assignment = self.practice_assignments.get(attempt["assignment_id"])
            task = self.practice_tasks.get(assignment.task_id) if assignment else None
            if not assignment or not task or task.deleted_at:
                continue
            review = self.instructor_reviews.get(("practice", attempt["attempt_id"]))
            rows.append({"review_type": "practice", "target_id": attempt["attempt_id"], "assignment_id": assignment.id,
                         "task_id": task.id, "task_title": task.title, "learner_id": assignment.user_id,
                         "learner_name": assignment.user_id, "class_id": None, "class_name": None,
                         "content_title": attempt.get("content_title"), "submitted_at": attempt["created_at"],
                         "ai_status": attempt.get("ai_status", "pending_adapter"),
                         "review_status": review["status"] if review else "pending", "priority": "normal"})
        for assignment in self.exam_assignments.values():
            if assignment.status not in {"submitted", "graded", "published"}:
                continue
            task = self.exam_tasks.get(assignment.task_id)
            if not task or task.deleted_at:
                continue
            review = self.instructor_reviews.get(("exam", assignment.id))
            rows.append({"review_type": "exam", "target_id": assignment.id, "assignment_id": assignment.id,
                         "task_id": assignment.task_id, "task_title": task.title if task else "考试任务",
                         "learner_id": assignment.user_id, "learner_name": assignment.user_id, "class_id": None,
                         "class_name": None, "content_title": None, "submitted_at": assignment.submitted_at or self.now(),
                         "ai_status": "pending_adapter", "review_status": review["status"] if review else "pending", "priority": "normal"})
        return [item for item in rows if (not review_type or item["review_type"] == review_type) and (not review_status or item["review_status"] == review_status) and (not class_id or item["class_id"] == class_id)]

    def list_instructor_learners(self, instructor_id: str) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in self.list_instructor_queue(instructor_id=instructor_id):
            learner = grouped.setdefault(item["learner_id"], {
                "learner_id": item["learner_id"], "learner_name": item["learner_name"],
                "external_ref": None, "class_id": item.get("class_id"), "class_name": item.get("class_name"),
                "assignment_types": ["both"], "assigned_at": item["submitted_at"],
                "submitted_count": 0, "pending_review_count": 0, "published_review_count": 0,
                "retraining_count": 0, "latest_submitted_at": None,
            })
            learner["submitted_count"] += 1
            if item["review_status"] == "published":
                learner["published_review_count"] += 1
            else:
                learner["pending_review_count"] += 1
            if item["priority"] == "retraining":
                learner["retraining_count"] += 1
            if learner["latest_submitted_at"] is None or item["submitted_at"] > learner["latest_submitted_at"]:
                learner["latest_submitted_at"] = item["submitted_at"]
        return sorted(grouped.values(), key=lambda item: (item["learner_name"], item["learner_id"]))

    def list_instructor_learner_submissions(self, instructor_id: str, learner_id: str) -> list[dict[str, Any]]:
        return sorted(
            (item for item in self.list_instructor_queue(instructor_id=instructor_id) if item["learner_id"] == learner_id),
            key=lambda item: item["submitted_at"], reverse=True,
        )

    def get_instructor_review_detail(self, review_type: str, target_id: str, instructor_id: str | None = None) -> dict[str, Any] | None:
        queue_item = next((item for item in self.list_instructor_queue(review_type, instructor_id=instructor_id) if item["target_id"] == target_id), None)
        if not queue_item:
            return None
        attempt = self.learner_attempt_details.get(target_id, {}) if review_type == "practice" else {}
        recordings = [{"id": key, "audio_url": f"/api/v1/cabinlingo/instructor/audio/{key}", "mime_type": value.get("mime_type"), "duration_ms": None, "created_at": self.now()} for key, value in self.recordings.items() if value["assignment_id"] == queue_item["assignment_id"]]
        recording_id = recordings[0]["id"] if recordings else None
        review_issues = instructor_review_issues(attempt.get("issues", []))
        review_issues.extend(
            issue for issue in attempt.get("pending_review_issues", [])
            if isinstance(issue, dict) and issue.get("issue_status") == "pending_review"
        )
        return {**queue_item, "reference_text": "", "recording_id": recording_id,
                "recording_url": f"/api/v1/cabinlingo/instructor/audio/{recording_id}" if recording_id else None,
                "recordings": recordings, "ai_scores": attempt.get("score_summary", {}),
                "ai_issues": review_issues, "ai_evidence": {"text_diagnosis": attempt.get("text_diagnosis")},
                "overall_score": attempt.get("overall_score"), "speed": attempt.get("speed"),
                "duration_seconds": attempt.get("duration_seconds"), "rear_tone": attempt.get("rear_tone"),
                "word_details": attempt.get("word_details", []),
                "word_detail_level": attempt.get("word_detail_level"),
                "word_detail_count": attempt.get("word_detail_count", 0),
                "recognized_text": attempt.get("recognized_text"), "alignment": attempt.get("alignment", []),
                "alignment_source": attempt.get("alignment_source"),
                "alignment_provider": attempt.get("alignment_provider"),
                "review": self.instructor_reviews.get((review_type, target_id))}

    def get_instructor_recording(self, recording_id: str, instructor_id: str | None = None) -> dict[str, Any] | None:
        item = self.recordings.get(recording_id)
        return dict(item) if item else None

    def save_instructor_review(self, review_type: str, target_id: str, reviewer_id: str, data: dict[str, Any], publish: bool) -> dict[str, Any]:
        data = dict(data)
        data["summary"] = str(data.get("summary") or "").strip() or "教员整改建议"
        data["correction_advice"] = str(data.get("correction_advice") or "").strip() or data["summary"]
        detail = self.get_instructor_review_detail(review_type, target_id, reviewer_id)
        if not detail:
            raise ValueError("Review target not found")
        existing = self.instructor_reviews.get((review_type, target_id))
        if existing and existing["status"] == "published":
            raise ValueError("Published review is immutable")
        now = self.now()
        review = {"id": existing["id"] if existing else new_id("ir"), "review_type": review_type,
                  "target_id": target_id, "reviewer_id": reviewer_id, "revision_no": 1,
                  "status": "published" if publish else "draft", **data, "reviewed_at": now,
                  "published_at": now if publish else None}
        self.instructor_reviews[(review_type, target_id)] = review
        if publish:
            self.teacher_feedback.append({"id": new_id("tf"), "learner_id": detail["learner_id"],
                "practice_attempt_id": target_id if review_type == "practice" else None,
                "exam_assignment_id": target_id if review_type == "exam" else None,
                "teacher_id": reviewer_id, "teacher_name": reviewer_id, "summary": data["summary"],
                "correction_advice": data.get("correction_advice", ""), "required_retraining": bool(data.get("required_retraining")),
                "status": "published", "published_at": now})
            if review_type == "exam":
                self.exam_assignments[target_id].status = "published"
            if data.get("required_retraining"):
                self.remediation_requests.append({"id": new_id("rr"), "review_id": review["id"], "learner_id": detail["learner_id"], "status": "open"})
        return review

    def class_review_analytics(self, instructor_id: str | None = None) -> list[dict[str, Any]]:
        return []

    def create_practice_task(self, task: PracticeTask) -> PracticeTask:
        self.practice_tasks[task.id] = task
        return task

    def get_practice_task(self, task_id: str) -> PracticeTask | None:
        task = self.practice_tasks.get(task_id)
        return task if task and not task.deleted_at else None

    def create_exam_task(self, task: ExamTask) -> ExamTask:
        self.exam_tasks[task.id] = task
        return task

    def get_exam_task(self, task_id: str) -> ExamTask | None:
        task = self.exam_tasks.get(task_id)
        return task if task and not task.deleted_at else None

    def is_task_unlocked(self, task_type: str, task_id: str, user_id: str) -> bool:
        task = (self.practice_tasks if task_type == "practice" else self.exam_tasks).get(task_id)
        if not task or task.deleted_at:
            return False
        prerequisite_id = task.unlock_after_task_id
        if not prerequisite_id:
            return True
        if task.unlock_after_task_type == "practice":
            prerequisite = self.practice_tasks.get(prerequisite_id)
            return bool(prerequisite and not prerequisite.deleted_at and any(
                assignment.task_id == prerequisite_id and assignment.user_id == user_id and assignment.status == "completed"
                for assignment in self.practice_assignments.values()
            ))
        prerequisite = self.exam_tasks.get(prerequisite_id)
        return bool(prerequisite and not prerequisite.deleted_at and any(
            assignment.task_id == prerequisite_id and assignment.user_id == user_id
            and assignment.status in {"submitted", "graded", "published"}
            for assignment in self.exam_assignments.values()
        ))

    def is_assignment_unlocked(self, task_type: str, assignment_id: str, user_id: str) -> bool:
        assignments = self.practice_assignments if task_type == "practice" else self.exam_assignments
        assignment = assignments.get(assignment_id)
        return bool(assignment and assignment.user_id == user_id
                    and self.is_task_unlocked(task_type, assignment.task_id, user_id))

    def get_practice_assignment(self, assignment_id: str, user_id: str) -> PracticeAssignment | None:
        assignment = self.practice_assignments.get(assignment_id)
        return assignment if assignment and assignment.user_id == user_id else None

    def create_practice_assignment(self, task_id: str, user_id: str) -> PracticeAssignment:
        for assignment in self.practice_assignments.values():
            if assignment.task_id == task_id and assignment.user_id == user_id:
                return assignment
        assignment = PracticeAssignment(new_id("pa"), task_id, user_id)
        self.practice_assignments[assignment.id] = assignment
        return assignment

    def list_practice_assignments(self, user_id: str) -> list[PracticeAssignment]:
        return [a for a in self.practice_assignments.values() if a.user_id == user_id and self.practice_tasks.get(a.task_id) and not self.practice_tasks[a.task_id].deleted_at and self.practice_tasks[a.task_id].status != "draft"]

    def create_exam_assignment(self, task_id: str, user_id: str) -> ExamAssignment:
        for assignment in self.exam_assignments.values():
            if assignment.task_id == task_id and assignment.user_id == user_id:
                return assignment
        assignment = ExamAssignment(new_id("ea"), task_id, user_id)
        self.exam_assignments[assignment.id] = assignment
        return assignment

    def list_exam_assignments(self, user_id: str) -> list[ExamAssignment]:
        return [a for a in self.exam_assignments.values() if a.user_id == user_id and self.exam_tasks.get(a.task_id) and not self.exam_tasks[a.task_id].deleted_at and self.exam_tasks[a.task_id].status != "draft"]

    def list_practice_progress(self, user_id: str) -> list[dict[str, Any]]:
        return [{"user_id": user_id, "assignment_id": a.id, "task_id": a.task_id, "attempts": len(a.attempt_ids), "status": a.status} for a in self.list_practice_assignments(user_id)]

    def save_practice_attempt(self, attempt: PracticeAttempt, feedback: dict[str, Any]) -> None:
        assignment = self.practice_assignments[attempt.assignment_id]
        self.practice_attempts[attempt.id] = attempt
        assignment.attempt_ids.append(attempt.id)
        assignment.status = "in_progress"

    def practice_attempt_count(self, assignment_id: str) -> int:
        assignment = self.practice_assignments.get(assignment_id)
        return len(assignment.attempt_ids) if assignment else 0

    def get_exam_assignment(self, assignment_id: str, user_id: str) -> ExamAssignment | None:
        assignment = self.exam_assignments.get(assignment_id)
        return assignment if assignment and assignment.user_id == user_id else None

    def submit_exam_assignment(self, assignment: ExamAssignment, recording_refs: list[str], submitted_at: datetime) -> None:
        assignment.submitted_recordings = list(recording_refs)
        assignment.submitted_at = submitted_at
        assignment.status = "submitted"
