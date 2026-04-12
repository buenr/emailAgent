"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type {
  Named,
  Inbox,
  AgentApiConfig,
  PaginatedResponse,
} from "@/lib/types";
import { toast } from "sonner";

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

interface AgentWorkflowConfig {
  id: number | "new";
  inbox_id: number | null;
  prompt_id: number | null;
  agent_apis: number[]; // IDs of agent APIs to call
  webhook_url?: string;
  extract_reference_numbers: boolean;
}

export default function AgenticWorkflowPage() {
  const [workflows, setWorkflows] = useState<AgentWorkflowConfig[]>([]);
  const [inboxes, setInboxes] = useState<Inbox[]>([]);
  const [prompts, setPrompts] = useState<Named[]>([]);
  const [agentApis, setAgentApis] = useState<AgentApiConfig[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const lastPopulatedIdRef = useRef<number | "new" | null>(null);

  // Form state
  const [inboxId, setInboxId] = useState<number | null>(null);
  const [promptId, setPromptId] = useState<number | null>(null);
  const [selectedAgentApis, setSelectedAgentApis] = useState<number[]>([]);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [extractReferenceNumbers, setExtractReferenceNumbers] = useState(true);

  const fetchData = useCallback(async () => {
    setError(null);
    try {
      const [inboxesRes, promptsRes, apisRes] = await Promise.all([
        apiGet<PaginatedResponse<Inbox>>("/api/inboxes?page=1&page_size=100"),
        apiGet<Named[]>("/api/prompt-templates"),
        apiGet<AgentApiConfig[]>("/api/agent-apis"),
      ]);

      setInboxes(inboxesRes?.items ?? []);
      setPrompts(promptsRes ?? []);
      setAgentApis(apisRes ?? []);

      // For now, workflows are stored locally (would need backend storage)
      setWorkflows([]);
      setSelectedId("new");
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

  const resetFormToDefaults = useCallback(() => {
    setInboxId(null);
    setPromptId(null);
    setSelectedAgentApis([]);
    setWebhookUrl("");
    setExtractReferenceNumbers(true);
  }, []);

  useEffect(() => {
    lastPopulatedIdRef.current = null;

    if (selectedId === "new") {
      resetFormToDefaults();
      return;
    }

    if (lastPopulatedIdRef.current === selectedId) {
      return;
    }

    // Load workflow from localStorage or state
    const workflow = workflows.find((w) => w.id === selectedId);
    if (workflow) {
      lastPopulatedIdRef.current = selectedId;
      setInboxId(workflow.inbox_id ?? null);
      setPromptId(workflow.prompt_id ?? null);
      setSelectedAgentApis(workflow.agent_apis ?? []);
      setWebhookUrl(workflow.webhook_url ?? "");
      setExtractReferenceNumbers(workflow.extract_reference_numbers ?? true);
    }
  }, [selectedId, workflows, resetFormToDefaults]);

  const handleSave = async () => {
    if (!inboxId || !promptId) {
      toast.error("Inbox and prompt are required");
      return;
    }

    if (selectedAgentApis.length === 0) {
      toast.error("At least one agent API must be selected");
      return;
    }

    setSaving(true);
    try {
      const config: AgentWorkflowConfig = {
        id: selectedId ?? "new",
        inbox_id: inboxId,
        prompt_id: promptId,
        agent_apis: selectedAgentApis,
        webhook_url: webhookUrl,
        extract_reference_numbers: extractReferenceNumbers,
      };

      // Store in localStorage for now (would save to backend in production)
      const stored = JSON.parse(localStorage.getItem("agentic_workflows") ?? "[]");
      const idx = stored.findIndex((w: AgentWorkflowConfig) => w.id === selectedId);

      if (selectedId === "new") {
        config.id = Math.max(...stored.map((w: AgentWorkflowConfig) => w.id ?? 0), 0) + 1;
        stored.push(config);
      } else {
        stored[idx] = config;
      }

      localStorage.setItem("agentic_workflows", JSON.stringify(stored));
      setWorkflows(stored);
      setSelectedId(config.id);
      toast.success("Agentic workflow saved successfully");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (selectedId === "new") return;

    try {
      const stored = JSON.parse(localStorage.getItem("agentic_workflows") ?? "[]");
      const filtered = stored.filter((w: AgentWorkflowConfig) => w.id !== selectedId);
      localStorage.setItem("agentic_workflows", JSON.stringify(filtered));
      setWorkflows(filtered);
      setSelectedId("new");
      toast.success("Workflow deleted");
    } catch (e) {
      toast.error("Failed to delete workflow");
    }
  };

  const toggleAgentApi = (apiId: number) => {
    setSelectedAgentApis((prev) =>
      prev.includes(apiId) ? prev.filter((id) => id !== apiId) : [...prev, apiId]
    );
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">Agentic Workflows</h1>
        <p className="text-slate-400">
          Configure AI-powered workflows to extract structured data and call external APIs
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
                  {workflows.map((w) => {
                    const inbox = inboxes.find((i) => i.id === w.inbox_id);
                    return (
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
                          {inbox?.mailbox_id?.split("@")[0] ?? "Workflow"}
                        </div>
                        <div className="text-xs text-opacity-75">
                          {w.agent_apis.length} API(s)
                        </div>
                      </button>
                    );
                  })}
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
                    {selectedId === "new" ? "New Agentic Workflow" : "Edit Workflow"}
                  </CardTitle>
                  <CardDescription>
                    Configure inbox, prompt, and agent integrations
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Step 1: Core Configuration */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">1. Select Inbox & Prompt</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="inbox-select">Inbox</Label>
                        <Select
                          value={String(inboxId ?? "")}
                          onValueChange={(v) => setInboxId(v ? Number(v) : null)}
                        >
                          <SelectTrigger id="inbox-select" className="mt-2">
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
                        <Label htmlFor="prompt-select">Extraction Prompt</Label>
                        <Select
                          value={String(promptId ?? "")}
                          onValueChange={(v) => setPromptId(v ? Number(v) : null)}
                        >
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
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="extract-refs"
                        checked={extractReferenceNumbers}
                        onCheckedChange={(c) =>
                          setExtractReferenceNumbers(Boolean(c))
                        }
                      />
                      <Label htmlFor="extract-refs" className="cursor-pointer">
                        Extract reference numbers (order ID, BOL, PRO#, etc.)
                      </Label>
                    </div>
                  </div>

                  {/* Step 2: Agent API Selection */}
                  <div className="space-y-4 pb-6 border-b border-slate-700">
                    <h3 className="font-semibold text-lg">2. Configure Agent APIs</h3>
                    <p className="text-sm text-slate-400">
                      Select which external APIs to call when processing emails
                    </p>
                    {agentApis.length === 0 ? (
                      <Alert>
                        <AlertDescription>
                          No agent APIs configured yet. Go to{" "}
                          <a href="/agent-apis" className="underline">
                            Agent APIs
                          </a>
                          {" "}to add one.
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
                              checked={selectedAgentApis.includes(api.name as any)}
                              onCheckedChange={() =>
                                toggleAgentApi(api.name as any)
                              }
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

                  {/* Step 3: Callback Configuration */}
                  <div className="space-y-4">
                    <h3 className="font-semibold text-lg">3. Callback Configuration</h3>
                    <div>
                      <Label htmlFor="webhook-url">Webhook URL (optional)</Label>
                      <p className="text-sm text-slate-400 mb-2">
                        POST extracted data and classification results to this URL
                      </p>
                      <Input
                        id="webhook-url"
                        value={webhookUrl}
                        onChange={(e) => setWebhookUrl(e.target.value)}
                        placeholder="https://your-api.example.com/webhooks/email-processing"
                        className="mt-2"
                      />
                    </div>
                    <div className="bg-slate-800 p-3 rounded text-xs text-slate-300">
                      <strong>Payload includes:</strong>
                      <ul className="list-disc list-inside mt-2">
                        <li>Email subject, sender, body</li>
                        <li>Extracted reference numbers (order ID, BOL, PRO#, etc.)</li>
                        <li>Agent API response data</li>
                        <li>Classification result (if enabled)</li>
                      </ul>
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
                    onClick={handleDelete}
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
