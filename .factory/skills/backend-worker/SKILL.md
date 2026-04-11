---
name: backend-worker
description: Backend implementation worker for FastAPI endpoints, database migrations, and Python logic
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving the FastAPI backend: new API endpoints, database migrations, Pydantic schema changes, db.py functions, pipeline logic, and curl-verified behaviors.

## Required Skills

None. Backend verification uses curl and Python directly.

## Work Procedure

1. **Read context**: Read mission.md, AGENTS.md, architecture.md. Understand the feature requirements and how they fit into the existing backend.

2. **Write tests first (red)**: Write API endpoint tests using FastAPI TestClient before implementing. Place tests in `graph_enterprise/tests/`. If no test framework is set up, create a minimal test file.

3. **Implement (green)**:
   - Add/modify Pydantic schemas in `graph_enterprise/api/main.py` (InboxCreate, InboxUpdate, etc.)
   - Add/modify DB functions in `graph_enterprise/ui/db.py`
   - Add new API routes in `graph_enterprise/api/main.py`
   - Add SQL migrations in `graph_enterprise/migrations/mssql/` (idempotent: IF NOT EXISTS)
   - Update `_row_to_config()` in `graph_enterprise/config/db_loader.py` if new inbox columns are added
   - Follow existing patterns: use `admin_auth` dependency for protected routes, use `get_db()` for database access

4. **Verify with curl**:
   ```bash
   # Start backend if not running
   python3 run_api.py &

   # Test each new/modified endpoint
   curl -s http://localhost:8000/api/health | python3 -m json.tool
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/new-endpoint | python3 -m json.tool
   ```

5. **Verify Python syntax**:
   ```bash
   python3 -m py_compile graph_enterprise/api/main.py
   python3 -m py_compile graph_enterprise/ui/db.py
   python3 -m py_compile graph_enterprise/config/db_loader.py
   ```

6. **Commit**: Stage and commit your changes with a descriptive message.

## Example Handoff

```json
{
  "salientSummary": "Added POST /api/inboxes/{id}/run endpoint that triggers run_scheduled_mailbox_pipeline. Added message_classification SQL table. Updated _persist_run_to_db to store per-message classifications. Added GET /api/run-logs/{id}/classifications and GET /api/inboxes/{id}/classifications endpoints with category and date filters.",
  "whatWasImplemented": "4 new API endpoints, 1 SQL migration, updated db.py with 3 new functions, updated db_loader.py _row_to_config for ETA fields. All endpoints return correct shapes verified via curl.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {"command": "curl -s POST /api/inboxes/1/run", "exitCode": 0, "observation": "Returns 202 with run_id"},
      {"command": "curl -s GET /api/run-logs/1/classifications", "exitCode": 0, "observation": "Returns array of per-email classification objects"},
      {"command": "python3 -m py_compile graph_enterprise/api/main.py", "exitCode": 0, "observation": "No syntax errors"}
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      {"file": "graph_enterprise/tests/test_run_endpoint.py", "cases": [{"name": "test_run_now_active_inbox", "verifies": "202 response for active inbox"}, {"name": "test_run_now_inactive_inbox", "verifies": "400 response for inactive inbox"}]}
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Frontend needs a data shape that differs from what was planned
- Database migration conflicts with existing schema
- Requirements are ambiguous or contradictory
- Missing Python dependencies that can't be installed
