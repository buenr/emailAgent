# Validation Contract — Cross-Area Flows

**Mission:** Production UI Overhaul  
**Scope:** Behaviors spanning multiple milestones / features  
**Prefix:** VAL-CROSS-

---

### VAL-CROSS-001: Full navigation flow renders shadcn/ui components throughout

A user who logs in, lands on the dashboard, navigates to an inbox detail
page, opens the edit form, makes a change, and saves must encounter only
shadcn/ui-styled components at every step. Specifically:

1. Login page uses shadcn/ui `<Button>` and `<Input>` (not raw HTML).
2. Dashboard cards and charts render inside shadcn/ui `<Card>` shells.
3. Inbox list rows use shadcn/ui `<Table>` / `<TableRow>` primitives.
4. Inbox edit form uses shadcn/ui `<Dialog>` or `<Sheet>`, `<Input>`,
   `<Switch>`, and `<Button>`.
5. The save action triggers a shadcn/ui `<Toast>` (not `window.alert`).

**Pass:** Every interactive element on each page in the flow is backed by a
shadcn/ui primitive (identifiable via `data-slot` attributes or radix
component class names in the DOM). No raw `<input>`, `<button type="submit">`
without shadcn wrapping, or `window.alert`/`confirm` appears.
**Fail:** Any page in the flow renders a native HTML control not wrapped by
a shadcn/ui component, or uses `window.alert`/`confirm`/`prompt`.

Tool: agent-browser  
Evidence: screenshots of each page (login, dashboard, inbox list, inbox
edit, post-save toast); DOM inspection showing shadcn/ui primitives

---

### VAL-CROSS-002: Dashboard charts reflect data from a manual "Run Now" trigger

When a user triggers "Run Now" on an inbox from the classification-results
or inbox detail page, the backend processes the run and records new
classification and token-spend data. After the run completes, navigating to
the dashboard must show updated charts that include the newly generated
data points (e.g., token spend line chart increments, classification
breakdown bar chart includes new categories or higher counts).

**Pass:** Dashboard token-spend and classification-breakdown charts show
visibly different data (higher values or additional data points) compared
to their state before the Run Now trigger. Network calls confirm the stats
endpoints return fresh payloads including the new run's contributions.
**Fail:** Charts remain unchanged after a completed Run Now, or the stats
endpoints still return stale data.

Tool: agent-browser  
Evidence: screenshot of dashboard charts before Run Now; screenshot of
Run Now trigger; screenshot of dashboard charts after Run Now completes;
network calls to stats endpoints showing updated payloads

---

### VAL-CROSS-003: Classification results page updates after Run Now completes

