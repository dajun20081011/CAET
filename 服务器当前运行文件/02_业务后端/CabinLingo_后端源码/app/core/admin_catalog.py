from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from .config import settings
from .rbac import Principal, assert_permission, get_principal


router = APIRouter(prefix="/api/v1/core", tags=["Core Administration"])
logger = logging.getLogger(__name__)


class OrganizationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)


class OrganizationOut(OrganizationCreate):
    id: str
    status: Literal["active", "inactive"] = "active"
    class_count: int = 0


class ClassCreate(BaseModel):
    organization_id: str
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    class_type: Literal["training", "assessment"] = "training"
    description: str = Field(default="", max_length=4000)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class ClassUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    class_type: Literal["training", "assessment"] | None = None
    description: str | None = Field(default=None, max_length=4000)
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["active", "inactive"] | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class ClassOut(ClassCreate):
    id: str
    status: Literal["active", "inactive"] = "active"
    member_count: int = 0


class ClassMemberBatch(BaseModel):
    student_ids: list[str] = Field(min_length=1, max_length=500)


class ClassMemberOut(BaseModel):
    id: str
    display_name: str
    employee_no: str | None = None
    email: str | None = None
    organization_id: str | None = None
    class_id: str | None = None
    status: Literal["active", "inactive"] = "active"
    training_instructors: list[str] = Field(default_factory=list)
    assessment_instructors: list[str] = Field(default_factory=list)


class ClassDetailOut(ClassOut):
    members: list[ClassMemberOut] = Field(default_factory=list)


class InstructorAssignmentCreate(BaseModel):
    instructor_id: str
    assignment_type: Literal["training", "assessment", "both"] = "both"
    course_id: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be earlier than effective_from")
        return self


class InstructorAssignmentUpdate(BaseModel):
    assignment_type: Literal["training", "assessment", "both"] | None = None
    course_id: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    status: Literal["active", "inactive"] | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be earlier than effective_from")
        return self


class InstructorAssignmentOut(InstructorAssignmentCreate):
    id: str
    student_id: str
    instructor_name: str
    instructor_account: str | None = None
    course_title: str | None = None
    status: Literal["active", "inactive"] = "active"
    created_at: Any
    updated_at: Any


class InstructorAssignmentBatchCreate(InstructorAssignmentCreate):
    student_ids: list[str] = Field(default_factory=list, max_length=500)
    class_ids: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def require_target(self):
        if not self.student_ids and not self.class_ids:
            raise ValueError("Select at least one learner or class")
        return self


class InstructorAssignmentBatchOut(BaseModel):
    selected: int
    created: int
    reactivated: int
    unchanged: int
    evaluation_tasks_created: int


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Organization management requires PostgreSQL")
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def _admin(principal: Principal) -> None:
    assert_permission(principal, "cabinlingo", "cabinlingo:organization.manage")


def _route_existing_evaluation_tasks(student_ids: list[str]) -> int:
    """Best-effort eager routing; instructor queue also performs an idempotent repair."""
    from ..products.cabinlingo.router import store

    created = 0
    for student_id in student_ids:
        created += int(store.reassign_evaluation_tasks(student_id).get("created", 0))
    return created


