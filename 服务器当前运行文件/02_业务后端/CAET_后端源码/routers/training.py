from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from db.connection import get_connection
from schemas.training import (
    EventIn,
    ExamSubmitIn,
    GradeIn,
    GroupIn,
    InitAdminIn,
    LoginIn,
    PracticeAttemptIn,
    ProgressIn,
    TaskCreateIn,
    UserCreateIn,
    UserUpdateIn,
)
from security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    require_instructor,
    require_training_admin,
    verify_password,
)


router = APIRouter(tags=["broadcast-training"])


def _public_user(user: dict) -> dict:
    return {k: user.get(k) for k in (
        "id", "email", "display_name", "employee_no", "role", "group_id",
        "is_active", "created_at", "updated_at",
    )}


def _lesson_id(content_id: str | int | None) -> int:
    match = re.match(r"^(\d+)", str(content_id or ""))
    if not match:
        raise HTTPException(status_code=400, detail="课程内容 ID 无效")
    return int(match.group(1))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+(?:'[a-z]+)?", (text or "").lower())


def _practice_feedback(reference: str, transcript: str, previous_score: int | None) -> dict:
    expected, actual = _tokens(reference), _tokens(transcript)
    matcher = SequenceMatcher(a=expected, b=actual, autojunk=False)
    missing, extra, replacements = [], [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            missing.extend(expected[i1:i2])
        elif tag == "insert":
            extra.extend(actual[j1:j2])
        elif tag == "replace":
            replacements.append({"expected": " ".join(expected[i1:i2]), "heard": " ".join(actual[j1:j2])})
    score = round(matcher.ratio() * 100) if expected else 0
    tips = []
    if missing:
        tips.append("重点补读：" + "、".join(missing[:8]))
    if replacements:
        tips.append("重点纠正替换词组，先慢速跟读再正常语速复练")
    if extra:
        tips.append("注意控制回读或增读：" + "、".join(extra[:8]))
    if not tips:
        tips.append("文本完整度良好，可继续练习节奏、重音与语调")
    return {
        "engine": "text_alignment_v1",
        "formal_pronunciation_score": False,
        "overall_score": score,
        "previous_score": previous_score,
        "trend_delta": None if previous_score is None else score - previous_score,
        "missing_words": missing,
        "extra_words": extra,
        "replacements": replacements,
        "correction_tips": tips,
        "notice": "本结果为练习即时反馈，不是正式发音成绩。",
    }


@router.post("/auth/init-admin", dependencies=[Depends(require_admin)], status_code=201)
def init_admin(payload: InitAdminIn):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM training_users WHERE lower(email)=lower(%s)", (payload.email,))
        existing = cur.fetchone()
        if existing:
            return _public_user(existing)
        cur.execute(
            "INSERT INTO training_users(email,password_hash,display_name,role) VALUES(%s,%s,%s,'admin') RETURNING *",
            (payload.email.lower(), hash_password(payload.password), payload.display_name),
        )
        user = cur.fetchone()
        conn.commit()
        return _public_user(user)


@router.post("/auth/login")
def login(payload: LoginIn):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM training_users WHERE lower(email)=lower(%s)", (payload.email,))
        user = cur.fetchone()
    if not user or not user["is_active"] or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return {"access_token": create_access_token(user["id"]), "token_type": "bearer", "user": _public_user(user)}


@router.get("/auth/me")
def me(user=Depends(get_current_user)):
    return _public_user(user)


@router.post("/auth/logout", status_code=204)
def logout(_user=Depends(get_current_user)):
    return None


@router.get("/admin/users")
def list_users(_admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM training_users ORDER BY created_at DESC")
        return [_public_user(row) for row in cur.fetchall()]


@router.post("/admin/users", status_code=201)
def create_user(payload: UserCreateIn, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM training_users WHERE lower(email)=lower(%s)", (payload.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="账号已存在")
        cur.execute(
            """INSERT INTO training_users(email,password_hash,display_name,employee_no,role,group_id)
               VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
            (payload.email.lower(), hash_password(payload.password), payload.display_name,
             payload.employee_no, payload.role, payload.group_id),
        )
        user = cur.fetchone()
        conn.commit()
        return _public_user(user)


@router.put("/admin/users/{user_id}")
def update_user(user_id: UUID, payload: UserUpdateIn, _admin=Depends(require_training_admin)):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="没有可更新字段")
    fields = []
    values = []
    for name in ("display_name", "employee_no", "role", "group_id", "is_active"):
        if name in changes:
            fields.append(f"{name}=%s")
            values.append(changes[name])
    values.append(user_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE training_users SET {','.join(fields)},updated_at=NOW() WHERE id=%s RETURNING *", values)
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        conn.commit()
        return _public_user(user)


@router.get("/admin/groups")
def list_groups(_admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT g.*,COUNT(u.id) FILTER (WHERE u.role='learner') AS learner_count
               FROM training_groups g LEFT JOIN training_users u ON u.group_id=g.id
               GROUP BY g.id ORDER BY g.created_at DESC"""
        )
        return cur.fetchall()


@router.post("/admin/groups", status_code=201)
def create_group(payload: GroupIn, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO training_groups(name) VALUES(%s) RETURNING *", (payload.name.strip(),))
        group = cur.fetchone()
        conn.commit()
        return {**group, "learner_count": 0}


@router.get("/admin/groups/{group_id}")
def group_detail(group_id: UUID, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM training_groups WHERE id=%s", (group_id,))
        group = cur.fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="班级不存在")
        cur.execute("SELECT * FROM training_users WHERE group_id=%s AND role='learner' ORDER BY display_name,email", (group_id,))
        learners = [_public_user(row) for row in cur.fetchall()]
        return {**group, "learner_count": len(learners), "learners": learners}


@router.put("/admin/groups/{group_id}")
def rename_group(group_id: UUID, payload: GroupIn, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE training_groups SET name=%s WHERE id=%s RETURNING *", (payload.name.strip(), group_id))
        group = cur.fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="班级不存在")
        conn.commit()
        return group


@router.delete("/admin/groups/{group_id}", status_code=204)
def delete_group(group_id: UUID, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM training_groups WHERE id=%s RETURNING id", (group_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="班级不存在")
        conn.commit()
        return None


@router.post("/admin/groups/{group_id}/members/{learner_id}", status_code=204)
def add_group_member(group_id: UUID, learner_id: UUID, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM training_groups WHERE id=%s", (group_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="班级不存在")
        cur.execute("UPDATE training_users SET group_id=%s,updated_at=NOW() WHERE id=%s AND role='learner' RETURNING id", (group_id, learner_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="学员不存在")
        conn.commit()
        return None


@router.delete("/admin/groups/{group_id}/members/{learner_id}", status_code=204)
def remove_group_member(group_id: UUID, learner_id: UUID, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE training_users SET group_id=NULL,updated_at=NOW() WHERE id=%s AND group_id=%s RETURNING id", (learner_id, group_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="班级中的学员不存在")
        conn.commit()
        return None


@router.get("/admin/learners")
def list_learners(_admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT u.*,
                (SELECT COUNT(*) FROM training_assignments a WHERE a.learner_id=u.id) assignment_count,
                (SELECT COUNT(*) FROM training_assignments a WHERE a.learner_id=u.id AND a.status='completed') completed_count,
                COALESCE((SELECT AVG(a.progress_percent) FROM training_assignments a WHERE a.learner_id=u.id),0) avg_progress,
                COALESCE((SELECT SUM(p.effective_seconds) FROM training_progress p JOIN training_assignments a ON a.id=p.assignment_id WHERE a.learner_id=u.id),0) total_seconds
                FROM training_users u WHERE u.role='learner' ORDER BY u.created_at DESC"""
        )
        return cur.fetchall()


@router.get("/admin/dashboard")
def admin_dashboard(_admin=Depends(require_training_admin)):
    """Return the compact learning metrics consumed by the production admin UI."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE role='learner' AND is_active) AS learning_people_count
               FROM training_users"""
        )
        people = cur.fetchone()["learning_people_count"]

        cur.execute(
            """SELECT COALESCE(SUM(effective_seconds), 0) AS total_effective_seconds
               FROM training_progress"""
        )
        total_seconds = cur.fetchone()["total_effective_seconds"]

        cur.execute(
            """SELECT COALESCE(AVG(progress_percent), 0) AS overall_completion_rate,
                      COUNT(*) FILTER (WHERE status='completed') AS task_completion_count
               FROM training_assignments"""
        )
        assignment_metrics = cur.fetchone()

        cur.execute(
            """SELECT l.title,
                      l.sort_order AS chapter_no,
                      CASE WHEN COUNT(p.id)=0 THEN 0
                           ELSE ROUND(100.0 * COUNT(p.id) FILTER (WHERE p.completed) / COUNT(p.id), 2)
                      END AS completion_rate
               FROM lessons l
               JOIN courses c ON c.id=l.course_id
               JOIN projects project ON project.id=c.project_id AND project.code='broadcast'
               LEFT JOIN training_progress p ON p.lesson_id=l.id
               GROUP BY l.id, l.title, l.sort_order
               ORDER BY completion_rate DESC, l.sort_order
               LIMIT 5"""
        )
        content_top5 = cur.fetchall()

        cur.execute(
            """SELECT day::date AS date, COUNT(DISTINCT e.learner_id) AS active
               FROM generate_series(CURRENT_DATE - INTERVAL '6 days', CURRENT_DATE, INTERVAL '1 day') day
               LEFT JOIN training_events e ON e.created_at >= day AND e.created_at < day + INTERVAL '1 day'
               GROUP BY day ORDER BY day"""
        )
        daily_trend = cur.fetchall()

        return {
            "learning_people_count": people,
            "total_effective_seconds": total_seconds,
            "avg_seconds_per_person": round(total_seconds / people, 2) if people else 0,
            "overall_completion_rate": assignment_metrics["overall_completion_rate"],
            "task_completion_count": assignment_metrics["task_completion_count"],
            "content_completion_top5": content_top5,
            "daily_active_trend": daily_trend,
        }


@router.get("/admin/learners/{learner_id}")
def learner_detail(learner_id: UUID, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT u.*,g.name AS group_name,
                      COALESCE((SELECT AVG(a.progress_percent) FROM training_assignments a WHERE a.learner_id=u.id),0) AS avg_progress,
                      COALESCE((SELECT SUM(p.effective_seconds) FROM training_progress p JOIN training_assignments a ON a.id=p.assignment_id WHERE a.learner_id=u.id),0) AS total_seconds,
                      (SELECT COUNT(DISTINCT e.created_at::date) FROM training_events e WHERE e.learner_id=u.id) AS active_days
               FROM training_users u LEFT JOIN training_groups g ON g.id=u.group_id
               WHERE u.id=%s AND u.role='learner'""",
            (learner_id,),
        )
        profile = cur.fetchone()
        if not profile:
            raise HTTPException(status_code=404, detail="学员不存在")
        profile.pop("password_hash", None)
        cur.execute(
            """SELECT a.*,t.title AS task_title,t.task_type,t.due_at
               FROM training_assignments a JOIN training_tasks t ON t.id=a.task_id
               WHERE a.learner_id=%s ORDER BY t.due_at DESC""",
            (learner_id,),
        )
        assignments = cur.fetchall()
        cur.execute(
            """SELECT day::date AS date,
                      ROUND(COALESCE(SUM(p.effective_seconds),0)/3600.0,2) AS hours
               FROM generate_series(CURRENT_DATE - INTERVAL '6 days', CURRENT_DATE, INTERVAL '1 day') day
               LEFT JOIN (
                   SELECT p.updated_at,p.effective_seconds
                   FROM training_progress p JOIN training_assignments a ON a.id=p.assignment_id
                   WHERE a.learner_id=%s
               ) p ON p.updated_at >= day AND p.updated_at < day + INTERVAL '1 day'
               GROUP BY day ORDER BY day""",
            (learner_id,),
        )
        duration_trend = cur.fetchall()
        cur.execute(
            """SELECT e.*,c.title AS course_title
               FROM training_events e LEFT JOIN courses c ON c.id=e.course_id
               WHERE e.learner_id=%s ORDER BY e.created_at DESC LIMIT 100""",
            (learner_id,),
        )
        return {"profile": profile, "assignments": assignments, "duration_trend": duration_trend, "events": cur.fetchall()}


@router.get("/admin/events")
def admin_events(
    learner_id: UUID | None = None,
    event_type: str | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_training_admin),
):
    clauses = []
    params = []
    if learner_id:
        clauses.append("e.learner_id=%s")
        params.append(learner_id)
    if event_type:
        clauses.append("e.event_type=%s")
        params.append(event_type)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT e.*,u.display_name,u.employee_no,c.title AS course_title,l.title AS content
               FROM training_events e JOIN training_users u ON u.id=e.learner_id
               LEFT JOIN courses c ON c.id=e.course_id LEFT JOIN lessons l ON l.id=e.lesson_id"""
            + where + " ORDER BY e.created_at DESC LIMIT %s OFFSET %s",
            params,
        )
        return cur.fetchall()


@router.get("/record")
def learning_record(user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(SUM(p.effective_seconds),0) AS total_effective_seconds,
                      COUNT(p.id) FILTER (WHERE p.completed) AS completed_contents
               FROM training_progress p JOIN training_assignments a ON a.id=p.assignment_id
               WHERE a.learner_id=%s""",
            (user["id"],),
        )
        stats = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS total_events FROM training_events WHERE learner_id=%s", (user["id"],))
        stats["total_events"] = cur.fetchone()["total_events"]
        cur.execute("SELECT COALESCE(AVG(progress_percent),0) AS rate FROM training_assignments WHERE learner_id=%s", (user["id"],))
        stats["task_completion_rate"] = cur.fetchone()["rate"]
        cur.execute(
            """SELECT p.*,l.title AS chapter_title,l.sort_order AS day_no
               FROM training_progress p JOIN training_assignments a ON a.id=p.assignment_id
               JOIN lessons l ON l.id=p.lesson_id WHERE a.learner_id=%s
               ORDER BY p.updated_at DESC LIMIT 10""",
            (user["id"],),
        )
        recent_content = cur.fetchall()
        cur.execute(
            "SELECT event_type,COUNT(*) AS count FROM training_events WHERE learner_id=%s GROUP BY event_type ORDER BY count DESC",
            (user["id"],),
        )
        event_distribution = cur.fetchall()
        cur.execute(
            """SELECT day::date AS date,COUNT(e.id) AS count
               FROM generate_series(CURRENT_DATE - INTERVAL '6 days', CURRENT_DATE, INTERVAL '1 day') day
               LEFT JOIN training_events e ON e.learner_id=%s AND e.created_at >= day AND e.created_at < day + INTERVAL '1 day'
               GROUP BY day ORDER BY day""",
            (user["id"],),
        )
        return {"stats": stats, "recent_content": recent_content, "event_distribution": event_distribution, "calendar_7d": cur.fetchall()}


def _assignment_view(cur, assignment_id: UUID) -> dict | None:
    cur.execute(
        """SELECT a.id assignment_id,t.id task_id,t.title task_title,t.task_type,
                  t.course_id,c.title course_title,p.code course_type,
                  t.chapter_from,t.chapter_to,t.day_from,t.day_to,a.status,a.progress_percent,
                  a.started_at,a.completed_at,t.due_at
           FROM training_assignments a JOIN training_tasks t ON t.id=a.task_id
           JOIN courses c ON c.id=t.course_id JOIN projects p ON p.id=c.project_id
           WHERE a.id=%s""",
        (assignment_id,),
    )
    return cur.fetchone()


@router.get("/tasks/my")
def my_tasks(user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM training_assignments WHERE learner_id=%s ORDER BY created_at DESC", (user["id"],))
        ids = [row["id"] for row in cur.fetchall()]
        return [_assignment_view(cur, assignment_id) for assignment_id in ids]


@router.post("/admin/tasks", status_code=201)
def create_task(payload: TaskCreateIn, admin=Depends(require_training_admin)):
    if payload.due_at <= payload.start_at:
        raise HTTPException(status_code=400, detail="截止时间必须晚于开始时间")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT c.id,p.code FROM courses c JOIN projects p ON p.id=c.project_id WHERE c.id=%s", (payload.course_id,))
        course = cur.fetchone()
        if not course or course["code"] != "broadcast":
            raise HTTPException(status_code=400, detail="本版本仅支持广播词课程任务")
        instructor_id = payload.instructor_id if payload.task_type == "exam" else None
        cur.execute(
            """INSERT INTO training_tasks(title,task_type,course_id,chapter_from,chapter_to,day_from,day_to,start_at,due_at,completion_rule,status,created_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING *""",
            (payload.title,payload.task_type,payload.course_id,payload.chapter_from,payload.chapter_to,
             payload.day_from,payload.day_to,payload.start_at,payload.due_at,
             json.dumps(payload.completion_rule,ensure_ascii=False),payload.status,admin["id"]),
        )
        task = cur.fetchone()
        for learner_id in payload.learner_ids:
            cur.execute("SELECT 1 FROM training_users WHERE id=%s AND role='learner' AND is_active", (learner_id,))
            if cur.fetchone():
                cur.execute(
                    "INSERT INTO training_assignments(task_id,learner_id,instructor_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (task["id"],learner_id,instructor_id),
                )
        conn.commit()
        return {"task": task, "assignments_created": len(payload.learner_ids)}


@router.get("/admin/tasks")
def admin_tasks(_admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM training_tasks ORDER BY created_at DESC")
        tasks = cur.fetchall()
        out = []
        for task in tasks:
            cur.execute("SELECT COUNT(*) total,COUNT(*) FILTER(WHERE status='completed') completed FROM training_assignments WHERE task_id=%s", (task["id"],))
            counts = cur.fetchone()
            total, completed = counts["total"], counts["completed"]
            out.append({"task": task,"assignment_count": total,"completed_count": completed,"completion_rate": round(completed*100/total,2) if total else 0})
        return out


@router.get("/tasks/{task_id}/detail")
def task_detail(task_id: int, user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM training_assignments WHERE task_id=%s AND learner_id=%s", (task_id,user["id"]))
        assignment = cur.fetchone()
        if not assignment:
            raise HTTPException(status_code=404, detail="你尚未被分配到该任务")
        cur.execute("SELECT t.*,c.title course_title,c.description,p.code course_type FROM training_tasks t JOIN courses c ON c.id=t.course_id JOIN projects p ON p.id=c.project_id WHERE t.id=%s", (task_id,))
        task = cur.fetchone()
        cur.execute("SELECT * FROM lessons WHERE course_id=%s ORDER BY sort_order,id", (task["course_id"],))
        lessons = cur.fetchall()[task["day_from"]-1:task["day_to"]]
        days=[]
        for index, lesson in enumerate(lessons, start=task["day_from"]):
            cur.execute("SELECT completed,id FROM training_progress WHERE assignment_id=%s AND lesson_id=%s", (assignment["id"],lesson["id"]))
            progress=cur.fetchone()
            days.append({"chapter_no":1,"day_no":index,"chapter_title":lesson["title"],"contents":[{"id":str(lesson["id"]),"content_type":"sentence","payload":lesson["content"],"completed":bool(progress and progress["completed"]),"progress_id":str(progress["id"]) if progress else None}]})
        return {"task":task,"course":{"id":task["course_id"],"title":task["course_title"],"description":task["description"],"course_type":task["course_type"]},"days":days,"assignment":assignment}


def _lesson_blocks(lesson: dict) -> list[dict]:
    content = lesson["content"] or {}
    audio = {"normal":content.get("standard_audio_url"),"slow":content.get("slow_audio_url")}
    base = str(lesson["id"])
    return [
        {"id":base,"course_id":lesson["course_id"],"chapter_no":1,"chapter_title":lesson["title"],"day_no":1,"content_order":1,"content_type":"sentence","payload":{"id":f"broadcast-{base}","zh":content.get("chinese_text", ""),"en":content.get("english_text", ""),"note":"","audio":audio}},
        {"id":base,"course_id":lesson["course_id"],"chapter_no":1,"chapter_title":lesson["title"],"day_no":1,"content_order":2,"content_type":"vocabulary","payload":{"items":content.get("key_words", [])}},
        {"id":base,"course_id":lesson["course_id"],"chapter_no":1,"chapter_title":lesson["title"],"day_no":1,"content_order":3,"content_type":"summary","payload":{"text":"完成本课练习并保存学习进度。"}},
    ]


@router.get("/content")
def content(course_id: int, chapter_no: int = 1, day_no: int = 1, _user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT l.* FROM lessons l JOIN courses c ON c.id=l.course_id JOIN projects p ON p.id=c.project_id WHERE l.course_id=%s AND p.code='broadcast' ORDER BY l.sort_order,l.id", (course_id,))
        rows=cur.fetchall()
        if day_no < 1 or day_no > len(rows):
            return []
        blocks=_lesson_blocks(rows[day_no-1])
        for block in blocks:
            block["day_no"]=day_no
        return blocks


@router.post("/progress")
def save_progress(payload: ProgressIn, user=Depends(get_current_user)):
    lesson_id=_lesson_id(payload.content_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT a.*,t.day_from,t.day_to,t.course_id FROM training_assignments a JOIN training_tasks t ON t.id=a.task_id WHERE a.id=%s AND a.learner_id=%s", (payload.assignment_id,user["id"]))
        assignment=cur.fetchone()
        if not assignment:
            raise HTTPException(status_code=404, detail="任务分配不存在")
        cur.execute("""INSERT INTO training_progress(assignment_id,lesson_id,completed,effective_seconds,last_position,attempt_count)
                       VALUES(%s,%s,%s,%s,%s::jsonb,1)
                       ON CONFLICT(assignment_id,lesson_id) DO UPDATE SET completed=EXCLUDED.completed,effective_seconds=training_progress.effective_seconds+EXCLUDED.effective_seconds,last_position=EXCLUDED.last_position,attempt_count=training_progress.attempt_count+1,updated_at=NOW() RETURNING *""",
                    (payload.assignment_id,lesson_id,payload.completed,payload.effective_seconds,json.dumps(payload.last_position or {},ensure_ascii=False)))
        progress=cur.fetchone()
        cur.execute("SELECT COUNT(*) total,COUNT(*) FILTER(WHERE completed) done FROM training_progress WHERE assignment_id=%s", (payload.assignment_id,))
        counts=cur.fetchone(); expected=max(1,assignment["day_to"]-assignment["day_from"]+1); percent=min(100,round(counts["done"]*100/expected,2))
        cur.execute("UPDATE training_assignments SET progress_percent=%s,status=CASE WHEN %s>=100 THEN 'completed' ELSE 'in_progress' END,started_at=COALESCE(started_at,NOW()),completed_at=CASE WHEN %s>=100 THEN NOW() ELSE completed_at END,updated_at=NOW() WHERE id=%s RETURNING *", (percent,percent,percent,payload.assignment_id))
        updated=cur.fetchone(); conn.commit(); return {"progress":progress,"assignment":updated}


@router.get("/progress")
def get_progress(assignment_id: UUID, user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM training_assignments WHERE id=%s AND (learner_id=%s OR %s IN ('instructor','admin'))", (assignment_id,user["id"],user["role"]))
        assignment=cur.fetchone()
        if not assignment: raise HTTPException(status_code=404,detail="任务分配不存在")
        cur.execute("SELECT p.*,p.lesson_id content_id FROM training_progress p WHERE p.assignment_id=%s ORDER BY p.updated_at DESC", (assignment_id,))
        return {"assignment":assignment,"items":cur.fetchall()}


@router.post("/events", status_code=201)
def add_event(payload: EventIn, user=Depends(get_current_user)):
    lesson_id=_lesson_id(payload.content_id) if payload.content_id else None
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO training_events(learner_id,assignment_id,course_id,lesson_id,event_type,event_value,client_timestamp) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING *", (user["id"],payload.assignment_id,payload.course_id,lesson_id,payload.event_type,json.dumps(payload.event_value or {},ensure_ascii=False),payload.client_timestamp))
        row=cur.fetchone(); conn.commit(); return row


@router.post("/practice/attempts", status_code=201)
def practice_attempt(payload: PracticeAttemptIn, user=Depends(get_current_user)):
    lesson_id=_lesson_id(payload.content_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT a.*,t.task_type,t.course_id FROM training_assignments a JOIN training_tasks t ON t.id=a.task_id WHERE a.id=%s AND a.learner_id=%s", (payload.assignment_id,user["id"]))
        assignment=cur.fetchone()
        if not assignment or assignment["task_type"]!="practice": raise HTTPException(status_code=409,detail="该任务不是练习任务")
        cur.execute("SELECT content FROM lessons WHERE id=%s AND course_id=%s", (lesson_id,assignment["course_id"]))
        lesson=cur.fetchone()
        if not lesson: raise HTTPException(status_code=400,detail="广播词内容无效")
        reference=(lesson["content"] or {}).get("english_text","")
        cur.execute("SELECT attempt_no,feedback FROM practice_attempts WHERE assignment_id=%s AND lesson_id=%s ORDER BY attempt_no DESC LIMIT 1", (payload.assignment_id,lesson_id))
        previous=cur.fetchone(); previous_score=int((previous["feedback"] or {}).get("overall_score",0)) if previous else None; attempt_no=(previous["attempt_no"]+1) if previous else 1
        feedback=_practice_feedback(reference,payload.transcript,previous_score)
        cur.execute("INSERT INTO practice_attempts(assignment_id,learner_id,lesson_id,attempt_no,audio_url,transcript,reference_text,feedback) VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING *", (payload.assignment_id,user["id"],lesson_id,attempt_no,payload.audio_url,payload.transcript,reference,json.dumps(feedback,ensure_ascii=False)))
        row=cur.fetchone(); cur.execute("UPDATE training_assignments SET status='in_progress',started_at=COALESCE(started_at,NOW()),updated_at=NOW() WHERE id=%s AND status='not_started'",(payload.assignment_id,)); conn.commit(); return {**row,"content_id":str(lesson_id)}


@router.get("/practice/history")
def practice_history(assignment_id: UUID, content_id: str | None = None, user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT learner_id FROM training_assignments WHERE id=%s", (assignment_id,)); assignment=cur.fetchone()
        if not assignment or (user["role"]=="learner" and assignment["learner_id"]!=user["id"]): raise HTTPException(status_code=403,detail="无权查看")
        sql="SELECT *,lesson_id content_id FROM practice_attempts WHERE assignment_id=%s"; params=[assignment_id]
        if content_id: sql+=" AND lesson_id=%s"; params.append(_lesson_id(content_id))
        cur.execute(sql+" ORDER BY created_at DESC LIMIT 100",params); return cur.fetchall()


def _exam_view(cur, submission_id: int) -> dict | None:
    cur.execute("""SELECT e.*,e.final_score score,'broadcast_recording' assessment_type,u.display_name learner_name,t.title task_title,c.title course_title
                   FROM exam_submissions e JOIN training_users u ON u.id=e.learner_id JOIN training_assignments a ON a.id=e.assignment_id JOIN training_tasks t ON t.id=a.task_id JOIN courses c ON c.id=t.course_id WHERE e.id=%s""",(submission_id,))
    return cur.fetchone()


@router.post("/assessments/submit", status_code=201)
def submit_exam(payload: ExamSubmitIn, user=Depends(get_current_user)):
    if not payload.answers.get("cn_audio_url") or not payload.answers.get("en_audio_url"): raise HTTPException(status_code=400,detail="考试需提交完整中文和英文录音")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT a.*,t.task_type,t.completion_rule FROM training_assignments a JOIN training_tasks t ON t.id=a.task_id WHERE a.id=%s AND a.learner_id=%s",(payload.assignment_id,user["id"])); assignment=cur.fetchone()
        if not assignment or assignment["task_type"]!="exam": raise HTTPException(status_code=409,detail="该任务不是考试任务")
        cur.execute("SELECT COUNT(*) total FROM exam_submissions WHERE assignment_id=%s",(payload.assignment_id,)); used=cur.fetchone()["total"]; max_attempts=max(1,int((assignment["completion_rule"] or {}).get("max_recordings",1)))
        if used>=max_attempts: raise HTTPException(status_code=409,detail="已达到考试允许的提交次数")
        cur.execute("INSERT INTO exam_submissions(assignment_id,learner_id,attempt_no,answers,ai_result) VALUES(%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING id",(payload.assignment_id,user["id"],used+1,json.dumps(payload.answers,ensure_ascii=False),json.dumps({"status":"pending_adapter","formal":True})))
        row_id=cur.fetchone()["id"]; cur.execute("UPDATE training_assignments SET status='in_progress',started_at=COALESCE(started_at,NOW()),updated_at=NOW() WHERE id=%s",(payload.assignment_id,)); conn.commit(); return _exam_view(cur,row_id)


@router.get("/assessments/my")
def my_exams(user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM exam_submissions WHERE learner_id=%s ORDER BY created_at DESC",(user["id"],)); ids=[r["id"] for r in cur.fetchall()]; out=[]
        for sid in ids:
            row=_exam_view(cur,sid)
            if row["status"]!="published": row={**row,"score":None,"final_score":None,"manual_score":None,"ai_score":None,"ai_result":{},"feedback":None}
            out.append(row)
        return out


@router.get("/assessments/pending")
def pending_exams(user=Depends(require_instructor)):
    with get_connection() as conn, conn.cursor() as cur:
        sql="SELECT e.id FROM exam_submissions e JOIN training_assignments a ON a.id=e.assignment_id WHERE e.status='submitted'"
        params=[]
        if user["role"]=="instructor": sql+=" AND a.instructor_id=%s"; params.append(user["id"])
        cur.execute(sql+" ORDER BY e.created_at",params); return [_exam_view(cur,r["id"]) for r in cur.fetchall()]


@router.get("/admin/assessments")
def admin_exams(_admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM exam_submissions ORDER BY created_at DESC LIMIT 500"); return [_exam_view(cur,r["id"]) for r in cur.fetchall()]


@router.put("/admin/assignments/{assignment_id}/instructor", status_code=204)
def assign_instructor(assignment_id: UUID, instructor_id: UUID, _admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM training_users WHERE id=%s AND role IN ('instructor','admin') AND is_active", (instructor_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="测评员不存在或账号不可用")
        cur.execute("UPDATE training_assignments SET instructor_id=%s,updated_at=NOW() WHERE id=%s RETURNING id", (instructor_id,assignment_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="任务分配不存在")
        conn.commit()
        return None


@router.get("/assessments/{submission_id}")
def get_exam(submission_id: int, user=Depends(get_current_user)):
    with get_connection() as conn, conn.cursor() as cur:
        row=_exam_view(cur,submission_id)
        if not row or (user["role"]=="learner" and row["learner_id"]!=user["id"]): raise HTTPException(status_code=404,detail="测评不存在")
        return row


@router.post("/assessments/{submission_id}/grade")
def grade_exam(submission_id: int,payload: GradeIn,user=Depends(require_instructor)):
    with get_connection() as conn, conn.cursor() as cur:
        row=_exam_view(cur,submission_id)
        if not row: raise HTTPException(status_code=404,detail="测评不存在")
        cur.execute("SELECT instructor_id FROM training_assignments WHERE id=%s",(row["assignment_id"],)); assigned=cur.fetchone()["instructor_id"]
        if user["role"]=="instructor" and assigned not in (None,user["id"]): raise HTTPException(status_code=403,detail="非你负责的测评")
        ai=row["ai_score"]; final=ai if payload.score is None else payload.score if ai is None else round((float(ai)+payload.score)/2,2)
        cur.execute("UPDATE exam_submissions SET manual_score=%s,final_score=%s,feedback=%s,status=%s,instructor_id=%s,graded_at=NOW(),updated_at=NOW() WHERE id=%s",(payload.score,final,payload.feedback,payload.status,user["id"],submission_id)); conn.commit(); return _exam_view(cur,submission_id)


@router.post("/admin/assessments/{submission_id}/publish")
def publish_exam(submission_id: int,_admin=Depends(require_training_admin)):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE exam_submissions SET status='published',published_at=NOW(),updated_at=NOW() WHERE id=%s AND status='graded' RETURNING id",(submission_id,))
        if not cur.fetchone(): raise HTTPException(status_code=409,detail="只有已评分成绩可以发布")
        conn.commit(); return _exam_view(cur,submission_id)
