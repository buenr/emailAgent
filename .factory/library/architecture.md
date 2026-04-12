# Email Tagging UI — Architecture

## System Overview

The Email Tagging UI is a two-tier web application for managing and monitoring an enterprise email classification pipeline that processes Microsoft Exchange shared mailboxes via Microsoft Graph and classifies them using Google Gemini on Vertex AI.

| Layer | Technology | Role |
|-------|-----------|------|
| Frontend | Next.js 14 (App Router) | Admin configuration UI |
| Backend | FastAPI (Python 3.9+) | REST API, auth, orchestration |
| Database | SQL Server (production) / SQLite (demo) | Persistent configuration |
| Queue | Celery + Redis | Scheduled mailbox processing |
| AI | Gemini on Vertex AI | Structured classification & extraction |
| Mail API | Microsoft Graph (OAuth2 client credentials) | Email fetch & write-back |

The frontend communicates exclusively with the FastAPI backend; it never calls Microsoft Graph, Vertex AI, or the database directly.

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  Next.js UI  │──────▶│   FastAPI    │──────▶│  SQL Server  │
│  (port 3000) │ REST  │  (port 8000) │ pyodbc│  / SQLite    │
└──────────────┘       └──────┬───────┘       └──────────────┘
                       │
              ┌────────┼────────┐
              ▼        ▼        ▼
        ┌──────────┐ ┌──────┐ ┌──────┐
        │ MS Graph │ │Gemini│ │Redis │
        │ (OAuth2) │ │(AI)  │ │(Cel) │
        └──────────┘ └──────┘ └──────┘
