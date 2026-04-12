# Workflow Architecture - Directory Structure

## Updated Project Layout

```
Email_Tagging_UI/
│
├── README.md                                 ← UPDATED: Added "Workflow Architecture" section
│
├── validation/
│   ├── IMPLEMENTATION_SUMMARY.md             ← NEW: Complete change summary
│   ├── WORKFLOW_ARCHITECTURE.md              ← NEW: Comprehensive architecture guide
│   ├── WORKFLOW_QUICK_START.md               ← NEW: Quick-start guide with examples
│   ├── dashboard-validation.md               (existing)
│   └── cross-area-flows.md                   (existing)
│
├── web/
│   ├── components/
│   │   ├── Nav.tsx                           ← UPDATED: Section-based navigation
│   │   └── ... (other components)
│   │
│   └── app/
│       ├── page.tsx                          (home redirect)
│       ├── layout.tsx                        (root layout)
│       ├── globals.css                       (styles)
│       │
│       ├── dashboard/                        (existing)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       ├── prompts/                          (existing - configuration)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       ├── classifications/                  (existing - configuration)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       ├── models/                           (existing - configuration)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       ├── agent-apis/                       (existing - configuration)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       ├── inboxes/                          (existing - marked as reference)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       ├── results/                          (existing - analytics)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       ├── login/                            (existing - auth)
│       │   ├── page.tsx
│       │   └── error.tsx
│       │
│       └── workflows/                        ← NEW: Workflow builders directory
│           │
│           ├── classification/               ← NEW: Classification workflow builder
│           │   ├── page.tsx                  (step-based workflow builder UI)
│           │   └── error.tsx                 (error boundary)
│           │
│           └── agentic/                      ← NEW: Agentic workflow builder
│               ├── page.tsx                  (step-based workflow builder UI)
│               └── error.tsx                 (error boundary)
│
└── graph_enterprise/                         (Python backend - unchanged)
    ├── api/
    │   ├── main.py                           (FastAPI endpoints)
    │   └── ...
    ├── classification/
    ├── config/
    ├── jobs/
    ├── microsoft_graph/
    ├── observability/
    ├── migrations/
    ├── preprocess/
    ├── tests/
    ├── ui/
    └── ...
```

## Navigation Structure (Updated)

The sidebar navigation (`Nav.tsx`) now organizes pages into sections:

```
Email Classifier
├── Fleet Dashboard
│   └── /dashboard
│
├── Configuration                     ← Section header
│   ├── Prompt Templates           → /prompts
│   ├── Classification Sets        → /classifications
│   ├── App Models                 → /models
│   └── Agent APIs                 → /agent-apis
│
├── Workflow Builders               ← NEW Section header
│   ├── Classification Workflows   → /workflows/classification
│   └── Agentic Workflows          → /workflows/agentic
│
├── Inboxes (Reference)
│   └── /inboxes
│
└── Results & Analytics
    └── /results
```

## Data Flow Architecture

### Classification Workflow
```
┌─────────────────────────────────────────────────────────────┐
│         /workflows/classification Page                       │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        v                   v                   v
   [Mailbox]         [Prompt Template]   [Classification Set]
   (Step 1)              (Step 2)             (Step 2)
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
        ┌───────────────────┴────────────────────┐
        │                                        │
        v                                        v
   [Fetch Settings]                     [Schedule & Writeback]
   (Step 3)                            (Step 4)
        │                                        │
        └────────────────────┬────────────────────┘
                             │
                             v
                    POST /api/inboxes
                             │
                             v
              SQL Server (persistent config)
                             │
                             v
          Scheduler & Celery Worker Process:
              - Fetch emails from Graph
              - Run subject rules
              - Call Gemini classification
              - Write back to Outlook
```

### Agentic Workflow
```
┌─────────────────────────────────────────────────────────────┐
│         /workflows/agentic Page                              │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        v                   v                   v
   [Mailbox]         [Extraction Prompt]  [Agent APIs]
   (Step 1)              (Step 1)          (Step 2)
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                    [Webhook URL]
                      (Step 3)
                            │
                            v
             localStorage or /api/agentic-workflows
                            │
                            v
          Agentic Processing Pipeline:
              - Fetch emails from Graph
              - Extract structured data (Gemini function calling)
              - Call registered Agent APIs
              - POST to webhook with results
```

## Component Hierarchy

