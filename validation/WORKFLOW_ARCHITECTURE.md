# Workflow Architecture Guide

## Overview

The Email Tagging UI now features **two separate workflow builders**, each designed for different use cases:

1. **Classification Workflows** (`/workflows/classification`)
   - For building pipelines that automatically categorize emails into predefined categories
   - Uses: Inbox → Prompt Template → Classification Set

2. **Agentic Workflows** (`/workflows/agentic`)
   - For building AI-powered pipelines that extract structured data and call external APIs
   - Uses: Inbox → Extraction Prompt → Agent APIs → Webhook Callbacks

---

## Classification Workflows

### Purpose
Automatically categorize emails from a mailbox into a predefined set of categories (taxonomy). The pipeline:
1. Fetches emails from a mailbox based on fetch filters
2. Evaluates optional subject rules for fast categorization
3. Uses Gemini to classify remaining emails with the selected prompt
4. Writes predicted categories back to Outlook (optional)

### Workflow Steps

#### Step 1: Select Inbox
- **Mailbox ID**: The SMTP address of the mailbox to monitor (e.g., `inbox@company.com`)
- This is the mailbox that will be polled for new emails

#### Step 2: Choose Prompt & Classification Set
- **Prompt Template**: The Jinja-like template sent to Gemini with email metadata
  - Context variables: `{{subject}}`, `{{sender}}`, `{{body}}`, `{{attachments}}`
  - The prompt should guide categorization into the selected classification set
- **Classification Set**: The taxonomy of categories to bucket emails into
  - Define categories with names and descriptions (e.g., "Critical", "EquipmentBreakdown", "ETATracking")
  - Gemini will output JSON Schema predictions for these categories

#### Step 3: Email Fetch Settings
- **Timezone**: Used for `local_today` time window mode (determines calendar day boundaries)
- **Mail Folder**: Which folder to fetch from (`inbox`, `junkemail`, `drafts`, `all`, etc.)

#### Step 4: Scheduling & Write-back
- **Polling Interval**: How often the scheduler checks this inbox (1–1440 minutes)
- **Max Messages**: Maximum emails to process per run (1–500)
- **Active**: Enable/disable the workflow without deleting it
- **Write Categories Back to Outlook**: If enabled, predicted categories are written as `AI-{CategoryName}`

### Configuration Tips
- Use **Subject Rules** to handle system alerts and automated emails (e.g., `%Automated%`, `%On-Time%`)
  - Subject rules are evaluated first and bypass Gemini entirely, saving tokens
- Adjust **Polling Interval** based on email volume and cost (high-volume → longer intervals)
- Use **Fetch Filters** to narrow the scope:
  - Sender allowlist/denylist
  - Subject/body keywords
  - Importance levels
  - Attachment presence
  - Existing categories (include/exclude)
- **Model Override**: Assign a specific Gemini model to this workflow if it needs different capabilities

### Real-World Example
**Inbox**: `support@logistics.com`  
**Prompt**: "Categorize support emails into: {Critical Issues, Account Issues, Billing, Documentation}"  
**Classification Set**: "Support Categories"  
**Polling**: Every 15 minutes  
**Write-back**: Enabled (writes `AI-Critical Issues`, `AI-Billing`, etc.)  
**Result**: All new support emails are automatically categorized and labeled in Outlook

---

## Agentic Workflows

### Purpose
Extract structured data (reference numbers, customer info, tracking IDs) from emails and call external APIs for further processing. The pipeline:
1. Fetches emails from a mailbox
2. Uses Gemini function calling to extract structured data from email content
3. Calls one or more Agent APIs with the extracted data
4. POSTs results to a webhook for downstream processing

### Workflow Steps

