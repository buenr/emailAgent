"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend, ApiError } from "@/lib/api";
import type { AppModel } from "@/lib/types";
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
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export default function AppModelsPage() {
  const [models, setModels] = useState<AppModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; name: string } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await apiGet<AppModel[]>("/api/app-models");
      setModels(list);
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

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setError(null);
    try {
      await apiSend<{ id: number }>("/api/app-models", "POST", { name });
      setNewName("");
      await load();
      toast.success("Model added");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Create failed";
      setError(msg);
      toast.error(msg);
    }
  }

  async function onDelete() {
    if (!deleteTarget) return;
    setDeleteError(null);
    try {
      await apiSend(`/api/app-models/${deleteTarget.id}`, "DELETE");
      setDeleteTarget(null);
      await load();
      toast.success("Model deleted");
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setDeleteError(`Cannot delete "${deleteTarget.name}": model is in use`);
        toast.error(`Cannot delete "${deleteTarget.name}": model is in use`);
      } else {
        const msg = err instanceof Error ? err.message : "Delete failed";
        setDeleteError(msg);
        toast.error(msg);
      }
    }
  }

  if (loading) {
    return (
      <div className="w-full space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="w-full">
      <h1 className="mb-2 text-2xl font-semibold text-white">App models</h1>
      <p className="mb-8 text-sm text-slate-500">
        Gemini model IDs for inbox configuration. Default runtime model is{" "}
        <code className="text-slate-400">gemini-2.5-flash-lite</code> when no inbox
        model is selected and <code className="text-slate-400">GEMINI_MODEL</code> is
        unset. Examples:{" "}
        <code className="text-slate-400">gemini-3.1-pro</code>,{" "}
        <code className="text-slate-400">gemini-3.1-flash-lite</code>.
      </p>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <form
        onSubmit={onAdd}
        className="mb-8 flex flex-wrap items-end gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-4"
      >
        <div className="min-w-[200px] flex-1">
          <Label className="mb-1 block text-sm text-slate-400">Model name</Label>
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="gemini-2.5-flash-lite"
            className="font-mono text-sm"
          />
        </div>
        <Button type="submit">Add model</Button>
      </form>

      <div className="rounded-lg border border-slate-800">
        <Table>
          <TableHeader className="border-b border-slate-800 bg-slate-900/60">
            <TableRow>
              <TableHead className="text-xs uppercase text-slate-500">ID</TableHead>
              <TableHead className="text-xs uppercase text-slate-500">Name</TableHead>
              <TableHead className="text-xs uppercase text-slate-500">Created</TableHead>
              <TableHead className="text-right text-xs uppercase text-slate-500">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-slate-500">
                  No models yet. Add a Gemini model identifier above.
                </TableCell>
              </TableRow>
            ) : (
              models.map((m) => (
                <TableRow key={m.id} className="border-b border-slate-800/80 last:border-0">
                  <TableCell className="font-mono text-slate-400">{m.id}</TableCell>
                  <TableCell className="font-mono text-slate-200">{m.name}</TableCell>
                  <TableCell className="text-slate-500">{m.created_at}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="destructive"
                      size="xs"
                      onClick={() => { setDeleteTarget({ id: m.id, name: m.name }); setDeleteError(null); }}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete model &ldquo;{deleteTarget?.name}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. If this model is currently in use by an inbox, deletion will fail.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && (
            <Alert variant="destructive" className="mt-2">
              <AlertDescription>{deleteError}</AlertDescription>
            </Alert>
          )}
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
    </div>
  );
}