### Classification Workflow Page
```
ClassificationWorkflowPage
├── State Management
│   ├── workflows, prompts, sets, appModels
│   ├── selectedId, detail
│   ├── Form State (mailboxId, promptId, setId, etc.)
│   └── UI State (loading, saving, error)
│
├── UI Layout
│   ├── Header (title + description)
│   ├── Error Alert (if error)
│   └── Main Grid (2 columns)
│       ├── Left Column (Workflow List)
│       │   └── Card: Workflows
│       │       └── Button: + New Workflow
│       │       └── List: Workflows
│       │
│       └── Right Column (Workflow Editor)
│           └── Card: Workflow Form
│               ├── Step 1: Select Inbox
│               ├── Step 2: Choose Prompt & Set
│               ├── Step 3: Fetch Settings
│               ├── Step 4: Scheduling & Writeback
│               └── Buttons: Save, Delete
│
└── API Integration
    ├── GET /api/inboxes (list)
    ├── GET /api/inboxes/{id} (detail)
    ├── GET /api/prompt-templates
    ├── GET /api/classification-sets
    ├── GET /api/app-models
    ├── POST /api/inboxes (create)
    ├── PATCH /api/inboxes/{id} (update)
    └── DELETE /api/inboxes/{id} (delete)
```

### Agentic Workflow Page
```
AgenticWorkflowPage
├── State Management
│   ├── workflows, inboxes, prompts, agentApis
│   ├── selectedId
│   ├── Form State (inboxId, promptId, selectedAgentApis, etc.)
│   └── UI State (loading, saving, error)
│
├── UI Layout
│   ├── Header (title + description)
│   ├── Error Alert (if error)
│   └── Main Grid (2 columns)
│       ├── Left Column (Workflow List)
│       │   └── Card: Workflows
│       │       └── Button: + New Workflow
│       │       └── List: Workflows
│       │
│       └── Right Column (Workflow Editor)
│           └── Card: Workflow Form
│               ├── Step 1: Inbox & Extraction Prompt
│               │   └── Checkbox: Extract reference numbers
│               ├── Step 2: Agent APIs
│               │   └── Checkboxes: Select APIs
│               ├── Step 3: Webhook Callback
│               │   └── Input: Webhook URL
│               │   └── Info: Payload structure
│               └── Buttons: Save, Delete
│
└── Storage
    ├── localStorage: agentic_workflows (temporary)
    └── Future: /api/agentic-workflows (backend)
```

## File Dependencies

### Classification Workflow Page
```
page.tsx
├── Imports
│   ├── @/lib/api         (apiGet, apiSend)
│   ├── @/lib/types       (Inbox, Named, etc.)
│   ├── sonner            (toast notifications)
│   └── UI Components     (Select, Input, Button, etc.)
│
└── Uses
    ├── /api/inboxes             (list, get, create, update, delete)
    ├── /api/prompt-templates    (list)
    ├── /api/classification-sets (list)
    └── /api/app-models          (list)
```

### Agentic Workflow Page
```
page.tsx
├── Imports
│   ├── @/lib/api         (apiGet, apiSend)
│   ├── @/lib/types       (Inbox, Named, AgentApiConfig)
│   ├── sonner            (toast notifications)
│   └── UI Components     (Select, Input, Button, etc.)
│
└── Uses
    ├── localStorage           (agentic_workflows)
    ├── /api/inboxes          (list)
    ├── /api/prompt-templates (list)
    └── /api/agent-apis       (list)
```

### Navigation Component
```
Nav.tsx
├── Imports
│   ├── next/navigation   (Link, usePathname, useRouter)
│   ├── @/lib/api        (clearAdminToken)
│   └── UI Components    (Button)
│
├── Links Structure (Mixed flat + sections)
│   ├── Flat: Fleet Dashboard, Inboxes, Results
│   └── Sections: Configuration, Workflow Builders
│
└── Renders
    ├── Flat links as simple Link components
    └── Sections as div with sub-items
```

## Configuration Storage

### Classification Workflows
- **Storage**: SQL Server (via `/api/inboxes`)
- **Table**: `inboxes` (existing)
- **Fields**: mailbox_id, prompt_id, classification_set_id, timezone, mail_folder, etc.
- **Persistence**: Always saved to SQL Server

### Agentic Workflows
- **Storage**: localStorage (temporary)
- **Table**: Future: `agentic_workflows` (not yet created)
- **Fields**: inbox_id, prompt_id, agent_apis[], webhook_url, extract_reference_numbers
- **Persistence**: Lost on page refresh (until backed by API)

## Next Steps for Production

1. **Backend Integration** for Agentic Workflows:
   - Create `/api/agentic-workflows` endpoints
   - Create database table with proper schema
   - Integrate with scheduler

2. **Enhanced Error Handling**:
   - More specific error messages
   - Validation feedback per field
   - Retry logic for failed API calls

3. **Workflow Execution Monitoring**:
   - Add run history to Results page
   - Show success/failure rates
   - Display token usage per workflow

4. **Advanced Features**:
   - Workflow templates
   - Duplicate/clone workflows
   - Bulk operations
   - Workflow versioning

