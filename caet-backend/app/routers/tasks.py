# ============================================================
# CAET 任务路由
# 学员端：GET /tasks/my, GET /tasks/{task_id}/detail
# 管理端：POST /admin/tasks, GET /admin/tasks
# （以上均相对于 /api 前缀）
# ============================================================
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import get_current_user, require_admin
from ..models import Course, CourseContent, LearnerProgress, Profile, Task, TaskAssignment
from ..schemas import AssignmentOut, TaskAdminOut, TaskCreateIn

router = APIRouter()


def _build_assignment_out(assignment: TaskAssignment, task: Task, course: Course | None) -> AssignmentOut:
    return AssignmentOut(
        assignment_id=assignment.id,
        task_id=task.id,
        task_title=task.title,
        course_id=task.course_id,
        course_title=course.title if course else "",
        course_type=course.course_type if course else None,
        chapter_from=task.chapter_from,
        chapter_to=task.chapter_to,
        day_from=task.day_from,
        day_to=task.day_to,
        status=assignment.status,
        progress_percent=float(assignment.progress_percent or 0),
        started_at=assignment.started_at,
        completed_at=assignment.completed_at,
        due_at=task.due_at,
    )


@router.get("/tasks/my", response_model=list[AssignmentOut])
async def my_tasks(
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignments = (
        await db.execute(
            select(TaskAssignment).where(TaskAssignment.learner_id == user.id)
        )
    ).scalars().all()

    result: list[AssignmentOut] = []
    for a in assignments:
        task = await db.get(Task, a.task_id)
        if task is None:
            continue
        course = await db.get(Course, task.course_id)
        result.append(_build_assignment_out(a, task, course))
    return result


@router.get("/tasks/{task_id}/detail")
async def task_detail(
    task_id: UUID,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    course = await db.get(Course, task.course_id)

    assignment = (
        await db.execute(
            select(TaskAssignment).where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.learner_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="你尚未被分配到该任务")

    # 该学员在此 assignment 下的完成状态
    prog_rows = (
        await db.execute(
            select(LearnerProgress).where(LearnerProgress.assignment_id == assignment.id)
        )
    ).scalars().all()
    prog_map = {p.content_id: p for p in prog_rows}

    # 范围内所有课程内容
    content_rows = (
        await db.execute(
            select(CourseContent)
            .where(
                CourseContent.course_id == task.course_id,
                CourseContent.chapter_no >= task.chapter_from,
                CourseContent.chapter_no <= task.chapter_to,
                CourseContent.day_no >= task.day_from,
                CourseContent.day_no <= task.day_to,
            )
            .order_by(
                CourseContent.chapter_no,
                CourseContent.day_no,
                CourseContent.content_order,
            )
        )
    ).scalars().all()

    # 按 (chapter_no, day_no) 聚合每天内容块与完成状态
    days_map: dict[tuple[int, int], dict] = {}
    for c in content_rows:
        key = (c.chapter_no, c.day_no)
        if key not in days_map:
            days_map[key] = {
                "chapter_no": c.chapter_no,
                "day_no": c.day_no,
                "chapter_title": c.chapter_title,
                "contents": [],
            }
        p = prog_map.get(c.id)
        days_map[key]["contents"].append(
            {
                **row_to_dict(c),
                "completed": bool(p.completed) if p else False,
                "progress_id": str(p.id) if p else None,
            }
        )
    days = [days_map[k] for k in sorted(days_map.keys())]

    return {
        "task": row_to_dict(task),
        "course": row_to_dict(course) if course else None,
        "days": days,
        "assignment": row_to_dict(assignment),
    }


@router.post("/admin/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreateIn,
    admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    course = await db.get(Course, payload.course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="课程不存在")

    # 可选教员预校验
    instructor_id = payload.instructor_id
    if instructor_id is not None:
        inst = await db.get(Profile, instructor_id)
        if inst is None or inst.role not in ("instructor", "admin"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="指派的教员不存在或角色错误")

    task = Task(
        title=payload.title,
        course_id=payload.course_id,
        chapter_from=payload.chapter_from,
        chapter_to=payload.chapter_to,
        day_from=payload.day_from,
        day_to=payload.day_to,
        start_at=payload.start_at,
        due_at=payload.due_at,
        completion_rule=payload.completion_rule,
        status=payload.status,
        created_by=admin.id,
    )
    db.add(task)
    await db.flush()

    created = 0
    for learner_id in payload.learner_ids:
        # 跳过已存在的分配（UNIQUE(task_id, learner_id)）
        existing = (
            await db.execute(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == task.id,
                    TaskAssignment.learner_id == learner_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        db.add(
            TaskAssignment(
                task_id=task.id,
                learner_id=learner_id,
                instructor_id=instructor_id,
                status="not_started",
                progress_percent=0,
            )
        )
        created += 1

    await db.commit()
    await db.refresh(task)
    return {"task": row_to_dict(task), "assignments_created": created}


@router.get("/admin/tasks", response_model=list[TaskAdminOut])
async def list_tasks(
    admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    tasks = (
        await db.execute(select(Task).order_by(Task.created_at.desc()))
    ).scalars().all()

    result: list[TaskAdminOut] = []
    for t in tasks:
        assignment_count = await db.scalar(
            select(func.count()).select_from(TaskAssignment).where(TaskAssignment.task_id == t.id)
        )
        completed_count = await db.scalar(
            select(func.count())
            .select_from(TaskAssignment)
            .where(TaskAssignment.task_id == t.id, TaskAssignment.status == "completed")
        )
        rate = 0.0
        if assignment_count:
            rate = round(completed_count / assignment_count * 100, 2)
        result.append(
            TaskAdminOut(
                task=row_to_dict(t),
                assignment_count=assignment_count or 0,
                completed_count=completed_count or 0,
                completion_rate=rate,
            )
        )
    return result