The classification results viewer must reflect the outcome of a "Run Now"
trigger without requiring a manual page refresh. While the results page is
open, triggering "Run Now" on its associated inbox must cause the
auto-refresh mechanism (from M2's 30-second poll) to eventually surface new
classification rows for the messages processed by the run.

**Pass:** Within ≤60 seconds of the Run Now completing, the classification
results page shows new rows (or updated rows) corresponding to the
just-completed run. No full page reload occurs — only the poll-driven
partial update.
**Fail:** New rows do not appear within 60 seconds, or the page requires a
full browser reload to show them.

Tool: agent-browser  
Evidence: screenshot of classification results page before Run Now; network
log showing the Run Now POST; screenshot of the same page after the
auto-refresh poll returns updated data (≤60 s); console log showing no
full-reload navigation events

---

### VAL-CROSS-004: ETA config fields appear in inbox form and are included in export bundle

An inbox that has been configured with ETA fields (lookup enabled, API URL,
API key, draft enabled) via the inbox edit form must carry those same ETA
fields when exported through the "Export Configuration" flow. This validates
that the same data model is shared between the CRUD form (M4 ETA config)
and the export endpoint (M4 export).

1. Edit an inbox, set `eta_lookup_enabled=true`, provide an API URL and
   key, set `eta_draft_enabled=false`, and save.
2. Trigger the "Export Configuration" download.
3. Open the downloaded JSON file and locate the inbox entry.

**Pass:** The exported JSON for the edited inbox includes all four ETA
fields with values exactly matching what was saved in the form.
**Fail:** Any ETA field is missing from the export, has a null value, or
does not match the saved form state.

Tool: agent-browser  
Evidence: screenshot of inbox edit form with ETA fields filled; screenshot
of export download; excerpt of exported JSON showing the inbox with ETA
fields

---

### VAL-CROSS-005: Import with ETA fields populates inbox ETA config correctly

Importing a configuration bundle that contains inboxes with ETA fields must
result in those inboxes being fully editable in the UI with the correct ETA
field values pre-populated in the edit form. After import:

1. POST `/api/import` with a bundle containing at least one inbox that has
   `eta_lookup_enabled=true`, `eta_lookup_api_url`, `eta_lookup_api_key`,
   and `eta_draft_enabled` set.
2. Navigate to the imported inbox's edit form in the UI.

**Pass:** The inbox edit form shows "ETA Lookup Enabled" checked, the API
URL and API key fields populated with the imported values, and "ETA Draft
Enabled" reflecting the imported toggle state. GET `/api/inboxes/{id}`
confirms the values match the import bundle.
**Fail:** ETA fields in the edit form are blank/default, or the GET
response lacks ETA fields.

Tool: agent-browser  
Evidence: screenshot of inbox edit form after import showing populated ETA
fields; GET response body confirming ETA field values

---

### VAL-CROSS-006: Bulk-activate inboxes then Run Now on one of them succeeds

A user must be able to bulk-activate a set of inactive inboxes via the
dashboard bulk action bar and then immediately trigger "Run Now" on one of
the newly activated inboxes without encountering an error.

1. Ensure ≥2 inboxes are inactive.
2. On the dashboard inbox list, select the inactive inboxes via checkboxes
   and click "Activate".
3. After the bulk activate succeeds, navigate to one of the now-active
   inboxes and click "Run Now".

**Pass:** Bulk activate completes (toast notification confirms), the inbox's
`is_active` flag is true, and "Run Now" triggers successfully (POST returns
2xx and a run is initiated). No 403/409 error claiming the inbox is
inactive.
**Fail:** Bulk activate appears to succeed but Run Now fails with an
inactive-inbox error, or Run Now button is disabled/hidden after activation.

Tool: agent-browser  
Evidence: screenshot of bulk-activate action and toast; screenshot of Run
Now button on the activated inbox; network call showing Run Now POST and
2xx response

---

### VAL-CROSS-007: Toast notifications render consistently across all pages

Shadcn/ui `<Toast>` notifications must function identically on the
dashboard, classification results viewer, inbox edit form, and ETA/export
settings page. The test triggers a toast-generating action on each page:

- Dashboard: bulk-activate inboxes → success toast
- Classification results: Run Now → "Run started" toast
- Inbox edit: save with invalid data → validation error toast
- Settings/Export: import invalid file → error toast

**Pass:** Every page renders the toast in the same screen position (bottom-
right or top-right per design), using the same styling (shadcn/ui Toast
component), and the toast auto-dismisses after the expected duration. No
page falls back to `window.alert` or renders a differently styled toast.
**Fail:** Any page uses a different toast mechanism, position, or styling,
or falls back to a browser native dialog.

Tool: agent-browser  
Evidence: four screenshots, one per page, each showing a toast notification
in consistent position and style; DOM snippets confirming shadcn/ui Toast
primitives

---

### VAL-CROSS-008: Dark theme is consistent across new pages

When the user toggles the application to dark mode, all four milestone
surfaces must render in dark theme with consistent color tokens:

1. Dashboard: chart backgrounds, card surfaces, and text use dark palette.
2. Classification results viewer: table rows, status badges, and detail
   panels use dark palette.
3. ETA config section: form labels, inputs, toggles, and section headers
   use dark palette.
4. Export/Import page: buttons, file-drop zone, and status messages use
   dark palette.

**Pass:** Every surface renders with dark background (`hsl(var(--card))` /
`hsl(var(--background))` dark tokens), light foreground text, and no
"flash of white" on any unstyled region. Charts render with dark grid lines
and axis labels. Form inputs show dark fill with light placeholder text.
**Fail:** Any page or component renders with a light background in dark
mode, or charts show light grid/axis styling.

Tool: agent-browser  
Evidence: four screenshots (dashboard, classification results, ETA config
form, export page) all in dark mode; CSS computed styles showing dark token
values on sampled elements

---

### VAL-CROSS-009: Search inboxes → select → Run Now → see classification results

A user must be able to search for an inbox by name, select it from filtered
results, trigger "Run Now," and then view the classification results for
that run — all within a single continuous workflow that spans the dashboard
search feature (M2), the Run Now action (M3), and the classification
results viewer (M3).

1. On the dashboard inbox list, type a search query into the search bar.
2. The inbox list filters to show matching results.
3. Click on one of the filtered inboxes to open its detail view.
4. Click "Run Now."
5. Wait for the run to complete, then navigate to the classification
   results viewer for that inbox.

**Pass:** Search filters correctly, the selected inbox's detail page opens,
Run Now initiates successfully, and the classification results viewer
eventually shows results from the triggered run. The entire flow requires
no page reloads or error recovery.
**Fail:** Search does not filter, inbox detail does not open, Run Now
fails, or classification results do not appear after the run completes.

Tool: agent-browser  
Evidence: screenshot of search input with filtered results; screenshot of
inbox detail page with Run Now button; network call showing Run Now POST;
screenshot of classification results page showing new results

---

### VAL-CROSS-010: Export → modify in UI → export again includes changes

A configuration export must be a live snapshot: if the user exports, makes
changes via the UI, then exports again, the second export must reflect all
intervening modifications.

1. Click "Export Configuration" and save the first JSON file.
2. Edit an inbox: change its classification set, toggle ETA lookup on, and
   update the ETA API URL.
3. Click "Export Configuration" again and save the second JSON file.
4. Diff the two files for the modified inbox.

**Pass:** The second export JSON shows the updated `classification_set_id`,
`eta_lookup_enabled: true`, and the new `eta_lookup_api_url` for the
modified inbox. All other inboxes and entities remain unchanged between
the two exports.
**Fail:** The second export still contains the old values, or unmodified
entities are unexpectedly altered.

Tool: agent-browser  
Evidence: first exported JSON (excerpt for the target inbox); screenshot of
inbox edit with changes; second exported JSON (excerpt for the same inbox);
diff highlighting the changed fields

---

### VAL-CROSS-011: Navigation highlighting persists across deep-linked pages

When a user navigates from the dashboard to a deep-linked sub-page (e.g.,
classification results for a specific inbox, or the ETA config section of
an inbox edit form), the sidebar or top-nav must continue to highlight the
correct parent section (e.g., "Dashboard" remains highlighted when viewing
classification results that were reached from the dashboard).

**Pass:** The navigation item corresponding to the user's logical section
remains highlighted (active state with visual indicator) even on sub-pages
reached via deep navigation. No nav item loses its highlight, and no
incorrect item becomes highlighted.
**Fail:** Active nav highlight disappears on a sub-page, or an incorrect
nav item is highlighted.

Tool: agent-browser  
Evidence: screenshots of the nav bar on the dashboard, then on a
classification results sub-page, then on an inbox edit sub-page — all
showing consistent highlighting

---

### VAL-CROSS-012: Error toast on network failure does not break subsequent flows

If a network request fails (e.g., the backend is temporarily unreachable
when the user clicks "Run Now"), a shadcn/ui error toast must appear. After
the backend recovers, the user must be able to retry the same action (Run
Now) or navigate to a different page and perform other actions without any
residual broken state.

1. With the backend unreachable, click "Run Now" on an inbox.
2. Observe the error toast.
3. Restore backend connectivity.
4. Click "Run Now" again on the same inbox.
5. Navigate to the dashboard and verify charts load.

**Pass:** Error toast appears for the failed request; after recovery, Run
Now succeeds (2xx response), and dashboard charts render correctly. No
JavaScript errors in console; no UI elements stuck in a loading state.
**Fail:** After the error, the UI becomes unresponsive, buttons remain
disabled, or subsequent successful requests still trigger error toasts.

Tool: agent-browser  
Evidence: screenshot of error toast on failed Run Now; screenshot of
successful Run Now after recovery; screenshot of dashboard loading
correctly; console-errors log showing no uncaught exceptions
