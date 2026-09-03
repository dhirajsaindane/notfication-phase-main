# Notification Platform — Phase 1

A runnable notification service for a first production-style integration. Applications submit an event and intended recipient; this service owns templates, SMTP delivery, status, idempotency, and retry/DLQ handling.

## Included scope

- FastAPI HTTP API and a small Python SDK
- Direct `EMAIL` and local-directory `USER` recipients
- One recipient or a list of up to 100 recipients per notification
- Central templates stored in PostgreSQL
- Plain-text and HTML email templates through SMTP (Mailpit is included for local development)
- Persistent statuses: `PENDING`, `PROCESSING`, `SENT`, `RETRYING`, `DEAD_LETTER`
- Exponential retry: 30 seconds, then 60 seconds; default maximum 3 attempts
- Idempotency per application

## Folder structure

```text
notification-platform-phase1/
├── service/app/
│   ├── main.py          # HTTP API, startup, seed templates
│   ├── worker.py        # polling delivery worker + retry/DLQ
│   ├── models.py        # PostgreSQL tables
│   ├── schemas.py       # API request/response contracts
│   ├── database.py      # SQLAlchemy connection
│   └── config.py        # environment settings
├── sdk/notification_sdk/
│   └── client.py        # application integration API
├── examples/send_notification.py
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Run everything with Docker

Prerequisites: Docker Desktop running.

```powershell
docker compose up --build
```

In another terminal, send the example:

```powershell
python examples/send_notification.py
```

View the received test email at [Mailpit](http://localhost:8025). Inspect the API documentation at [Swagger UI](http://localhost:8000/docs).

Stop the stack with `docker compose down`. The PostgreSQL data remains in the named Docker volume. To remove it too: `docker compose down -v`.

## Run the API and worker locally (with Docker dependencies)

This mode is convenient while developing the Python code: PostgreSQL and Mailpit run in Docker, while FastAPI and its worker run directly on Windows.

Open three PowerShell terminals in this project directory.

**Terminal 1 — start only PostgreSQL and Mailpit**

```powershell
docker compose up postgres mailpit
```

**Terminal 2 — install dependencies and start the API**

```powershell
Copy-Item .env.local .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\service"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3 — start the worker**

```powershell
$env:PYTHONPATH = "$PWD\service"
.\.venv\Scripts\python.exe -m app.worker
```

Now run `.\.venv\Scripts\python.exe examples/send_notification.py` in a fourth terminal. The API is at [Swagger UI](http://localhost:8000/docs) and Mailpit is at [Mailpit](http://localhost:8025).

`docker compose up --build` uses `.env.docker` automatically, so it remains safe to leave `.env` set to the local configuration.

## API examples

Create a notification:

```powershell
$body = @{
  application_id = "payment-service"
  event = "PAYMENT_FAILED"
  recipient = @{ type = "EMAIL"; value = "user@example.com" }
  data = @{ payment_id = "PAY-100"; amount = "500 INR" }
  idempotency_key = "PAY-100-failed-v1"
} | ConvertTo-Json -Depth 4
Invoke-RestMethod http://localhost:8000/notifications -Method POST -ContentType 'application/json' -Body $body
```

Check status (replace the ID):

```powershell
Invoke-RestMethod http://localhost:8000/notifications/<notification-id>
```

Send the same event to multiple people. The service sends independent emails, so recipients cannot see each other's addresses and each address gets its own retry/status:

```python
notifications.send(
    event="PAYMENT_FAILED",
    recipients=[
        {"type": "EMAIL", "value": "admin1@example.com"},
        {"type": "EMAIL", "value": "admin2@example.com"},
        {"type": "EMAIL", "value": "devops@example.com"},
    ],
    data={"payment_id": "PAY-100", "amount": "500 INR"},
    idempotency_key="pay-100-failed-admin-alert",
)
```

Register a Phase-1 local user before sending to a `USER` recipient:

```powershell
$user = @{ user_id = "user-123"; email = "user@example.com" } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/recipients -Method POST -ContentType 'application/json' -Body $user
```

Then use `recipient = @{ type = "USER"; value = "user-123" }`.

Add or update a template:

```powershell
$template = @{ subject = "Hello {{ name }}"; body = "Hi {{ name }}, your item {{ item }} is ready." } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/templates/ITEM_READY -Method PUT -ContentType 'application/json' -Body $template
```

For HTML email, add `html_body` to the same request. Jinja placeholders such as `{{ invoice_id }}` are rendered from notification `data`:

```powershell
$template = @{
  subject = "We could not generate invoice {{ invoice_id }}"
  body = "Invoice {{ invoice_id }} could not be generated. Reason: {{ reason }}"
  html_body = "<html><body style='font-family:Arial'><h2>Invoice generation failed</h2><p>Invoice <strong>{{ invoice_id }}</strong> could not be generated.</p><p>Reason: {{ reason }}</p></body></html>"
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/templates/INVOICE_GENERATION_FAILED -Method PUT -ContentType 'application/json' -Body $template
```

See `examples/simple_project_integration.py` for a complete failure-handling pattern. The source project catches its own business exception, submits the notification, logs a notification-system failure separately, and then re-raises the original exception.

If you started the Docker stack before this HTML-template update, reset the local development database once so PostgreSQL receives the new column:

```powershell
docker compose down -v
docker compose up --build
```

Use proper database migrations (for example Alembic) instead of this reset for any environment containing real notification history.

## Add the SDK to an application

Deploy this service once (for example at `https://notifications.company.internal`). Each product then installs only the SDK and points it to that shared URL.

For a local path during development:

```powershell
pip install .\sdk
```

For a project that clones this repository from internal Git:

```powershell
pip install "git+https://github.com/your-company/notification-platform.git#subdirectory=sdk"
```

Later, publish `sdk/` to a private PyPI/Artifactory feed and let projects install a version such as `pip install company-notification-sdk==0.1.0`. Then:

```python
from notification_sdk import NotificationClient

notifications = NotificationClient(
    base_url="http://localhost:8000",
    application_id="reporting-service",
)

notifications.send(
    event="REPORT_READY",
    recipient={"type": "USER", "value": "user-123"},
    data={"report_name": "Daily report"},
    idempotency_key="report-123-ready",
)
```

Each project needs a unique `application_id`, for example `payment-service` or `employee-service`. In Phase 1 this identifies the source of notifications and scopes idempotency. Before a shared production rollout, add API-key or OAuth authentication so one project cannot submit notifications under another project's identity.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL SQLAlchemy connection string |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM` | Email provider connection |
| `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | Production SMTP credentials/security |
| `MAX_DELIVERY_ATTEMPTS` | Attempts before `DEAD_LETTER` |
| `WORKER_POLL_SECONDS` | Queue polling interval |

For production, replace Mailpit settings with your provider and inject secrets through a secret manager; do not commit `.env`. Phase 2 should replace the local `recipients` table with a shared Identity/Directory API and add Kafka plus other delivery channels.
