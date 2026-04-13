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
import { PlayIcon, PlusIcon, TrashIcon, HistoryIcon, Settings2Icon, ActivityIcon, SearchIcon, FilterIcon } from "lucide-react";

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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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

function parseAppModelSelectValue(raw: string): number | null {
  if (raw === "" || raw === "__none__") return null;
  const n = Number.parseInt(raw, 10);
  if (!Number.isSafeInteger(n) || String(n) !== raw) return null;
  return n;
}

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

const INBOX_LIST_PAGE_SIZE = 200;

export default function ClassificationWorkflowPage() {
  const [workflows, setWorkflows] = useState<Inbox[]>([]);
  const [workflowTotal, setWorkflowTotal] = useState(0);
  const [listPage, setListPage] = useState(1);
  const [detail, setDetail] = useState<Inbox | null>(null);
  const [prompts, setPrompts] = useState<Named[]>([]);
  const [sets, setSets] = useState<Named[]>([]);
  const [appModels, setAppModels] = useState<AppModelRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new"| null>(null);
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
  const [fetchFilter, setFetchFilter] = useState<FetchFilter>(defaultFetchFilter());
  const [ffLines, setFfLines] = useState({
    allow: "",
    deny: "",
    subj: "",
    body: "",
    catIn: "",
    catEx: "",
  });

  const fetchWorkflows = useCallback(async () => {
    setError(null);
    try {
      const [ib, pr, st, am] = await Promise.all([
        apiGet<PaginatedResponse<Inbox>>(
          `/api/inboxes?page=1&page_size=${INBOX_LIST_PAGE_SIZE}`
        ),
        apiGet<Named[]>("/api/prompt-templates"),
        apiGet<Named[]>("/api/classification-sets"),
        apiGet<AppModelRow[]>("/api/app-models"),
      ]);
      setWorkflows(ib.items);
      setWorkflowTotal(ib.total);
      setPrompts(pr.map((p) => ({ id: p.id, name: p.name })));
      setSets(st.map((s) => ({ id: s.id, name: s.name })));
      setAppModels(am.map((m) => ({ id: m.id, name: m.name })));

      if (ib.items.length > 0 && selectedId === null) {
        const first = ib.items[0];
        if (first) setSelectedId(first.id);
      } else if (ib.items.length === 0) {
        setSelectedId("new");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load workflows";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void fetchWorkflows();
  }, [fetchWorkflows]);

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

  useEffect(() => {
    lastPopulatedIdRef.current = null;

    if (selectedId === null) {
      setDetail(null);
      return;
    }

    if (selectedId === "new") {
      setDetail(null);
      resetFormToDefaults();
      setPromptId(prompts[0]?.id ?? 0);
      setSetId(sets[0]?.id ?? 0);
      setRunLogs([]);
      lastPopulatedIdRef.current = "new";
      return;
    }

    setDetail(null);
    resetFormToDefaults();

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
  }, [selectedId, prompts, sets, resetFormToDefaults]);

  useEffect(() => {
    if (selectedId === null || selectedId === "new") return;
    if (!detail || detail.id !== selectedId) return;
    if (lastPopulatedIdRef.current === selectedId) return;

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
      allow: (merged.sender_allowlist || []).join("\n"),
      deny: (merged.sender_denylist || []).join("\n"),
      subj: (merged.subject_keywords || []).join("\n"),
      body: (merged.body_keywords || []).join("\n"),
      catIn: (merged.category_include_any || []).join("\n"),
      catEx: (merged.category_exclude_any || []).join("\n"),
    });

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
    if (!setId) {
      setSetTaxonomy([]);
      return;
    }
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

  async function onSave() {
    setError(null);

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
      mailbox_id: mailboxId.trim(),
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
        lastPopulatedIdRef.current = null;
        setSelectedId(created.id);
        await fetchWorkflows();
        toast.success("Workflow created successfully");
      } else if (selectedId) {
        await apiSend(`/api/inboxes/${selectedId}`, "PUT", payload);
        await fetchWorkflows();
        toast.success("Workflow saved successfully");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    if (selectedId === "new" || !selectedId) return;
    setDeleteDialogOpen(false);
    setSaving(true);
    try {
      await apiSend(`/api/inboxes/${selectedId}`, "DELETE");
      lastPopulatedIdRef.current = null;
      setSelectedId("new");
      await fetchWorkflows();
      toast.success("Workflow deleted successfully");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function onRunNow() {
    if (typeof selectedId !== "number") return;
    setRunNowLoading(true);
    try {
      await apiSend(`/api/inboxes/${selectedId}/run`, "POST");
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
      <div className="flex flex-col gap-6 p-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-4 w-96" />
        <div className="grid grid-cols-4 gap-6">
          <Skeleton className="col-span-1 h-96" />
          <Skeleton className="col-span-3 h-[600px]" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">Classification Workflows</h1>
        <p className="text-slate-400">
          Configure inboxes to automatically classify emails using prompts and categorization rules
        </p>
      </div>

      <Dialog open={logDetail !== null} onOpenChange={(open) => { if (!open) setLogDetail(null); }}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Run diagnostics</DialogTitle>
            <DialogDescription>
              Run #{logDetail?.id} · {logDetail?.created_at}
            </DialogDescription>
          </DialogHeader>

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

          {logDetail?.status === "Failed" && logDetail.error_message && (
            <Alert variant="destructive">
              <AlertDescription className="whitespace-pre-wrap break-words font-mono text-xs">
                {logDetail.error_message}
              </AlertDescription>
            </Alert>
          )}

          {logClassificationsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
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
                      </ShadcnTableRow>
                    ))}
                  </ShadcnTableBody>
                </ShadcnTable>
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => setLogDetail(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Workflow</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this classification workflow? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void onDelete()}>Delete</AlertDialogAction>
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
            <AlertDialogAction disabled={runNowLoading} onClick={() => void onRunNow()}>
              {runNowLoading ? "Running…" : "Run Now"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <div className="grid grid-cols-4 gap-6">
        {/* Sidebar List */}
        <div className="col-span-1">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Workflows</CardTitle>
              <CardDescription>{workflows.length} total</CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                variant={selectedId === "new" ? "default" : "outline"}
                className="w-full mb-3"
                onClick={() => setSelectedId("new")}
              >
                + New Workflow
              </Button>
              <div className="space-y-2 max-h-[500px] overflow-y-auto">
                {workflows.map((w) => (
                  <button
                    key={w.id}
                    onClick={() => setSelectedId(w.id)}
                    className={`w-full text-left text-sm p-2 rounded transition-colors ${
                      selectedId === w.id
                        ? "bg-blue-600 text-white"
                        : "bg-slate-800 hover:bg-slate-700 text-slate-300"
                    }`}
                  >
                    <div className="font-medium truncate" title={w.mailbox_id}>
                      {w.mailbox_id.split("@")[0]}
                    </div>
                    <div className="text-xs text-opacity-75">
                      {w.is_active ? "🟢 Active" : "🔴 Inactive"} · {(w as any).prompt_name || "Prompt"}
                    </div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Editor Main Area */}
        <div className="col-span-3 space-y-6">
          {selectedId !== null && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>
                    {selectedId === "new" ? "New Classification Workflow" : "Edit Workflow"}
                  </CardTitle>
                  <CardDescription>
                    Configure extraction settings and subject classification rules
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Step 1: Core Config */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">1. Inbox Configuration</h3>
                    <div>
                      <Label htmlFor="mailbox-id">Mailbox ID (UPN/SMTP)</Label>
                      <Input
                        id="mailbox-id"
                        value={mailboxId}
                        onChange={(e) => setMailboxId(e.target.value)}
                        placeholder="user@example.com"
                        className="mt-2"
                      />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Prompt Template</Label>
                        <Select value={String(promptId)} onValueChange={(val) => val && setPromptId(Number(val))}>
                          <SelectTrigger className="mt-2">
                            <SelectValue placeholder="Select template..." />
                          </SelectTrigger>
                          <SelectContent>
                            {prompts.map((p) => (
                              <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label>Classification Set</Label>
                        <Select value={String(setId)} onValueChange={(val) => val && setSetId(Number(val))}>
                          <SelectTrigger className="mt-2">
                            <SelectValue placeholder="Select set..." />
                          </SelectTrigger>
                          <SelectContent>
                            {sets.map((s) => (
                              <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label>Gemini Model Override</Label>
                        <Select
                          value={appModelId === null ? "__none__" : String(appModelId)}
                          onValueChange={(val) => {
                            if (val) setAppModelId(parseAppModelSelectValue(val));
                          }}
                        >
                          <SelectTrigger className="mt-2">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">Default Strategy (Lite / ENV)</SelectItem>
                            {appModels.map((m) => (
                              <SelectItem key={m.id} value={String(m.id)}>{m.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label>Timezone</Label>
                        <Select value={timezone} onValueChange={(v) => v && setTimezone(v)}>
                          <SelectTrigger className="mt-2">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {COMMON_TIMEZONES.map((tz) => (
                              <SelectItem key={tz} value={tz}>{tz}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Mail Folder</Label>
                        <Input value={mailFolder} onChange={(e) => setMailFolder(e.target.value)} className="mt-2" />
                      </div>
                      <div>
                        <Label>Max Messages Per Run</Label>
                        <Input type="number" min={1} value={maxMessages} onChange={(e) => setMaxMessages(Number(e.target.value))} className="mt-2" />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-8 pt-2">
                      <div className="space-y-4">
                        <Label>Polling Interval: Every {polling}m</Label>
                        <Slider
                          value={[POLLING_OPTIONS.indexOf(polling)]}
                          onValueChange={(val) => {
                            const idx = Array.isArray(val) ? val[0] : val;
                            if (typeof idx === "number") setPolling(POLLING_OPTIONS[idx] ?? polling);
                          }}
                          min={0}
                          max={POLLING_OPTIONS.length - 1}
                          step={1}
                        />
                      </div>
                      <div className="space-y-4">
                        <Label>Max Workers: {workers}</Label>
                        <Slider value={[workers]} onValueChange={(v) => {
                          const val = Array.isArray(v) ? v[0] : v;
                          if (typeof val === "number") setWorkers(val);
                        }} min={1} max={10} step={1} />
                      </div>
                    </div>

                    <div className="flex gap-6 mt-4">
                      <div className="flex items-center gap-2">
                        <Checkbox id="active-chk" checked={isActive} onCheckedChange={(c) => setIsActive(Boolean(c))} />
                        <Label htmlFor="active-chk" className="cursor-pointer">Workflow Active</Label>
                      </div>
                      <div className="flex items-center gap-2">
                        <Checkbox id="wb-chk" checked={graphWriteBackEnabled} onCheckedChange={(c) => setGraphWriteBackEnabled(Boolean(c))} />
                        <Label htmlFor="wb-chk" className="cursor-pointer">Write Categories to Outlook</Label>
                      </div>
                    </div>
                  </div>

                  {/* Step 2: Subject Rules */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-lg">2. Subject Classification</h3>
                      <Checkbox checked={subjectClassifyEnabled} onCheckedChange={(c) => setSubjectClassifyEnabled(Boolean(c))} />
                    </div>
                    <p className="text-sm text-slate-400">
                      Match the message subject with patterns (% any substring, _ one character). 
                      First matching rule wins; messages that match no rule are classified with Gemini.
                    </p>
                    
                    {subjectClassifyEnabled && (
                      <div className="space-y-3">
                        {subjectRules.map((row, idx) => (
                          <div key={idx} className="flex gap-2 items-end bg-slate-900/40 p-3 rounded border border-slate-700">
                            <div className="flex-1 space-y-1.5">
                              <Label className="text-xs text-slate-500">Subject Pattern (LIKE)</Label>
                              <Input
                                value={row.pattern}
                                onChange={(e) => setSubjectRules(prev => prev.map((r, i) => i === idx ? { ...r, pattern: e.target.value } : r))}
                                className="font-mono text-xs"
                                placeholder="%Automated%"
                              />
                            </div>
                            <div className="flex-1 space-y-1.5">
                              <Label className="text-xs text-slate-500">Label</Label>
                              <Select
                                value={row.category || "__none__"}
                                onValueChange={(val) => val && setSubjectRules(prev => prev.map((r, i) => i === idx ? { ...r, category: val === "__none__" ? "" : val } : r))}
                              >
                                <SelectTrigger className="h-9">
                                  <SelectValue placeholder="Category..." />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none__">None</SelectItem>
                                  {setTaxonomy.map(c => <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>)}
                                </SelectContent>
                              </Select>
                            </div>
                            <Button variant="ghost" size="icon" onClick={() => setSubjectRules(prev => prev.filter((_, i) => i !== idx))} disabled={subjectRules.length <= 1}>
                              <TrashIcon className="h-4 w-4 text-slate-400" />
                            </Button>
                          </div>
                        ))}
                        <Button variant="outline" size="sm" onClick={() => setSubjectRules(prev => [...prev, { pattern: "", category: "" }])}>
                          <PlusIcon className="mr-2 h-4 w-4" /> Add Rule
                        </Button>
                      </div>
                    )}
                  </div>

                  {/* Step 3: Fetch Filters */}
                  <div className="space-y-4">
                    <h3 className="font-semibold text-lg">3. Fetch Filters (Graph Query)</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="flex items-center gap-2 py-2">
                        <Checkbox checked={fetchFilter.unread_only} onCheckedChange={(c) => setFetchFilter(f => ({ ...f, unread_only: Boolean(c) }))} />
                        <Label>Unread Only</Label>
                      </div>
                      <div className="space-y-2">
                        <Label>Time Window</Label>
                        <Select value={fetchFilter.time_window_mode} onValueChange={(v) => v && setFetchFilter(f => ({ ...f, time_window_mode: v as TimeWindowMode }))}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="local_today">Local calendar day</SelectItem>
                            <SelectItem value="rolling_hours">Rolling hours (UTC)</SelectItem>
                            <SelectItem value="since_last_run">Since last run</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="col-span-2 space-y-2">
                        <Label>Sender Allowlist (optional)</Label>
                        <Textarea value={ffLines.allow} onChange={(e) => setFfLines(l => ({ ...l, allow: e.target.value }))} className="font-mono text-xs h-20" placeholder="user@company.com\n@vendor.com" />
                      </div>
                      <div className="col-span-1 space-y-2">
                         <Label>Subject Keywords</Label>
                         <Textarea value={ffLines.subj} onChange={(e) => setFfLines(l => ({ ...l, subj: e.target.value }))} className="font-mono text-xs h-20" />
                      </div>
                      <div className="col-span-1 space-y-2">
                         <Label>Match Strategy</Label>
                         <Select value={fetchFilter.subject_keyword_mode} onValueChange={(v) => v && setFetchFilter(f => ({ ...f, subject_keyword_mode: v as SubjectKeywordMode }))}>
                           <SelectTrigger><SelectValue /></SelectTrigger>
                           <SelectContent>
                             <SelectItem value="any">Match Any (OR)</SelectItem>
                             <SelectItem value="all">Match All (AND)</SelectItem>
                           </SelectContent>
                         </Select>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Action Buttons */}
              <div className="flex gap-3">
                <Button onClick={onSave} disabled={saving}>
                  {saving ? "Saving..." : "Save Workflow"}
                </Button>
                {typeof selectedId === "number" && (
                  <>
                    <Button variant="outline" onClick={() => setRunNowDialogOpen(true)}>
                      <PlayIcon className="mr-2 h-4 w-4" /> Run Now
                    </Button>
                    <Button variant="secondary" className="text-red-400 hover:text-red-300" onClick={() => setDeleteDialogOpen(true)}>
                      Delete
                    </Button>
                  </>
                )}
              </div>

              {/* Run Logs Card */}
              {selectedId !== "new" && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <ActivityIcon className="h-5 w-5 text-indigo-400" /> Execution History
                    </CardTitle>
                    <CardDescription>Recent classification results and performance tracking</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {logsLoading ? (
                      <div className="space-y-4">
                        {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full" />)}
                      </div>
                    ) : runLogs.length === 0 ? (
                      <div className="text-center py-8 text-slate-500">No execution history recorded yet.</div>
                    ) : (
                      <div className="overflow-hidden rounded border border-slate-800">
                        <ShadcnTable>
                          <ShadcnTableHeader>
                            <ShadcnTableRow className="bg-slate-900/50">
                              <ShadcnTableHead className="text-xs">ID</ShadcnTableHead>
                              <ShadcnTableHead className="text-xs">Date</ShadcnTableHead>
                              <ShadcnTableHead className="text-xs">Status</ShadcnTableHead>
                              <ShadcnTableHead className="text-xs">Details</ShadcnTableHead>
                              <ShadcnTableHead className="text-xs text-right">Actions</ShadcnTableHead>
                            </ShadcnTableRow>
                          </ShadcnTableHeader>
                          <ShadcnTableBody>
                            {runLogs.map((log) => (
                              <ShadcnTableRow key={log.id} className="hover:bg-slate-800/30">
                                <ShadcnTableCell className="font-mono text-xs">#{log.id}</ShadcnTableCell>
                                <ShadcnTableCell className="text-xs text-slate-400">{log.created_at}</ShadcnTableCell>
                                <ShadcnTableCell>
                                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${log.status === "Success" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
                                    {log.status}
                                  </span>
                                </ShadcnTableCell>
                                <ShadcnTableCell className="text-xs text-slate-300">
                                  {log.fetched_count} msg · {log.classified_count} clsf · {log.total_tokens_used ?? "—"} tokens
                                </ShadcnTableCell>
                                <ShadcnTableCell className="text-right">
                                  <Button variant="ghost" size="xs" onClick={() => setLogDetail(log)}>Diagnostics</Button>
                                </ShadcnTableCell>
                              </ShadcnTableRow>
                            ))}
                          </ShadcnTableBody>
                        </ShadcnTable>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
