from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.case_comment import CaseComment


CASE_STATUS_OPEN = "OPEN"
CASE_STATUS_IN_PROGRESS = "IN_PROGRESS"
CASE_STATUS_CLOSED = "CLOSED"
CASE_STATUSES = {CASE_STATUS_OPEN, CASE_STATUS_IN_PROGRESS, CASE_STATUS_CLOSED}

ALLOWED_STATUS_TRANSITIONS = {
    CASE_STATUS_OPEN: {CASE_STATUS_IN_PROGRESS, CASE_STATUS_CLOSED},
    CASE_STATUS_IN_PROGRESS: {CASE_STATUS_CLOSED},
    CASE_STATUS_CLOSED: set(),
}


class CaseService:
    """Owns case creation, status transitions, and comments."""

    @staticmethod
    def create_case_from_alert(alert: Alert, db: Session) -> Case | None:
        if alert.id is None:
            raise ValueError("Cases can only be created from persisted alerts.")

        existing_case = db.query(Case).filter(Case.alert_id == alert.id).one_or_none()
        if existing_case is not None:
            return None

        case = Case(
            case_code=CaseService.case_code_for(alert.id),
            alert_id=alert.id,
            status=CASE_STATUS_OPEN,
            priority=alert.priority,
            assigned_to=alert.assigned_to,
        )
        db.add(case)
        return case

    @staticmethod
    def update_status(case: Case, new_status: str) -> Case:
        if new_status not in CASE_STATUSES:
            raise ValueError(f"Unsupported case status: {new_status}")
        if new_status not in ALLOWED_STATUS_TRANSITIONS[case.status]:
            raise ValueError(f"Invalid case status transition: {case.status} -> {new_status}")

        case.status = new_status
        if new_status == CASE_STATUS_CLOSED:
            case.closed_at = datetime.now(timezone.utc)
        return case

    @staticmethod
    def update_priority(case: Case, priority: int) -> Case:
        if priority not in {1, 2, 3, 4}:
            raise ValueError("Unsupported case priority.")
        case.priority = priority
        return case

    @staticmethod
    def update_assignment(case: Case, assigned_to: str | None) -> Case:
        if assigned_to is not None:
            assigned_to = assigned_to.strip()
            if not assigned_to:
                raise ValueError("assigned_to must not be blank.")
        case.assigned_to = assigned_to
        return case

    @staticmethod
    def add_comment(case: Case, comment: str, created_by: str, db: Session) -> CaseComment:
        comment = comment.strip()
        created_by = created_by.strip()
        if not comment or not created_by:
            raise ValueError("Comment and created_by must not be blank.")

        case_comment = CaseComment(
            case_id=case.id,
            comment=comment,
            created_by=created_by,
        )
        db.add(case_comment)
        case.updated_at = datetime.now(timezone.utc)
        return case_comment

    @staticmethod
    def case_code_for(alert_id: int) -> str:
        return f"CASE-A{alert_id:08d}"
