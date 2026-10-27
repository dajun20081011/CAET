from fastapi import APIRouter, Depends

from db.connection import get_connection
from security import require_admin


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/summary", dependencies=[Depends(require_admin)])
def summary():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.code, p.name,
                       COUNT(DISTINCT c.id) AS course_count,
                       COUNT(DISTINCT c.id) FILTER (WHERE c.status = 'published') AS published_count,
                       COUNT(DISTINCT l.id) AS lesson_count
                FROM projects p
                LEFT JOIN courses c ON c.project_id = p.id
                LEFT JOIN lessons l ON l.course_id = c.id
                GROUP BY p.id, p.code, p.name
                ORDER BY p.id
                """
            )
            projects = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS total FROM courses")
            course_total = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM lessons")
            lesson_total = cur.fetchone()["total"]
            return {
                "course_total": course_total,
                "lesson_total": lesson_total,
                "projects": projects,
            }
