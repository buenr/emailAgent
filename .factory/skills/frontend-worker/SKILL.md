---
name: frontend-worker
description: Frontend implementation worker for Next.js UI features using shadcn/ui
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving the Next.js 14 frontend: component migration, new pages, UI forms, charts, shadcn/ui integration, and browser-verified behaviors.

## Required Skills

- `agent-browser` — for verifying UI flows after implementation. Invoke after each feature's implementation is complete to verify rendering, interactions, and data flow.

## Work Procedure

1. **Read context**: Read mission.md, AGENTS.md, architecture.md. Understand the feature requirements and how they fit into the existing app.

2. **Install shadcn components first** (if not already available): Before implementing any feature that needs shadcn/ui components, install them:
   ```bash
   cd web && npx shadcn@latest add button input select table card dialog alert-dialog toast tabs badge slider skeleton alert
   ```
   If `components.json` doesn't exist, run `npx shadcn@latest init -d` first.

3. **Write tests first (red)**: For each UI component or page change, write a test that verifies the expected behavior before implementing. Use the existing test patterns in the project. If no test framework exists, document manual test steps.

4. **Implement (green)**: Make changes to the Next.js app. Follow these rules:
   - Use shadcn/ui components from `@/components/ui/` for all UI elements
   - Use `@/lib/api.ts` for all API calls (apiGet, apiSend)
   - Use shadcn Toast for success/error notifications (import from `@/components/ui/use-toast` or `@/components/ui/sonner`)
   - Use shadcn AlertDialog for delete confirmations (never window.confirm)
   - Use shadcn Skeleton for loading states (never "Loading..." text)
   - Use shadcn Alert for inline error display (never hand-rolled error divs)
   - Use shadcn Select for all dropdowns (never raw `<select>`)
   - Use shadcn Slider for range inputs (never raw `<input type="range">`)
   - Preserve ALL existing functionality — no regressions
   - Match existing dark theme styling

5. **Typecheck and lint**:
   ```bash
   cd web && npx tsc --noEmit
   cd web && npm run lint
   ```
   Fix all errors before proceeding.

6. **Verify with agent-browser**: Use agent-browser to:
   - Navigate to the affected page(s)
   - Verify rendering (no blank pages, no console errors)
   - Test all interactive flows (CRUD, filters, navigation)
   - Take screenshots as evidence

7. **Commit**: Stage and commit your changes with a descriptive message.

## Example Handoff

```json
{
  "salientSummary": "Migrated inboxes page from raw HTML to shadcn/ui components (Table, Input, Select, Button, AlertDialog, Slider). Added toast notifications for save/delete errors. Verified all CRUD flows work via agent-browser.",
  "whatWasImplemented": "Replaced all native HTML form elements on /inboxes with shadcn/ui equivalents. Added AlertDialog for delete confirmation. Added Toast for success/error feedback. Added Skeleton loading state. Typecheck and lint pass clean.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {"command": "cd web && npx tsc --noEmit", "exitCode": 0, "observation": "No type errors"},
      {"command": "cd web && npm run lint", "exitCode": 0, "observation": "No lint errors"}
    ],
    "interactiveChecks": [
      {"action": "Navigate to /inboxes, create a new inbox with all fields", "observed": "Form renders with shadcn components, save succeeds with toast, inbox appears in list"},
      {"action": "Delete an inbox", "observed": "AlertDialog appears, confirming deletes the inbox with success toast"},
      {"action": "Submit form with missing required fields", "observed": "Validation errors shown, no API call made"}
    ]
  },
  "tests": {
    "added": []
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Backend API endpoint needed by the feature doesn't exist yet
- shadcn/ui component doesn't exist for a needed UI pattern
- Requirements are ambiguous or contradictory
- Type errors that can't be resolved without backend changes