```

---

## Frontend

### App Router Pages

| Route | Purpose |
|-------|---------|
| `/login` | OTP-based sign-in flow |
| `/dashboard` | Fleet overview with token-spend charts, classification breakdown, health cards, inbox search/filter, bulk ops |
| `/prompts` | CRUD for Jinja-like prompt templates |
| `/classifications` | CRUD for classification sets and their taxonomy rows |
| `/models` | CRUD for Gemini model aliases (e.g., `gemini-2.5-flash-lite`) |
| `/inboxes` | CRUD for inbox mappings with fetch filters and subject rules |

### Key Components

- **AppShell** (`components/AppShell.tsx`) — Root layout wrapper. Checks for a JWT in `sessionStorage`; redirects unauthenticated users to `/login`. Renders the sidebar `Nav` and a `<main>` content area.
- **Nav** (`components/Nav.tsx`) — Fixed sidebar with links to the five content pages and a sign-out button that clears the session token.
- **PromptMonaco** (`components/PromptMonaco.tsx`) — Monaco Editor wrapper for editing prompt template bodies with dark theme and word-wrap.

### API Client

`lib/api.ts` is a thin fetch-based client that:
- Resolves the backend base URL from `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`).
- Attaches `Authorization: Bearer <token>` from `sessionStorage` on every request.
- Redirects to `/login` on 401.
- Exposes `apiGet`, `apiSend` (for mutating requests), and `apiPublicPost` (for login flow, no auth header).

### shadcn/ui Migration Plan

The application is being migrated from hand-rolled Tailwind components to shadcn/ui primitives. The plan calls for:
- Replacing all raw `<input>`, `<button>`, and `<select>` elements with shadcn/ui counterparts (`<Input>`, `<Button>`, `<Switch>`, etc.).
- Using `<Card>` shells for dashboard panels, `<Table>` primitives for inbox/classification lists.
- Using `<Dialog>` or `<Sheet>` for inbox edit forms, `<Toast>` for all user feedback (replacing `window.alert`).
- Ensuring consistent dark theme via shadcn/ui CSS custom properties (`--background`, `--card`, etc.).

---

## Backend

### FastAPI Application (`graph_enterprise/api/main.py`)

The API is structured as two routers:
- **Public** (`/api` prefix) — health check only.
- **Protected** (`/api` prefix, `require_admin` dependency) — all CRUD endpoints for prompt templates, classification sets, inboxes, app models, run logs, fleet summary, global polling, and test-prompt.

The startup handler calls `db.init_db()` which runs T-SQL migrations on first run against SQL Server.

### Database Layer (`graph_enterprise/ui/db.py`)

Dual-mode persistence:
- **Production**: pyodbc connection to SQL Server, auto-migrated on startup.
- **Demo mode** (`graph_enterprise/ui/demo_db.py`): in-memory store activated when `MSSQL_ODBC_CONNECTION_STRING` is unset or `GRAPH_ENTERPRISE_DEMO=1`. Changes are lost on process exit.

All CRUD functions accept an open connection and return plain dicts. The module also provides pagination, run-log queries, fleet-summary joins, and integrity-error detection.

### Pydantic Models (`graph_enterprise/config/models.py`)

Core domain models:
- **MailboxPipelineConfig** — Top-level per-inbox configuration: mailbox ID, categories, run policy, prompt template, Gemini model, fetch filter, and subject rules.
- **InboxFetchFilter** — Microsoft Graph `$filter` / `$search` predicates: time window mode, sender allow/deny lists, subject/body keywords, importance, attachment filter, category include/exclude.
- **SubjectClassifyRule** — SQL `LIKE` pattern + target category for hybrid classification (pre-LLM fast path).
- **RunPolicy** — Polling interval, message cap, timezone, folder, write-back concurrency.
- **AppModelDefinition** — Named Gemini model alias.
- **CategoryDefinition** — Category name + description for Gemini prompting.

These models are used both as API request/response schemas and as internal configuration objects loaded from the database via `config/db_loader.py`.

---

## Pipeline

### Main Classification Pipeline

```
Auth → Fetch → Preprocess → Subject Rules → Gemini Classify → Write-Back → Log
```

1. **Auth** (`auth/token.py`): MSAL client credentials produce a Graph access token.
2. **Fetch** (`microsoft_graph/fetch.py`): `GraphMessageFetcher` pages messages for the configured mailbox, folder, and time window using `$filter`, `$search`, `$select`, `$expand`, and `@odata.nextLink`.
3. **Preprocess** (`preprocess/body.py`, `preprocess/attachments.py`): Extracts plain text from HTML bodies and attachment metadata for the prompt.
4. **Subject Rules** (`classification/subject_rules.py`): Fast path — SQL `LIKE` patterns are evaluated before the LLM. First match wins; matched messages skip the Gemini call.
5. **Gemini Classify** (`classification/gemini_category_batch.py`): Dynamic JSON Schema is built from the inbox's taxonomy (`schema_from_config.py`). The prompt template is rendered (`prompt.py`) and sent to Gemini with structured output. Retry and backoff handle 429s and server errors.
6. **Write-Back** (`microsoft_graph/writeback.py`): `patch_message_categories` merges predicted categories (prefixed with `AI-`) onto each message in Exchange via PATCH.
7. **Log** (`observability/run_log.py`): Structured JSON run record with metrics (fetched, classified, tagged, tokens, latency, histogram).

### Agent Workflow (post-classification)

Messages classified as `ETAOrTracking` are optionally routed into a post-classification agent workflow.

```
Extract Ref Numbers → External Agent API Call → Draft Reply
```

1. **Extract** (`classification/eta_extractor.py`): Gemini function calling extracts order, BOL, PRO, truck, and trailer numbers from the email body.
2. **Agent API Call** (`graph_enterprise/agent_workflow/orchestrator.py`): The workflow builds a structured payload from extracted reference numbers and message metadata, then dispatches it to configured external agent endpoints.
3. **Draft** (`microsoft_graph/draft.py`): Uses Graph `createReply` to create a draft reply in Outlook, then patches the draft body with a formatted summary of the agent workflow result.

Failures in the agent workflow are logged but do not break the main classification run.

---

## Data Flow

### End-to-End Email Lifecycle

```
Microsoft Exchange
       │
       ▼ (OAuth2 client credentials)
  GraphMessageFetcher ─── pages unread/recent messages
       │
       ▼
  Preprocessor ─── strips HTML, extracts attachment info
       │
       ▼
  Subject Rules ─── LIKE pattern match? → assign category, skip LLM
       │ (no match)
       ▼
  Gemini Structured Output ─── dynamic JSON Schema per taxonomy
       │
       ▼
  Write-Back ─── PATCH `AI-<Category>` onto message in Exchange
       │
       ▼ (if category == ETAOrTracking and agent workflow is configured)
  Agent Extractor ─── Gemini function calling → ref numbers
       │
       ▼
  Agent API Call ─── external endpoint invocation
       │
       ▼
  Draft Reply ─── createReply + PATCH body in Outlook
```

### Configuration Data Flow

```
SQL Server ──▶ db_loader.py ──▶ MailboxPipelineConfig
                                    │
                     ┌──────────────┼──────────────┐
                     ▼              ▼              ▼
               GraphFetcher    GeminiBatch     AgentWorkflow
               (fetch filter)  (schema, prompt) (agent configs)
