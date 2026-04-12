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
- **Agentic workflow integration**: A fully customizable pipeline for extracting structured data from emails using **Gemini Function Calling**. Define arbitrary JSON schemas in the UI, chain multiple sequential API calls, and POST results to webhooks. Includes a built-in **Dry Run Simulator** for testing extraction prompts and schemas.
- **Web UI**: A Next.js dashboard to manage prompt templates, custom classification sets, mailbox mappings, subject rules, agent workflows, run logs, and token spend analytics.
- **Statistics & monitoring**: Real-time token usage trends, classification breakdown by category, run volume metrics, and category histograms for fleet-wide visibility.

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

Inserts Logistics/Trucking-oriented default categories, prompt template, and sample inbox (not used in demo mode).

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

## Manual and on-demand runs

### Manual inbox trigger (API)

Trigger a single inbox to run immediately, bypassing the scheduler:

```bash
# Trigger mailbox run for a specific inbox (SQL mode only)
curl -X POST http://127.0.0.1:8000/api/inboxes/{inbox_id}/run \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Returns the `run_log` entry if successful. Useful for testing configuration changes or urgent re-processing without waiting for the next scheduled interval.

### One-off CLI runs

You can run the pipeline as a one-off without Celery or the scheduler. If `MSSQL_ODBC_CONNECTION_STRING` is set, config for `TARGET_MAILBOX` is loaded from the database; otherwise the job uses local defaults (see `graph_enterprise/config/default_categories.py` and env tuning).

Default behavior fetches **unread** messages for the mailbox’s **local calendar day** (see run policy / time zone). Use `--hours` for a rolling UTC window instead.

```bash
# Fetch unread messages for the local day, classify, and write categories back to Outlook
export TARGET_MAILBOX="afterhours@mytruckingcompany.com"
python -m graph_enterprise.jobs.mailbox_run --classify --write-back

# Last 24 hours (all messages unless --unread-only), classify only
python -m graph_enterprise.jobs.mailbox_run --hours 24 --classify
```

PowerShell equivalent:

```powershell
$env:TARGET_MAILBOX = "afterhours@mytruckingcompany.com"
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

## Workflow Architecture

The UI provides **two separate workflow builders** for different use cases:

### Classification Workflows (`/workflows/classification`)
**Purpose**: Automatically categorize emails into predefined categories.

- **Input**: Inbox → Email messages
- **Processing**: Fetch → Optional subject rules → Gemini classification → Write-back
- **Output**: Category labels in Outlook (prefixed `AI-`)
- **Use case**: Email triage, operational categorization, incoming request routing

**Example**: Monitor a support inbox and automatically categorize emails as `Critical`, `Account Issues`, `Billing`, or `Documentation`.

### Agentic Workflows (`/workflows/agentic`)
**Purpose**: Extract structured data from emails and call external APIs.

- **Input**: Inbox → Email messages
- **Processing**: Fetch → Gemini function calling with **configurable schemas** → Sequential agent API chaining → POST to webhook
- **Output**: Extracted JSON objects, API response logs, webhook callbacks
- **Use case**: Order extraction, ETA processing, automated data entry into ERPs, complex multi-step integrations

**Example**: Monitor a "Logistics" inbox; when an email is classified as `ETAUpdate`, trigger an agentic workflow that extracts `Order #`, `Truck ID`, and `New ETA` into a structured JSON, sends it to your internal Transport Management System (TMS) API, and notifies a Slack webhook.

### Key Differences

| Aspect | Classification | Agentic |
|--------|-----------------|---------|
| **Goal** | Categorize into predefined categories | Extract structured data & call APIs |
| **Output** | Category labels | JSON with extracted fields |
| **Integration** | Write-back to Outlook | Webhooks & external APIs |
| **Subject Rules** | Supported | N/A |

**For details**, see [WORKFLOW_ARCHITECTURE.md](validation/WORKFLOW_ARCHITECTURE.md). For a visual overview of the system, see the [Architecture Diagram](ARCHITECTURE.md).
---

