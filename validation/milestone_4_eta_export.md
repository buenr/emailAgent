# Validation Contract — Milestone 4: ETA Pipeline Config + Export/Import

Mission: Production UI Overhaul

This contract defines behavioral assertions for Milestone 4, which adds ETA
pipeline configuration fields to the inbox CRUD flow and introduces full
configuration export/import endpoints with a UI surface.

---

## ETA Pipeline Config

### VAL-ETA-001: ETA fields appear in inbox create/edit form

When the user opens the inbox create or edit form, the page must render an
"ETA Pipeline" section containing four controls:
- a toggle labeled "ETA Lookup Enabled"
- a text input labeled "ETA Lookup API URL"
- a password-masked text input labeled "ETA Lookup API Key"
- a toggle labeled "ETA Draft Enabled"

All four controls must be visible without scrolling past the fetch-filter
accordion. On a new inbox, the toggles default to **off** and **on**
respectively (see VAL-ETA-003), and the text fields are empty.

**Pass**: All four controls are present and labelled as above.
**Fail**: Any control is missing, mislabeled, or hidden behind an extra click.

Tool: agent-browser
Evidence: screenshot of the inbox edit form showing the ETA Pipeline section

---

### VAL-ETA-002: ETA lookup toggle enables/disables API URL and key fields

When "ETA Lookup Enabled" is **unchecked**, the "ETA Lookup API URL" and
"ETA Lookup API Key" inputs must be disabled (greyed out, unclickable, and
not submitted). When the toggle is **checked**, both inputs become editable.

**Pass**: Toggling the checkbox immediately flips the disabled state of both
URL and API key fields.
**Fail**: Fields remain editable when the toggle is off, or remain disabled
when the toggle is on.

Tool: agent-browser
Evidence: two screenshots — toggle off (fields disabled), toggle on (fields
enabled); or a single screenshot with the disabled styling clearly visible

---

### VAL-ETA-003: ETA draft toggle defaults to enabled

When creating a **new** inbox or editing an inbox that has never had ETA
fields set, the "ETA Draft Enabled" toggle must default to **checked** (true).
This mirrors the backend default `eta_draft_enabled: bool = True` in
`MailboxPipelineConfig`.

When editing an existing inbox where `eta_draft_enabled` was previously set
to `false`, the toggle must reflect that saved value (unchecked).

**Pass**: New inbox shows ETA Draft toggle checked; existing inbox with
`eta_draft_enabled=false` shows it unchecked.
**Fail**: Toggle defaults to unchecked on a new inbox, or does not reflect
the persisted value on edit.

Tool: agent-browser
Evidence: screenshot of new-inbox form (toggle checked); screenshot editing
an inbox where `eta_draft_enabled` was saved as `false` (toggle unchecked)

---

### VAL-ETA-004: Creating an inbox with ETA fields persists them

POST `/api/inboxes` with a payload that includes:
```json
{
  "mailbox_id": "eta-test@example.com",
  "prompt_template_id": 1,
  "classification_set_id": 1,
  "eta_lookup_enabled": true,
  "eta_lookup_api_url": "https://eta.example.com/api",
  "eta_lookup_api_key": "sk-abc123",
  "eta_draft_enabled": false
}
```
Then GET `/api/inboxes/{id}` must return the created inbox with all four ETA
fields exactly matching the submitted values.

**Pass**: The GET response includes `eta_lookup_enabled: true`,
`eta_lookup_api_url: "https://eta.example.com/api"`,
`eta_lookup_api_key: "sk-abc123"`, `eta_draft_enabled: false`.
**Fail**: Any ETA field is missing, null, or has a different value.

Tool: curl
Evidence: POST response body; GET response body showing persisted ETA fields

---

### VAL-ETA-005: Updating an inbox ETA fields persists changes

Given an existing inbox (id=N) with `eta_lookup_enabled=false`, call
PUT `/api/inboxes/N` with:
```json
{
  "eta_lookup_enabled": true,
  "eta_lookup_api_url": "https://new-url.example.com",
  "eta_lookup_api_key": "key-updated",
  "eta_draft_enabled": true,
  …other required fields unchanged
}
```
Then GET `/api/inboxes/N` must reflect the updated ETA values.

**Pass**: GET returns the new `eta_lookup_api_url`, `eta_lookup_api_key`,
and both toggles in their updated state.
**Fail**: ETA fields remain at their previous values or are missing.

Tool: curl
Evidence: PUT response; subsequent GET response showing updated ETA fields

---

### VAL-ETA-006: _row_to_config maps ETA fields into MailboxPipelineConfig

After creating an inbox with ETA fields (as in VAL-ETA-004), the internal
`_row_to_config` function (used by `load_mailbox_config_from_db` and the
test-prompt endpoint) must produce a `MailboxPipelineConfig` whose
`eta_lookup_enabled`, `eta_lookup_api_url`, `eta_lookup_api_key`, and
`eta_draft_enabled` fields match the database row.

