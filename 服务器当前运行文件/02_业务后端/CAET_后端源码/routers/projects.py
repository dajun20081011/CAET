from fastapi import APIRouter

from db.connection import get_connection


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code, name, description, status
                FROM projects
                ORDER BY id
                """
            )
            return cur.fetchall()
