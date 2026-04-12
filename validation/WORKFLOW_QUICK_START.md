# Workflow Builder Quick-Start Guide

This guide helps you get started with the Classification and Agentic workflow builders.

## Getting Started

Open the UI at [http://localhost:3000](http://localhost:3000) and navigate to:
- **Workflow Builders** → **Classification Workflows** (for email categorization)
- **Workflow Builders** → **Agentic Workflows** (for data extraction & API calls)

---

## Classification Workflow Quick-Start

### Scenario
You have a support inbox (`support@company.com`) that receives hundreds of emails daily. You want to automatically categorize them as: "Critical", "Account Issues", "Billing", or "Documentation".

### Steps

#### 1. Create a Classification Set
1. Go to **Configuration** → **Classification Sets**
2. Click **+ New Classification Set**
3. Name: "Support Categories"
4. Add categories:
   - Name: `Critical` → Description: "Urgent issues, system outages, customer escalations"
   - Name: `Account Issues` → Description: "Login problems, account access, password resets"
   - Name: `Billing` → Description: "Invoicing, payment issues, quotes"
   - Name: `Documentation` → Description: "How-to guides, FAQ, technical documentation"
5. Click **Save**

#### 2. Create a Prompt Template
1. Go to **Configuration** → **Prompt Templates**
2. Click **+ New Prompt**
3. Name: "Support Email Classifier"
4. Body:
```jinja
You are a support email classifier. Analyze the email and categorize it.

Email Subject: {{subject}}
Email From: {{sender}}
Email Body: {{body}}

Categories:
1. Critical - Urgent issues, system outages, customer escalations
2. Account Issues - Login problems, account access, password resets
3. Billing - Invoicing, payment issues, quotes
4. Documentation - How-to guides, FAQ, technical documentation

Return ONLY the category name.
```
5. Click **Save**

#### 3. Build the Classification Workflow
1. Go to **Workflow Builders** → **Classification Workflows**
2. Click **+ New Workflow**
3. **Step 1: Select Inbox**
   - Mailbox ID: `support@company.com`
4. **Step 2: Choose Prompt & Classification Set**
   - Prompt Template: "Support Email Classifier"
   - Classification Set: "Support Categories"
5. **Step 3: Email Fetch Settings**
   - Timezone: `America/Chicago` (or your timezone)
   - Mail Folder: `inbox`
6. **Step 4: Scheduling & Write-back**
   - Polling Interval: `15` minutes (check every 15 min)
   - Max Messages: `50`
   - Active: ✓ (checked)
   - Write Categories Back to Outlook: ✓ (checked)
7. Click **Save Workflow**

### Result
Every 15 minutes, the scheduler will:
1. Fetch up to 50 unread emails from the support inbox
2. Send each email to Gemini with your prompt
3. Write the predictions back to Outlook with labels like `AI-Critical`, `AI-Billing`, etc.

---

## Agentic Workflow Quick-Start

### Scenario
You have an orders inbox (`orders@company.com`) that receives order confirmations and updates. You want to:
1. Extract order ID, BOL, and PRO numbers from email bodies
2. Call your Order Management API to create/update orders
3. Call your ETA Tracking API to get delivery status
4. POST final results to a webhook for logging

### Steps

#### 1. Create Agent API Configurations
1. Go to **Configuration** → **Agent APIs**
2. Create first API:
   - Name: `Order Management API`
   - API URL: `https://api.company.com/orders`
   - API Key: `your-secret-key` (stored securely)
3. Create second API:
   - Name: `ETA Tracking API`
   - API URL: `https://api.company.com/eta`
   - API Key: `another-secret-key`

#### 2. Create an Extraction Prompt
1. Go to **Configuration** → **Prompt Templates**
2. Click **+ New Prompt**
3. Name: "Order Data Extractor"
4. Body:
```jinja
Extract structured order data from this email.

Subject: {{subject}}
From: {{sender}}
Body: {{body}}

Extract and return as JSON:
{
  "order_id": "string (e.g., ORD-12345)",
  "bol_number": "string (Bill of Lading, e.g., BOL-98765)",
  "pro_number": "string (PRO number, e.g., PRO-54321)",
  "shipper": "string (company name)",
  "consignee": "string (company name)",
  "pickup_date": "string (YYYY-MM-DD)",
  "delivery_date": "string (YYYY-MM-DD)"
}

If a field is not found, use null.
```
5. Click **Save**

#### 3. Build the Agentic Workflow
1. Go to **Workflow Builders** → **Agentic Workflows**
2. Click **+ New Workflow**
3. **Step 1: Select Inbox & Extraction Prompt**
   - Inbox: `orders@company.com`
   - Extraction Prompt: "Order Data Extractor"
   - Extract reference numbers: ✓ (checked)
4. **Step 2: Configure Agent APIs**
   - Check both:
     - ✓ Order Management API
     - ✓ ETA Tracking API
5. **Step 3: Callback Configuration**
   - Webhook URL: `https://api.company.com/webhooks/email-processing`
6. Click **Save Workflow**

### Result
When emails arrive at the orders inbox, the system will:
1. Extract order ID, BOL, PRO numbers, dates, etc. using Gemini
2. POST to Order Management API with extracted data
3. POST to ETA Tracking API to fetch delivery status
4. POST both the extraction results and API responses to your webhook
5. Log everything for monitoring and debugging

### Webhook Payload Example
```json
{
  "email": {
    "subject": "Order Confirmation - ORD-12345",
    "sender": "orders@supplier.com",
    "body": "..."
  },
  "extracted_data": {
    "order_id": "ORD-12345",
    "bol_number": "BOL-98765",
    "pro_number": "PRO-54321",
    "pickup_date": "2026-04-13",
    "delivery_date": "2026-04-15"
  },
  "agent_api_responses": {
    "Order Management API": {
      "status": "created",
      "order_url": "https://api.company.com/orders/ORD-12345"
    },
    "ETA Tracking API": {
      "status": "in_transit",
      "estimated_delivery": "2026-04-15T14:30:00Z"
    }
  },
  "timestamp": "2026-04-12T09:15:00Z"
}
```

---

## Advanced Tips

### Classification Workflows

#### Use Subject Rules for Fast Categorization
Subject rules bypass Gemini and categorize emails instantly. In the Classification Workflow:
1. Edit your workflow
2. Scroll to **Subject Classify Rules**
3. Add rules:
   - Pattern: `%OnTime%` → Category: `Critical` (auto-assign "Critical" to on-time delivery emails)
   - Pattern: `%Invoice%` → Category: `Billing` (auto-assign "Billing" to invoice emails)

This saves tokens and latency for predictable emails.

#### Narrow Fetch Filters
In **Step 3**, after creating the workflow, you can add fetch filters:
- **Sender allowlist**: Only fetch from specific senders (e.g., `support@vendor.com`)
- **Subject keywords**: Only fetch emails with certain words (e.g., `critical`, `urgent`)
- **Importance**: Only fetch high/normal/low importance emails
- **No attachments**: Skip emails with attachments if not needed

This reduces token spend and improves speed.

#### Model Override
For complex taxonomies, use a more capable model:
1. In your workflow, expand "Advanced Settings" (if available)
2. Model Override: `gemini-3.1-pro` (more capable, higher cost)
3. Save

### Agentic Workflows

#### Chain Multiple APIs
If you need to call APIs in sequence:
1. Add both Agent APIs to your workflow
2. The system calls them in the order you selected
3. Response from first API is available to second API's input (if configured in the backend)

#### Test with a Webhook Service
Before deploying, test your webhook:
1. Use [webhook.site](https://webhook.site) to generate a temporary URL
2. In your workflow, set Webhook URL to the generated URL
3. Trigger an email test and check webhook.site for the payload

#### Conditional Extraction
Use your extraction prompt to handle edge cases:
```jinja
Extract order data. If order_id is not found but PO_number is present, 
use PO_number as order_id. Return null if neither is found.
```

---

## Troubleshooting

### "Prompt and Classification Set are required"
**Problem**: Classification workflow won't save.  
**Solution**: Make sure both a prompt template and classification set are selected. Create them in Configuration first.

### "Workflow appears to run but no emails are categorized"
**Problem**: Polling interval is set but no processing happens.  
**Solution**:
1. Check if your mailbox ID is correct (go to Inboxes to verify it's there)
2. Check if the scheduler is running: `python -m graph_enterprise.jobs.scheduler_loop`
3. Check if a Celery worker is running: `celery -A graph_enterprise.jobs.celery_app worker -l info`

### "Agent APIs are not being called"
**Problem**: Agentic workflow saved but no API calls happen.  
**Solution**:
1. Make sure Agent API credentials are valid (go to Agent APIs page)
2. Ensure at least one API is selected in Step 2
3. Check the webhook URL is accessible (your webhook should receive a POST on each email)

### "Write-back is not working"
**Problem**: Categories are not appearing in Outlook.  
**Solution**:
1. Ensure **Write Categories Back to Outlook** is enabled in Step 4
2. Verify your Azure credentials have `Mail.ReadWrite` permission (check README)
3. Check run logs in Results page for errors

---

## Next Steps

- **Monitor runs**: Go to **Results & Analytics** to see real-time token usage and email volumes
- **Fine-tune prompts**: Use **Prompt Templates** test feature to validate classifier behavior
- **Add more workflows**: Scale to handle multiple inboxes or use cases
- **Check logs**: Results page shows classification accuracy, API response times, and errors

