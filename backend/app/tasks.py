import logging

from celery import Celery
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.imports import process_batch
from app.models import Batch
from app.models import EmailMessage, MailboxState, now
from app.mailbox import lock_mail_workflow, poll_mailbox
from app.mailer import claim, send_claimed
from app import bedrock
from app.models import EmailReply
from app.reply_actions import apply_classification

logger = logging.getLogger(__name__)
celery_app = Celery("prospecting", broker=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "dispatch-pending-imports": {"task": "app.tasks.dispatch_pending", "schedule": 10.0},
        "poll-inbox": {"task": "app.tasks.poll_inbox", "schedule": 30.0},
        "dispatch-due-mail": {"task": "app.tasks.dispatch_due_mail", "schedule": 30.0},
        "classify-replies": {"task": "app.tasks.classify_replies", "schedule": 60.0},
        "poll-meeting-artifacts": {"task": "app.tasks.poll_meeting_artifacts", "schedule": 300.0},
        "cleanup-expired-booking-reservations": {"task": "app.tasks.cleanup_expired_booking_reservations_task", "schedule": 60.0},
    },
)


@celery_app.task(name="app.tasks.dispatch_pending")
def dispatch_pending():
    with SessionLocal() as session:
        ids = session.scalars(select(Batch.id).where(Batch.status == "pending").limit(100)).all()
    for batch_id in ids:
        import_batch.delay(batch_id)


@celery_app.task(name="app.tasks.import_batch")
def import_batch(batch_id: str):
    try:
        with SessionLocal.begin() as session:
            process_batch(session, batch_id)
    except Exception:
        logger.exception("Import failed for batch %s", batch_id)
        with SessionLocal.begin() as session:
            batch = session.get(Batch, batch_id)
            if batch and batch.status == "pending":
                batch.status = "failed"
                batch.error = "Import failed. Check worker logs and retry."
        raise


@celery_app.task(name="app.tasks.poll_inbox")
def poll_inbox():
    if not settings.gmail_address or not settings.gmail_app_password:
        return
    try:
        with SessionLocal.begin() as session:
            poll_mailbox(session)
    except RuntimeError as exc:
        logger.warning("Inbox polling failed: %s", exc)
        with SessionLocal.begin() as session:
            state = session.get(MailboxState, 1)
            if state is None:
                state = MailboxState(id=1, last_uid=0)
                session.add(state)
            state.last_error = str(exc)
            state.last_success_at = None


@celery_app.task(name="app.tasks.dispatch_due_mail")
def dispatch_due_mail():
    if not settings.mail_send_enabled:
        return
    with SessionLocal() as session:
        ids = session.scalars(select(EmailMessage.id).where(
            EmailMessage.status == "approved", EmailMessage.due_at <= now()
        ).limit(100)).all()
    for message_id in ids:
        send_due_mail.delay(message_id)


@celery_app.task(name="app.tasks.send_due_mail")
def send_due_mail(message_id: str):
    if claim(message_id):
        send_claimed(message_id)


@celery_app.task(name="app.tasks.classify_replies")
def classify_replies():
    if not settings.aws_region or not settings.bedrock_model_id:
        return
    with SessionLocal() as session:
        replies = session.scalars(select(EmailReply).where(
            EmailReply.enrollment_id.is_not(None), EmailReply.classification.is_(None)
        ).limit(25)).all()
        pending = [(reply.id, reply.body) for reply in replies]
    for reply_id, body in pending:
        try:
            classification = bedrock.classify_reply(body)
        except RuntimeError as exc:
            logger.warning("Reply classification failed for %s: %s", reply_id, exc)
            continue
        with SessionLocal.begin() as session:
            lock_mail_workflow(session)
            reply = session.get(EmailReply, reply_id)
            if not reply or reply.classification is not None:
                continue
            apply_classification(session, reply, classification)


@celery_app.task(name="app.company_intelligence.run_research")
def run_company_research(job_id: str):
    from sqlalchemy import select

    from app.company_intelligence.orchestrator import run_research_job
    from app.company_intelligence.models import ResearchAgentRun, ResearchJob

    try:
        return run_research_job(job_id)
    except Exception:
        logger.exception("Company intelligence job failed unexpectedly: %s", job_id)
        with SessionLocal.begin() as session:
            job = session.get(ResearchJob, job_id)
            if job and job.status not in {"cancelled", "completed"}:
                job.status, job.stage, job.error, job.finished_at = (
                    "failed", "worker_error", "Research encountered an internal worker error. See worker logs.", now()
                )
                for run in session.scalars(select(ResearchAgentRun).where(
                    ResearchAgentRun.job_id == job_id, ResearchAgentRun.status == "running"
                )):
                    run.status, run.error, run.finished_at = (
                        "failed", "Research encountered an internal worker error.", now()
                    )
        return {"status": "failed"}


@celery_app.task(name="app.tasks.sync_meeting_artifacts_task")
def sync_meeting_artifacts_task(meeting_id: str):
    from app.meetings.models import Meeting
    from app.meetings.service import meeting_service

    try:
        with SessionLocal.begin() as session:
            result = meeting_service.sync_meeting_artifacts(session, meeting_id)
        
        # If no analysis exists, run Bedrock AI analysis automatically
        with SessionLocal.begin() as session:
            meeting = session.get(Meeting, meeting_id)
            if meeting and not meeting.analysis:
                try:
                    meeting_service.analyze_meeting(session, meeting_id)
                except Exception as e:
                    logger.info("Automatic analysis for meeting %s skipped or postponed: %s", meeting_id, e)
        return result
    except Exception as exc:
        logger.warning("Failed to sync meeting artifacts for %s: %s", meeting_id, exc)
        return {"status": "failed", "error": str(exc)}


@celery_app.task(name="app.tasks.poll_meeting_artifacts")
def poll_meeting_artifacts():
    from datetime import timedelta
    from sqlalchemy import or_
    from app.meetings.models import Meeting

    cutoff = now() - timedelta(days=2)
    with SessionLocal() as session:
        meetings = session.scalars(
            select(Meeting).where(
                Meeting.status.in_(["scheduled", "in_progress", "completed"]),
                or_(
                    Meeting.scheduled_start >= cutoff,
                    Meeting.created_at >= cutoff,
                ),
            ).limit(20)
        ).all()
        meeting_ids = [m.id for m in meetings]

    for mid in meeting_ids:
        sync_meeting_artifacts_task.delay(mid)


@celery_app.task(name="app.tasks.cleanup_expired_booking_reservations_task")
def cleanup_expired_booking_reservations_task():
    from app.booking.tasks.booking_tasks import cleanup_expired_booking_reservations_sync
    return cleanup_expired_booking_reservations_sync()

