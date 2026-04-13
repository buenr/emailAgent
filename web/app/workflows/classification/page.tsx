"use client";

import { useCallback, useEffect, useState, useRef } from "react";
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  Table as ShadcnTable,
  TableBody as ShadcnTableBody,
  TableCell as ShadcnTableCell,
  TableHead as ShadcnTableHead,
  TableHeader as ShadcnTableHeader,
  TableRow as ShadcnTableRow,
} from "@/components/ui/table";

const COMMON_TIMEZONES = [
  "UTC",
  "America/Phoenix",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/New_York",
];

const POLLING_OPTIONS = [5, 10, 15, 30, 60];

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

export default function ClassificationWorkflowPage() {
  const [workflows, setWorkflows] = useState<Inbox[]>([]);
  const [workflowTotal, setWorkflowTotal] = useState(0);
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
  const [fetchFilter, setFetchFilter] = useState<FetchFilter>(defaultFetchFilter());
  const [ffLines, setFfLines] = useState({
    allow: "",
    deny: "",
    subj: "",
    body: "",
    catIn: "",
    catEx: "",
  });

  const fetchWorkflows = useCallback(async (page: number) => {
    setError(null);
    try {
      const [ib, pr, st, am] = await Promise.all([
        apiGet<PaginatedResponse<Inbox>>(
          `/api/inboxes?page=${page}&page_size=25`
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

      setSelectedId((prev) => {
        if (prev === "new") return "new";
        if (prev !== null && ib.items.some((x) => x.id === prev)) return prev;
        if (!ib.items.length) return "new";
        return ib.items[0]?.id ?? "new";
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load workflows";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchWorkflows(listPage);
  }, [listPage, fetchWorkflows]);

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
      return;
    }

    if (lastPopulatedIdRef.current === selectedId) {
      return;
    }

    const fetchDetail = async () => {
      try {
        const d = await apiGet<Inbox>(`/api/inboxes/${selectedId}`);
        if (d) {
          setDetail(d);
          lastPopulatedIdRef.current = selectedId;

          setMailboxId(d.mailbox_id ?? "");
          setPromptId(d.prompt_id ?? 0);
          setSetId(d.classification_set_id ?? 0);
          setTimezone(d.timezone ?? "UTC");
          setMailFolder(d.mail_folder ?? "inbox");
          setMaxMessages(d.max_fetch ?? 500);
          setWorkers(d.write_back_workers ?? 4);
          setPolling(d.polling_interval_minutes ?? 5);
          setIsActive(d.is_active ?? true);
          setAppModelId(d.app_model_id ?? null);
          setGraphWriteBackEnabled(d.graph_write_back_enabled ?? true);
          setSubjectClassifyEnabled(d.subject_classify_enabled ?? false);
          setSubjectRules(d.subject_classify_rules ?? [{ pattern: "", category: "" }]);
          setFetchFilter(mergeFetchFilter(d.fetch_filter));
          setFfLines({ allow: "", deny: "", subj: "", body: "", catIn: "", catEx: "" });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to fetch workflow";
        toast.error(msg);
      }
    };

    void fetchDetail();
  }, [selectedId, prompts, sets, resetFormToDefaults]);

  const handleSave = async () => {
    if (!mailboxId.trim()) {
      toast.error("Mailbox ID is required");
      return;
    }

    if (!promptId || !setId) {
      toast.error("Prompt template and classification set are required");
      return;
    }

    setSaving(true);
    try {
      const payload: any = {
        mailbox_id: mailboxId.trim(),
        prompt_id: promptId,
        classification_set_id: setId,
        timezone,
        mail_folder: mailFolder,
        max_fetch: maxMessages,
        write_back_workers: workers,
        polling_interval_minutes: polling,
        is_active: isActive,
        app_model_id: appModelId,
        graph_write_back_enabled: graphWriteBackEnabled,
        subject_classify_enabled: subjectClassifyEnabled,
        subject_classify_rules: subjectRules.filter((r) => r.pattern.trim()),
        fetch_filter: fetchFilter,
      };

      let result;
      if (selectedId === "new") {
        result = await apiSend("POST", "/api/inboxes", payload);
      } else {
        result = await apiSend("PATCH", `/api/inboxes/${selectedId}`, payload);
      }

      if (result?.id) {
        setSelectedId(result.id);
        await fetchWorkflows(listPage);
        toast.success("Classification workflow saved successfully");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">Classification Workflows</h1>
        <p className="text-slate-400">
          Configure inboxes to automatically classify emails using prompts and categorization rules
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-4 gap-6">
        {/* Workflow List */}
        <div className="col-span-1">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Workflows</CardTitle>
              <CardDescription>{workflowTotal} total</CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                variant={selectedId === "new" ? "default" : "outline"}
                className="w-full mb-3"
                onClick={() => setSelectedId("new")}
              >
                + New Workflow
              </Button>
              {loading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
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
                      <div className="font-medium" title={w.mailbox_id}>
                        {w.mailbox_id?.split("@")[0]}
                      </div>
                      <div className="text-xs text-opacity-75">
                        {w.is_active ? "🟢 Active" : "🔴 Inactive"}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Workflow Editor */}
        <div className="col-span-3 space-y-6">
          {selectedId !== null && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>
                    {selectedId === "new" ? "New Classification Workflow" : "Edit Workflow"}
                  </CardTitle>
                  <CardDescription>
                    Configure inbox, prompt, and classification settings
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Step 1: Inbox Configuration */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">1. Select Inbox</h3>
                    <div>
                      <Label htmlFor="mailbox-id">Mailbox ID (SMTP address)</Label>
                      <Input
                        id="mailbox-id"
                        value={mailboxId}
                        onChange={(e) => setMailboxId(e.target.value)}
                        placeholder="e.g. inbox@company.com"
                        className="mt-2"
                      />
                    </div>
                  </div>

                  {/* Step 2: Prompt & Classification Selection */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">2. Choose Prompt & Classification Set</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="prompt-select">Prompt Template</Label>
                        <Select value={String(promptId)} onValueChange={(v) => setPromptId(Number(v))}>
                          <SelectTrigger id="prompt-select" className="mt-2">
                            <SelectValue placeholder="Select prompt..." />
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
                        <Label htmlFor="set-select">Classification Set</Label>
                        <Select value={String(setId)} onValueChange={(v) => setSetId(Number(v))}>
                          <SelectTrigger id="set-select" className="mt-2">
                            <SelectValue placeholder="Select set..." />
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
                    </div>
                  </div>

                  {/* Step 3: Fetch Configuration */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">3. Email Fetch Settings</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="timezone">Timezone</Label>
                        <Select value={timezone} onValueChange={setTimezone}>
                          <SelectTrigger id="timezone" className="mt-2">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {COMMON_TIMEZONES.map((tz) => (
                              <SelectItem key={tz} value={tz}>
                                {tz}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor="mail-folder">Mail Folder</Label>
                        <Select value={mailFolder} onValueChange={setMailFolder}>
                          <SelectTrigger id="mail-folder" className="mt-2">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="inbox">Inbox</SelectItem>
                            <SelectItem value="junkemail">Junk Email</SelectItem>
                            <SelectItem value="drafts">Drafts</SelectItem>
                            <SelectItem value="deleteditems">Deleted Items</SelectItem>
                            <SelectItem value="all">All Folders</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  </div>

                  {/* Step 4: Scheduling & Write-back */}
                  <div className="space-y-4">
                    <h3 className="font-semibold text-lg">4. Scheduling & Write-back</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="polling">
                          Polling Interval (minutes): {polling}
                        </Label>
                        <Slider
                          id="polling"
                          min={1}
                          max={1440}
                          step={5}
                          value={[polling]}
                          onValueChange={(v) => setPolling(v[0]!)}
                          className="mt-2"
                        />
                      </div>
                      <div>
                        <Label htmlFor="max-messages">Max Messages: {maxMessages}</Label>
                        <Slider
                          id="max-messages"
                          min={1}
                          max={500}
                          step={10}
                          value={[maxMessages]}
                          onValueChange={(v) => setMaxMessages(v[0]!)}
                          className="mt-2"
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id="active"
                          checked={isActive}
                          onCheckedChange={(c) => setIsActive(Boolean(c))}
                        />
                        <Label htmlFor="active">Active</Label>
                      </div>
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id="write-back"
                          checked={graphWriteBackEnabled}
                          onCheckedChange={(c) =>
                            setGraphWriteBackEnabled(Boolean(c))
                          }
                        />
                        <Label htmlFor="write-back">Write Categories Back to Outlook</Label>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="flex gap-3">
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save Workflow"}
                </Button>
                {selectedId !== "new" && (
                  <Button
                    variant="outline"
                    onClick={() => setDeleteDialogOpen(true)}
                  >
                    Delete
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
