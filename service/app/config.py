from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://notification:notification@localhost:5432/notifications"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "notifications@example.local"
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    max_delivery_attempts: int = 3
    worker_poll_seconds: int = 2

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

