# Developer & AI Agent Codebase Guide

This document serves as a high-level architectural map, it describes the purpose of the main folders and files, the data flow, and where specific logic resides.

## Project Overview

The **Intelligent Inbox Classifier** is an enterprise-grade pipeline for classifying Microsoft Exchange mailboxes.
- **Backend**: FastAPI (Python) + SQL Server.
- **Frontend**: Next.js (TypeScript) + Tailwind CSS.
- **AI**: Google Gemini (Vertex AI) for classification & extraction.
- **Integration**: Microsoft Graph API (MSAL Auth).
- **Orchestration**: Celery + Redis for fleet management.

## Architecture Diagram

For a visual overview of the system architecture and data flow, see the [Architecture Diagram](ARCHITECTURE.md).


---

## Repository Structure

### Root Directory
- [`run_api.py`](run_api.py): The entry point for the FastAPI backend.
- [`requirements.txt`](requirements.txt): Python dependencies.
- [`README.md`](README.md): High-level setup and operation manual.
- [`.env`](.env): (User-provided) Configuration for Azure, Google Cloud, SQL, and Auth.

### [`graph_enterprise/`](graph_enterprise) (Backend Source)
The core Python package containing all business logic.

- **[`api/`](graph_enterprise/api)**: FastAPI route definitions.
  - `main.py`: Defines all 35+ REST endpoints for the UI.
  - `admin_auth.py`: Logic for OTP-based administrative sign-in.
- **[`classification/`](graph_enterprise/classification)**: The "Brain" of the project.
  - `gemini_category_batch.py`: Vertex AI integration, batching, and retry logic.
  - `subject_rules.py`: Hybrid path for fast, non-LLM classification using regex/LIKE patterns.
  - `prompt.py`: Jinja-like template rendering for LLM instructions.
  - `schema_from_config.py`: Automatically generates JSON Schemas from DB taxonomies to ensure structured LLM output.
- **[`jobs/`](graph_enterprise/jobs)**: Execution and Scheduling.
  - `mailbox_run.py`: The master orchestrator for a single inbox run. **Start here to understand the data flow.**
  - `scheduler_loop.py`: Polls the database and enqueues due inboxes into Celery.
  - `celery_app.py` & `tasks.py`: Background worker definitions.
- **[`microsoft_graph/`](graph_enterprise/microsoft_graph)**: Communication with Microsoft.
  - `fetch.py`: Paginated and filtered email retrieval.
  - `writeback.py`: Updates Outlook categories on processed messages.
- **[`auth/`](graph_enterprise/auth)**: App-only authentication using MSAL.
- **[`ui/`](graph_enterprise/ui)**: Database Abstraction Layer.
  - `db.py`: Every T-SQL query used by the API is defined here. No ORM is used; it uses raw pyodbc for performance and SQL Server specific features.
- **[`config/`](graph_enterprise/config)**: Pydantic models for configuration and DB row-to-object mapping.
- **[`observability/`](graph_enterprise/observability)**: Logic for recording `run_log` entries and performance metrics.

### [`web/`](web) (Frontend)
Next.js 14+ application using the App Router.

- **[`app/`](web/app)**: Main pages (Dashboard, Prompts, Classifications, Workflows).
- **[`components/`](web/components)**: UI components (using shadcn/ui patterns).
- **[`lib/`](web/lib)**: API clients (`api.ts`) and TypeScript definitions (`types.ts`).

---

## Core Data Flows

### 1. The Processing Pipeline
When a mailbox is processed (via scheduler or manual trigger), the flow in `mailbox_run.py` is:
1. **Auth**: Get Graph token from MSAL.
2. **Fetch**: Query Graph API for messages based on the inbox's `FetchFilter` (time window, folders, etc.).
3. **Partition**: Check messages against **Subject Rules**. Matching messages are handled immediately.
4. **Classify**: Remaining messages are batched and sent to **Gemini** with a dynamic JSON Schema and Prompt Template.
5. **Extract** (Optional): If Agentic workflow is enabled, extract reference numbers (Order #, BOL, etc.).
6. **Write-back**: PATCH predicted categories back to Outlook.
7. **Callback**: Trigger webhooks for Agentic integrations.
8. **Record**: Save the `run_log` and `message_classification` metrics to SQL Server.

### 2. Configuration & State
- **SQL Server**: The source of truth for all templates, sets, models, and inbox mappings.
- **Redis**: Used for Celery task queuing and distributed locks (to prevent an inbox from being processed twice simultaneously).

---

## Guidance for AI Agents

- **Modifying API behavior?** Change [`graph_enterprise/api/main.py`](graph_enterprise/api/main.py).
- **Adding/Changing DB Queries?** Update [`graph_enterprise/ui/db.py`](graph_enterprise/ui/db.py) and check for existing migrations in [`graph_enterprise/migrations`](graph_enterprise/migrations).
- **Refining AI Classification?** Look at [`graph_enterprise/classification/`](graph_enterprise/classification/).
- **Fixing Fleet-wide scheduling?** Investigate [`graph_enterprise/jobs/scheduler_loop.py`](graph_enterprise/jobs/scheduler_loop.py).
- **UI Tweaks?** Files are in [`web/app/`](web/app/).

---

## Related Documentation
- [Workflow Architecture](validation/WORKFLOW_ARCHITECTURE.md): Detailed logic for Classification vs. Agentic pathways.
- [Directory Structure (Workflows)](validation/DIRECTORY_STRUCTURE.md): Detailed breakdown of the `web/` folder's recent additions.
