import logging
import smtplib
import time
from datetime import timedelta
from email.message import EmailMessage

import httpx
from jinja2 import Environment, StrictUndefined
from sqlalchemy import select

from .config import settings
from .database import Base, SessionLocal, engine
from .models import Delivery, DeliveryStatus, Notification, Template, utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
templates = Environment(undefined=StrictUndefined, autoescape=False)


def send_email(destination: str, subject: str, body: str, html_body: str | None = None) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = destination
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)


def send_sms(destination: str, body: str) -> None:
    """Submit one SMS to Twilio's Programmable Messaging REST API."""
    if not settings.sms_enabled:
        raise RuntimeError("SMS delivery is disabled")
    if settings.sms_provider != "twilio":
        raise RuntimeError(f"Unsupported SMS provider: {settings.sms_provider}")
    if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number]):
        raise RuntimeError("Twilio credentials or TWILIO_FROM_NUMBER are not configured")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    request_data = {"From": settings.twilio_from_number, "To": destination}
    if settings.twilio_trial_content_sid:
        # Trial accounts reject arbitrary Body text. Twilio renders this predefined
        # content template instead; custom sms_body is used again after upgrade.
        request_data["ContentSid"] = settings.twilio_trial_content_sid
    else:
        request_data["Body"] = body

    response = httpx.post(
        url,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        data=request_data,
        timeout=20,
    )
    if response.is_error:
        # Twilio returns a useful JSON error code/message. Surface it in our delivery
        # record and container logs without ever logging the account token.
        try:
            detail = response.json()
            code = detail.get("code", "unknown") if isinstance(detail, dict) else "unknown"
            message = detail.get("message", response.text) if isinstance(detail, dict) else response.text
        except ValueError:
            code, message = "unknown", response.text
        raise RuntimeError(f"Twilio rejected SMS: HTTP {response.status_code}, code {code}: {message}")


def process_one() -> bool:
    with SessionLocal() as session:
        delivery = session.scalar(
            select(Delivery)
            .where(Delivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.RETRYING]), Delivery.next_attempt_at <= utcnow())
            .order_by(Delivery.next_attempt_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not delivery:
            return False
        delivery.status = DeliveryStatus.PROCESSING
        session.commit()
        notification = session.get(Notification, delivery.notification_id)
        template = session.get(Template, notification.event)
        try:
            if delivery.channel == "EMAIL":
                subject = templates.from_string(template.subject).render(**notification.payload)
                body = templates.from_string(template.body).render(**notification.payload)
                html_body = templates.from_string(template.html_body).render(**notification.payload) if template.html_body else None
                send_email(delivery.destination, subject, body, html_body)
            elif delivery.channel == "SMS":
                if not template.sms_body:
                    raise RuntimeError(f"No SMS template configured for event {notification.event}")
                sms_body = templates.from_string(template.sms_body).render(**notification.payload)
                send_sms(delivery.destination, sms_body)
            else:
                raise RuntimeError(f"Unsupported delivery channel: {delivery.channel}")
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = utcnow()
            delivery.last_error = None
            log.info("sent delivery=%s destination=%s", delivery.id, delivery.destination)
        except Exception as exc:  # Delivery must be retried; preserve the provider/template failure.
            delivery.attempt_count += 1
            delivery.last_error = str(exc)[:4000]
            if delivery.attempt_count >= settings.max_delivery_attempts:
                delivery.status = DeliveryStatus.DEAD_LETTER
                log.exception("dead-lettered delivery=%s", delivery.id)
            else:
                delivery.status = DeliveryStatus.RETRYING
                delay_seconds = 30 * (2 ** (delivery.attempt_count - 1))
                delivery.next_attempt_at = utcnow() + timedelta(seconds=delay_seconds)
                log.exception("will retry delivery=%s in %ss", delivery.id, delay_seconds)
        session.commit()
        return True


def main():
    Base.metadata.create_all(bind=engine)
    log.info("notification worker started")
    while True:
        if not process_one():
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