## Core concepts and configuration

Configuration is driven primarily through the web UI, with persistent state in SQL Server.

### Prompt templates

**Prompt templates** are Jinja-like templates filled with email metadata (subject, sender, body, attachment names) and sent to Gemini for classification. Each template:
- Can be assigned to one or more classification sets
- Uses context variables: `{{subject}}`, `{{sender}}`, `{{body}}`, `{{attachments}}`
- Optionally includes extended thinking budget (configurable per model)
- Can be tested on mock emails via the UI before deployment

### Classification sets and categories

**Classification sets** are taxonomies (e.g., "Operational", "Support", etc.) assigned to specific mailboxes. Each category has:
- **Name**: Used as the Outlook label (prefixed with `AI-` on write-back)
- **Description**: Steers the LLM on what this category represents
- **JSON Schema**: Auto-generated from category metadata for Gemini structured output

Inboxes reference a single classification set; all messages are categorized into one of that set's categories.

### Subject rules (hybrid classification)

**Subject rules** enable fast, non-LLM categorization of predictable emails:
- Defined as case-insensitive SQL `LIKE` patterns (e.g., `%Automated%`, `%On-Time%`)
- Evaluated **before** Vertex AI; on match, category is assigned immediately
- Reduces token spend and latency for rule-matching traffic
- Applied during fetch filtering (subject only) or post-fetch classification

### Inbox mappings and fetch filters

When you add or edit an inbox in the UI, configure:

- **Polling interval** (1–1440 minutes): How often the scheduler checks for due inboxes
- **Time window mode**:
  - `local_today`: Enqueue unread messages for the mailbox's local calendar day (midnight-to-midnight in the inbox's configured time zone)
  - `rolling_hours`: Fetch the last N hours (UTC); useful with `--unread-only` for rolling windows
  - `since_last_run`: Incremental fetch since the last execution (scheduled runs only)
- **Mail folder**: Well-known folder (`inbox`, `junkemail`, `drafts`, …), a folder ID, or `all`
- **Fetch filters**: Narrow the Graph query with:
  - Sender allow/deny lists (exact match or domain wildcards)
  - Subject/body keywords (`$search` parameters)
  - Importance levels (high, normal, low)
  - Attachment filters (any, none, specific types)
  - Existing categories (include/exclude)
  - Unread-only constraint
  - Max message count per run (1–500)
- **Write-back**: Whether to PATCH predicted categories on messages (prefixed `AI-`)
- **Worker count** (1–4): Concurrent PATCH calls during write-back
- **Model override**: Assign a different Gemini model to this inbox (overrides `GEMINI_MODEL` env)

### Agentic workflows

**Agentic workflows** enable zero-code AI extraction and downstream integration:
- **Dynamic Schemas**: Define function names and parameters (strings, numbers, booleans) directly in the UI.
- **Gemini Function Calling**: The system automatically constructs tool definitions for Gemini to ensure 100% schema-compliant extraction.
- **API Chaining**: Sequentially call multiple external APIs. The results of each call are logged and can be sent to a master webhook.
- **Workflow Simulator**: Test your extraction prompts and schemas against mock emails side-by-side before going live.

### AI models

Pre-configured models available for assignment:
- `gemini-2.5-flash-lite`: Fast, cost-effective; supports extended thinking via HIGH budget
- `gemini-3.1-pro`: Most capable; high token cost; recommended for complex taxonomies
- `gemini-3.1-flash-lite`: Balanced cost/capability ratio

Each inbox can override the default model. Fine-tuning and RAG are not currently supported.

### Demo mode vs. SQL Server

- **Demo mode**: No `MSSQL_ODBC_CONNECTION_STRING` (or forced via `GRAPH_ENTERPRISE_DEMO=1`) — in-memory sample data; ideal for local development and testing. Changes are lost when the API process exits.
- **SQL Server mode**: Full CRUD, persistent run logs, fleet scheduling, and DB-backed `mailbox_run` configuration. Required for production use of Celery scheduler.

