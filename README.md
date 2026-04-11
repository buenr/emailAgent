# Intelligent Inbox Classifier (Microsoft Graph)

An enterprise-grade pipeline for classifying Microsoft Exchange mailboxes using **Microsoft Graph** for email fetching and updating, and **Gemini on Vertex AI** for structured AI classification.

The system features a **Next.js** administration UI backed by a **FastAPI** + **SQL Server** configuration database, and a **Celery + Redis** scheduling engine to orchestrate concurrent mailbox processing across a fleet of shared inboxes.

## Features

- **Microsoft Graph integration**: Uses application permissions (OAuth2 client credentials) to securely read messages and optionally write predicted categories back to Outlook.
- **Vertex AI Gemini classification**: Leverages Gemini’s structured output (JSON Schema) to reliably bucket emails into operational categories using dynamic, per-inbox prompts and taxonomies.
- **Hybrid classification (subject rules)**: Define fast `LIKE`-style subject matching rules (for example `%Automated%`) to categorize system alerts *before* falling back to the LLM, saving tokens and latency.
- **Advanced fetch filtering**: Configure robust Graph `$filter` and `$search` parameters per inbox (sender allow/deny lists, body keywords, attachment filters, importance levels).
- **Fleet scheduling**: A dedicated loop and Celery worker pool reliably poll multiple inboxes at custom intervals. Redis-based locking prevents overlapping runs.
- **Multi-model support**: Assign different Gemini models (for example `gemini-3.1-pro`, `gemini-2.5-flash-lite`) to different inboxes based on complexity requirements.
- **Web UI**: A Next.js dashboard to manage prompt templates, custom classification sets, mailbox mappings, subject rules, and to monitor run logs and token spend.

## Prerequisites

1. **Python 3.9+** (uses `zoneinfo`; on Windows, IANA time zones come from `tzdata`)
2. **Node.js 18+** (for the Next.js frontend)
3. **Microsoft Entra ID (Azure AD) app registration** with client credentials and `Mail.Read` / `Mail.ReadWrite` application permissions (as needed for read vs. write-back)
4. **Google Cloud / Vertex AI** credentials and a project enabled for Gemini API access
5. **Microsoft SQL Server** (or Azure SQL) and **ODBC Driver 18** (required for production scheduling and persistent configuration)
6. **Redis** (required for Celery queue brokering and distributed run locks)

---

## Setup

### 1. Install dependencies

```bash
# Python backend
pip install -r requirements.txt

# Next.js frontend
cd web
npm install
cd ..
```

### 2. Environment variables

Create a `.env` file in the project root (or set the same variables in your process environment):


