"""Create the notification platform schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    delivery_status = sa.Enum("PENDING", "PROCESSING", "SENT", "RETRYING", "DEAD_LETTER", name="deliverystatus")
    op.create_table(
        "applications",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("application_id", sa.String(length=100), nullable=False),
        sa.Column("event", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("recipient_type", sa.String(length=20), nullable=False),
        sa.Column("recipient_value", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "idempotency_key", name="uq_notification_idempotency"),
    )
    op.create_index("ix_notifications_application_id", "notifications", ["application_id"])
    op.create_index("ix_notifications_event", "notifications", ["event"])
    op.create_table(
        "templates",
        sa.Column("event", sa.String(length=100), primary_key=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("sms_body", sa.Text(), nullable=True),
    )
    op.create_table(
        "recipients",
        sa.Column("user_id", sa.String(length=100), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("notification_id", sa.String(length=36), sa.ForeignKey("notifications.id"), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="EMAIL"),
        sa.Column("destination", sa.String(length=320), nullable=False),
        sa.Column("status", delivery_status, nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deliveries_notification_id", "deliveries", ["notification_id"])
    op.create_index("ix_deliveries_status", "deliveries", ["status"])
    op.create_index("ix_deliveries_next_attempt_at", "deliveries", ["next_attempt_at"])
    op.create_index("ix_deliveries_claimed_at", "deliveries", ["claimed_at"])
    op.create_index("ix_deliveries_ready", "deliveries", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("recipients")
    op.drop_table("templates")
    op.drop_table("notifications")
    op.drop_table("applications")
    op.execute("DROP TYPE IF EXISTS deliverystatus")
