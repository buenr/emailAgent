# User Testing

Testing surface, required testing skills/tools, and resource cost classification.

## Validation Surface

**Primary surface:** Browser (Next.js web application at http://localhost:3000)
**Secondary surface:** API endpoints via curl at http://localhost:8000

**Required skills/tools:**
- `agent-browser` — for all UI flow validation
- `curl` — for backend API endpoint testing

**Setup requirements:**
1. Start FastAPI backend: `python3 run_api.py` (port 8000)
2. Start Next.js frontend: `cd web && npm run dev` (port 3000)
3. Ensure demo DB has seed data (auto-seeded on startup in demo mode)
4. Auth: Use dev bypass (email: dev@local, password: x, OTP: 0000) or set ADMIN_AUTH_DISABLED=1

**Known limitations:**
- Pipeline features (Run Now, classification results) require Graph/Gemini credentials for real data
- In demo mode without credentials, test UI and API shapes only (empty results acceptable)
- No automated E2E test suite exists yet

## Validation Concurrency

**Machine specs:** 32 CPU cores, 46 GB RAM (43 GB available), 846 GB disk free

**agent-browser (lightweight Next.js app):**
- Dev server: ~200 MB RAM
- Each agent-browser instance: ~300 MB RAM
- Max concurrent validators: **5** (5 × 300MB + 200MB server = 1.7 GB, well within 43 GB headroom at 70% utilization)

**curl (API testing):**
- Negligible resource consumption
- Max concurrent validators: **5**
