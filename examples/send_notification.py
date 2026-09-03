"""Run after docker compose is up: python examples/send_notification.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "sdk"))
from notification_sdk import NotificationClient

client = NotificationClient(base_url="http://localhost:8000", application_id="reporting-service")
result = client.send(
    event="REPORT_READY",
    recipient={"type": "EMAIL", "value": "dhiraj@example.com"},
    data={"report_name": "Weekly Operations Report"},
    idempotency_key="weekly-report-2026-08-25",
)
print(result)