```

Admin changes in the Next.js UI flow as:

```
Browser ──▶ api.ts (fetch + JWT) ──▶ FastAPI endpoint ──▶ db.py CRUD ──▶ SQL Server
```

Run logs flow the opposite direction for observability:

```
Celery worker ──▶ run_log.py ──▶ db.py insert ──▶ FastAPI /run-logs ──▶ Dashboard charts
```

---

## Authentication

The application uses a custom OTP-based authentication flow (not OAuth2/Entra ID SSO):

1. **Request Code** (`POST /api/auth/request-code`): User submits email + shared company password. The server validates the email against `ADMIN_EMAIL_ALLOWLIST` and `ALLOWED_EMAIL_DOMAINS`, verifies the company password (bcrypt hash or plaintext via env vars), generates a 6-digit OTP, and emails it via SMTP (or logs to console in dev).
2. **Verify** (`POST /api/auth/verify`): User submits email + company password + OTP. The server validates all three, consumes the OTP (single-use), and returns a signed JWT (via `itsdangerous URLSafeTimedSerializer`, max age 24h).
3. **Session**: The JWT is stored in the browser's `sessionStorage` and sent as `Authorization: Bearer <token>` on every API call. The `require_admin` dependency validates the token and checks the email against the allowlist.
4. **Rate Limiting**: Redis-backed rate limits per IP and per email prevent brute-force attacks. In-memory fallback when Redis is unavailable.

Development mode: `ADMIN_AUTH_DISABLED=1` bypasses all auth checks, returning a fixed `dev@auth-disabled.local` identity.

---

## New Features Being Added

The following features are in active development as part of a production UI overhaul:

### Message Classification Table

A new `message_classification` table persists individual classification results (email ID, predicted category, confidence, model used, timestamp). This replaces the current transient approach where classifications are only visible in run logs and enables:

- **Stats endpoints**: `GET /api/stats/token-trends`, `/api/stats/classification-breakdown`, `/api/stats/run-volume` — time-bucketed aggregates powering dashboard charts.
- **Classification results viewer**: A new page/section showing per-message classification history with auto-refresh polling.

### Search & Filter

- Inbox list accepts `?search=` (substring match on `mailbox_id`) and `?is_active=` query parameters.
- Both filters compose together for faceted browsing.

### Bulk Operations

- `POST /api/inboxes/bulk-activate` and `POST /api/inboxes/bulk-delete` accept arrays of inbox IDs.
- UI presents checkboxes on inbox rows and a floating action bar with activate/delete actions and confirmation dialogs.

### Agent API Configuration

- The UI includes a dedicated Agent APIs page for defining external agent endpoints used by post-classification workflows.
- Configured agent API entries are persisted in app settings and consumed by `graph_enterprise/agent_workflow/orchestrator.py`.

### Export / Import

- `GET /api/export` produces a JSON snapshot of all configuration (prompt templates, classification sets, inboxes, app models).
- `POST /api/import` accepts the same JSON shape and upserts into the database, enabling configuration portability across environments.
- UI surfaces with download/upload controls.

---

## Key Invariants

- **AI- prefix**: All categories written back to Outlook are prefixed with `AI-` to distinguish model predictions from human-assigned labels. The prefix is applied in `writeback.py` and stripped when loading from config.
- **Demo mode is ephemeral**: Without `MSSQL_ODBC_CONNECTION_STRING`, the entire backend operates in-memory. Changes are lost on restart.
- **Subject rules bypass LLM**: When a subject rule matches, the message is classified immediately and the Gemini call is skipped. This is an intentional optimization for predictable traffic.
- **Agent workflow failures are non-fatal**: Each step in the agent workflow catches its own exceptions. A failure in any agent step is logged but does not affect the main classification run's success status.
- **One token source**: The frontend stores exactly one JWT in `sessionStorage`. Its absence redirects to `/login`; its expiry returns 401 and clears storage.
- **Write-back is opt-in**: `graph_write_back_enabled` on each inbox controls whether categories are PATCHed back to Exchange. When disabled, the pipeline runs in dry-run mode (classify only).
- **Run locks prevent overlap**: Redis-based locks ensure that only one worker processes a given inbox at a time. The scheduler skips enqueue when a lock is already held.
- **First subject rule wins**: Subject rules are evaluated in order; the first pattern match assigns the category and stops further rule evaluation.
