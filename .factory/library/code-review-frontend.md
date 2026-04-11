# Frontend Code Review Findings

**Date:** 2026-04-11  
**Scope:** `web/app` — 7 pages, 4 custom components, 6 config files, 18 shadcn/ui primitives  
**Severity counts:** 3 Critical, 21 High, 36 Medium, 22 Low

---

## Critical Issues (3)

1. **No error boundaries** — Zero `error.tsx` files anywhere. Any render error crashes the entire app to a white screen with no recovery.
2. **Results page client-side pagination** — `results/page.tsx` fetches ALL classifications from the API, then slices for display with `rows.slice()`. Doesn't scale; will break if API ever adds server-side pagination.
3. **Inboxes page 3 conflicting useEffect blocks** — `inboxes/page.tsx` has 3 overlapping effects for form state sync. The 2nd effect resets form state whenever `prompts` or `sets` change (even during user edits), and the 3rd re-populates. Causes form flicker, overwrites in-progress edits, and makes the 30+ useState hooks fragile.

## High Issues (21)

### Bugs
4. **Stale closure in `handleBulkDelete`** — `dashboard/page.tsx` line ~219: `selectedIds` captured at function definition time may differ from current state when AlertDialog confirm is clicked.
5. **`onRunNow` bypasses centralized `apiSend`** — `inboxes/page.tsx` lines 336–360: uses raw `fetch` with hardcoded URL, duplicating auth/401 logic.
6. **Checkbox `indeterminate` prop ignored** — `dashboard/page.tsx` line 82: Base UI Checkbox doesn't support `indeterminate`; the "select all" checkbox never shows indeterminate visual state.
7. **Prompt page `selected` is new reference every render** — `prompts/page.tsx` line ~86: `.find()` returns new object each render, causing the form-sync useEffect to fire on every render and overwrite user edits.
8. **No AbortController on fetches** — Multiple pages: login health check, results classifications, inboxes detail fetch. Stale responses can overwrite fresh state.
9. **`setLoading(true)` only on initial mount** — prompts, classifications, models pages: after first load, `loading` stays `false` forever; no loading indicator on subsequent refetches.
10. **Dialog closes before async action completes** — classifications, models, inboxes: AlertDialog closes immediately on click; if the async delete/save fails, user has no visual feedback since the dialog is already gone.

### Security / Auth
11. **Auth is purely client-side** — `AppShell.tsx`: reads `sessionStorage` token with no server validation. No Next.js middleware. XSS-vulnerable storage.
12. **Auth token in `sessionStorage`** — Lost on new tabs, doesn't persist, vulnerable to XSS extraction. Should be HTTP-only cookie via proxy route or at minimum localStorage with expiry.

### Accessibility
13. **No Label-Input `htmlFor`/`id` linking** — All form pages: `<Label>` components are never programmatically associated with inputs. Screen readers announce inputs without labels.
14. **No `aria-current="page"` on active nav links** — `Nav.tsx`: active state is visual-only (bg color change). Screen readers can't identify current page.
15. **Nav `pathname === href` doesn't match sub-routes** — `Nav.tsx` line 21: `/prompts/edit/1` won't highlight `/prompts` link.
16. **Charts have zero accessible alternatives** — `dashboard/page.tsx`: LineChart, BarChart, AreaChart have no aria-label, no data table, no caption. Completely invisible to screen readers.
17. **Table row `onClick` without keyboard handler** — `inboxes/page.tsx` line 641: row selection only works via mouse click. No `tabIndex`, `role="button"`, or `onKeyDown`.
18. **Monaco editor completely inaccessible** — `PromptMonaco.tsx`: no aria-label, no fallback textarea. Screen reader users cannot use this input.
19. **Category table inputs lack labels** — `classifications/page.tsx` lines 267–286: Input/Textarea in table cells have no aria-label. Screen readers hear "edit text" with no row/column context.

