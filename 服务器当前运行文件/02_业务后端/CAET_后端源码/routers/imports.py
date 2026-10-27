import json
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from db.connection import get_connection
from services.html_parser import parse_course_html
from services.zip_importer import MAX_ZIP_SIZE, process_course_zip
from security import require_admin


router = APIRouter(prefix="/imports", tags=["imports"])
MAX_HTML_SIZE = 2 * 1024 * 1024


def _insert_imported_lesson(course_id: int, sort_order: int, parsed: dict, source_type: str, source_filename: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, p.code AS project_code
                FROM courses c
                JOIN projects p ON p.id = c.project_id
                WHERE c.id = %s
                """,
                (course_id,),
            )
            course = cur.fetchone()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")
            if course["project_code"] != parsed["template_type"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Template type '{parsed['template_type']}' does not match project '{course['project_code']}'",
                )
            cur.execute(
                """
                INSERT INTO lessons (
                    course_id, title, sort_order, template_type, content, source_type, source_filename
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id, course_id, title, sort_order, template_type, content,
                          source_type, source_filename, created_at
                """,
                (
                    course_id,
                    parsed["title"],
                    sort_order,
                    parsed["template_type"],
                    json.dumps(parsed["content"], ensure_ascii=False),
                    source_type,
                    source_filename,
                ),
            )
            lesson = cur.fetchone()
            conn.commit()
            return lesson


@router.post("/html", status_code=201, dependencies=[Depends(require_admin)])
async def import_html_course(
    course_id: int = Form(...),
    sort_order: int = Form(0),
    file: UploadFile = File(...),
):
    filename = file.filename or ""
    if not filename.lower().endswith((".html", ".htm")):
        raise HTTPException(status_code=400, detail="Only HTML files are supported")
    data = await file.read(MAX_HTML_SIZE + 1)
    if len(data) > MAX_HTML_SIZE:
        raise HTTPException(status_code=413, detail="HTML file is too large")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as temp:
            temp.write(data)
            temp_path = temp.name
        try:
            parsed = parse_course_html(temp_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"HTML parse failed: {exc}")
        lesson = _insert_imported_lesson(course_id, sort_order, parsed, "html", filename)
        return {"message": "HTML imported successfully", "lesson": lesson}
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        await file.close()


@router.post("/zip", status_code=201, dependencies=[Depends(require_admin)])
async def import_zip_course(
    course_id: int = Form(...),
    sort_order: int = Form(0),
    file: UploadFile = File(...),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are supported")
    data = await file.read(MAX_ZIP_SIZE + 1)
    if len(data) > MAX_ZIP_SIZE:
        raise HTTPException(status_code=413, detail="ZIP file is too large")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp:
            temp.write(data)
            temp_path = temp.name
        try:
            parsed = process_course_zip(temp_path, uploads_root="/uploads")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"ZIP import failed: {exc}")
        bundle_id = parsed.get("bundle_id")
        try:
            lesson = _insert_imported_lesson(course_id, sort_order, parsed, "zip", filename)
        except Exception:
            if bundle_id:
                shutil.rmtree(f"/uploads/lessons/{bundle_id}", ignore_errors=True)
            raise
        return {
            "message": "ZIP imported successfully",
            "bundle_id": bundle_id,
            "lesson": lesson,
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        await file.close()