| Variable                                                                          | Purpose                                                                                                                                                                                                        |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MSSQL_ODBC_CONNECTION_STRING`                                                    | [Pyodbc](https://github.com/mkleehammer/pyodbc) connection string for SQL Server. Omit for **demo mode** (in-memory UI). Required for production workers and persistent config.                                |
| `GRAPH_ENTERPRISE_DEMO`                                                           | Optional. `1`/`true` forces demo even if a SQL string exists; `0`/`false` requires SQL Server (startup fails if the connection string is missing). If unset, demo is used when the connection string is empty. |
| `CELERY_BROKER_URL`                                                               | Redis URL for Celery (default `redis://localhost:6379/0` if unset).                                                                                                                                            |
| `REDIS_URL`                                                                       | Explicit Redis URL for **run locks**; if unset, locking falls back to `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (see `graph_enterprise/jobs/run_lock.py`).                                                 |
| `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`                       | MSAL client credentials for Microsoft Graph.                                                                                                                                                                   |
| `VERTEX_PROJECT`, `VERTEX_REGION`                                                 | Google Cloud project and region for Vertex AI.                                                                                                                                                                 |
| `GOOGLE_APPLICATION_CREDENTIALS`                                                  | Path to your GCP service account JSON key (standard Application Default Credentials flow).                                                                                                                     |
| `GEMINI_MODEL`                                                                    | Default fallback model (for example `gemini-2.5-flash-lite`) if none is set on the inbox. Per-inbox settings in SQL override this.                                                                             |
| `TARGET_MAILBOX`                                                                  | Shared mailbox UPN/SMTP when loading inbox config from SQL for CLI runs; defaults apply when unset (see `mailbox_run`).                                                                                        |
| `NEXT_PUBLIC_API_URL`                                                             | Optional. Set if the FastAPI backend is not at `http://127.0.0.1:8000` (Next.js dev default).                                                                                                                  |
| **Admin UI sign-in**                                                              |                                                                                                                                                                                                                |
| `ADMIN_EMAIL_ALLOWLIST`                                                           | Comma-separated admin emails (lowercase matching). Required unless `ADMIN_AUTH_DISABLED=1`.                                                                                                                    |
| `ALLOWED_EMAIL_DOMAINS`                                                           | Comma-separated allowed domain suffixes (no `@`), e.g. `swifttrans.com`.                                                                                                                                       |
| `ADMIN_SESSION_SECRET`                                                            | At least 16 characters; signs browser session tokens.                                                                                                                                                          |
| `ADMIN_COMPANY_PASSWORD_HASH`                                                     | Preferred: bcrypt hash of the shared company password (`python -c "from passlib.hash import bcrypt; print(bcrypt.hash('your-secret'))"`).                                                                      |
| `ADMIN_COMPANY_PASSWORD`                                                          | Alternative to hash: shared password in plaintext (use only for local dev; prefer a long random value).                                                                                                        |
| `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Outbound SMTP for one-time sign-in codes.                                                                                                                                                                      |
| `SMTP_DISABLE_TLS`                                                                | Set to `1` if the relay does not use STARTTLS.                                                                                                                                                                 |
| `ADMIN_OTP_LOG_TO_CONSOLE`                                                        | `1` logs OTPs to the API log instead of sending email (local dev).                                                                                                                                             |
| `ADMIN_AUTH_DISABLED`                                                             | `**1` disables all API auth (development only).**                                                                                                                                                              |


### 3. Running the web UI and API

The developer/admin UI manages configuration and monitors runs.

**Start the FastAPI backend** (from the repo root):

```bash
python run_api.py
```

On first run against SQL Server, the API runs T-SQL migrations under `graph_enterprise/migrations/mssql/`.

**Start the Next.js frontend**:

```bash
cd web
npm run dev
```

Open the UI at [http://localhost:3000](http://localhost:3000). The API listens on [http://127.0.0.1:8000](http://127.0.0.1:8000) by default; `GET /api/health` includes `"demo": true` when using in-memory demo data and `admin_auth_disabled` when `ADMIN_AUTH_DISABLED` is set. Configure the admin env vars above (or use `ADMIN_AUTH_DISABLED=1` for local development); unauthenticated requests to configuration endpoints receive **503** until auth is configured.

**Optional — seed default data** (SQL Server only, after migrations):

```bash
python -m graph_enterprise.ui.seed
```

Inserts Knight-Swift-oriented default categories, prompt template, and sample inbox (not used in demo mode).

### 4. Running the scheduler and workers (production)

To process mailboxes continuously from the database polling schedule:

**Start a Celery worker**:

```bash
celery -A graph_enterprise.jobs.celery_app worker -l info
```

**Start the scheduler loop** (checks the database every 60 seconds for due inboxes and enqueues tasks):

```bash
python -m graph_enterprise.jobs.scheduler_loop
```

Redis ensures only one worker processes a given inbox at a time via run locks. The scheduler skips enqueue when a lock is already held.

---

## Manual / CLI usage

You can run the pipeline as a one-off without Celery. If `MSSQL_ODBC_CONNECTION_STRING` is set, config for `TARGET_MAILBOX` is loaded from the database; otherwise the job uses local defaults (see `graph_enterprise/config/default_categories.py` and env tuning).

Default behavior fetches **unread** messages for the mailbox’s **local calendar day** (see run policy / time zone). Use `--hours` for a rolling UTC window instead.

```bash
# Fetch unread messages for the local day, classify, and write categories back to Outlook
export TARGET_MAILBOX="afterhours@knightswift.com"
python -m graph_enterprise.jobs.mailbox_run --classify --write-back

