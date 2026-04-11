# Validation Contract — Milestone 2: Dashboard & Statistics

**Mission:** Production UI Overhaul  
**Milestone:** 2 — Dashboard & Statistics  
**Prefix:** VAL-DASH-

---

### VAL-DASH-001: Token Spend Line Chart Renders with Data Points

The dashboard page at `/dashboard` must display a line chart visualizing token spend over time. When the backend returns non-empty data from `GET /api/stats/token-trends`, the chart must render a continuous line with visible data points for each time bucket. The chart must include a toggle or selector for 7-day and 30-day windows. **Pass:** chart canvas is present in the DOM, contains an SVG/Canvas line with ≥1 data point, and the 7d/30d toggle is visible and functional. **Fail:** chart element missing, no data points rendered, or toggle absent.

Tool: agent-browser  
Evidence: screenshot of dashboard showing token spend chart; screenshot after clicking 30d toggle

---

### VAL-DASH-002: Classification Breakdown Bar Chart Renders

The dashboard page must display a bar chart showing classification counts per category. When `GET /api/stats/classification-breakdown` returns non-empty data, each category must appear as a labeled bar whose height is proportional to its count. **Pass:** bar chart canvas is present with ≥1 labeled bar matching category names from the response payload. **Fail:** chart element missing or bars not rendered.

Tool: agent-browser  
Evidence: screenshot of classification breakdown chart

---

### VAL-DASH-003: Health Status Cards Display Trend Indicators

The dashboard must render one health status card per fleet inbox showing current health (OK / Error) and a trend indicator comparing the current period's health to the prior period. Trend indicators must be directional arrows or color shifts (e.g., green up-arrow for improvement, red down-arrow for degradation). **Pass:** each inbox row or card shows a health badge (green/red) plus a trend arrow or delta value. **Fail:** health badges present but no trend indicator visible.

Tool: agent-browser  
Evidence: screenshot showing health cards with trend arrows

---

### VAL-DASH-004: GET /api/stats/token-trends Returns Correct Data Shape

`GET /api/stats/token-trends?range=7d` must return HTTP 200 with a JSON body containing an array of time-bucketed objects. Each object must include at minimum `date` (ISO 8601 date string) and `tokens` (numeric). The response must cover exactly 7 buckets for `range=7d` and 30 buckets for `range=30d`. **Pass:** response is a JSON array of objects, each with `date` and `tokens` keys, array length equals the requested range. **Fail:** missing keys, wrong length, or non-200 status.

Tool: curl  
Evidence: raw response body and HTTP status code

---

### VAL-DASH-005: GET /api/stats/classification-breakdown Returns Correct Data Shape

`GET /api/stats/classification-breakdown` must return HTTP 200 with a JSON array of objects, each containing `category` (string) and `count` (integer ≥ 0). Categories must match those defined in the active classification sets. **Pass:** response is a JSON array of `{category, count}` objects. **Fail:** missing keys, non-numeric count, or non-200 status.

Tool: curl  
Evidence: raw response body and HTTP status code

---

### VAL-DASH-006: GET /api/stats/run-volume Returns Correct Data Shape

`GET /api/stats/run-volume?range=7d` must return HTTP 200 with a JSON array of time-bucketed objects containing `date` and `runs` (integer) at minimum. Used by the dashboard for run-volume trend lines. **Pass:** response is a JSON array of `{date, runs}` objects with length matching the range parameter. **Fail:** missing keys, wrong length, or non-200 status.

Tool: curl  
Evidence: raw response body and HTTP status code

---

### VAL-DASH-007: Dashboard Auto-Refreshes Without Page Reload

The dashboard must poll the backend for updated data every 30 seconds without requiring a full page reload. After the initial load, the browser must issue periodic `GET` requests to the stats endpoints at 30-second intervals. Chart data and health cards must update in-place when fresh data arrives. **Pass:** after 35 seconds on the dashboard, browser DevTools network tab shows at least one additional round of stats requests, and the page URL has not changed (no full reload). **Fail:** no network activity after initial load, or page performs a full reload.

Tool: agent-browser  
Evidence: network tab capture showing second round of stats requests after 30s; console-errors log showing no errors

---

### VAL-DASH-008: Inbox Search Filters Results by mailbox_id Substring

The inbox list must accept a `?search=` query parameter. Calling `GET /api/inboxes?search=test` must return only inboxes whose `mailbox_id` contains the substring "test" (case-insensitive). When the search parameter is omitted or empty, all inboxes are returned (subject to pagination). **Pass:** response `items` array contains only rows where `mailbox_id` includes the search string; total reflects the filtered count. **Fail:** unfiltered results returned, or endpoint returns 4xx/5xx.

Tool: curl  
Evidence: response bodies for `GET /api/inboxes` (unfiltered) vs `GET /api/inboxes?search=<known_substring>`

---

