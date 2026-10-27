from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.connection import get_connection
from schemas.course_admin import CourseCreate, CourseUpdate
from security import require_admin


router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("")
def list_courses(project_code: Optional[str] = Query(default=None), status: Optional[str] = Query(default=None)):
    sql = """
        SELECT
            c.id, p.code AS project_code, p.name AS project_name,
            c.title, c.description, c.status, c.sort_order,
            c.published_at, c.offline_at, c.created_at, c.updated_at,
            (SELECT COUNT(*) FROM lessons l WHERE l.course_id = c.id) AS lesson_count
        FROM courses c
        JOIN projects p ON p.id = c.project_id
        WHERE 1=1
    """
    params = []
    if project_code:
        sql += " AND p.code = %s"
        params.append(project_code)
    if status:
        sql += " AND c.status = %s"
        params.append(status)
    sql += " ORDER BY p.id, c.sort_order, c.id"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


@router.get("/{course_id}")
def get_course(course_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.*, p.code AS project_code, p.name AS project_name,
                       (SELECT COUNT(*) FROM lessons l WHERE l.course_id = c.id) AS lesson_count
                FROM courses c
                JOIN projects p ON p.id = c.project_id
                WHERE c.id = %s
                """,
                (course_id,),
            )
            course = cur.fetchone()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")
            return course


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
def create_course(payload: CourseCreate):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM projects WHERE code = %s AND status = 'active'", (payload.project_code,))
            project = cur.fetchone()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            cur.execute(
                """
                INSERT INTO courses (project_id, title, description, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, description, status, sort_order, created_at
                """,
                (project["id"], payload.title, payload.description, payload.sort_order),
            )
            course = cur.fetchone()
            conn.commit()
            return {"project_code": payload.project_code, **course}


@router.patch("/{course_id}", dependencies=[Depends(require_admin)])
def update_course(course_id: int, payload: CourseUpdate):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return get_course(course_id)
    allowed = {"title", "description", "sort_order"}
    fields = []
    params = []
    for key, value in updates.items():
        if key in allowed:
            fields.append(f"{key} = %s")
            params.append(value)
    fields.append("updated_at = NOW()")
    params.append(course_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE courses SET {', '.join(fields)} WHERE id = %s RETURNING id", params)
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Course not found")
            conn.commit()
    return get_course(course_id)


@router.post("/{course_id}/publish", dependencies=[Depends(require_admin)])
def publish_course(course_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM courses WHERE id = %s", (course_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Course not found")
            cur.execute("SELECT COUNT(*) AS count FROM lessons WHERE course_id = %s", (course_id,))
            if cur.fetchone()["count"] == 0:
                raise HTTPException(status_code=400, detail="Course has no lessons")
            cur.execute(
                """
                UPDATE courses
                SET status = 'published', published_at = NOW(), offline_at = NULL, updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (course_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Course not found")
            conn.commit()
    return get_course(course_id)


@router.post("/{course_id}/offline", dependencies=[Depends(require_admin)])
def offline_course(course_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE courses
                SET status = 'offline', offline_at = NOW(), updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (course_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Course not found")
            conn.commit()
    return get_course(course_id)


@router.delete("/{course_id}", dependencies=[Depends(require_admin)])
def delete_course(course_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM courses WHERE id = %s", (course_id,))
            course = cur.fetchone()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")
            if course["status"] != "draft":
                raise HTTPException(status_code=400, detail="Only draft courses can be deleted")
            cur.execute("DELETE FROM courses WHERE id = %s", (course_id,))
            conn.commit()
    return {"message": "Course deleted", "id": course_id}