---

## Configuration limits and defaults

### Default models

| Model                   | Tier        | Best for                                         |
| ----------------------- | ----------- | ------------------------------------------------- |
| `gemini-2.5-flash-lite` | Cost        | High-volume emails, simple taxonomies            |
| `gemini-3.1-flash-lite` | Balanced    | Reliable mid-range classification                |
| `gemini-3.1-pro`        | Capable     | Complex taxonomies, multi-faceted classification |

### Default categories (Logistics/Trucking orientation)

Seeded on first run if `default_categories.py` is applied:
- `Critical` – Urgent issues, escalations
- `EquipmentBreakdownRoadside` – Vehicle/equipment failures
- `ETAOrTracking` – Status updates and location tracking
- `AppointmentScheduling` – Meetings, confirmations
- `DocumentsOrForms` – Administrative paperwork
- (and others per deployment policy)

### Configuration limits and ranges

| Setting                      | Min | Max  | Notes                                                          |
| ---------------------------- | --- | ---- | -------------------------------------------------------------- |
| Polling interval (minutes)   | 1   | 1440 | 24 hours maximum; 1 minute minimum for high-frequency inboxes |
| Message batch per run        | 1   | 500  | Limits Graph query latency and token spend per execution       |
| Concurrent PATCH workers     | 1   | 4    | Parallel write-back calls; max 4 enforced by Microsoft Graph API rate limits  |
| Email body character limit   | —   | 65K  | First 1000 words of latest reply; truncated for Gemini input   |
| Token spend tracking         | —   | ∞    | Persisted per `message_classification` row; queryable via API  |
| Subject rule patterns (LIKE) | —   | ∞    | SQL `LIKE` syntax; `%` wildcards, case-insensitive matching    |
| Inbox time zone             | —   | IANA | Any IANA timezone (e.g., `America/Chicago`); affects `local_today` window |

---

## Architecture and code map


| Area                | Location                                                | Role                                                                                                                                                                                         |
| ------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Authentication      | `graph_enterprise/auth/`                                | MSAL app-only tokens for Microsoft Graph.                                                                                                                                                    |
| Microsoft Graph     | `graph_enterprise/microsoft_graph/`                     | Paginated `/messages` with `$filter` / `$search`; concurrent PATCH write-back.                                                                                                               |
| Agent workflows     | `graph_enterprise/agent_workflow/`                      | `orchestrator.py` handles dynamic function calling, API sequence orchestration, and results logging.                                         |
| API and UI          | `graph_enterprise/api/`, `graph_enterprise/ui/`, `web/` | FastAPI backend (39 endpoints) and Next.js frontend (8 pages) for prompts, classifications, inboxes, models, agent APIs, run logs, and statistics.                                           |


### End-to-end flow

1. **Authentication**: Client credentials produce a Graph access token (`graph_enterprise/auth/token.py`).
2. **Fetch**: `GraphMessageFetcher` pages messages for the mailbox, folder, and time window (`graph_enterprise/microsoft_graph/fetch.py`).
3. **Classification** (optional): Subject rules first; then Gemini structured output via `classify_graph_messages` (`gemini_category_batch.py`).
4. **Write-back** (optional): `patch_message_categories` merges predicted categories onto each message (`graph_enterprise/microsoft_graph/writeback.py`).
5. **Observability**: Run metrics and records (`graph_enterprise/observability/run_log.py`).

### Local defaults and code-first categories

For CLI runs without SQL-backed inbox rows, category definitions come from `graph_enterprise/config/default_categories.py` (`DEFAULT_CATEGORIES`). If you change labels for those defaults, keep prompts, seeds (`graph_enterprise/ui/seed.py`), and any SQL or dashboards aligned. With `--write-back`, Outlook receives an `AI-` prefix on category names (for example `AI-EquipmentBreakdownRoadside`).