#### Step 1: Select Inbox & Extraction Prompt
- **Inbox**: The mailbox to monitor
- **Extraction Prompt**: A prompt optimized for Gemini function calling
  - Should specify what reference numbers/data to extract (order ID, BOL, PRO#, truck/trailer IDs, etc.)
  - Guides Gemini on how to parse email bodies for structured data
- **Extract Reference Numbers**: If enabled, automatically attempts to extract common IDs

#### Step 2: Configure Agent APIs
- Select one or more **Agent API configurations** to call
- Each Agent API is a webhook endpoint that processes extracted data
- Examples:
  - ETA Tracking API: Updates delivery status
  - Order Management API: Creates or updates orders
  - Dispatch API: Assigns drivers to shipments
  - Custom Webhook: Your own service endpoint

#### Step 3: Callback Configuration
- **Webhook URL** (optional): POST results here
- Payload includes:
  - Email metadata (subject, sender, body)
  - Extracted reference numbers
  - Agent API response data
  - Classification results (if enabled)

### Configuration Tips
- Use **dedicated extraction prompts** (not classification prompts)
  - Classification prompts guide categorization; extraction prompts guide reference number extraction
  - Extraction prompts should be explicit about output format (JSON, structured fields)
- **Chain multiple APIs**: If you need to update an order and then notify dispatch, add both Agent APIs
- **Webhooks are optional**: If you don't need downstream integration, omit the webhook URL
- Different from **Classification Workflows**: Agentic workflows focus on *data extraction* not *categorization*

### Real-World Example
**Inbox**: `orders@logistics.com`  
**Extraction Prompt**: "Extract order ID, BOL, PRO#, shipper, consignee, and pickup/delivery dates"  
**Agent APIs**:
  - Order Management API (`https://api.company.com/orders`)
  - ETA Tracking API (`https://api.company.com/eta`)  
**Webhook**: `https://api.company.com/webhooks/email-processing`  
**Result**: New emails have structured data extracted, APIs are called to update order status, and results are logged to the webhook

---

## Key Differences

| Aspect | Classification Workflows | Agentic Workflows |
|--------|--------------------------|-------------------|
| **Goal** | Categorize emails into predefined categories | Extract data and call external APIs |
| **Prompt Type** | Classification prompt with context variables | Extraction prompt optimized for function calling |
| **Output** | Category label (written to Outlook as `AI-{Category}`) | Structured data (JSON with extracted fields) |
| **Integration** | Writes back to Outlook | POSTs to webhooks and Agent APIs |
| **Use Case** | Triage, routing, tagging | Data extraction, downstream integration, automation |
| **Subject Rules** | Supported (LIKE patterns) | Not applicable |
| **Write-back** | Optional, writes category labels | Not applicable; uses webhooks instead |

---

## Navigation Structure

The updated UI navigation is organized as:

```
Fleet Dashboard
├── Configuration (section header)
│   ├── Prompt Templates
│   ├── Classification Sets
│   ├── App Models
│   └── Agent APIs
├── Workflow Builders (section header)
│   ├── Classification Workflows ← Primary interface for classification pipelines
│   └── Agentic Workflows ← Primary interface for agentic pipelines
├── Inboxes (Reference) ← Legacy/reference view
└── Results & Analytics
```

- **Workflow Builders**: Use these to create and manage your workflows
- **Configuration pages**: Manage reusable components (prompts, taxonomies, APIs)
- **Inboxes (Reference)**: Legacy view; for reference only. Use Workflow Builders instead.

---

## Development Notes for Developers

### Adding a Custom Workflow Type
To add a new workflow type (e.g., `classification-with-ml`):

1. Create new folder: `web/app/workflows/{type-name}/`
2. Create `page.tsx` with workflow builder UI
3. Create `error.tsx` for error handling
4. Update `web/components/Nav.tsx` to add a link under "Workflow Builders"
5. Implement workflow configuration storage (API endpoint or localStorage)

### Backend Integration
- Classification workflows save directly to `/api/inboxes` (existing inbox table)
- Agentic workflows should have a dedicated `/api/agentic-workflows` endpoint (not yet implemented)
- Consider database schema:
  ```sql
  CREATE TABLE agentic_workflows (
    id INT PRIMARY KEY,
    inbox_id INT,
    prompt_id INT,
    agent_api_ids JSON,  -- Array of API IDs
    webhook_url VARCHAR(MAX),
    extract_reference_numbers BIT,
    created_at DATETIME,
    FOREIGN KEY (inbox_id) REFERENCES inboxes(id),
    FOREIGN KEY (prompt_id) REFERENCES prompt_templates(id)
  )
  ```

### UI/UX Best Practices
- Use **step-based layouts** to guide users through configuration (as in both workflow builders)
- Provide **active/inactive toggles** to test without deletion
- Show **counts and statuses** in list sidebars
- Link to related configuration pages (e.g., "Configure agent APIs")
- Support **bulk operations** for power users

---

## FAQ

**Q: Can I use the same inbox in multiple workflows?**  
A: Yes, but it's recommended to keep classification and agentic workflows separate. An inbox can only have one classification set, but can call multiple agent APIs.

**Q: What happens if both subject rules and Gemini categorization apply?**  
A: Subject rules are evaluated first. If a rule matches, Gemini is skipped for that email.

**Q: Can I extract data AND categorize in the same workflow?**  
A: Not with the current architecture. Use separate workflows: Classification Workflow for categorization, Agentic Workflow for extraction.

**Q: How do I test my prompt before deploying?**  
A: Go to **Prompt Templates** page and use the test feature to run mock emails through your prompt.

**Q: What's the difference between an "agent API" and a "webhook"?**  
A: **Agent APIs** are predefined integrations (configured in `/agent-apis`). **Webhooks** are custom endpoints where agentic workflows POST results. You can use both together.

