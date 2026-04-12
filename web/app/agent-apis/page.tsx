"use client";

import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type { AgentApiConfig } from "@/lib/types";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const initialConfig: AgentApiConfig = {
  name: "",
  api_url: "",
  api_key: "",
};

export default function AgentApisPage() {
  const [configs, setConfigs] = useState<AgentApiConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadConfigs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiGet<AgentApiConfig[]>("/api/agent-apis");
      setConfigs(result ?? []);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to load agent APIs";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  function updateRow(index: number, field: keyof AgentApiConfig, value: string) {
    setConfigs((current: AgentApiConfig[]) =>
      current.map((row: AgentApiConfig, idx: number) =>
        idx === index ? { ...row, [field]: value } : row
      )
    );
  }

  function addRow() {
    setConfigs((current: AgentApiConfig[]) => [...current, { ...initialConfig }]);
  }

  function removeRow(index: number) {
    setConfigs((current: AgentApiConfig[]) => current.filter((_: AgentApiConfig, idx: number) => idx !== index));
  }

  function validate(): string | null {
    for (const [index, config] of configs.entries()) {
      if (!config.name.trim()) {
        return `Name is required for row ${index + 1}.`;
      }
      if (!config.api_url.trim()) {
        return `Endpoint URL is required for row ${index + 1}.`;
      }
      if (!config.api_key.trim()) {
        return `API key is required for row ${index + 1}.`;
      }
    }
    return null;
  }

  async function saveConfigs() {
    setError(null);
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      toast.error(validationError);
      return;
    }

    setSaving(true);
    try {
      await apiSend<{ status: string }>("/api/agent-apis", "PUT", configs);
      toast.success("Agent API settings saved");
      await loadConfigs();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to save agent APIs";
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="w-full space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-10 w-full max-w-3xl" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Agent APIs</h1>
          <p className="max-w-2xl text-sm text-slate-500">
            Configure the email agent integrations that the system will use. Each entry includes a named API, an endpoint URL, and a secret key.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={addRow} disabled={saving}>
            Add API config
          </Button>
          <Button type="button" onClick={saveConfigs} disabled={saving}>
            {saving ? "Saving..." : "Save settings"}
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {configs.length === 0 ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-slate-300">
          No agent API configurations are defined. Click “Add API config” to create one.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900/40">
          <Table>
            <TableHeader className="border-b border-slate-800 bg-slate-900/70">
              <TableRow>
                <TableHead className="text-xs uppercase text-slate-500">Name</TableHead>
                <TableHead className="text-xs uppercase text-slate-500">Endpoint URL</TableHead>
                <TableHead className="text-xs uppercase text-slate-500">API key</TableHead>
                <TableHead className="text-right text-xs uppercase text-slate-500">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {configs.map((config: AgentApiConfig, index: number) => (
                <TableRow key={`${config.name}-${index}`} className="border-b border-slate-800/80 last:border-0">
                  <TableCell className="p-3 align-top">
                    <Label className="mb-1 block text-sm text-slate-400" htmlFor={`agent-name-${index}`}>
                      API name
                    </Label>
                    <Input
                      id={`agent-name-${index}`}
                      value={config.name}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => updateRow(index, "name", event.target.value)}
                      placeholder="Example: Gemini Agent"
                      className="min-w-[180px] text-sm"
                    />
                  </TableCell>
                  <TableCell className="p-3 align-top">
                    <Label className="mb-1 block text-sm text-slate-400" htmlFor={`agent-url-${index}`}>
                      Endpoint URL
                    </Label>
                    <Input
                      id={`agent-url-${index}`}
                      value={config.api_url}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => updateRow(index, "api_url", event.target.value)}
                      placeholder="https://api.example.com/v1/messages"
                      className="min-w-[260px] text-sm"
                    />
                  </TableCell>
                  <TableCell className="p-3 align-top">
                    <Label className="mb-1 block text-sm text-slate-400" htmlFor={`agent-key-${index}`}>
                      API key
                    </Label>
                    <Input
                      id={`agent-key-${index}`}
                      type="password"
                      value={config.api_key}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => updateRow(index, "api_key", event.target.value)}
                      placeholder="●●●●●●●●"
                      className="min-w-[220px] text-sm"
                    />
                  </TableCell>
                  <TableCell className="p-3 text-right align-top">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => removeRow(index)}
                    >
                      Remove
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
