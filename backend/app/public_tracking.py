from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.mailbox import lock_mail_workflow
from app.models import EmailEvent, EmailMessage, Enrollment, Suppression, TrackingLink

router = APIRouter()
PIXEL = bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")


@router.get("/public/open/{token}")
def record_open(token: str, session: Session = Depends(get_db)):
    if not settings.tracking_enabled:
        raise HTTPException(404, "Tracking disabled.")
    message = session.scalar(select(EmailMessage).where(EmailMessage.open_token == token))
    if message is None or message.status != "sent":
        raise HTTPException(404, "Not found.")
    session.add(EmailEvent(email_id=message.id, event_type="open"))
    session.commit()
    return Response(content=PIXEL, media_type="image/gif", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/public/r/{token}")
def record_click(token: str, session: Session = Depends(get_db)):
    if not settings.tracking_enabled:
        raise HTTPException(404, "Tracking disabled.")
    link = session.scalar(select(TrackingLink).where(TrackingLink.token == token))
    message = session.get(EmailMessage, link.email_id) if link else None
    if not link or not message or message.status != "sent":
        raise HTTPException(404, "Not found.")
    session.add(EmailEvent(email_id=message.id, event_type="click", detail=link.destination))
    session.commit()
    return RedirectResponse(link.destination, status_code=302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/public/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_page(token: str, session: Session = Depends(get_db)):
    if not session.scalar(select(Enrollment.id).where(Enrollment.unsubscribe_token == token)):
        raise HTTPException(404, "Not found.")
    return HTMLResponse('<!doctype html><title>Unsubscribe</title><h1>Unsubscribe</h1>'
                        '<p>Stop future sales emails to this address.</p>'
                        '<form method="post"><button type="submit">Unsubscribe</button></form>',
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/public/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    enrollment = session.scalar(select(Enrollment).where(Enrollment.unsubscribe_token == token))
    if not enrollment:
        raise HTTPException(404, "Not found.")
    if not session.get(Suppression, enrollment.recipient):
        session.add(Suppression(email=enrollment.recipient, reason="unsubscribe"))
    enrollment.reply_blocked = True
    session.commit()
    return HTMLResponse("<!doctype html><title>Unsubscribed</title><p>You have been unsubscribed.</p>")
