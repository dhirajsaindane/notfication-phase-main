"""Example code to place in a simple application's service layer."""
import logging
import os

from notification_sdk import NotificationClient

logger = logging.getLogger(__name__)
notifications = NotificationClient(
    base_url=os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8000"),
    application_id="simple-project",
)


def generate_invoice(invoice_id: str, customer_email: str) -> None:
    try:
        # Your existing business logic goes here.
        raise RuntimeError("Invoice PDF provider timed out")  # Example failure only
    except Exception as exc:
        # Do not include passwords, access tokens, or raw customer data in notification data.
        try:
            notifications.send(
                event="INVOICE_GENERATION_FAILED",
                recipient={"type": "EMAIL", "value": customer_email},
                data={"invoice_id": invoice_id, "reason": str(exc)},
                idempotency_key=f"invoice-{invoice_id}-generation-failed",
            )
        except Exception:
            # A notification failure should be logged, but normally should not hide the original business failure.
            logger.exception("Could not submit failure notification for invoice=%s", invoice_id)
        raise
