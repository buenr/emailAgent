"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type {
  Named,
  TaxRow,
  TimeWindowMode,
  SubjectKeywordMode,
  AttachmentFilter,
  FetchFilter,
  SubjectRuleRow,
  Inbox,
  ClassificationSetDetail,
  AppModelRow,
  RunLogRow,
  ClassificationRow,
  PaginatedResponse,
} from "@/lib/types";
import { toast } from "sonner";
import { PlayIcon } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import {
  Table as ShadcnTable,
  TableBody as ShadcnTableBody,
  TableCell as ShadcnTableCell,
  TableHead as ShadcnTableHead,
  TableHeader as ShadcnTableHeader,
  TableRow as ShadcnTableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const COMMON_TIMEZONES = [
  "UTC",
  "America/Phoenix",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/New_York",
];

const POLLING_OPTIONS = [5, 10, 15, 30, 60];

function snapPolling(n: number): number {
  if (POLLING_OPTIONS.includes(n)) return n;
  return POLLING_OPTIONS.reduce((best, x) =>
    Math.abs(x - n) < Math.abs(best - n) ? x : best
  );
}

/** Parse select value: only `""` → null or a decimal string that round-trips as a safe integer. */
function parseAppModelSelectValue(raw: string): number | null {
  if (raw === "") return null;
  const n = Number.parseInt(raw, 10);
  if (!Number.isSafeInteger(n) || String(n) !== raw) return null;
  return n;
}

/** Normalize API / JSON values to `number | null` (never string or NaN). */
function coerceAppModelIdFromApi(v: unknown): number | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "number") return Number.isSafeInteger(v) ? v : null;
  if (typeof v === "string") return parseAppModelSelectValue(v.trim());
  return null;
}

function appModelIdForJson(id: number | null): number | null {
  return id !== null && Number.isSafeInteger(id) ? id : null;
}

function defaultFetchFilter(): FetchFilter {
  return {
    unread_only: true,
    time_window_mode: "local_today",
    rolling_hours: 24,
    sender_allowlist: [],
    sender_denylist: [],
    subject_keywords: [],
    subject_keyword_mode: "any",
    body_keywords: [],
    importance_levels: [],
    has_attachments: "any",
    category_include_any: [],
    category_exclude_any: [],
  };
}

function mergeFetchFilter(raw: unknown): FetchFilter {
  const d = defaultFetchFilter();
  if (!raw || typeof raw !== "object") return d;
  const o = raw as Record<string, unknown>;
  return {
    unread_only: typeof o.unread_only === "boolean" ? o.unread_only : d.unread_only,
    time_window_mode:
      o.time_window_mode === "rolling_hours" ||
      o.time_window_mode === "since_last_run"
        ? o.time_window_mode
        : "local_today",
    rolling_hours:
      typeof o.rolling_hours === "number" && o.rolling_hours >= 1
        ? o.rolling_hours
        : d.rolling_hours,
    sender_allowlist: Array.isArray(o.sender_allowlist)
      ? o.sender_allowlist.map(String)
      : d.sender_allowlist,
    sender_denylist: Array.isArray(o.sender_denylist)
      ? o.sender_denylist.map(String)
      : d.sender_denylist,
    subject_keywords: Array.isArray(o.subject_keywords)
      ? o.subject_keywords.map(String)
      : d.subject_keywords,
    subject_keyword_mode:
      o.subject_keyword_mode === "all" ? "all" : "any",
    body_keywords: Array.isArray(o.body_keywords)
      ? o.body_keywords.map(String)
      : d.body_keywords,
    importance_levels: Array.isArray(o.importance_levels)
      ? o.importance_levels.map(String).filter((x) =>
          ["low", "normal", "high"].includes(x)
        )
      : d.importance_levels,
    has_attachments:
      o.has_attachments === "yes" || o.has_attachments === "no"
        ? o.has_attachments
        : "any",
    category_include_any: Array.isArray(o.category_include_any)
      ? o.category_include_any.map(String)
      : d.category_include_any,
    category_exclude_any: Array.isArray(o.category_exclude_any)
      ? o.category_exclude_any.map(String)
      : d.category_exclude_any,
  };
}

const INBOX_LIST_PAGE_SIZE = 25;

