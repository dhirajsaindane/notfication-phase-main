"""Apply migrations and safely adopt databases created by pre-Alembic releases."""
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from .database import engine
from .models import Application


def main() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    config = Config("alembic.ini")

    # Older releases used Base.metadata.create_all(). Such databases have tables
    # but no alembic_version. Adopt only the known legacy layout without deleting
    # notification history, then hand future changes to Alembic.
    if "notifications" in tables and "alembic_version" not in tables:
        with engine.begin() as connection:
            Application.__table__.create(connection, checkfirst=True)
            connection.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS sms_body TEXT"))
            connection.execute(text("ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_deliveries_claimed_at ON deliveries (claimed_at)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_deliveries_ready ON deliveries (status, next_attempt_at)"))
        command.stamp(config, "0001_initial")

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