def _class_row(cur, class_id: str) -> dict[str, Any] | None:
    cur.execute("""SELECT c.id::text AS id,c.organization_id::text AS organization_id,c.code,c.name,
                   c.class_type,c.description,c.start_date,c.end_date,c.status,c.updated_at,
                   count(cm.user_id) FILTER (WHERE cm.status='active')::int AS member_count
                   FROM classes c LEFT JOIN class_memberships cm ON cm.class_id=c.id
                   WHERE c.id=%s GROUP BY c.id""", (class_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def _student_exists(cur, student_id: str) -> bool:
    cur.execute("""SELECT 1 FROM users u WHERE u.id=%s AND u.is_active=true
                   AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                              WHERE ur.user_id=u.id AND r.code='learner')""", (student_id,))
    return cur.fetchone() is not None


def _instructor_exists(cur, instructor_id: str) -> bool:
    cur.execute("""SELECT 1 FROM users u WHERE u.id=%s AND u.is_active=true
                   AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                              WHERE ur.user_id=u.id AND r.code IN ('instructor','evaluator'))""", (instructor_id,))
    return cur.fetchone() is not None


@router.get("/organizations", response_model=list[OrganizationOut])
async def list_organizations(principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT o.id::text AS id,o.code,o.name,o.status,count(c.id)::int AS class_count
                       FROM organizations o LEFT JOIN classes c ON c.organization_id=o.id
                       GROUP BY o.id ORDER BY o.name""")
        return [dict(row) for row in cur.fetchall()]


@router.post("/organizations", response_model=OrganizationOut)
async def create_organization(data: OrganizationCreate, principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO organizations(code,name,status) VALUES (%s,%s,'active')
                           RETURNING id::text AS id,code,name,status,0::int AS class_count""", (data.code.strip(), data.name.strip()))
            return dict(cur.fetchone())
    except Exception as exc:
        raise HTTPException(409, "Organization code already exists") from exc


@router.get("/classes", response_model=list[ClassOut])
async def list_classes(organization_id: str | None = None, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT c.id::text AS id,c.organization_id::text AS organization_id,c.code,c.name,
                       c.class_type,c.description,c.start_date,c.end_date,c.status,
                       count(cm.user_id) FILTER (WHERE cm.status='active')::int AS member_count
                       FROM classes c LEFT JOIN class_memberships cm ON cm.class_id=c.id
                       WHERE (%s::uuid IS NULL OR c.organization_id=%s::uuid)
                       GROUP BY c.id ORDER BY c.status DESC,c.start_date NULLS LAST,c.name""", (organization_id, organization_id))
        return [dict(row) for row in cur.fetchall()]


@router.post("/classes", response_model=ClassOut)
async def create_class(data: ClassCreate, principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO classes(organization_id,code,name,class_type,description,start_date,end_date,status,updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,'active',now())
                           RETURNING id::text AS id,organization_id::text AS organization_id,code,name,class_type,description,start_date,end_date,status,0::int AS member_count""",
                        (data.organization_id, data.code.strip(), data.name.strip(), data.class_type, data.description.strip(), data.start_date, data.end_date))
            return dict(cur.fetchone())
    except Exception as exc:
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate == "23505":
            raise HTTPException(409, "Class code already exists in this organization") from exc
        if sqlstate == "23503":
            raise HTTPException(422, "Selected organization does not exist") from exc
        logger.exception("Class creation failed for organization %s", data.organization_id)
        raise HTTPException(500, "Class could not be created") from exc


@router.get("/classes/{class_id}", response_model=ClassDetailOut)
async def get_class(class_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        item = _class_row(cur, class_id)
        if not item:
            raise HTTPException(404, "Class not found")
        cur.execute("""SELECT u.id::text AS id,u.display_name,u.employee_no,u.email,
                       u.organization_id::text AS organization_id,cm.class_id::text AS class_id,cm.status,
                       COALESCE((SELECT array_agg(DISTINCT teacher.display_name ORDER BY teacher.display_name)
                                 FROM student_instructor_assignments sia JOIN users teacher ON teacher.id=sia.instructor_id
                                 WHERE sia.student_id=u.id AND sia.status='active' AND sia.assignment_type IN ('training','both')
                                   AND (sia.effective_from IS NULL OR sia.effective_from<=CURRENT_DATE)
                                   AND (sia.effective_to IS NULL OR sia.effective_to>=CURRENT_DATE)), ARRAY[]::text[]) AS training_instructors,
                       COALESCE((SELECT array_agg(DISTINCT teacher.display_name ORDER BY teacher.display_name)
                                 FROM student_instructor_assignments sia JOIN users teacher ON teacher.id=sia.instructor_id
                                 WHERE sia.student_id=u.id AND sia.status='active' AND sia.assignment_type IN ('assessment','both')
                                   AND (sia.effective_from IS NULL OR sia.effective_from<=CURRENT_DATE)
                                   AND (sia.effective_to IS NULL OR sia.effective_to>=CURRENT_DATE)), ARRAY[]::text[]) AS assessment_instructors
                       FROM class_memberships cm JOIN users u ON u.id=cm.user_id
                       WHERE cm.class_id=%s AND cm.status='active' ORDER BY u.display_name""", (class_id,))
        item["members"] = [dict(row) for row in cur.fetchall()]
        return item


@router.put("/classes/{class_id}", response_model=ClassOut)
async def update_class(class_id: str, data: ClassUpdate, principal: Principal = Depends(get_principal)):
    _admin(principal)
    changes = data.model_dump(exclude_unset=True)
    with _connect() as conn, conn.cursor() as cur:
        current = _class_row(cur, class_id)
        if not current:
            raise HTTPException(404, "Class not found")
        if not changes:
            return current
        start_date = changes.get("start_date", current.get("start_date"))
        end_date = changes.get("end_date", current.get("end_date"))
        if start_date and end_date and end_date < start_date:
            raise HTTPException(422, "end_date must not be earlier than start_date")
        assignments = ", ".join(f"{key}=%s" for key in changes)
        values = [changes[key].strip() if isinstance(changes[key], str) and key in {"code", "name", "description"} else changes[key] for key in changes]
        cur.execute(f"UPDATE classes SET {assignments},updated_at=now() WHERE id=%s", (*values, class_id))
        return _class_row(cur, class_id)


@router.delete("/classes/{class_id}", response_model=ClassOut)
async def deactivate_class(class_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE classes SET status='inactive',updated_at=now() WHERE id=%s", (class_id,))
        item = _class_row(cur, class_id)
        if not item:
            raise HTTPException(404, "Class not found")
        return item


@router.post("/classes/{class_id}/students", response_model=list[ClassMemberOut])
async def add_class_students(class_id: str, data: ClassMemberBatch, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        if not _class_row(cur, class_id):
            raise HTTPException(404, "Class not found")
        invalid = [student_id for student_id in data.student_ids if not _student_exists(cur, student_id)]
        if invalid:
            raise HTTPException(422, f"Only active learner accounts can join a class: {', '.join(invalid)}")
        for student_id in dict.fromkeys(data.student_ids):
            cur.execute("""INSERT INTO class_memberships(class_id,user_id,status)
                           VALUES (%s,%s,'active') ON CONFLICT(class_id,user_id)
                           DO UPDATE SET status='active',joined_at=now()""", (class_id, student_id))
        cur.execute("""SELECT u.id::text AS id,u.display_name,u.employee_no,u.email,
                       u.organization_id::text AS organization_id,cm.class_id::text AS class_id,cm.status,
                       ARRAY[]::text[] AS training_instructors,ARRAY[]::text[] AS assessment_instructors
                       FROM class_memberships cm JOIN users u ON u.id=cm.user_id
                       WHERE cm.class_id=%s AND cm.status='active' ORDER BY u.display_name""", (class_id,))
        return [dict(row) for row in cur.fetchall()]


@router.delete("/classes/{class_id}/students/{student_id}", response_model=ClassOut)
async def remove_class_student(class_id: str, student_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE class_memberships SET status='inactive' WHERE class_id=%s AND user_id=%s", (class_id, student_id))
        item = _class_row(cur, class_id)
        if not item:
            raise HTTPException(404, "Class not found")
        return item


@router.get("/learners/{student_id}/instructors", response_model=list[InstructorAssignmentOut])
async def list_student_instructors(student_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT sia.id::text AS id,sia.student_id::text AS student_id,sia.instructor_id::text AS instructor_id,
                       sia.assignment_type,sia.course_id::text AS course_id,sia.effective_from,sia.effective_to,sia.status,
                       sia.created_at,sia.updated_at,teacher.display_name AS instructor_name,teacher.external_ref AS instructor_account,
                       course.title AS course_title
                       FROM student_instructor_assignments sia JOIN users teacher ON teacher.id=sia.instructor_id
                       LEFT JOIN cl_courses course ON course.id=sia.course_id
                       WHERE sia.student_id=%s ORDER BY sia.status DESC,sia.assignment_type,sia.created_at DESC""", (student_id,))
        return [dict(row) for row in cur.fetchall()]


@router.post("/learners/{student_id}/instructors", response_model=InstructorAssignmentOut)
async def create_student_instructor(student_id: str, data: InstructorAssignmentCreate, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        if not _student_exists(cur, student_id):
            raise HTTPException(422, "Student must be an active learner account")
        if not _instructor_exists(cur, data.instructor_id):
            raise HTTPException(422, "Instructor must be an active instructor or evaluator account")
        if data.course_id:
            cur.execute("SELECT 1 FROM cl_courses WHERE id=%s", (data.course_id,))
            if not cur.fetchone():
                raise HTTPException(422, "Course does not exist")
        cur.execute("""SELECT 1 FROM student_instructor_assignments
                       WHERE student_id=%s AND instructor_id=%s AND assignment_type=%s
                         AND status='active' AND COALESCE(course_id,'00000000-0000-0000-0000-000000000000')=
                             COALESCE(%s::uuid,'00000000-0000-0000-0000-000000000000')""",
                    (student_id, data.instructor_id, data.assignment_type, data.course_id))
        if cur.fetchone():
            raise HTTPException(409, "This instructor assignment already exists")
        cur.execute("""INSERT INTO student_instructor_assignments(student_id,instructor_id,assignment_type,course_id,effective_from,effective_to)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       RETURNING id::text AS id,student_id::text AS student_id,instructor_id::text AS instructor_id,assignment_type,
                       course_id::text AS course_id,effective_from,effective_to,status,created_at,updated_at""",
                    (student_id, data.instructor_id, data.assignment_type, data.course_id, data.effective_from, data.effective_to))
        item = dict(cur.fetchone())
        cur.execute("SELECT display_name,external_ref FROM users WHERE id=%s", (data.instructor_id,))
        teacher = cur.fetchone(); item["instructor_name"] = teacher["display_name"]; item["instructor_account"] = teacher["external_ref"] if teacher else None
        item["course_title"] = None
        if data.course_id:
            cur.execute("SELECT title FROM cl_courses WHERE id=%s", (data.course_id,)); course = cur.fetchone(); item["course_title"] = course["title"] if course else None
    try:
        _route_existing_evaluation_tasks([student_id])
    except Exception:
        logger.exception("Instructor binding saved but eager evaluation routing failed for learner %s", student_id)
    return item


@router.post("/learner-instructor-assignments/batch", response_model=InstructorAssignmentBatchOut)
async def batch_create_student_instructors(data: InstructorAssignmentBatchCreate, principal: Principal = Depends(get_principal)):
    """Bind one instructor to many learners without duplicating active relationships."""
    _admin(principal)
    student_ids = list(dict.fromkeys(data.student_ids))
    created = 0
    reactivated = 0
    unchanged = 0
    with _connect() as conn, conn.cursor() as cur:
        if not _instructor_exists(cur, data.instructor_id):
            raise HTTPException(422, "Instructor must be an active instructor or evaluator account")
        if data.class_ids:
            class_ids = list(dict.fromkeys(data.class_ids))
            cur.execute("SELECT id::text AS id FROM classes WHERE id=ANY(%s::uuid[]) AND status='active'", (class_ids,))
            valid_class_ids = {row["id"] for row in cur.fetchall()}
            invalid_class_ids = [class_id for class_id in class_ids if class_id not in valid_class_ids]
            if invalid_class_ids:
                raise HTTPException(422, f"Only active classes can be assigned: {', '.join(invalid_class_ids)}")
            cur.execute("""SELECT DISTINCT cm.user_id::text AS student_id
                           FROM class_memberships cm JOIN users u ON u.id=cm.user_id
                           WHERE cm.class_id=ANY(%s::uuid[]) AND cm.status='active' AND u.is_active=true
                             AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                                         WHERE ur.user_id=u.id AND r.code='learner')""", (class_ids,))
            student_ids.extend(row["student_id"] for row in cur.fetchall())
            student_ids = list(dict.fromkeys(student_ids))
        if not student_ids:
            raise HTTPException(422, "Selected classes do not contain active learners")
        cur.execute("""SELECT u.id::text AS id FROM users u
                       WHERE u.id=ANY(%s::uuid[]) AND u.is_active=true
                         AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                                     WHERE ur.user_id=u.id AND r.code='learner')""", (student_ids,))
        valid_ids = {row["id"] for row in cur.fetchall()}
        invalid_ids = [student_id for student_id in student_ids if student_id not in valid_ids]
        if invalid_ids:
            raise HTTPException(422, f"Only active learner accounts can be assigned: {', '.join(invalid_ids)}")
        if data.course_id:
            cur.execute("SELECT 1 FROM cl_courses WHERE id=%s", (data.course_id,))
            if not cur.fetchone():
                raise HTTPException(422, "Course does not exist")
        for student_id in student_ids:
            cur.execute("""SELECT id::text AS id,status FROM student_instructor_assignments
                           WHERE student_id=%s AND instructor_id=%s AND assignment_type=%s
                             AND COALESCE(course_id,'00000000-0000-0000-0000-000000000000')=
                                 COALESCE(%s::uuid,'00000000-0000-0000-0000-000000000000')
                           ORDER BY (status='active') DESC,updated_at DESC LIMIT 1""",
                        (student_id, data.instructor_id, data.assignment_type, data.course_id))
            existing = cur.fetchone()
            if existing and existing["status"] == "active":
                unchanged += 1
                continue
            if existing:
                cur.execute("""UPDATE student_instructor_assignments
                               SET status='active',effective_from=%s,effective_to=%s,updated_at=now()
                               WHERE id=%s""", (data.effective_from, data.effective_to, existing["id"]))
                reactivated += 1
                continue
            cur.execute("""INSERT INTO student_instructor_assignments
                           (student_id,instructor_id,assignment_type,course_id,effective_from,effective_to)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (student_id, data.instructor_id, data.assignment_type, data.course_id,
                         data.effective_from, data.effective_to))
            created += 1
    try:
        evaluation_tasks_created = _route_existing_evaluation_tasks(student_ids)
    except Exception:
        logger.exception("Instructor bindings saved but eager evaluation routing failed for %s learners", len(student_ids))
        evaluation_tasks_created = 0
    return {"selected": len(student_ids), "created": created, "reactivated": reactivated,
            "unchanged": unchanged, "evaluation_tasks_created": evaluation_tasks_created}


@router.put("/learners/{student_id}/instructors/{assignment_id}", response_model=InstructorAssignmentOut)
async def update_student_instructor(student_id: str, assignment_id: str, data: InstructorAssignmentUpdate, principal: Principal = Depends(get_principal)):
    _admin(principal)
    changes = data.model_dump(exclude_unset=True)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT instructor_id::text AS instructor_id,effective_from,effective_to FROM student_instructor_assignments WHERE id=%s AND student_id=%s", (assignment_id, student_id))
        current = cur.fetchone()
        if not current:
            raise HTTPException(404, "Instructor assignment not found")
        start_date = changes.get("effective_from", current["effective_from"]); end_date = changes.get("effective_to", current["effective_to"])
        if start_date and end_date and end_date < start_date:
            raise HTTPException(422, "effective_to must not be earlier than effective_from")
        if not changes:
            changes = {"status": "active"}
        assignments = ", ".join(f"{key}=%s" for key in changes)
        values = [changes[key] for key in changes]
        cur.execute(f"UPDATE student_instructor_assignments SET {assignments},updated_at=now() WHERE id=%s AND student_id=%s", (*values, assignment_id, student_id))
        cur.execute("""SELECT sia.id::text AS id,sia.student_id::text AS student_id,sia.instructor_id::text AS instructor_id,
                       sia.assignment_type,sia.course_id::text AS course_id,sia.effective_from,sia.effective_to,sia.status,
                       sia.created_at,sia.updated_at,teacher.display_name AS instructor_name,teacher.external_ref AS instructor_account,
                       course.title AS course_title FROM student_instructor_assignments sia JOIN users teacher ON teacher.id=sia.instructor_id
                       LEFT JOIN cl_courses course ON course.id=sia.course_id WHERE sia.id=%s""", (assignment_id,))
        item = dict(cur.fetchone())
    try:
        _route_existing_evaluation_tasks([student_id])
    except Exception:
        logger.exception("Instructor binding updated but eager evaluation routing failed for learner %s", student_id)
    return item


@router.delete("/learners/{student_id}/instructors/{assignment_id}", response_model=InstructorAssignmentOut)
async def deactivate_student_instructor(student_id: str, assignment_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE student_instructor_assignments SET status='inactive',updated_at=now() WHERE id=%s AND student_id=%s", (assignment_id, student_id))
        cur.execute("""SELECT sia.id::text AS id,sia.student_id::text AS student_id,sia.instructor_id::text AS instructor_id,
                       sia.assignment_type,sia.course_id::text AS course_id,sia.effective_from,sia.effective_to,sia.status,
                       sia.created_at,sia.updated_at,teacher.display_name AS instructor_name,teacher.external_ref AS instructor_account,
                       course.title AS course_title FROM student_instructor_assignments sia JOIN users teacher ON teacher.id=sia.instructor_id
                       LEFT JOIN cl_courses course ON course.id=sia.course_id WHERE sia.id=%s""", (assignment_id,))
        item = cur.fetchone()
        if not item:
            raise HTTPException(404, "Instructor assignment not found")
        return dict(item)


@router.post("/learners/{student_id}/evaluation-tasks/reassign")
async def reassign_student_evaluation_tasks(student_id: str, principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        from ..products.cabinlingo.router import store
        return store.reassign_evaluation_tasks(student_id)
    except AttributeError as exc:
        raise HTTPException(503, "Evaluation task routing requires PostgreSQL") from exc


@router.get("/evaluation-tasks/unassigned")
async def list_unassigned_evaluation_tasks(principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        from ..products.cabinlingo.router import store
        return store.list_unassigned_evaluation_tasks()
    except AttributeError as exc:
        raise HTTPException(503, "Evaluation task routing requires PostgreSQL") from exc