export default function InboxesPage() {
  const [inboxRows, setInboxRows] = useState<Inbox[]>([]);
  const [inboxTotal, setInboxTotal] = useState(0);
  const [listPage, setListPage] = useState(1);
  const [detail, setDetail] = useState<Inbox | null>(null);
  const [prompts, setPrompts] = useState<Named[]>([]);
  const [sets, setSets] = useState<Named[]>([]);
  const [appModels, setAppModels] = useState<AppModelRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runLogs, setRunLogs] = useState<RunLogRow[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logDetail, setLogDetail] = useState<RunLogRow | null>(null);
  const [logClassifications, setLogClassifications] = useState<ClassificationRow[]>([]);
  const [logClassificationsLoading, setLogClassificationsLoading] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [runNowDialogOpen, setRunNowDialogOpen] = useState(false);
  const [runNowLoading, setRunNowLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  /** Ref to track which selectedId the form was last populated for,
   *  so we don't overwrite user edits on re-renders / data reloads. */
  const lastPopulatedIdRef = useRef<number | "new" | null>(null);

  // Form state
  const [mailboxId, setMailboxId] = useState("");
  const [promptId, setPromptId] = useState<number>(0);
  const [setId, setSetId] = useState<number>(0);
  const [timezone, setTimezone] = useState("UTC");
  const [mailFolder, setMailFolder] = useState("inbox");
  const [maxMessages, setMaxMessages] = useState(500);
  const [workers, setWorkers] = useState(4);
  const [polling, setPolling] = useState(5);
  const [isActive, setIsActive] = useState(true);
  const [appModelId, setAppModelId] = useState<number | null>(null);
  const [graphWriteBackEnabled, setGraphWriteBackEnabled] = useState(true);
  const [subjectClassifyEnabled, setSubjectClassifyEnabled] = useState(false);
  const [subjectRules, setSubjectRules] = useState<SubjectRuleRow[]>([
    { pattern: "", category: "" },
  ]);
  const [setTaxonomy, setSetTaxonomy] = useState<TaxRow[]>([]);
  const [fetchFilter, setFetchFilter] = useState<FetchFilter>(defaultFetchFilter);
  const [ffLines, setFfLines] = useState({
    allow: "",
    deny: "",
    subj: "",
    body: "",
    catIn: "",
    catEx: "",
  });

  const fetchLists = useCallback(async (page: number) => {
    setError(null);
    try {
      const [ib, pr, st, am] = await Promise.all([
        apiGet<PaginatedResponse<Inbox>>(
          `/api/inboxes?page=${page}&page_size=${INBOX_LIST_PAGE_SIZE}`
        ),
        apiGet<Named[]>("/api/prompt-templates"),
        apiGet<Named[]>("/api/classification-sets"),
        apiGet<AppModelRow[]>("/api/app-models"),
      ]);
      setInboxRows(ib.items);
      setInboxTotal(ib.total);
      setPrompts(pr.map((p) => ({ id: p.id, name: p.name })));
      setSets(st.map((s) => ({ id: s.id, name: s.name })));
      setAppModels(am.map((m) => ({ id: m.id, name: m.name })));

      setSelectedId((prev) => {
        if (prev === "new") return "new";
        if (prev !== null) {
          if (ib.items.some((x) => x.id === prev)) return prev;
          return prev;
        }
        if (!ib.items.length) return "new";
        return ib.items[0]!.id;
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchLists(listPage);
  }, [listPage, fetchLists]);

  /** Set form fields to default values (for "new" or loading state). */
  const resetFormToDefaults = useCallback(() => {
    setMailboxId("");
    setTimezone("UTC");
    setMailFolder("inbox");
    setMaxMessages(500);
    setWorkers(4);
    setPolling(5);
    setIsActive(true);
    setAppModelId(null);
    setGraphWriteBackEnabled(true);
    setSubjectClassifyEnabled(false);
    setSubjectRules([{ pattern: "", category: "" }]);
    setFetchFilter(defaultFetchFilter());
    setFfLines({ allow: "", deny: "", subj: "", body: "", catIn: "", catEx: "" });
  }, []);

  /**
   * Single consolidated effect for form synchronization.
   *
   * - When selectedId changes → reset ref, clear detail, reset form or fetch detail
   * - When detail arrives for the current selectedId → populate form (once per selectedId)
   * - Does NOT depend on `prompts` or `sets`, preventing spurious resets during CRUD
   */
  useEffect(() => {
    // selectedId changed → mark form as not yet populated for this ID
    lastPopulatedIdRef.current = null;

    if (selectedId === null) {
      setDetail(null);
      return;
    }

    if (selectedId === "new") {
      setDetail(null);
      resetFormToDefaults();
      // Pick first prompt/set from current lists (stable reads, not deps)
      setPromptId(prompts[0]?.id ?? 0);
      setSetId(sets[0]?.id ?? 0);
      setRunLogs([]);
      lastPopulatedIdRef.current = "new";
      return;
    }

    // selectedId is a number — fetch detail if not already loaded
    setDetail(null);
    resetFormToDefaults();
    // Use current prompt/set defaults while loading
    setPromptId(prompts[0]?.id ?? 0);
    setSetId(sets[0]?.id ?? 0);

    let cancelled = false;
    (async () => {
      try {
        const d = await apiGet<Inbox>(`/api/inboxes/${selectedId}`);
        if (!cancelled) setDetail(d);
      } catch {
        if (!cancelled) setDetail(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  /** Populate form when detail arrives for the current selectedId (runs on detail change). */
  useEffect(() => {
    if (selectedId === null || selectedId === "new") return;
    // Only populate if detail is loaded and matches selectedId, and we haven't already populated for this ID
    if (!detail || detail.id !== selectedId) return;
    if (lastPopulatedIdRef.current === selectedId) return; // already populated

    // Populate form from detail
    setMailboxId(detail.mailbox_id);
    setPromptId(detail.prompt_template_id);
    setSetId(detail.classification_set_id);
    setTimezone(
      detail.timezone && COMMON_TIMEZONES.includes(detail.timezone)
        ? detail.timezone
        : "UTC"
    );
    setMailFolder(detail.mail_folder);
    setMaxMessages(detail.max_messages_per_run ?? 500);
    setWorkers(detail.patch_max_workers);
    setPolling(snapPolling(detail.polling_interval_minutes ?? 5));
    setIsActive(detail.is_active !== false);
    setAppModelId(coerceAppModelIdFromApi(detail.app_model_id));
    setGraphWriteBackEnabled(detail.graph_write_back_enabled !== false);
    setSubjectClassifyEnabled(detail.subject_classify_enabled === true);
    const sr = detail.subject_classify_rules;
    if (Array.isArray(sr) && sr.length > 0) {
      setSubjectRules(
        sr.map((r) => ({
          pattern: typeof r.pattern === "string" ? r.pattern : "",
          category: typeof r.category === "string" ? r.category : "",
        }))
      );
    } else {
      setSubjectRules([{ pattern: "", category: "" }]);
    }
    const merged = mergeFetchFilter(detail.fetch_filter);
    setFetchFilter(merged);
    setFfLines({
      allow: merged.sender_allowlist.join("\n"),
      deny: merged.sender_denylist.join("\n"),
      subj: merged.subject_keywords.join("\n"),
      body: merged.body_keywords.join("\n"),
      catIn: merged.category_include_any.join("\n"),
      catEx: merged.category_exclude_any.join("\n"),
    });

    // Mark as populated so subsequent detail changes (e.g. from re-fetch) don't overwrite user edits
    lastPopulatedIdRef.current = selectedId;
  }, [selectedId, detail]);

  useEffect(() => {
    if (selectedId === "new" || !selectedId) {
      setRunLogs([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setLogsLoading(true);
      try {
        const logs = await apiGet<RunLogRow[]>(
          `/api/inboxes/${selectedId}/run-logs?limit=50`
        );
        if (!cancelled) setRunLogs(logs);
      } catch {
        if (!cancelled) setRunLogs([]);
      } finally {
        if (!cancelled) setLogsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!logDetail) {
      setLogClassifications([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setLogClassificationsLoading(true);
      try {
        const rows = await apiGet<ClassificationRow[]>(
          `/api/run-logs/${logDetail.id}/classifications`
        );
        if (!cancelled) setLogClassifications(rows);
      } catch {
        if (!cancelled) setLogClassifications([]);
      } finally {
        if (!cancelled) setLogClassificationsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [logDetail]);

  useEffect(() => {
    if (!setId) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await apiGet<ClassificationSetDetail>(
          `/api/classification-sets/${setId}`
        );
        if (!cancelled) setSetTaxonomy(d.categories ?? []);
      } catch {
        if (!cancelled) setSetTaxonomy([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setId]);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    // Client-side validation
    if (!mailboxId.trim()) {
      toast.error("Mailbox ID is required");
      return;
    }
    if (!promptId || promptId <= 0) {
      toast.error("A prompt template must be selected");
      return;
    }
    if (!setId || setId <= 0) {
      toast.error("A classification set must be selected");
      return;
    }
    if (!maxMessages || maxMessages <= 0) {
      toast.error("Max messages per run must be greater than 0");
      return;
    }

    const lineParse = (s: string) =>
      s
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean);

    const ffPayload = {
      ...fetchFilter,
      sender_allowlist: lineParse(ffLines.allow),
      sender_denylist: lineParse(ffLines.deny),
      subject_keywords: lineParse(ffLines.subj),
      body_keywords: lineParse(ffLines.body),
      category_include_any: lineParse(ffLines.catIn),
      category_exclude_any: lineParse(ffLines.catEx),
      rolling_hours:
        fetchFilter.time_window_mode === "rolling_hours"
          ? fetchFilter.rolling_hours ?? 24
          : null,
    };

    const payload = {
      mailbox_id: mailboxId,
      prompt_template_id: promptId,
      classification_set_id: setId,
      app_model_id: appModelIdForJson(appModelId),
      timezone: timezone,
      mail_folder: mailFolder,
      max_messages_per_run: maxMessages,
      patch_max_workers: workers,
      polling_interval_minutes: polling,
      is_active: isActive,
      graph_write_back_enabled: graphWriteBackEnabled,
      fetch_filter: ffPayload,
      subject_classify_enabled: subjectClassifyEnabled,
      subject_classify_rules: subjectRules
        .filter((r) => r.pattern.trim() && r.category.trim())
        .map((r) => ({
          pattern: r.pattern.trim(),
          category: r.category.trim(),
        })),
    };

    setSaving(true);
    try {
      if (selectedId === "new") {
        const created = await apiSend<{ id: number }>("/api/inboxes", "POST", payload);
        // Mark form as not-yet-populated for the new ID so detail-load effect can populate it
        lastPopulatedIdRef.current = null;
        setSelectedId(created.id);
        if (listPage !== 1) setListPage(1);
        else await fetchLists(1);
        toast.success("Inbox mapping created");
      } else if (selectedId) {
        await apiSend(`/api/inboxes/${selectedId}`, "PUT", payload);
        await fetchLists(listPage);
        toast.success("Inbox mapping saved");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    if (selectedId === "new" || !selectedId) return;
    setDeleteDialogOpen(false);
    setError(null);
    setSaving(true);
    try {
      await apiSend(`/api/inboxes/${selectedId}`, "DELETE");
      lastPopulatedIdRef.current = null;
      setSelectedId(null);
      await fetchLists(listPage);
      toast.success("Inbox mapping deleted");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function onRunNow() {
    if (typeof selectedId !== "number") return;
    setRunNowLoading(true);
    try {
      const res = await apiSend<{ detail?: string }>(
        `/api/inboxes/${selectedId}/run`,
        "POST"
      );
      // apiSend throws on non-2xx, so if we get here the run started
      toast.success("Classification run started");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Run failed";
      if (msg.toLowerCase().includes("already in progress") || msg.toLowerCase().includes("conflict")) {
        toast.warning("A run is already in progress");
      } else {
        toast.error(msg);
      }
    } finally {
      setRunNowLoading(false);
      setRunNowDialogOpen(false);
    }
  }

  if (loading) {
    return (
      <div className="w-full space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!prompts.length || !sets.length) {
    return (
      <div>
        <h1 className="mb-4 text-2xl font-semibold text-white">Inboxes</h1>
        <Alert>
          <AlertDescription className="text-amber-200">
            Create at least one prompt template and one classification set first.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="w-full">
      <h1 className="mb-8 text-2xl font-semibold text-white">Inboxes</h1>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Dialog open={logDetail !== null} onOpenChange={(open) => { if (!open) setLogDetail(null); }}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Run diagnostics</DialogTitle>
            <DialogDescription>
              Run #{logDetail?.id} · {logDetail?.created_at}
            </DialogDescription>
          </DialogHeader>

          {/* Diagnostics key-value pairs */}
          <div className="rounded-md border border-slate-800 bg-slate-950/50 p-4">
            <h4 className="mb-3 text-sm font-medium text-slate-300">Diagnostics</h4>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-1.5">
                <span className="text-xs text-slate-500">Status</span>
                <span className={`text-sm font-medium ${logDetail?.status === "Success" ? "text-emerald-400" : logDetail?.status === "Failed" ? "text-red-400" : "text-yellow-400"}`}>
                  {logDetail?.status}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-1.5">
                <span className="text-xs text-slate-500">Latency</span>
                <span className="text-sm text-slate-300">
                  {logDetail?.latency_ms != null ? `${(logDetail.latency_ms / 1000).toFixed(1)}s` : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-1.5">
                <span className="text-xs text-slate-500">Tokens</span>
                <span className="text-sm text-slate-300">{logDetail?.total_tokens_used ?? "—"}</span>
              </div>
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-1.5">
                <span className="text-xs text-slate-500">Fetched</span>
                <span className="text-sm text-slate-300">{logDetail?.fetched_count ?? 0}</span>
              </div>
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-1.5">
                <span className="text-xs text-slate-500">Classified</span>
                <span className="text-sm text-slate-300">{logDetail?.classified_count ?? 0}</span>
              </div>
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-1.5">
                <span className="text-xs text-slate-500">Tagged</span>
                <span className="text-sm text-slate-300">{logDetail?.tagged_count ?? 0}</span>
              </div>
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-1.5">
                <span className="text-xs text-slate-500">Failures</span>
                <span className="text-sm text-slate-300">{logDetail?.failures ?? 0}</span>
              </div>
            </div>
          </div>

          {/* Error alert for failed runs */}
          {logDetail?.status === "Failed" && logDetail.error_message && (
            <Alert variant="destructive">
              <AlertDescription className="whitespace-pre-wrap break-words font-mono text-xs">
                {logDetail.error_message}
              </AlertDescription>
            </Alert>
          )}

          {/* Classifications mini-table */}
          {logClassificationsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : logClassifications.length > 0 ? (
            <div>
              <h4 className="mb-2 text-sm font-medium text-slate-300">
                Classifications ({logClassifications.length})
              </h4>
              <div className="max-h-[240px] overflow-y-auto rounded-lg border border-slate-800">
                <ShadcnTable>
                  <ShadcnTableHeader>
                    <ShadcnTableRow className="bg-slate-900/50 hover:bg-slate-900/50">
                      <ShadcnTableHead className="text-xs text-slate-400">Subject</ShadcnTableHead>
                      <ShadcnTableHead className="text-xs text-slate-400">Sender</ShadcnTableHead>
                      <ShadcnTableHead className="text-xs text-slate-400">Category</ShadcnTableHead>
                      <ShadcnTableHead className="text-xs text-slate-400">Received</ShadcnTableHead>
                    </ShadcnTableRow>
                  </ShadcnTableHeader>
                  <ShadcnTableBody>
                    {logClassifications.map((c) => (
                      <ShadcnTableRow key={c.id}>
                        <ShadcnTableCell className="max-w-[200px] truncate text-sm text-slate-200">{c.subject || "—"}</ShadcnTableCell>
                        <ShadcnTableCell className="text-sm text-slate-300">{c.sender || "—"}</ShadcnTableCell>
                        <ShadcnTableCell className="text-sm">
                          <span className="inline-flex items-center rounded-md bg-indigo-500/15 px-1.5 py-0.5 text-xs font-medium text-indigo-300">
                            {c.category}
                          </span>
                        </ShadcnTableCell>
                        <ShadcnTableCell className="text-xs text-slate-400">
                          {c.received_at ? new Date(c.received_at).toLocaleString() : "—"}
                        </ShadcnTableCell>
                      </ShadcnTableRow>
                    ))}
                  </ShadcnTableBody>
                </ShadcnTable>
              </div>
            </div>
          ) : null}

          <DialogFooter showCloseButton />
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Inbox Mapping</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this inbox mapping? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void onDelete()}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={runNowDialogOpen} onOpenChange={setRunNowDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Run Classification</AlertDialogTitle>
            <AlertDialogDescription>
              Run classification for this inbox now? This may take a moment.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={runNowLoading}
              onClick={() => void onRunNow()}
            >
              {runNowLoading ? "Running…" : "Run Now"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <div className="mb-6 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-medium text-slate-400">Inbox mappings</h2>
          <Button variant="outline" onClick={() => setSelectedId("new")}>
            + New mapping
          </Button>
        </div>
        {inboxTotal === 0 ? (
          <p className="text-sm text-slate-500">No mappings yet. Create one below.</p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <ShadcnTable className="min-w-[480px]">
                <ShadcnTableHeader>
                  <ShadcnTableRow className="bg-slate-900/50 hover:bg-slate-900/50">
                    <ShadcnTableHead className="text-slate-400">Mailbox</ShadcnTableHead>
                    <ShadcnTableHead className="text-slate-400">Active</ShadcnTableHead>
                  </ShadcnTableRow>
                </ShadcnTableHeader>
                <ShadcnTableBody>
                  {inboxRows.map((i) => (
                    <ShadcnTableRow
                      key={i.id}
                      onClick={() => setSelectedId(i.id)}
                      tabIndex={0}
                      role="button"
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedId(i.id); } }}
                      aria-selected={selectedId === i.id}
                      className={`cursor-pointer hover:bg-slate-900/40 ${
                        selectedId === i.id ? "bg-slate-800/50" : ""
                      }`}
                    >
                      <ShadcnTableCell className="text-slate-200">{i.mailbox_id}</ShadcnTableCell>
                      <ShadcnTableCell className="text-slate-400">
                        {i.is_active !== false ? "yes" : "no"}
                      </ShadcnTableCell>
                    </ShadcnTableRow>
                  ))}
                </ShadcnTableBody>
              </ShadcnTable>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <span>
                Page {listPage} · {(listPage - 1) * INBOX_LIST_PAGE_SIZE + 1}–
                {Math.min(listPage * INBOX_LIST_PAGE_SIZE, inboxTotal)} of {inboxTotal}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="xs"
                  disabled={listPage <= 1}
                  onClick={() => setListPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="xs"
                  disabled={listPage * INBOX_LIST_PAGE_SIZE >= inboxTotal}
                  onClick={() => setListPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
            {typeof selectedId === "number" &&
              !inboxRows.some((r) => r.id === selectedId) && (
                <p className="text-xs text-slate-500">
                  Selected inbox is not on this page; form below still loads from the
                  server.
                </p>
              )}
          </>
        )}
      </div>

      <div className="mb-8 rounded-lg border border-slate-800 bg-slate-900/40 p-6">
        <h2 className="mb-4 text-lg font-medium text-white">
          {selectedId === "new" ? "Create Inbox Mapping" : "Edit Inbox Mapping"}
        </h2>
        <form onSubmit={onSave} className="space-y-6">
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor="inbox-mailbox" className="mb-1 block text-sm text-slate-400">Mailbox ID (UPN/SMTP)</Label>
              <Input
                id="inbox-mailbox"
                value={mailboxId}
                onChange={(e) => setMailboxId(e.target.value)}
                placeholder="user@example.com"
              />
            </div>

            <div>
              <Label id="inbox-prompt-label" className="mb-1 block text-sm text-slate-400">Prompt Template</Label>
              <Select
                value={String(promptId)}
                onValueChange={(val) => {
                  if (val !== null) setPromptId(Number(val));
                }}
              >
                <SelectTrigger className="w-full" aria-labelledby="inbox-prompt-label">
                  <SelectValue placeholder="Select template" />
                </SelectTrigger>
                <SelectContent>
                  {prompts.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label id="inbox-set-label" className="mb-1 block text-sm text-slate-400">Classification Set</Label>
              <Select
                value={String(setId)}
                onValueChange={(val) => {
                  if (val !== null) setSetId(Number(val));
                }}
              >
                <SelectTrigger className="w-full" aria-labelledby="inbox-set-label">
                  <SelectValue placeholder="Select set" />
                </SelectTrigger>
                <SelectContent>
                  {sets.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label id="inbox-model-label" className="mb-1 block text-sm text-slate-400">Gemini model</Label>
              <Select
                value={appModelId === null ? "__none__" : String(appModelId)}
                onValueChange={(val) =>
                  setAppModelId(val === "__none__" || val === null ? null : parseAppModelSelectValue(val))
                }
              >
                <SelectTrigger className="w-full" aria-labelledby="inbox-model-label">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">
                    Default (gemini-2.5-flash-lite, or GEMINI_MODEL if set)
                  </SelectItem>
                  {appModels.map((m) => (
                    <SelectItem key={m.id} value={String(m.id)}>
                      {m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="mt-1 text-xs text-slate-500">
                Manage entries under App models. Empty uses{" "}
                <code className="text-slate-500">GEMINI_MODEL</code> if set, otherwise{" "}
                gemini-2.5-flash-lite.
              </p>
            </div>

            <div>
              <Label id="inbox-timezone-label" className="mb-1 block text-sm text-slate-400">Timezone</Label>
              <Select
                value={timezone}
                onValueChange={(val) => {
                  if (val !== null) setTimezone(val);
                }}
              >
                <SelectTrigger className="w-full" aria-labelledby="inbox-timezone-label">
                  <SelectValue placeholder="Select timezone" />
                </SelectTrigger>
                <SelectContent>
                  {COMMON_TIMEZONES.map((z) => (
                    <SelectItem key={z} value={z}>
                      {z}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="inbox-mail-folder" className="mb-1 block text-sm text-slate-400">Mail Folder</Label>
              <Input
                id="inbox-mail-folder"
                value={mailFolder}
                onChange={(e) => setMailFolder(e.target.value)}
              />
            </div>

            <div>
              <Label id="inbox-poll-interval-label" className="mb-1 block text-sm text-slate-400">
                Polling interval: Every {polling} minutes
              </Label>
              <Slider
                aria-labelledby="inbox-poll-interval-label"
                value={[POLLING_OPTIONS.indexOf(polling)]}
                onValueChange={(val) => setPolling(POLLING_OPTIONS[Array.isArray(val) ? val[0]! : val] ?? polling)}
                min={0}
                max={POLLING_OPTIONS.length - 1}
                step={1}
              />
            </div>

            <div>
              <Label htmlFor="inbox-max-messages" className="mb-1 block text-sm text-slate-400">Max Messages Per Run</Label>
              <Input
                id="inbox-max-messages"
                type="number"
                min={1}
                value={maxMessages}
                onChange={(e) => setMaxMessages(Number(e.target.value))}
              />
            </div>

            <div>
              <Label id="inbox-workers-label" className="mb-1 block text-sm text-slate-400">
                Patch Max Workers: {workers}
              </Label>
              <Slider
                aria-labelledby="inbox-workers-label"
                value={[workers]}
                onValueChange={(val) => setWorkers(Array.isArray(val) ? val[0] : val)}
                min={1}
                max={10}
                step={1}
              />
            </div>

            <div className="flex items-center">
              <Label className="flex cursor-pointer items-center gap-2 text-sm font-normal text-slate-300">
                <Checkbox
                  id="inbox-active"
                  checked={isActive}
                  onCheckedChange={(checked) => setIsActive(checked)}
                />
                Inbox active (scheduler includes this mailbox)
              </Label>
            </div>

            <div className="sm:col-span-2">
              <Label className="flex cursor-pointer items-center gap-2 text-sm font-normal text-slate-300">
                <Checkbox
                  id="inbox-graph-write-back"
                  checked={graphWriteBackEnabled}
                  onCheckedChange={(checked) => setGraphWriteBackEnabled(checked)}
                />
                Enable Graph write-back (Outlook categories)
              </Label>
              <p className="mt-1 pl-6 text-xs text-slate-500">
                When off, scheduled runs still classify messages but do not PATCH categories on
                Exchange—useful to test models without changing live mailboxes.
              </p>
            </div>

            <div className="sm:col-span-2 rounded-md border border-slate-800 bg-slate-950/30 px-4 py-4">
              <Label className="mb-2 flex cursor-pointer items-center gap-2 text-sm font-normal text-slate-300">
                <Checkbox
                  id="inbox-subject-classify"
                  checked={subjectClassifyEnabled}
                  onCheckedChange={(checked) => setSubjectClassifyEnabled(checked)}
                />
                Subject-first classification (before Gemini)
              </Label>
              <p className="mb-3 pl-6 text-xs text-slate-500">
                Match the message subject with SQL-style patterns (<code className="text-slate-400">%</code>{" "}
                any substring, <code className="text-slate-400">_</code> one character). First matching
                rule wins; messages that match no rule are classified with Gemini. Categories must exist
                in the selected classification set.
              </p>
              {subjectClassifyEnabled && (
                <div className="space-y-3 pl-6">
                  {subjectRules.map((row, idx) => (
                    <div
                      key={idx}
                      className="flex flex-col gap-2 rounded-md border border-slate-800/80 bg-slate-950/50 p-3 sm:flex-row sm:items-end"
                    >
                      <div className="min-w-0 flex-1">
                        <Label htmlFor={`inbox-subject-pattern-${idx}`} className="mb-1 block text-xs font-normal text-slate-500">Subject pattern (LIKE)</Label>
                        <Input
                          id={`inbox-subject-pattern-${idx}`}
                          className="font-mono"
                          placeholder="%Automated%"
                          value={row.pattern}
                          onChange={(e) => {
                            const v = e.target.value;
                            setSubjectRules((rules) =>
                              rules.map((r, i) => (i === idx ? { ...r, pattern: v } : r))
                            );
                          }}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <Label id={`inbox-subject-category-label-${idx}`} className="mb-1 block text-xs font-normal text-slate-500">Classification label</Label>
                        <Select
                          value={row.category || "__none__"}
                          onValueChange={(val) => {
                            const v = val === "__none__" || val === null ? "" : val;
                            setSubjectRules((rules) =>
                              rules.map((r, i) => (i === idx ? { ...r, category: v } : r))
                            );
                          }}
                        >
                          <SelectTrigger className="w-full" aria-labelledby={`inbox-subject-category-label-${idx}`}>
                            <SelectValue placeholder="— select category —" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">— select category —</SelectItem>
                            {setTaxonomy.map((c) => (
                              <SelectItem key={c.name} value={c.name}>
                                {c.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <Button
                        variant="outline"
                        size="xs"
                        disabled={subjectRules.length <= 1}
                        onClick={() =>
                          setSubjectRules((rules) => rules.filter((_, i) => i !== idx))
                        }
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={subjectRules.length >= 20}
                    onClick={() =>
                      setSubjectRules((rules) => [
                        ...rules,
                        { pattern: "", category: "" },
                      ])
                    }
                  >
                    + Add rule
                  </Button>
                  {!setTaxonomy.length && (
                    <p className="text-xs text-amber-200/90">
                      Load categories by choosing a classification set above, or add categories on the
                      Classification Sets page.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          <details className="rounded-md border border-slate-800 bg-slate-950/40 px-4 py-3">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm font-medium text-slate-200 transition-colors hover:bg-muted hover:text-foreground [&::-webkit-details-marker]:hidden dark:bg-input/30 dark:hover:bg-input/50">
              Fetch filters (Graph query)
            </summary>
            <p className="mt-2 mb-4 text-xs text-slate-500">
              Reduce noise with OData filters. Body keywords use Microsoft Graph{" "}
              <code className="text-slate-400">$search</code> (may not combine with all
              tenants). One sender or keyword per line.
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Label className="flex cursor-pointer items-center gap-2 text-sm font-normal text-slate-300 sm:col-span-2">
                <Checkbox
                  id="inbox-unread-only"
                  checked={fetchFilter.unread_only}
                  onCheckedChange={(checked) =>
                    setFetchFilter((f) => ({ ...f, unread_only: checked }))
                  }
                />
                Unread only
              </Label>

              <div>
                <Label id="inbox-time-window-label" className="mb-1 block text-sm text-slate-400">Time window</Label>
                <Select
                  value={fetchFilter.time_window_mode}
                  onValueChange={(val) => {
                    if (val !== null)
                      setFetchFilter((f) => ({
                        ...f,
                        time_window_mode: val as TimeWindowMode,
                      }));
                  }}
                >
                  <SelectTrigger className="w-full" aria-labelledby="inbox-time-window-label">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="local_today">Local calendar day (mailbox timezone)</SelectItem>
                    <SelectItem value="rolling_hours">Rolling hours (UTC, ending now)</SelectItem>
                    <SelectItem value="since_last_run">Since last run (fallback: last 24h if never run)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="inbox-rolling-hours" className="mb-1 block text-sm text-slate-400">
                  Rolling hours (only if window is rolling)
                </Label>
                <Input
                  id="inbox-rolling-hours"
                  type="number"
                  min={1}
                  max={720}
                  disabled={fetchFilter.time_window_mode !== "rolling_hours"}
                  value={fetchFilter.rolling_hours ?? 24}
                  onChange={(e) =>
                    setFetchFilter((f) => ({
                      ...f,
                      rolling_hours: Number(e.target.value) || 24,
                    }))
                  }
                />
              </div>

              <div className="sm:col-span-2">
                <Label htmlFor="inbox-sender-allow" className="mb-1 block text-sm text-slate-400">
                  Sender allowlist (optional; if set, only these senders)
                </Label>
                <Textarea
                  id="inbox-sender-allow"
                  rows={3}
                  className="font-mono text-sm"
                  placeholder={"user@company.com\n@vendor.com"}
                  value={ffLines.allow}
                  onChange={(e) =>
                    setFfLines((L) => ({ ...L, allow: e.target.value }))
                  }
                />
              </div>

              <div className="sm:col-span-2">
                <Label htmlFor="inbox-sender-deny" className="mb-1 block text-sm text-slate-400">Sender denylist</Label>
                <Textarea
                  id="inbox-sender-deny"
                  rows={3}
                  className="font-mono text-sm"
                  placeholder={"noreply@…\n@spamdomain.com"}
                  value={ffLines.deny}
                  onChange={(e) =>
                    setFfLines((L) => ({ ...L, deny: e.target.value }))
                  }
                />
              </div>

              <div>
                <Label htmlFor="inbox-subject-keywords" className="mb-1 block text-sm text-slate-400">Subject keywords</Label>
                <Textarea
                  id="inbox-subject-keywords"
                  rows={3}
                  className="font-mono text-sm"
                  value={ffLines.subj}
                  onChange={(e) =>
                    setFfLines((L) => ({ ...L, subj: e.target.value }))
                  }
                />
              </div>

              <div>
                <Label id="inbox-subject-keyword-mode-label" className="mb-1 block text-sm text-slate-400">Subject keyword match</Label>
                <Select
                  value={fetchFilter.subject_keyword_mode}
                  onValueChange={(val) => {
                    if (val !== null)
                      setFetchFilter((f) => ({
                        ...f,
                        subject_keyword_mode: val as SubjectKeywordMode,
                      }));
                  }}
                >
                  <SelectTrigger className="w-full" aria-labelledby="inbox-subject-keyword-mode-label">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Match any (OR)</SelectItem>
                    <SelectItem value="all">Match all (AND)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="sm:col-span-2">
                <Label htmlFor="inbox-body-keywords" className="mb-1 block text-sm text-slate-400">
                  Body keywords ($search, experimental)
                </Label>
                <Textarea
                  id="inbox-body-keywords"
                  rows={2}
                  className="font-mono text-sm"
                  value={ffLines.body}
                  onChange={(e) =>
                    setFfLines((L) => ({ ...L, body: e.target.value }))
                  }
                />
              </div>

              <div>
                <Label className="mb-1 block text-sm text-slate-400">Importance</Label>
                <div className="flex flex-wrap gap-3 text-sm text-slate-300">
                  {(["low", "normal", "high"] as const).map((lvl) => (
                    <label key={lvl} className="flex items-center gap-1.5">
                      <Checkbox
                        checked={fetchFilter.importance_levels.includes(lvl)}
                        onCheckedChange={(checked) =>
                          setFetchFilter((f) => ({
                            ...f,
                            importance_levels: checked
                              ? [...f.importance_levels, lvl]
                              : f.importance_levels.filter((x) => x !== lvl),
                          }))
                        }
                      />
                      {lvl}
                    </label>
                  ))}
                </div>
                <p className="mt-1 text-xs text-slate-500">None checked = any importance</p>
              </div>

              <div>
                <Label id="inbox-attachments-label" className="mb-1 block text-sm text-slate-400">Attachments</Label>
                <Select
                  value={fetchFilter.has_attachments}
                  onValueChange={(val) => {
                    if (val !== null)
                      setFetchFilter((f) => ({
                        ...f,
                        has_attachments: val as AttachmentFilter,
                      }));
                  }}
                >
                  <SelectTrigger className="w-full" aria-labelledby="inbox-attachments-label">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any</SelectItem>
                    <SelectItem value="yes">Has attachments</SelectItem>
                    <SelectItem value="no">No attachments</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="inbox-cat-include" className="mb-1 block text-sm text-slate-400">
                  Outlook categories (include any)
                </Label>
                <Textarea
                  id="inbox-cat-include"
                  rows={2}
                  className="font-mono text-sm"
                  value={ffLines.catIn}
                  onChange={(e) =>
                    setFfLines((L) => ({ ...L, catIn: e.target.value }))
                  }
                />
              </div>

              <div>
                <Label htmlFor="inbox-cat-exclude" className="mb-1 block text-sm text-slate-400">
                  Outlook categories (exclude any)
                </Label>
                <Textarea
                  id="inbox-cat-exclude"
                  rows={2}
                  className="font-mono text-sm"
                  value={ffLines.catEx}
                  onChange={(e) =>
                    setFfLines((L) => ({ ...L, catEx: e.target.value }))
                  }
                />
              </div>
            </div>
          </details>

          <div className="flex items-center justify-between border-t border-slate-800 pt-6">
            <div className="flex items-center gap-3">
              {selectedId !== "new" && (
                <Button
                  variant="destructive"
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  Delete Mapping
                </Button>
              )}
              {typeof selectedId === "number" && (
                <Button
                  variant="outline"
                  onClick={() => setRunNowDialogOpen(true)}
                >
                  <PlayIcon />
                  Run Now
                </Button>
              )}
            </div>
            <Button type="submit" disabled={saving}>
              {saving
                ? "Saving…"
                : selectedId === "new"
                ? "Create Mapping"
                : "Save Changes"}
            </Button>
          </div>
        </form>
      </div>

      {selectedId !== "new" && selectedId && (
        <div className="mt-10 rounded-lg border border-slate-800 bg-slate-900/40 p-6">
          <h3 className="mb-4 text-lg font-medium text-white">Run logs (last 50)</h3>
          {logsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-64" />
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-56" />
            </div>
          ) : runLogs.length === 0 ? (
            <p className="text-slate-500">No runs recorded yet.</p>
          ) : (
            <ul className="space-y-2 border-l border-slate-700 pl-4">
              {runLogs.map((log) => (
                <li key={log.id} className="text-sm">
                  <span
                    className={
                      log.status === "Success"
                        ? "text-emerald-400"
                        : "text-red-400"
                    }
                  >
                    {log.status}
                  </span>
                  <span className="text-slate-500">
                    {" "}
                    · {log.created_at} · fetched {log.fetched_count} · tokens{" "}
                    {log.total_tokens_used ?? "—"}
                  </span>
                  <Button
                    variant="link"
                    size="xs"
                    onClick={() => setLogDetail(log)}
                  >
                    View details
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
