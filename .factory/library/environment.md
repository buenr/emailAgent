# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Required Environment Variables

### Backend (FastAPI)
- `ADMIN_AUTH_DISABLED=1` — Disables auth for development. Frontend shows "Continue without auth" bypass button.
- `MSSQL_ODBC_CONNECTION_STRING` — SQL Server connection string. When unset, app uses in-memory SQLite (demo mode).
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` — Required for Microsoft Graph pipeline (not needed for UI dev).
- `VERTEX_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_CLOUD_API_KEY` — Required for Gemini classification (not needed for UI dev).
- `CORS_ORIGINS` — Override CORS origins (defaults to localhost:3000, 127.0.0.1:3000).

### Frontend (Next.js)
- `NEXT_PUBLIC_API_URL` — Backend API base URL. Defaults to `http://127.0.0.1:8000`.

## Demo Mode

When `MSSQL_ODBC_CONNECTION_STRING` is not set, the app runs in demo mode:
- Uses in-memory SQLite that is seeded on startup
- All CRUD operations work but data is lost on restart
- Auth can be disabled with `ADMIN_AUTH_DISABLED=1`
- No Graph/Gemini credentials needed for UI development

## Platform Notes

- This is WSL2 on Windows. File paths use `/mnt/c/...` format.
- `node_modules` is not currently installed — `npm install` must run first.
- Docker is not available in this environment.
- Python 3.12.3 is available but pip packages may not be installed.