### VAL-DASH-009: Inbox is_active Filter Works

The inbox list must accept an `?is_active=` query parameter. Calling `GET /api/inboxes?is_active=true` must return only inboxes where `is_active` is true; `?is_active=false` must return only inactive inboxes. **Pass:** every item in the response has `is_active` matching the requested filter value. **Fail:** items with wrong `is_active` appear, or endpoint returns 4xx/5xx.

Tool: curl  
Evidence: response bodies for `?is_active=true` and `?is_active=false`

---

### VAL-DASH-010: Bulk Activate Selects Multiple Inboxes and Activates Them

The UI must present checkboxes on each inbox row and a floating action bar when ≥1 checkbox is selected. Clicking "Activate" in the action bar must send `POST /api/inboxes/bulk-activate` with a JSON body `{inbox_ids: [1, 2, …]}`. The backend must set `is_active = true` for every listed inbox and return HTTP 200 with `{updated: N}`. **Pass:** after selecting 2+ inboxes via checkboxes and clicking Activate, the POST request is observed in network traffic, the response confirms the count, and a subsequent `GET /api/inboxes` shows those inboxes as active. **Fail:** no checkboxes, no action bar, POST not issued, or inboxes remain inactive.

Tool: agent-browser  
Evidence: screenshot of checkbox selection + action bar; network call showing POST with inbox_ids; screenshot of updated inbox list

---

### VAL-DASH-011: Bulk Delete Selects Multiple Inboxes with Confirmation

The UI must offer a "Delete" button in the bulk action bar. Clicking it must display a confirmation dialog listing the selected mailbox IDs. On confirm, `POST /api/inboxes/bulk-delete` is sent with `{inbox_ids: [1, 2, …]}`. The backend must delete those inboxes and return HTTP 200 with `{deleted: N}`. **Pass:** confirmation dialog appears before deletion, POST is sent only after user confirms, and a subsequent `GET /api/inboxes` no longer contains the deleted entries. **Fail:** no confirmation dialog, POST sent without confirmation, or inboxes still present after deletion.

Tool: agent-browser  
Evidence: screenshot of confirmation dialog; network call showing POST; screenshot of inbox list after deletion

---

### VAL-DASH-012: Bulk Endpoints Reject Empty or Missing inbox_ids

`POST /api/inboxes/bulk-activate` and `POST /api/inboxes/bulk-delete` must validate the request body. Sending `{}` (no `inbox_ids` key) or `{"inbox_ids": []}` must return HTTP 422 with a descriptive error message. **Pass:** both endpoints return 422 for empty/missing `inbox_ids`. **Fail:** endpoint returns 200 or any non-422 status.

Tool: curl  
Evidence: response status and body for both endpoints with empty payload

---

### VAL-DASH-013: Charts Handle Empty Data Gracefully

When backend stats endpoints return empty arrays (e.g., no runs recorded yet), the token spend chart and classification breakdown chart must not crash or show broken SVG/Canvas artifacts. Instead, they must display an empty-state message such as "No data available" or render a blank chart area with no console errors. **Pass:** dashboard loads without JavaScript errors; charts show empty state or blank area; no stack traces in console. **Fail:** JavaScript error thrown, or chart renders broken artifacts.

Tool: agent-browser  
Evidence: screenshot of dashboard with empty data; console-errors log showing zero errors

---

### VAL-DASH-014: Search and is_active Filters Combine Correctly

`GET /api/inboxes?search=foo&is_active=true` must return only inboxes whose `mailbox_id` contains "foo" **and** whose `is_active` is true. Both filters must be applied simultaneously. **Pass:** every returned item satisfies both conditions. **Fail:** items returned that violate either condition.

Tool: curl  
Evidence: response body for combined query showing filtered results

---

### VAL-DASH-015: Auto-Poll Pauses When Dashboard Tab Is Hidden

When the browser tab containing the dashboard is hidden (e.g., user switches to another tab), the 30-second polling must pause to avoid unnecessary network traffic. When the tab becomes visible again, polling resumes. **Pass:** after hiding the tab for >60 seconds, only 0–1 polling requests appear (not 2+); after tab becomes visible, polling resumes within 30 seconds. **Fail:** polling continues at 30s intervals while tab is hidden.

Tool: agent-browser  
Evidence: network tab capture during tab-hidden period showing no/reduced polling; capture after tab-visible showing resumed polling

---

### VAL-DASH-016: Bulk Activate Is Idempotent

Calling `POST /api/inboxes/bulk-activate` with inbox IDs that are already active must succeed without error. The response must still return `{updated: N}` where N reflects the number of inboxes processed (including those already active). **Pass:** second call for already-active inboxes returns 200 with a valid `updated` count; no 409 or 500 errors. **Fail:** endpoint returns error on already-active inboxes.

Tool: curl  
Evidence: two sequential POST requests with same inbox_ids; both return 200