### Architecture / Config
20. **Duplicate/conflicting CSS variable blocks** — `globals.css`: custom `:root` vars (`--bg`, `--surface`, etc.) conflict with shadcn standard vars (`--background`, `--foreground`). `body { bg-slate-950 }` vs `body { bg-background }` causes unpredictable theming.
21. **All types inline/duplicated across pages** — No shared `types/` directory. `InboxListResponse` defined in both `prompts/page.tsx` and `inboxes/page.tsx`. Type drift risk.
22. **`apiSend` discards HTTP status codes** — `lib/api.ts`: errors surface only as `Error.message` strings. Consumers do fragile `msg.includes("409")` string matching.
23. **All 7 pages are `"use client"` + useEffect+fetch** — Zero Server Components, zero `loading.tsx`, zero streaming. All pages pay full JS bundle cost.
24. **Empty `next.config.mjs`** — No `reactStrictMode`, no API rewrites/proxy, no image config, no `poweredByHeader: false`.

## Medium Issues (36)

- No RSC or Suspense boundaries
- Inboxes page: 30+ useState hooks, should use react-hook-form + zod
- Filter state in useState, not URL params (no deep-linking, no back-button support)
- `next-themes` installed but never used (dead dependency)
- `shadcn` CLI in `dependencies` instead of `devDependencies`
- Missing `noUncheckedIndexedAccess` in tsconfig
- Checkbox `onCheckedChange` passes `"indeterminate"` to boolean setters
- `onSave` in inboxes causes full-page skeleton flash (destroying form context)
- No client-side form validation on inbox form
- Silent error swallowing in dashboard `loadStats` (empty catch)
- Results page: category dropdown derived from fetched data — categories disappear when filters narrow results
- Results page: date filters sent without timezone context
- No retry mechanism for failed data loads
- AppShell: no redirect-back logic after login
- AppShell: flash of loading skeleton on initial render
- Derived data (classBreakdownEntries, allChecked, someChecked) not memoized in dashboard
- Inline objects in recharts props create new references every render
- Hardcoded `text-white`/`text-slate-400` in login page (breaks with light theme)
- `new Date().toLocaleString()` without explicit locale
- Classifications: `key={i}` (array index) on category table rows
- Classifications: `normalizeRows` silently drops empty-name rows
- Classifications: Save button is `type="button"`, bypassing HTML form validation
- Models: 409 detection via string matching on error message
- Models: Delete button lacks aria-label indicating which model
- PromptMonaco: controlled editor causes cursor jumps on re-render
- PromptMonaco: options object recreated every render
- PromptMonaco: no debounce on onChange
- No skip-to-content link in AppShell
- No `aria-label` on `<main>` landmark
- No `aria-label` on `<aside>` and `<nav>` in Nav
- Run log dialog lacks focus trapping annotations
- "View details" buttons in run logs list lack unique accessible names
- `<details>/<summary>` for fetch filters has no ARIA enhancement
- Missing `@tailwindcss/typography` plugin
- Theme not customized — still default shadcn zinc values

## Low Issues (22)

- Inline arrow functions in JSX (new reference per render) — multiple files
- `signOut` in Nav not wrapped in useCallback
- No focus management on login step transitions
- Health check failure is silent (no user notification)
- No loading indicator during initial health check
- Dead type fields in FleetRow (`prompt_name`, `classification_set_name`)
- `null` check in Select `onValueChange` is dead code
- `raw as Record<string, unknown>` unsafe type assertion in inboxes
- No explicit return type on PromptMonaco
- `React.FormEvent` used without explicit React import
- Optional chaining on `logDetail` during Dialog close animation
- Results page: inboxes fetched once on mount, never refreshed
- No optimistic update or polling after run initiation
- Double error message on save failure (setError + toast.error)
- Missing `forceConsistentCasingInFileNames` and `noFallthroughCasesInSwitch` in tsconfig
- `--font-sans` CSS var references itself (circular no-op)
- No custom animation keyframes in Tailwind config
- No `darkMode` config in Tailwind (implicit, works but not explicit)
- Missing `poweredByHeader: false` in Next.js config
- No images config for remote patterns
- `baseColor: "neutral"` in components.json but custom vars suggest blue-accent intent
- No CSS `@layer` ordering for custom vs. shadcn styles
