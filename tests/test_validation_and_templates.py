import pytest
from pydantic import ValidationError

from app.default_templates import DEFAULT_TEMPLATES
from app.schemas import NotificationRequest, TemplateInput
from app.worker import html_templates, text_templates


def test_rejects_invalid_email_and_phone():
    with pytest.raises(ValidationError):
        NotificationRequest(application_id="billing", event="PAYMENT_FAILED", recipient={"type": "EMAIL", "value": "not-an-email"}, idempotency_key="one")
    with pytest.raises(ValidationError):
        NotificationRequest(application_id="billing", event="PAYMENT_FAILED", recipient={"type": "PHONE", "value": "9876543210"}, idempotency_key="two")


def test_rejects_duplicate_recipients():
    with pytest.raises(ValidationError):
        NotificationRequest(
            application_id="billing", event="PAYMENT_FAILED", idempotency_key="three",
            recipients=[{"type": "EMAIL", "value": "same@example.com"}, {"type": "EMAIL", "value": "SAME@example.com"}],
        )


def test_templates_render_and_html_escapes_user_values():
    payment = DEFAULT_TEMPLATES["PAYMENT_FAILED"]
    data = {"payment_id": "PAY-1", "amount": "500 INR", "reason": "<script>alert(1)</script>"}
    assert "PAY-1" in text_templates.from_string(payment["body"]).render(**data)
    html = html_templates.from_string(payment["html_body"]).render(**data)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_template_subject_rejects_header_injection():
    with pytest.raises(ValidationError):
        TemplateInput(subject="Hello\r\nBcc: attacker@example.com", body="Body")
