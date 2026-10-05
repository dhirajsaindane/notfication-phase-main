from datetime import datetime
from typing import Any, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re


class RecipientInput(BaseModel):
    type: Literal["EMAIL", "USER", "PHONE"]
    value: str = Field(min_length=1, max_length=320)

    @field_validator("value")
    @classmethod
    def validate_destination(cls, value: str, info):
        recipient_type = info.data.get("type")
        if recipient_type == "EMAIL":
            try:
                return validate_email(value, check_deliverability=False).normalized
            except EmailNotValidError as exc:
                raise ValueError("Provide a valid email address") from exc
        if recipient_type == "PHONE" and not re.fullmatch(r"\+[1-9]\d{7,14}", value):
            raise ValueError("PHONE recipients must use E.164 format, e.g. +919876543210")
        if "\r" in value or "\n" in value:
            raise ValueError("Recipient value cannot contain line breaks")
        return value


class NotificationRequest(BaseModel):
    application_id: str = Field(min_length=1, max_length=100)
    event: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z0-9_]+$")
    recipient: RecipientInput | None = None
    recipients: list[RecipientInput] = Field(default_factory=list, max_length=100)
    data: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_recipients(self):
        if self.recipient and self.recipients:
            raise ValueError("Provide either recipient or recipients, not both")
        if not self.recipient and not self.recipients:
            raise ValueError("At least one recipient is required")
        recipient_list = self.recipients or ([self.recipient] if self.recipient else [])
        identities = [(item.type, item.value.lower() if item.type == "EMAIL" else item.value) for item in recipient_list]
        if len(identities) != len(set(identities)):
            raise ValueError("Each recipient may appear only once")
        return self


class NotificationResponse(BaseModel):
    notification_id: str
    status: str
    duplicate: bool = False


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str
    destination: str
    status: str
    attempt_count: int
    last_error: str | None
    sent_at: datetime | None


class NotificationStatusResponse(BaseModel):
    notification_id: str
    event: str
    application_id: str
    created_at: datetime
    deliveries: list[DeliveryResponse]


class TemplateInput(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    html_body: str | None = None
    sms_body: str | None = Field(default=None, max_length=1600)

    @field_validator("subject")
    @classmethod
    def reject_subject_line_breaks(cls, value: str):
        if "\r" in value or "\n" in value:
            raise ValueError("Subject cannot contain line breaks")
        return value


class ApplicationConfigInput(BaseModel):
    email_enabled: bool = True
    sms_enabled: bool = False


class RecipientDirectoryInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_recipient_email(cls, value: str):
        try:
            return validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise ValueError("Provide a valid email address") from exc
