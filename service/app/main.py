from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from jinja2 import Environment, TemplateSyntaxError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_session
from .default_templates import DEFAULT_TEMPLATES
from .models import Application, Delivery, Notification, Recipient, Template
from .schemas import (NotificationRequest, NotificationResponse, NotificationStatusResponse,
                      ApplicationConfigInput, RecipientDirectoryInput, TemplateInput)

template_parser = Environment()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema changes are applied by Alembic before this process starts.
    with SessionLocal() as session:
        for event, content in DEFAULT_TEMPLATES.items():
            if session.get(Template, event) is None:
                session.add(Template(event=event, **content))
        session.commit()
    yield


app = FastAPI(title="Notification Platform — Phase 1", version="1.0.0", lifespan=lifespan)


def resolve_destination(session: Session, recipient_type: str, recipient_value: str) -> tuple[str, str]:
    if recipient_type == "EMAIL":
        return "EMAIL", recipient_value
    if recipient_type == "PHONE":
        if not recipient_value.startswith("+") or not recipient_value[1:].isdigit():
            raise HTTPException(422, "PHONE recipients must use E.164 format, e.g. +919876543210")
        return "SMS", recipient_value
    user = session.get(Recipient, recipient_value)
    if not user:
        raise HTTPException(422, f"Unknown USER recipient: {recipient_value}. Register it with POST /recipients first.")
    return "EMAIL", user.email


@app.get("/health")
def health():
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        raise HTTPException(503, "Database is unavailable") from exc


@app.post("/notifications", response_model=NotificationResponse, status_code=status.HTTP_202_ACCEPTED)
def create_notification(request: NotificationRequest, session: Session = Depends(get_session)):
    existing = session.scalar(select(Notification).where(
        Notification.application_id == request.application_id,
        Notification.idempotency_key == request.idempotency_key,
    ))
    if existing:
        return NotificationResponse(notification_id=existing.id, status="ACCEPTED", duplicate=True)

    if not session.get(Template, request.event):
        raise HTTPException(422, f"No template configured for event {request.event}")
    application = session.get(Application, request.application_id)
    if not application:
        # Backward compatible default: existing applications can use email, but must opt in to SMS.
        application = Application(id=request.application_id, email_enabled=True, sms_enabled=False)
        session.add(application)
        session.flush()
    requested_recipients = request.recipients or [request.recipient]
    resolved_recipients = [
        (recipient, *resolve_destination(session, recipient.type, recipient.value))
        for recipient in requested_recipients
    ]
    for _, channel, _ in resolved_recipients:
        if channel == "EMAIL" and not application.email_enabled:
            raise HTTPException(422, f"Email is disabled for application {request.application_id}")
        if channel == "SMS" and not application.sms_enabled:
            raise HTTPException(422, f"SMS is disabled for application {request.application_id}")
        if channel == "SMS" and not settings.sms_enabled:
            raise HTTPException(503, "SMS delivery is disabled on this notification platform")
    try:
        notification = Notification(
            application_id=request.application_id, event=request.event,
            idempotency_key=request.idempotency_key,
            recipient_type=resolved_recipients[0][0].type, recipient_value=resolved_recipients[0][0].value,
            payload=request.data,
        )
        session.add(notification)
        session.flush()
        for _, channel, destination in resolved_recipients:
            session.add(Delivery(notification_id=notification.id, channel=channel, destination=destination))
        session.commit()
    except IntegrityError:
        session.rollback()
        duplicate = session.scalar(select(Notification).where(
            Notification.application_id == request.application_id,
            Notification.idempotency_key == request.idempotency_key,
        ))
        return NotificationResponse(notification_id=duplicate.id, status="ACCEPTED", duplicate=True)
    return NotificationResponse(notification_id=notification.id, status="PENDING")


@app.get("/notifications/{notification_id}", response_model=NotificationStatusResponse)
def get_notification(notification_id: str, session: Session = Depends(get_session)):
    notification = session.get(Notification, notification_id)
    if not notification:
        raise HTTPException(404, "Notification not found")
    deliveries = session.scalars(select(Delivery).where(Delivery.notification_id == notification_id)).all()
    return NotificationStatusResponse(
        notification_id=notification.id, event=notification.event,
        application_id=notification.application_id, created_at=notification.created_at,
        deliveries=deliveries,
    )


@app.put("/templates/{event}")
def upsert_template(event: str, request: TemplateInput, session: Session = Depends(get_session)):
    try:
        for source in (request.subject, request.body, request.html_body, request.sms_body):
            if source:
                template_parser.parse(source)
    except TemplateSyntaxError as exc:
        raise HTTPException(422, f"Invalid template syntax: {exc.message}") from exc
    template = session.get(Template, event)
    if template:
        template.subject, template.body, template.html_body, template.sms_body = request.subject, request.body, request.html_body, request.sms_body
    else:
        session.add(Template(event=event, subject=request.subject, body=request.body, html_body=request.html_body, sms_body=request.sms_body))
    session.commit()
    return {"event": event, "status": "saved"}


@app.post("/recipients", status_code=status.HTTP_201_CREATED)
def register_recipient(request: RecipientDirectoryInput, session: Session = Depends(get_session)):
    recipient = session.get(Recipient, request.user_id)
    if recipient:
        recipient.email = request.email
    else:
        session.add(Recipient(user_id=request.user_id, email=request.email))
    session.commit()
    return {"user_id": request.user_id, "email": request.email}


@app.put("/applications/{application_id}")
def configure_application(application_id: str, request: ApplicationConfigInput, session: Session = Depends(get_session)):
    application = session.get(Application, application_id)
    if application:
        application.email_enabled = request.email_enabled
        application.sms_enabled = request.sms_enabled
    else:
        session.add(Application(id=application_id, email_enabled=request.email_enabled, sms_enabled=request.sms_enabled))
    session.commit()
    return {"application_id": application_id, "email_enabled": request.email_enabled, "sms_enabled": request.sms_enabled}
