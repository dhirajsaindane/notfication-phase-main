from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecipientInput(BaseModel):
    type: Literal["EMAIL", "USER", "PHONE"]
    value: str = Field(min_length=1, max_length=320)


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


class ApplicationConfigInput(BaseModel):
    email_enabled: bool = True
    sms_enabled: bool = False


class RecipientDirectoryInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
