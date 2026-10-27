from fastapi import HTTPException

from ...integrations.ai_gateway import AIGateway, aggregate_status
from .domain import ExamAssignment, ExamTask, PracticeAttempt, PracticeTask, TrainingStore, new_id
from .schemas import ExamSubmit, LearnerPracticeSubmit, PracticeAttemptCreate


class PracticeService:
    def __init__(self, store: TrainingStore, gateway: AIGateway | None = None) -> None:
        self.store, self.gateway = store, gateway or AIGateway()

    def submit_attempt(self, data: PracticeAttemptCreate, user_id: str):
        assignment = self.store.get_practice_assignment(data.assignment_id, user_id)
        if not assignment:
            raise HTTPException(404, "Practice assignment not found")
        task = self.store.get_practice_task(assignment.task_id)
        if not task:
            raise HTTPException(409, "Assignment is not a practice task")
        if task.status != "published":
            raise HTTPException(409, "Practice task is not open")
        attempt_no = self.store.practice_attempt_count(assignment.id) + 1
        attempt = PracticeAttempt(new_id("pat"), assignment.id, data.segment_id, data.audio_ref, attempt_no, self.store.now())
        results = self.gateway.analyze(reference_text=data.reference_text, audio_ref=data.audio_ref)
        attempt.ai_status = aggregate_status(results)
        feedback = {"ai_status": attempt.ai_status, "issues": [{"source": r.adapter, "status": r.status} for r in results]}
        self.store.save_practice_attempt(attempt, feedback)
        return {
            "attempt_id": attempt.id,
            "mode": "practice",
            "ai_status": attempt.ai_status,
            "issues": [{"source": r.adapter, "status": r.status} for r in results],
            "next_action": "review_feedback_and_retry",
            "attempt_no": attempt_no,
        }


class ExamService:
    def __init__(self, store: TrainingStore) -> None:
        self.store = store

    def submit_whole_paper(self, data: ExamSubmit, user_id: str, task_id: str | None = None):
        assignment = self.store.get_exam_assignment(data.assignment_id, user_id)
        if not assignment:
            raise HTTPException(404, "Exam assignment not found")
        task = self.store.get_exam_task(assignment.task_id)
        if not task:
            raise HTTPException(409, "Assignment is not an exam task")
        if task_id is not None and assignment.task_id != task_id:
            raise HTTPException(409, "Assignment does not belong to this exam task")
        if task.status not in {"open", "published"}:
            raise HTTPException(409, "Exam task is not open")
        if assignment.status in {"submitted", "graded", "published"}:
            raise HTTPException(409, "Exam already submitted")
        if len(data.recording_refs) > task.max_recordings:
            raise HTTPException(422, "Recording limit exceeded")
        if not data.paper_item_ids:
            raise HTTPException(422, "Whole paper submission is required")
        submitted_at = self.store.now()
        self.store.submit_exam_assignment(assignment, data.recording_refs, submitted_at)
        return {
            "assignment_id": assignment.id,
            "task_type": "exam",
            "status": "submitted",
            "recording_count": len(data.recording_refs),
            "max_recordings": task.max_recordings,
            "submitted_at": submitted_at,
        }


class LearnerPracticeService:
    """Course-based learner practice. Reference text always comes from the server catalog."""

    def __init__(self, store: TrainingStore, gateway: AIGateway | None = None) -> None:
        self.store, self.gateway = store, gateway or AIGateway()

    def submit(self, data: LearnerPracticeSubmit, user_id: str):
        workspace = self.store.learner_practice_workspace(data.assignment_id, user_id)
        if not workspace:
            raise HTTPException(404, "Practice assignment not found")
        content = next((item for item in workspace["contents"] if item["id"] == data.content_item_id), None)
        if not content:
            raise HTTPException(409, "Content does not belong to this assignment")
        if content.get('learning_card_id'):
            raise HTTPException(409, '学习卡片仅记录阅读，不提交录音或生成 AI 分数')
        task = self.store.get_practice_task(workspace["task_id"])
        if not task or task.status != "published":
            raise HTTPException(409, "Practice task is not open")
        if not content["reference_text"]:
            raise HTTPException(409, "Course standard text is empty")
        recording = getattr(self.store, "recordings", {}).get(data.recording_id) if hasattr(self.store, "recordings") else None
        audio_ref = recording["audio_ref"] if recording else self.store.get_recording_audio_ref(data.recording_id, data.assignment_id, user_id)
        if not audio_ref:
            raise HTTPException(409, "Recording is not ready")
        results = self.gateway.analyze(reference_text=content["reference_text"], audio_ref=audio_ref)
        normalized = [result.as_record() for result in results]
        try:
            return self.store.save_learner_practice_attempt(
                data.assignment_id, user_id, data.content_item_id, data.recording_id,
                data.correction_of_attempt_id, normalized,
                recognized_text=data.recognized_text,
                reference_text=content["reference_text"],
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def reanalyze(self, attempt_id: str, user_id: str):
        context = self.store.get_learner_attempt_reanalysis_context(attempt_id, user_id)
        if not context:
            raise HTTPException(404, "Practice attempt or recording not found")
        results = self.gateway.analyze(
            reference_text=context["reference_text"],
            audio_ref=context["audio_ref"],
        )
        normalized = [result.as_record() for result in results]
        suntone_completed = any(
            item["adapter"] == "suntone" and item["status"] == "completed"
            for item in normalized
        )
        if not suntone_completed:
            # Keep the prior saved assessment intact when a provider retry fails.
            raise HTTPException(502, "Suntone reanalysis failed; the saved result was not changed")
        try:
            return self.store.replace_learner_practice_analysis(
                attempt_id,
                user_id,
                normalized,
                recognized_text=context.get("recognized_text"),
                reference_text=context["reference_text"],
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
