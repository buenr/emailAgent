"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type {
  Named,
  Inbox,
  AgentApiConfig,
  AgenticWorkflow,
  FunctionDeclarationConfig,
  FunctionParameter,
  DryRunResult,
  PaginatedResponse,
  ClassificationSetDetail,
  FetchFilter,
} from "@/lib/types";
import { toast } from "sonner";
import { PlayIcon, PlusIcon, TrashIcon, FlaskConical } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

function emptyFuncParam(): FunctionParameter {
  return { name: "", type: "string", description: "", required: false };
}

function emptyFuncDecl(): FunctionDeclarationConfig {
  return { name: "", description: "", parameters: [emptyFuncParam()] };
}

export default function AgenticWorkflowPage() {
  const [workflows, setWorkflows] = useState<AgenticWorkflow[]>([]);
  const [inboxes, setInboxes] = useState<Inbox[]>([]);
  const [prompts, setPrompts] = useState<Named[]>([]);
  const [agentApis, setAgentApis] = useState<AgentApiConfig[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [inboxId, setInboxId] = useState<number | null>(null);
  const [workflowName, setWorkflowName] = useState("");
  const [promptId, setPromptId] = useState<number | null>(null);
  const [triggerCategories, setTriggerCategories] = useState<string[]>([]);
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [funcDecls, setFuncDecls] = useState<FunctionDeclarationConfig[]>([
    emptyFuncDecl(),
  ]);
  const [selectedAgentApis, setSelectedAgentApis] = useState<string[]>([]);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [responsePromptId, setResponsePromptId] = useState<number | null>(null);
  const [workflowFilter, setWorkflowFilter] = useState<FetchFilter>({
    unread_only: false,
    time_window_mode: "local_today",
    rolling_hours: null,
    sender_allowlist: [],
    sender_denylist: [],
    subject_keywords: [],
    subject_keyword_mode: "any",
    body_keywords: [],
    importance_levels: [],
    has_attachments: "any",
    category_include_any: [],
    category_exclude_any: [],
  });
  const [autoSend, setAutoSend] = useState(false);
  const [isActive, setIsActive] = useState(true);

  // Dry run
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [dryRunSubject, setDryRunSubject] = useState("Test ETA Update");
  const [dryRunSender, setDryRunSender] = useState("dispatch@example.com");
  const [dryRunBody, setDryRunBody] = useState(
    "Order #12345, BOL 67890. ETA is 3pm today. Truck T-100, Trailer TL-200."
  );

  const fetchData = useCallback(async () => {
    setError(null);
    try {
      const [wfRes, inboxesRes, promptsRes, apisRes] = await Promise.all([
        apiGet<AgenticWorkflow[]>("/api/agentic-workflows"),
        apiGet<PaginatedResponse<Inbox>>("/api/inboxes?page=1&page_size=200"),
        apiGet<Named[]>("/api/prompt-templates"),
        apiGet<AgentApiConfig[]>("/api/agent-apis"),
      ]);
      setWorkflows(wfRes ?? []);
      setInboxes(inboxesRes?.items ?? []);
      setPrompts(promptsRes ?? []);
      setAgentApis(apisRes ?? []);

      const firstWorkflow = (wfRes ?? [])[0];
      if (firstWorkflow?.id != null) {
        setSelectedId(firstWorkflow.id);
      } else {
        setSelectedId("new");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load data";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Load categories when inbox changes
  useEffect(() => {
    if (!inboxId) {
      setAvailableCategories([]);
      return;
    }
    const inbox = inboxes.find((i) => i.id === inboxId);
    if (!inbox) return;
    const setIdVal = inbox.classification_set_id;
    if (!setIdVal) return;
    apiGet<ClassificationSetDetail>(`/api/classification-sets/${setIdVal}`)
      .then((detail) => {
        setAvailableCategories(
          (detail?.categories ?? []).map((c) => c.name)
        );
      })
      .catch(() => setAvailableCategories([]));
  }, [inboxId, inboxes]);

  const resetForm = useCallback(() => {
    setInboxId(null);
    setWorkflowName("");
    setPromptId(null);
    setResponsePromptId(null);
    setTriggerCategories([]);
    setFuncDecls([emptyFuncDecl()]);
    setSelectedAgentApis([]);
    setWebhookUrl("");
    setWorkflowFilter({
      unread_only: false,
      time_window_mode: "local_today",
      rolling_hours: null,
      sender_allowlist: [],
      sender_denylist: [],
      subject_keywords: [],
      subject_keyword_mode: "any",
      body_keywords: [],
      importance_levels: [],
      has_attachments: "any",
      category_include_any: [],
      category_exclude_any: [],
    });
    setAutoSend(false);
    setIsActive(true);
    setDryRunResult(null);
  }, []);

  // Populate form when selection changes
  useEffect(() => {
    if (selectedId === "new") {
      resetForm();
      return;
    }
    if (selectedId === null) return;
    const wf = workflows.find((w) => w.id === selectedId);
    if (!wf) return;
    setInboxId(wf.inbox_id);
    setWorkflowName(wf.name ?? "");
    setPromptId(wf.extraction_prompt_id);
    setResponsePromptId(wf.response_prompt_id ?? null);
    setTriggerCategories(wf.trigger_categories ?? []);
    setFuncDecls(
      wf.function_declarations?.length
        ? wf.function_declarations
        : [emptyFuncDecl()]
    );
    setSelectedAgentApis(wf.agent_api_names ?? []);
    setWebhookUrl(wf.webhook_url ?? "");
    setWorkflowFilter(wf.workflow_filter ?? {
      unread_only: false,
      time_window_mode: "local_today",
      rolling_hours: null,
      sender_allowlist: [],
      sender_denylist: [],
      subject_keywords: [],
      subject_keyword_mode: "any",
      body_keywords: [],
      importance_levels: [],
      has_attachments: "any",
      category_include_any: [],
      category_exclude_any: [],
    });
    setAutoSend(wf.auto_send ?? false);
    setIsActive(wf.is_active ?? true);
    setDryRunResult(null);
  }, [selectedId, workflows, resetForm]);

  const handleSave = async () => {
    if (!inboxId || !promptId) {
      toast.error("Inbox and extraction prompt are required");
      return;
    }
    if (triggerCategories.length === 0) {
      toast.error("At least one trigger category is required");
      return;
    }

    setSaving(true);
    try {
      const cleanFds = funcDecls
        .filter((fd) => fd.name.trim())
        .map((fd) => ({
          ...fd,
          parameters: fd.parameters.filter((p) => p.name.trim()),
        }));

      const payload = {
        inbox_id: inboxId,
        name: workflowName.trim(),
        extraction_prompt_id: promptId,
        response_prompt_id: responsePromptId,
        workflow_filter: workflowFilter,
        trigger_categories: triggerCategories,
        function_declarations: cleanFds,
        agent_api_names: selectedAgentApis,
        webhook_url: webhookUrl.trim() || null,
        auto_send: autoSend,
        is_active: isActive,
      };

      if (selectedId === "new") {
        const result = await apiSend<{ id: number }>(
          "/api/agentic-workflows",
          "POST",
          payload
        );
        if (result?.id) setSelectedId(result.id);
      } else {
        await apiSend(`/api/agentic-workflows/${selectedId}`, "PUT", payload);
      }

      await fetchData();
      toast.success("Agentic workflow saved");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (selectedId === "new" || selectedId === null) return;
    try {
      await apiSend(`/api/agentic-workflows/${selectedId}`, "DELETE");
      setSelectedId("new");
      await fetchData();
      toast.success("Workflow deleted");
    } catch (e) {
      toast.error("Failed to delete workflow");
    }
  };

  const handleDryRun = async () => {
    if (selectedId === "new" || selectedId === null) return;
    setDryRunLoading(true);
    setDryRunResult(null);
    try {
      const result = await apiSend<DryRunResult>(
        `/api/agentic-workflows/${selectedId}/dry-run`,
        "POST",
        { subject: dryRunSubject, sender: dryRunSender, body: dryRunBody }
      );
      setDryRunResult(result);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Dry run failed";
      toast.error(msg);
    } finally {
      setDryRunLoading(false);
    }
  };

  const toggleCategory = (cat: string) => {
    setTriggerCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const toggleAgentApi = (name: string) => {
    setSelectedAgentApis((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );
  };

  const parseCsv = (value: string): string[] =>
    value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

  const updateWorkflowFilter = <K extends keyof FetchFilter>(
    field: K,
    value: FetchFilter[K]
  ) => {
    setWorkflowFilter((prev) => ({ ...prev, [field]: value }));
  };

  // Function declaration helpers
  const updateFuncDecl = (
    idx: number,
    field: keyof FunctionDeclarationConfig,
    value: unknown
  ) => {
    setFuncDecls((prev) =>
      prev.map((fd, i) => (i === idx ? { ...fd, [field]: value } : fd))
    );
  };
  const addFuncDecl = () => setFuncDecls((prev) => [...prev, emptyFuncDecl()]);
  const removeFuncDecl = (idx: number) =>
    setFuncDecls((prev) => prev.filter((_, i) => i !== idx));

  const updateParam = (
    fdIdx: number,
    pIdx: number,
    field: keyof FunctionParameter,
    value: unknown
  ) => {
    setFuncDecls((prev) =>
      prev.map((fd, fi) =>
        fi === fdIdx
          ? {
              ...fd,
              parameters: fd.parameters.map((p, pi) =>
                pi === pIdx ? { ...p, [field]: value } : p
              ),
            }
          : fd
      )
    );
  };
  const addParam = (fdIdx: number) =>
    setFuncDecls((prev) =>
      prev.map((fd, i) =>
        i === fdIdx
          ? { ...fd, parameters: [...fd.parameters, emptyFuncParam()] }
          : fd
      )
    );
  const removeParam = (fdIdx: number, pIdx: number) =>
    setFuncDecls((prev) =>
      prev.map((fd, i) =>
        i === fdIdx
          ? { ...fd, parameters: fd.parameters.filter((_, pi) => pi !== pIdx) }
          : fd
      )
    );

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">Agentic Workflows</h1>
        <p className="text-slate-400">
          Build custom AI extraction pipelines with Gemini Function Calling and
          external API integrations
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
                      <div className="font-medium">
                        {w.name || w.inbox_mailbox_id?.split("@")[0] || `Workflow #${w.id}`}
                      </div>
                      <div className="text-xs text-opacity-75">
                        {w.is_active ? "🟢 Active" : "🔴 Inactive"} ·{" "}
                        {w.trigger_categories?.length ?? 0} trigger(s)
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
                    {selectedId === "new"
                      ? "New Agentic Workflow"
                      : "Edit Workflow"}
                  </CardTitle>
                  <CardDescription>
                    Configure extraction, trigger categories, and API
                    integrations
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Step 1: Core Config */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">
                      1. Select Inbox & Extraction Prompt
                    </h3>
                    <div>
                      <Label>Workflow Name (optional)</Label>
                      <Input
                        value={workflowName}
                        onChange={(e) => setWorkflowName(e.target.value)}
                        placeholder="e.g. ETA Extraction Pipeline"
                        className="mt-2"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="aw-inbox">Inbox</Label>
                        <Select
                          value={String(inboxId ?? "")}
                          onValueChange={(v) =>
                            setInboxId(v ? Number(v) : null)
                          }
                        >
                          <SelectTrigger id="aw-inbox" className="mt-2">
                            <SelectValue placeholder="Select inbox..." />
                          </SelectTrigger>
                          <SelectContent>
                            {inboxes.map((i) => (
                              <SelectItem key={i.id} value={String(i.id)}>
                                {i.mailbox_id}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor="aw-prompt">Extraction Prompt</Label>
                        <Select
                          value={String(promptId ?? "")}
                          onValueChange={(v) =>
                            setPromptId(v ? Number(v) : null)
                          }
                        >
                          <SelectTrigger id="aw-prompt" className="mt-2">
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
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="aw-active"
                        checked={isActive}
                        onCheckedChange={(c) => setIsActive(Boolean(c))}
                      />
                      <Label htmlFor="aw-active" className="cursor-pointer">
                        Active
                      </Label>
                    </div>
                  </div>

                  {/* Step 2: Trigger Categories */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">
                      2. Trigger Categories
                    </h3>
                    <p className="text-sm text-slate-400">
                      Only emails classified into these categories will trigger
                      extraction
                    </p>
                    {!inboxId ? (
                      <Alert>
                        <AlertDescription>
                          Select an inbox first to see available categories.
                        </AlertDescription>
                      </Alert>
                    ) : availableCategories.length === 0 ? (
                      <Alert>
                        <AlertDescription>
                          No categories found for the selected inbox&apos;s
                          classification set.
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <div className="grid grid-cols-3 gap-2 max-h-48 overflow-y-auto">
                        {availableCategories.map((cat) => (
                          <div
                            key={cat}
                            className="flex items-center gap-2 p-2 border border-slate-700 rounded"
                          >
                            <Checkbox
                              id={`cat-${cat}`}
                              checked={triggerCategories.includes(cat)}
                              onCheckedChange={() => toggleCategory(cat)}
                            />
                            <Label
                              htmlFor={`cat-${cat}`}
                              className="cursor-pointer text-sm"
                            >
                              {cat}
                            </Label>
                          </div>
                        ))}
                      </div>
                    )}
                    {triggerCategories.length > 0 && (
                      <div className="text-xs text-slate-400">
                        Selected: {triggerCategories.join(", ")}
                      </div>
                    )}
                  </div>

                  {/* Step 3: Function Declarations */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-semibold text-lg">
                          3. Function Declarations
                        </h3>
                        <p className="text-sm text-slate-400">
                          Define what Gemini should extract via function calling
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={addFuncDecl}
                      >
                        <PlusIcon className="w-4 h-4 mr-1" /> Add Function
                      </Button>
                    </div>

                    {funcDecls.map((fd, fdIdx) => (
                      <Card key={fdIdx} className="bg-slate-800/50 border-slate-700">
                        <CardContent className="pt-4 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-300">
                              Function {fdIdx + 1}
                            </span>
                            {funcDecls.length > 1 && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => removeFuncDecl(fdIdx)}
                              >
                                <TrashIcon className="w-4 h-4 text-red-400" />
                              </Button>
                            )}
                          </div>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <Label>Function Name</Label>
                              <Input
                                value={fd.name}
                                onChange={(e) =>
                                  updateFuncDecl(fdIdx, "name", e.target.value)
                                }
                                placeholder="e.g. extract_shipment_info"
                                className="mt-1"
                              />
                            </div>
                            <div>
                              <Label>Description</Label>
                              <Input
                                value={fd.description}
                                onChange={(e) =>
                                  updateFuncDecl(
                                    fdIdx,
                                    "description",
                                    e.target.value
                                  )
                                }
                                placeholder="Extract shipment details from email"
                                className="mt-1"
                              />
                            </div>
                          </div>

                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <Label className="text-xs text-slate-400">
                                Parameters
                              </Label>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => addParam(fdIdx)}
                              >
                                <PlusIcon className="w-3 h-3 mr-1" /> Add
                              </Button>
                            </div>
                            {fd.parameters.map((p, pIdx) => (
                              <div
                                key={pIdx}
                                className="grid grid-cols-12 gap-2 items-center"
                              >
                                <Input
                                  value={p.name}
                                  onChange={(e) =>
                                    updateParam(
                                      fdIdx,
                                      pIdx,
                                      "name",
                                      e.target.value
                                    )
                                  }
                                  placeholder="name"
                                  className="col-span-3"
                                />
                                <Select
                                  value={p.type}
                                  onValueChange={(v) =>
                                    updateParam(fdIdx, pIdx, "type", v)
                                  }
                                >
                                  <SelectTrigger className="col-span-2">
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="string">
                                      string
                                    </SelectItem>
                                    <SelectItem value="number">
                                      number
                                    </SelectItem>
                                    <SelectItem value="integer">
                                      integer
                                    </SelectItem>
                                    <SelectItem value="boolean">
                                      boolean
                                    </SelectItem>
                                  </SelectContent>
                                </Select>
                                <Input
                                  value={p.description}
                                  onChange={(e) =>
                                    updateParam(
                                      fdIdx,
                                      pIdx,
                                      "description",
                                      e.target.value
                                    )
                                  }
                                  placeholder="description"
                                  className="col-span-4"
                                />
                                <div className="col-span-2 flex items-center gap-1">
                                  <Checkbox
                                    checked={p.required}
                                    onCheckedChange={(c) =>
                                      updateParam(
                                        fdIdx,
                                        pIdx,
                                        "required",
                                        Boolean(c)
                                      )
                                    }
                                  />
                                  <span className="text-xs">req</span>
                                </div>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="col-span-1"
                                  onClick={() => removeParam(fdIdx, pIdx)}
                                >
                                  <TrashIcon className="w-3 h-3 text-red-400" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>

                  {/* Step 4: Response Prompt */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">
                      4. Response Prompt
                    </h3>
                    <p className="text-sm text-slate-400">
                      Optional second prompt used to turn API results into a draft reply.
                    </p>
                    <div>
                      <Label htmlFor="aw-response-prompt">Response Prompt</Label>
                      <Select
                        value={String(responsePromptId ?? "")}
                        onValueChange={(v) =>
                          setResponsePromptId(v ? Number(v) : null)
                        }
                      >
                        <SelectTrigger
                          id="aw-response-prompt"
                          className="mt-2"
                        >
                          <SelectValue placeholder="None" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="">None</SelectItem>
                          {prompts.map((p) => (
                            <SelectItem key={p.id} value={String(p.id)}>
                              {p.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* Step 5: Workflow Filter */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">
                      5. Workflow Filter
                    </h3>
                    <p className="text-sm text-slate-400">
                      Only run this workflow on emails that meet these criteria.
                    </p>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id="wf-unread-only"
                          checked={workflowFilter.unread_only}
                          onCheckedChange={(c) =>
                            updateWorkflowFilter("unread_only", Boolean(c))
                          }
                        />
                        <Label htmlFor="wf-unread-only" className="cursor-pointer">
                          Unread only
                        </Label>
                      </div>
                      <div>
                        <Label htmlFor="wf-has-attachments">Attachments</Label>
                        <Select
                          value={workflowFilter.has_attachments}
                          onValueChange={(value) =>
                            updateWorkflowFilter(
                              "has_attachments",
                              value as FetchFilter["has_attachments"]
                            )
                          }
                        >
                          <SelectTrigger
                            id="wf-has-attachments"
                            className="mt-2"
                          >
                            <SelectValue placeholder="Any" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
                            <SelectItem value="yes">Yes</SelectItem>
                            <SelectItem value="no">No</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor="wf-sender-allowlist">Sender allowlist</Label>
                        <Input
                          id="wf-sender-allowlist"
                          value={workflowFilter.sender_allowlist.join(", ")}
                          onChange={(e) =>
                            updateWorkflowFilter(
                              "sender_allowlist",
                              parseCsv(e.target.value)
                            )
                          }
                          placeholder="comma-separated email addresses or domains"
                          className="mt-2"
                        />
                      </div>
                      <div>
                        <Label htmlFor="wf-sender-denylist">Sender denylist</Label>
                        <Input
                          id="wf-sender-denylist"
                          value={workflowFilter.sender_denylist.join(", ")}
                          onChange={(e) =>
                            updateWorkflowFilter(
                              "sender_denylist",
                              parseCsv(e.target.value)
                            )
                          }
                          placeholder="comma-separated email addresses or domains"
                          className="mt-2"
                        />
                      </div>
                      <div>
                        <Label htmlFor="wf-subject-keywords">
                          Subject keywords
                        </Label>
                        <Input
                          id="wf-subject-keywords"
                          value={workflowFilter.subject_keywords.join(", ")}
                          onChange={(e) =>
                            updateWorkflowFilter(
                              "subject_keywords",
                              parseCsv(e.target.value)
                            )
                          }
                          placeholder="comma-separated keywords"
                          className="mt-2"
                        />
                      </div>
                      <div>
                        <Label htmlFor="wf-subject-mode">
                          Subject keyword mode
                        </Label>
                        <Select
                          value={workflowFilter.subject_keyword_mode}
                          onValueChange={(value) =>
                            updateWorkflowFilter(
                              "subject_keyword_mode",
                              value as FetchFilter["subject_keyword_mode"]
                            )
                          }
                        >
                          <SelectTrigger id="wf-subject-mode" className="mt-2">
                            <SelectValue placeholder="Any" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
                            <SelectItem value="all">All</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor="wf-body-keywords">Body keywords</Label>
                        <Input
                          id="wf-body-keywords"
                          value={workflowFilter.body_keywords.join(", ")}
                          onChange={(e) =>
                            updateWorkflowFilter(
                              "body_keywords",
                              parseCsv(e.target.value)
                            )
                          }
                          placeholder="comma-separated keywords"
                          className="mt-2"
                        />
                      </div>
                      <div>
                        <Label htmlFor="wf-importance-levels">
                          Importance levels
                        </Label>
                        <Input
                          id="wf-importance-levels"
                          value={workflowFilter.importance_levels.join(", ")}
                          onChange={(e) =>
                            updateWorkflowFilter(
                              "importance_levels",
                              parseCsv(e.target.value)
                            )
                          }
                          placeholder="comma-separated levels (low, normal, high)"
                          className="mt-2"
                        />
                      </div>
                      <div>
                        <Label htmlFor="wf-category-include-any">
                          Include categories
                        </Label>
                        <Input
                          id="wf-category-include-any"
                          value={workflowFilter.category_include_any.join(", ")}
                          onChange={(e) =>
                            updateWorkflowFilter(
                              "category_include_any",
                              parseCsv(e.target.value)
                            )
                          }
                          placeholder="comma-separated categories"
                          className="mt-2"
                        />
                      </div>
                      <div>
                        <Label htmlFor="wf-category-exclude-any">
                          Exclude categories
                        </Label>
                        <Input
                          id="wf-category-exclude-any"
                          value={workflowFilter.category_exclude_any.join(", ")}
                          onChange={(e) =>
                            updateWorkflowFilter(
                              "category_exclude_any",
                              parseCsv(e.target.value)
                            )
                          }
                          placeholder="comma-separated categories"
                          className="mt-2"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="aw-auto-send"
                        checked={autoSend}
                        onCheckedChange={(c) => setAutoSend(Boolean(c))}
                      />
                      <Label htmlFor="aw-auto-send" className="cursor-pointer">
                        Auto-send generated draft when available
                      </Label>
                    </div>
                  </div>

                  {/* Step 6: Agent APIs */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">
                      6. Agent APIs
                    </h3>
                    <p className="text-sm text-slate-400">
                      Select which external APIs to call sequentially with
                      extracted data
                    </p>
                    {agentApis.length === 0 ? (
                      <Alert>
                        <AlertDescription>
                          No agent APIs configured yet. Go to{" "}
                          <a href="/agent-apis" className="underline">
                            Agent APIs
                          </a>{" "}
                          to add one.
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <div className="space-y-2">
                        {agentApis.map((api) => (
                          <div
                            key={api.name}
                            className="flex items-center gap-3 p-3 border border-slate-700 rounded"
                          >
                            <Checkbox
                              id={`api-${api.name}`}
                              checked={selectedAgentApis.includes(api.name)}
                              onCheckedChange={() => toggleAgentApi(api.name)}
                            />
                            <Label
                              htmlFor={`api-${api.name}`}
                              className="flex-1 cursor-pointer"
                            >
                              <div className="font-medium">{api.name}</div>
                              <div className="text-xs text-slate-400">
                                {api.api_url}
                              </div>
                            </Label>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Step 5: Webhook */}
                  <div className="space-y-4">
                    <h3 className="font-semibold text-lg">
                      5. Webhook Callback (optional)
                    </h3>
                    <div>
                      <Label htmlFor="aw-webhook">Webhook URL</Label>
                      <Input
                        id="aw-webhook"
                        value={webhookUrl}
                        onChange={(e) => setWebhookUrl(e.target.value)}
                        placeholder="https://api.example.com/webhooks/agentic"
                        className="mt-2"
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Action buttons */}
              <div className="flex gap-3">
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save Workflow"}
                </Button>
                {selectedId !== "new" && (
                  <>
                    <Button variant="outline" onClick={handleDelete}>
                      Delete
                    </Button>
                  </>
                )}
              </div>

              {/* Dry Run */}
              {selectedId !== "new" && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <FlaskConical className="w-5 h-5" />
                      Workflow Simulator (Dry Run)
                    </CardTitle>
                    <CardDescription>
                      Test extraction on a mock email — no APIs will be called
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Subject</Label>
                        <Input
                          value={dryRunSubject}
                          onChange={(e) => setDryRunSubject(e.target.value)}
                          className="mt-1"
                        />
                      </div>
                      <div>
                        <Label>Sender</Label>
                        <Input
                          value={dryRunSender}
                          onChange={(e) => setDryRunSender(e.target.value)}
                          className="mt-1"
                        />
                      </div>
                    </div>
                    <div>
                      <Label>Body</Label>
                      <Textarea
                        value={dryRunBody}
                        onChange={(e) => setDryRunBody(e.target.value)}
                        rows={4}
                        className="mt-1"
                      />
                    </div>
                    <Button
                      onClick={handleDryRun}
                      disabled={dryRunLoading}
                      variant="outline"
                    >
                      <PlayIcon className="w-4 h-4 mr-2" />
                      {dryRunLoading ? "Running..." : "Run Simulation"}
                    </Button>

                    {dryRunResult && (
                      <div className="grid grid-cols-2 gap-4 mt-4">
                        <Card className="bg-slate-800/50 border-slate-700">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-sm">
                              Extracted Data
                            </CardTitle>
                          </CardHeader>
                          <CardContent>
                            {dryRunResult.error ? (
                              <p className="text-red-400 text-sm">
                                {dryRunResult.error}
                              </p>
                            ) : Object.keys(dryRunResult.extracted_data)
                                .length === 0 ? (
                              <p className="text-slate-400 text-sm">
                                No data extracted
                              </p>
                            ) : (
                              <pre className="text-xs text-green-400 whitespace-pre-wrap">
                                {JSON.stringify(
                                  dryRunResult.extracted_data,
                                  null,
                                  2
                                )}
                              </pre>
                            )}
                          </CardContent>
                        </Card>
                        <Card className="bg-slate-800/50 border-slate-700">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-sm">
                              API Payload Preview
                            </CardTitle>
                          </CardHeader>
                          <CardContent>
                            {Object.keys(dryRunResult.api_payload_preview)
                              .length === 0 ? (
                              <p className="text-slate-400 text-sm">
                                No payload
                              </p>
                            ) : (
                              <pre className="text-xs text-blue-400 whitespace-pre-wrap">
                                {JSON.stringify(
                                  dryRunResult.api_payload_preview,
                                  null,
                                  2
                                )}
                              </pre>
                            )}
                          </CardContent>
                        </Card>
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
