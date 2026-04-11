"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type {
  Template,
  InboxPick,
  PaginatedResponse,
  TestPromptResult,
} from "@/lib/types";
import { PromptMonaco } from "@/components/PromptMonaco";
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
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function PromptsPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formName, setFormName] = useState("");
  const [formBody, setFormBody] = useState("");
  const lastPopulatedIdRef = useRef<number | "new" | null>(null);

  const [inboxChoices, setInboxChoices] = useState<InboxPick[]>([]);
  const [testInboxId, setTestInboxId] = useState<number | "">("");
  const [testSubject, setTestSubject] = useState("Test subject");
  const [testSender, setTestSender] = useState("sender@example.com");
  const [testBody, setTestBody] = useState(
    "Paste a sample email body here to see the model JSON."
  );
  const [testUseEditorTemplate, setTestUseEditorTemplate] = useState(true);
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestPromptResult | null>(null);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await apiGet<Template[]>("/api/prompt-templates");
      setTemplates(list);
      setSelectedId((prev) => {
        if (prev === "new") return "new";
        if (!list.length) return "new";
        if (prev !== null && typeof prev === "number" && list.some((t) => t.id === prev)) return prev;
        return list[0]!.id;
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
    load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await apiGet<PaginatedResponse<InboxPick>>(
          "/api/inboxes?page=1&page_size=200"
        );
        if (!cancelled) {
          setInboxChoices(r.items);
          setTestInboxId((prev) => {
            if (prev !== "" && r.items.some((x) => x.id === prev)) return prev;
            return r.items[0]?.id ?? "";
          });
        }
      } catch {
        if (!cancelled) {
          setInboxChoices([]);
          setTestInboxId("");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(() => typeof selectedId === "number" ? templates.find((t) => t.id === selectedId) ?? null : null, [templates, selectedId]);

  useEffect(() => {
    if (selectedId === lastPopulatedIdRef.current) return;
    lastPopulatedIdRef.current = selectedId;
    if (selectedId === "new") {
      setFormName("");
      setFormBody("");
    } else if (selected) {
      setFormName(selected.name);
      setFormBody(selected.body);
    }
  }, [selected, selectedId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (selectedId === "new") {
        const created = await apiSend<Template>("/api/prompt-templates", "POST", {
          name: formName,
          body: formBody,
        });
        await load();
        setSelectedId(created.id);
        toast.success("Template created");
      } else if (typeof selectedId === "number") {
        await apiSend(`/api/prompt-templates/${selectedId}`, "PUT", {
          name: formName,
          body: formBody,
        });
        await load();
        toast.success("Template saved");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Operation failed";
      setError(msg);
      toast.error(msg);
    }
  }

  async function onDelete() {
    if (typeof selectedId !== "number") return;
    setError(null);
    try {
      await apiSend(`/api/prompt-templates/${selectedId}`, "DELETE");
      setDeleteDialogOpen(false);
      setSelectedId(null);
      await load();
      toast.success("Template deleted");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      setError(msg);
      toast.error(msg);
    }
  }

  async function runTestPrompt() {
    if (testInboxId === "") {
      const msg = "Select an inbox (taxonomy and model come from that mapping).";
      setTestError(msg);
      toast.error(msg);
      return;
    }
    if (!testBody.trim()) {
      const msg = "Mock email body is required.";
      setTestError(msg);
      toast.error(msg);
      return;
    }
    setTestError(null);
    setTestResult(null);
    setTestLoading(true);
    try {
      const payload: Record<string, unknown> = {
        inbox_id: testInboxId,
        subject: testSubject,
        sender: testSender,
        body: testBody,
      };
      if (testUseEditorTemplate && formBody.length > 0) {
        payload.prompt_template_override = formBody;
      }
      const out = await apiSend<TestPromptResult>(
        "/api/test-prompt",
        "POST",
        payload
      );
      setTestResult(out);
      toast.success("Test complete");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Test failed";
      setTestError(msg);
      toast.error(msg);
    } finally {
      setTestLoading(false);
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

  return (
    <div className="w-full">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-semibold text-white">
            Prompt Templates
          </h1>
          <p className="text-sm text-slate-500">
            Placeholders:{" "}
            <code className="text-slate-400">
              {"{{ mailbox_id }}, {{ categories_block }}, {{ attachments_block }}, {{ email_block }}"}
            </code>
            , plus{" "}
            <code className="text-slate-400">
              {"{{ subject }}, {{ sender }}, {{ received }}, {{ body }}"}
            </code>
          </p>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="mb-6 flex items-end gap-3">
        <div className="flex-1 max-w-md">
          <Label className="mb-1 block text-sm text-slate-400">Template</Label>
          <Select
            value={selectedId === null ? null : String(selectedId)}
            onValueChange={(val) => {
              if (val === null) return;
              setSelectedId(val === "new" ? "new" : Number(val));
            }}
          >
            <SelectTrigger className="w-full max-w-md">
              <SelectValue placeholder="Select template" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="new">+ Create New Template</SelectItem>
              {templates.map((t) => (
                <SelectItem key={t.id} value={String(t.id)}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-slate-800 bg-slate-900/40 p-6">
        <h2 className="text-lg font-medium text-white">
          {selectedId === "new" ? "Create Template" : "Edit Template"}
        </h2>
        <div>
          <Label className="mb-1 block text-sm text-slate-400">Name</Label>
          <Input
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="Template Name"
            required
          />
        </div>
        <div>
          <Label className="mb-1 block text-sm text-slate-400">Body</Label>
          <PromptMonaco value={formBody} onChange={setFormBody} height={selectedId === "new" ? "300px" : "600px"} />
        </div>
        <div className="flex gap-3 pt-2">
          <Button type="submit">
            {selectedId === "new" ? "Create" : "Save Changes"}
          </Button>
          {typeof selectedId === "number" && (
            <>
              <Button
                type="button"
                variant="destructive"
                onClick={() => setDeleteDialogOpen(true)}
              >
                Delete
              </Button>
              <AlertDialog open={deleteDialogOpen} onOpenChange={(open) => setDeleteDialogOpen(open)}>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete Template</AlertDialogTitle>
                    <AlertDialogDescription>
                      Are you sure you want to delete this template? This action cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={() => void onDelete()}
                    >
                      Delete
                    </Button>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </>
          )}
          {selectedId === "new" && templates.length > 0 && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setSelectedId(templates[0]!.id)}
            >
              Cancel
            </Button>
          )}
        </div>
      </form>

      <div className="mt-10 space-y-4 rounded-lg border border-slate-800 bg-slate-900/40 p-6">
        <h2 className="text-lg font-medium text-white">Test prompt (Gemini)</h2>
        <p className="text-sm text-slate-500">
          Runs one classification call with a mock message. Choose an inbox for its
          categories and model; optionally send the template text from the editor above
          without saving.
        </p>
        {inboxChoices.length === 0 ? (
          <p className="text-sm text-amber-200/90">
            No inboxes configured. Add an inbox mapping first so taxonomy and model are
            defined.
          </p>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Label className="mb-1 block text-sm text-slate-400">Context inbox</Label>
                <Select
                  value={testInboxId === "" ? null : String(testInboxId)}
                  onValueChange={(val) => {
                    if (val === null) return;
                    setTestInboxId(Number(val));
                  }}
                >
                  <SelectTrigger className="w-full max-w-md">
                    <SelectValue placeholder="Select inbox" />
                  </SelectTrigger>
                  <SelectContent>
                    {inboxChoices.map((i) => (
                      <SelectItem key={i.id} value={String(i.id)}>
                        {i.mailbox_id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="mb-1 block text-sm text-slate-400">Subject</Label>
                <Input
                  value={testSubject}
                  onChange={(e) => setTestSubject(e.target.value)}
                />
              </div>
              <div>
                <Label className="mb-1 block text-sm text-slate-400">Sender</Label>
                <Input
                  value={testSender}
                  onChange={(e) => setTestSender(e.target.value)}
                />
              </div>
              <div className="sm:col-span-2">
                <Label className="mb-1 block text-sm text-slate-400">Mock body</Label>
                <Textarea
                  rows={8}
                  className="font-mono text-sm"
                  value={testBody}
                  onChange={(e) => setTestBody(e.target.value)}
                />
              </div>
              <Label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300 sm:col-span-2">
                <Checkbox
                  checked={testUseEditorTemplate}
                  onCheckedChange={(checked) => setTestUseEditorTemplate(checked)}
                />
                Use current editor template (unsaved OK); when off, the saved template
                linked to the inbox is used.
              </Label>
            </div>
            <Button
              type="button"
              disabled={testLoading}
              onClick={() => void runTestPrompt()}
            >
              {testLoading ? "Running…" : "Run test"}
            </Button>
            {testError && (
              <Alert variant="destructive">
                <AlertDescription>{testError}</AlertDescription>
              </Alert>
            )}
            {testResult && (
              <div className="space-y-2 text-sm">
                {testResult.error && (
                  <p className="text-red-300">{testResult.error}</p>
                )}
                {testResult.warning && (
                  <p className="text-amber-200">{testResult.warning}</p>
                )}
                <p className="text-slate-400">
                  Resolved category:{" "}
                  <span className="text-slate-200">{testResult.category_resolved}</span>
                  {" · "}
                  Tokens in/out: {testResult.usage.prompt_token_count}/
                  {testResult.usage.candidates_token_count}
                </p>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950 p-4 font-mono text-xs text-emerald-200/90">
                  {testResult.model_json != null
                    ? JSON.stringify(testResult.model_json, null, 2)
                    : testResult.raw_text ?? "(no JSON)"}
                </pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
