from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmailReply, Enrollment, SalesTask, Suppression


def apply_classification(session: Session, reply: EmailReply, classification: str):
    reply.classification = classification
    enrollment = session.get(Enrollment, reply.enrollment_id) if reply.enrollment_id else None
    if not enrollment:
        return
    if classification == "unsubscribe" and not session.get(Suppression, enrollment.recipient):
        session.add(Suppression(email=enrollment.recipient, reason="unsubscribe"))
    if classification == "meeting_requested" and not session.scalar(
        select(SalesTask.id).where(SalesTask.reply_id == reply.id)
    ):
        session.add(SalesTask(reply_id=reply.id, title=f"Arrange a meeting with {enrollment.recipient}",
                              status="open"))