# Last 24 hours (all messages unless --unread-only), classify only
python -m graph_enterprise.jobs.mailbox_run --hours 24 --classify
```

PowerShell equivalent:

```powershell
$env:TARGET_MAILBOX = "afterhours@knightswift.com"
python -m graph_enterprise.jobs.mailbox_run --classify --write-back
```

### Common CLI flags


| Flag               | Effect                                                                          |
| ------------------ | ------------------------------------------------------------------------------- |
| `-v`, `--verbose`  | DEBUG logging (subjects and predicted categories).                              |
| `--hours N`        | Look back *N* hours (UTC). If omitted, uses the mailbox’s local calendar day.   |
| `--unread-only`    | Restrict to unread messages (especially useful with `--hours`).                 |
| `--mail-folder ID` | Well-known folder (`inbox`, `junkemail`, …), a folder id, or `all`.             |
| `--classify`       | Calls Vertex AI to categorize messages.                                         |
| `--write-back`     | Updates the message in Graph with the predicted category (prefixes with `AI-`). |


---

## Core concepts and configuration

Configuration is driven primarily through the web UI, with persistent state in SQL Server.

### Prompts and classification sets

- **Classification sets**: Taxonomies mapped to specific mailboxes. Each category has a **name** (JSON schema and Outlook label) and a **description** (steers the LLM).
- **Prompt templates**: Jinja-like templates filled with the email’s subject, sender, body, and attachments. Tailor instructions per department or mailbox.

### Subject rules (hybrid classification)

Configure **subject rules** in the UI to bypass the LLM for predictable traffic.

- Case-insensitive SQL `LIKE` syntax (for example `%Automated%`).
- Evaluated **before** Vertex AI. On match, the assigned category can be applied immediately (including write-back when enabled), reducing token cost and latency.

### Inbox mappings and fetch filters

When you add or edit an inbox in the UI, you can set:

- **Polling interval**: How often the scheduler considers the inbox for a run.
- **Fetch filters**: Narrow the Graph query with sender allow/deny lists, body keywords (`$search`), importance, attachments, existing categories, and related options.
- **Write-back**: Whether to PATCH categories on messages in Exchange.

### Demo mode vs. SQL Server

- **Demo mode**: No `MSSQL_ODBC_CONNECTION_STRING` (or forced via `GRAPH_ENTERPRISE_DEMO`) — in-memory sample data; changes are lost when the API process exits.
- **SQL Server**: Full CRUD, run logs, fleet scheduling, and DB-backed `mailbox_run` configuration.

---

## Architecture and code map


| Area                | Location                                                | Role                                                                                                                                                                                         |
| ------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Authentication      | `graph_enterprise/auth/`                                | MSAL app-only tokens for Microsoft Graph.                                                                                                                                                    |
| Microsoft Graph     | `graph_enterprise/microsoft_graph/`                     | Paginated `/messages` with `$filter` / `$search`; concurrent PATCH write-back.                                                                                                               |
| Classification      | `graph_enterprise/classification/`                      | `schema_from_config.py` (dynamic JSON Schema), `prompt.py` (templates and normalization), `gemini_category_batch.py` (Vertex calls, retry/backoff), `subject_rules.py` (LIKE / hybrid path). |
| Jobs and scheduling | `graph_enterprise/jobs/`                                | `celery_app.py`, `tasks.py`, `scheduler_loop.py`, `run_lock.py` (Redis), `mailbox_run.py` (CLI orchestration).                                                                               |
| API and UI          | `graph_enterprise/api/`, `graph_enterprise/ui/`, `web/` | FastAPI backend and Next.js frontend for fleet config, taxonomies, and metrics.                                                                                                              |


### End-to-end flow

1. **Authentication**: Client credentials produce a Graph access token (`graph_enterprise/auth/token.py`).
2. **Fetch**: `GraphMessageFetcher` pages messages for the mailbox, folder, and time window (`graph_enterprise/microsoft_graph/fetch.py`).
3. **Classification** (optional): Subject rules first; then Gemini structured output via `classify_graph_messages` (`gemini_category_batch.py`).
4. **Write-back** (optional): `patch_message_categories` merges predicted categories onto each message (`graph_enterprise/microsoft_graph/writeback.py`).
5. **Observability**: Run metrics and records (`graph_enterprise/observability/run_log.py`).

### Local defaults and code-first categories

For CLI runs without SQL-backed inbox rows, category definitions come from `graph_enterprise/config/default_categories.py` (`DEFAULT_CATEGORIES`). If you change labels for those defaults, keep prompts, seeds (`graph_enterprise/ui/seed.py`), and any SQL or dashboards aligned. With `--write-back`, Outlook receives an `AI-` prefix on category names (for example `AI-EquipmentBreakdownRoadside`).