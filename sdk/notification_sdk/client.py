import uuid
from typing import Any

import httpx


class NotificationClient:
    """Tiny application-facing SDK. No SMTP or template knowledge is exposed."""

    def __init__(self, base_url: str, application_id: str, timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.application_id = application_id
        self.timeout = timeout

    def send(self, event: str, recipient: dict[str, str] | None = None,
             data: dict[str, Any] | None = None, idempotency_key: str | None = None,
             recipients: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Submit one notification to one recipient or an independent delivery to each recipient."""
        payload = {
            "application_id": self.application_id,
            "event": event,
            "data": data or {},
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        }
        if recipient is not None:
            payload["recipient"] = recipient
        if recipients is not None:
            payload["recipients"] = recipients
        response = httpx.post(f"{self.base_url}/notifications", json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
1