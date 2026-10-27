import json

from fastapi import APIRouter, Depends, HTTPException

from db.connection import get_connection
from schemas.lesson_admin import LessonCreate, LessonUpdate
from security import require_admin


router = APIRouter(prefix="/lessons", tags=["lessons"])


def _course_project(cur, course_id: int):
    cur.execute(
        """
        SELECT c.id, p.code AS project_code
        FROM courses c
        JOIN projects p ON p.id = c.project_id
        WHERE c.id = %s
        """,
        (course_id,),
    )
    return cur.fetchone()


def _validate_template(project_code: str, template_type: str):
    if project_code != template_type:
        raise HTTPException(
            status_code=400,
            detail=f"Template type '{template_type}' does not match project '{project_code}'",
        )


@router.get("")
def list_lessons(course_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, course_id, title, sort_order, template_type, content,
                       source_type, source_filename, created_at, updated_at
                FROM lessons
                WHERE course_id = %s
                ORDER BY sort_order, id
                """,
                (course_id,),
            )
            return cur.fetchall()


@router.get("/{lesson_id}")
def get_lesson(lesson_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, course_id, title, sort_order, template_type, content,
                       source_type, source_filename, created_at, updated_at
                FROM lessons WHERE id = %s
                """,
                (lesson_id,),
            )
            lesson = cur.fetchone()
            if not lesson:
                raise HTTPException(status_code=404, detail="Lesson not found")
            return lesson


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
def create_lesson(payload: LessonCreate):
    with get_connection() as conn:
        with conn.cursor() as cur:
            course = _course_project(cur, payload.course_id)
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")
            template_type = payload.content.template_type
            _validate_template(course["project_code"], template_type)
            cur.execute(
                """
                INSERT INTO lessons (course_id, title, sort_order, template_type, content, source_type)
                VALUES (%s, %s, %s, %s, %s::jsonb, 'manual')
                RETURNING id, course_id, title, sort_order, template_type, content, source_type, created_at
                """,
                (
                    payload.course_id,
                    payload.title,
                    payload.sort_order,
                    template_type,
                    json.dumps(payload.content.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
            lesson = cur.fetchone()
            conn.commit()
            return lesson


@router.patch("/{lesson_id}", dependencies=[Depends(require_admin)])
def update_lesson(lesson_id: int, payload: LessonUpdate):
    changes = payload.model_dump(exclude_unset=True)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT course_id, template_type FROM lessons WHERE id = %s", (lesson_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Lesson not found")
            fields = []
            params = []
            if "title" in changes:
                fields.append("title = %s")
                params.append(changes["title"])
            if "sort_order" in changes:
                fields.append("sort_order = %s")
                params.append(changes["sort_order"])
            if payload.content is not None:
                course = _course_project(cur, existing["course_id"])
                _validate_template(course["project_code"], payload.content.template_type)
                fields.extend(["template_type = %s", "content = %s::jsonb"])
                params.extend([
                    payload.content.template_type,
                    json.dumps(payload.content.model_dump(mode="json"), ensure_ascii=False),
                ])
            if fields:
                fields.append("updated_at = NOW()")
                params.append(lesson_id)
                cur.execute(f"UPDATE lessons SET {', '.join(fields)} WHERE id = %s", params)
                conn.commit()
    return get_lesson(lesson_id)


@router.delete("/{lesson_id}", dependencies=[Depends(require_admin)])
def delete_lesson(lesson_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lessons WHERE id = %s RETURNING id", (lesson_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Lesson not found")
            conn.commit()
    return {"message": "Lesson deleted", "id": lesson_id}