This is verified indirectly: POST `/api/test-prompt` for the inbox must not
raise a 500 error due to a missing `eta_lookup_enabled` key when the
pipeline config is assembled.

**Pass**: Test-prompt endpoint returns 200 (or 503 if Vertex is
unconfigured, but not a 500 KeyError).
**Fail**: 500 error with a traceback referencing a missing ETA attribute.

Tool: curl
Evidence: test-prompt response status and body

---

## Export / Import

### VAL-EXPORT-001: GET /api/export returns full config bundle

GET `/api/export` must return HTTP 200 with a JSON body containing four
top-level keys: `prompts`, `classification_sets`, `inboxes`, `models`.
Each key maps to an array of the corresponding entities with all their
fields (including ETA fields on inboxes).

**Pass**: Response is valid JSON; all four keys exist; each array is
non-empty when the database has at least one entity of that type; inbox
objects include ETA fields.
**Fail**: Any top-level key missing; inbox objects lack ETA fields; response
is not JSON or status is not 200.

Tool: curl
Evidence: response body (or truncated excerpt) showing the four keys and
sample inbox with ETA fields

---

### VAL-EXPORT-002: POST /api/import upserts all entities from a valid bundle

POST `/api/import` with a JSON body containing a full config bundle (same
shape as the export response) where all entity IDs reference objects that
do **not** yet exist in the database. The endpoint must create all prompts,
classification sets (with their categories), inboxes, and models, and return
HTTP 200 with a summary (e.g. `{"created": 4, "updated": 0}`).

After import, GET `/api/inboxes` must list the newly created inboxes with
correct ETA field values.

**Pass**: All entities are created; inboxes carry correct ETA fields; import
response indicates creation counts.
**Fail**: Any entity missing after import; ETA fields lost; endpoint returns
4xx/5xx.

Tool: curl
Evidence: POST response body; subsequent GET listing confirming created
entities

---

### VAL-EXPORT-003: Import handles ID conflicts via remapping

POST `/api/import` with a bundle where a prompt template has `id=1` but the
database already has a different prompt at `id=1`. The endpoint must remap
the imported prompt to a new ID and update all inbound foreign key references
(e.g. inboxes referencing `prompt_template_id=1` in the bundle must be
rewired to the new prompt ID).

Alternatively, if the design chooses "upsert if name matches, skip if
conflict", the response must clearly indicate which entities were skipped
and which were updated.

**Pass**: No 409/integrity error; imported inboxes reference valid
(prompt/template/model) IDs; response indicates remapping or skip decisions.
**Fail**: 409 integrity error; imported inbox references a stale FK; silent
data corruption.

Tool: curl
Evidence: POST response body showing remap/skip details; subsequent GET
confirming referential integrity

---

### VAL-EXPORT-004: Export button in UI downloads JSON file

On the dashboard or settings page, an "Export Configuration" button must be
present. Clicking it triggers a browser download of a `.json` file whose
contents match the structure returned by GET `/api/export`.

**Pass**: Clicking the button initiates a file download; the downloaded file
is valid JSON with `prompts`, `classification_sets`, `inboxes`, `models`
keys.
**Fail**: No download starts; file is empty or not JSON; button is missing.

Tool: agent-browser
Evidence: screenshot of the button; downloaded file contents (or console
network log showing the download request)

---

### VAL-EXPORT-005: Import button accepts JSON file upload and shows success/error

An "Import Configuration" button (or file-drop zone) must appear on the same
page as the export button. When the user selects a valid JSON config file,
the UI must:
1. POST the file contents to `/api/import`
2. On 2xx: display a success message (e.g. "Imported N entities")
3. On 4xx/5xx: display an error message with the server detail string

**Pass**: Valid file → success toast/message; invalid file (e.g. malformed
JSON) → error message displayed; no uncaught exceptions in the browser
console.
**Fail**: No visual feedback after upload; error thrown in console; page
crashes.

Tool: agent-browser
Evidence: screenshot of success message after valid import; screenshot of
error message after invalid import; console-errors log

---

### VAL-EXPORT-006: Import preserves ETA fields across round-trip

Export the current configuration via GET `/api/export`, then immediately
import the same bundle via POST `/api/import` (into a clean or remapped
state). All ETA fields (`eta_lookup_enabled`, `eta_lookup_api_url`,
`eta_lookup_api_key`, `eta_draft_enabled`) on every inbox must survive the
round-trip unchanged.

**Pass**: Post-import GET `/api/inboxes/{id}` for each inbox matches the
pre-export ETA field values.
**Fail**: Any ETA field is dropped, reset to default, or altered during the
round-trip.

Tool: curl
Evidence: pre-export GET response for a sample inbox; post-import GET
response for the same inbox showing identical ETA fields
