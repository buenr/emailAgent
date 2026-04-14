"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type { SetRow, TaxRow, ClassificationSetDetail } from "@/lib/types";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";

export default function ClassificationsPage() {
  const [sets, setSets] = useState<SetRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [setName, setSetName] = useState("");
  const [categories, setCategories] = useState<TaxRow[]>([{ name: "", description: "" }]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadSets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await apiGet<SetRow[]>("/api/classification-sets");
      setSets(list);
      setSelectedId((prev) => {
        if (prev === "new") return "new";
        if (!list.length) return "new";
        if (prev !== null && list.some((s) => s.id === prev)) return prev;
        return list[0]!.id;
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load sets";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    setError(null);
    try {
      const d = await apiGet<ClassificationSetDetail>(`/api/classification-sets/${id}`);
      setSetName(d.name);
      const cats = d.categories?.length ? d.categories.map((c) => ({ name: c.name, description: c.description ?? "" })) : [{ name: "", description: "" }];
      setCategories(cats);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load detail";
      setError(msg);
      toast.error(msg);
    }
  }, []);

  useEffect(() => {
    loadSets();
  }, [loadSets]);

  useEffect(() => {
    if (selectedId === "new") {
      setSetName("");
      setCategories([{ name: "", description: "" }]);
    } else if (selectedId !== null) {
      loadDetail(selectedId);
    }
  }, [selectedId, loadDetail]);

  function normalizeRows(rows: TaxRow[]): TaxRow[] {
    return rows
      .map((r) => ({ name: r.name.trim(), description: (r.description ?? "").trim() }))
      .filter((r) => r.name.length > 0);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (selectedId === "new") {
        const { id } = await apiSend<{ id: number }>("/api/classification-sets", "POST", {
          name: setName,
        });
        const cleanCats = normalizeRows(categories);
        if (cleanCats.length > 0) {
          await apiSend(`/api/classification-sets/${id}/taxonomy`, "PUT", {
            categories: cleanCats,
          });
        }
        await loadSets();
        setSelectedId(id);
        toast.success("Classification set created");
      } else if (selectedId !== null) {
        await apiSend(`/api/classification-sets/${selectedId}`, "PUT", { name: setName });
        const cleanCats = normalizeRows(categories);
        await apiSend(`/api/classification-sets/${selectedId}/taxonomy`, "PUT", {
          categories: cleanCats,
        });
        await loadSets();
        await loadDetail(selectedId);
        toast.success("Changes saved");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed";
      setError(msg);
      toast.error(msg);
    }
  }

  async function onDeleteSet() {
    if (selectedId === null || selectedId === "new") return;
    setDeleteError(null);
    try {
      await apiSend(`/api/classification-sets/${selectedId}`, "DELETE");
      setDeleteDialogOpen(false);
      setSelectedId(null);
      await loadSets();
      toast.success("Classification set deleted");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      setDeleteError(msg);
      toast.error(msg);
    }
  }

  async function onSeedDefaults() {
    if (selectedId === null || selectedId === "new") return;
    setError(null);
    try {
      await apiSend(`/api/classification-sets/${selectedId}/seed-defaults`, "POST");
      await loadDetail(selectedId);
      toast.success("Defaults seeded successfully");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Seed failed";
      setError(msg);
      toast.error(msg);
    }
  }

  function addCategoryRow() {
    setCategories((c) => [...c, { name: "", description: "" }]);
  }
  function removeCategoryRow(i: number) {
    setCategories((c) => c.filter((_, j) => j !== i));
  }

  if (loading) {
    return (
      <div className="w-full space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="w-full">
      <h1 className="mb-8 text-2xl font-semibold text-white">Classification Sets</h1>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="mb-6">
        <Label id="classification-set-select-label" className="mb-1 block text-sm text-slate-400">Select Set</Label>
        <div className="flex items-center gap-3">
          <Select
            value={selectedId === "new" ? "new" : selectedId !== null ? String(selectedId) : ""}
            onValueChange={(val) => {
              setSelectedId(val === "new" ? "new" : val ? Number(val) : null);
            }}
          >
            <SelectTrigger className="w-full max-w-md" aria-labelledby="classification-set-select-label">
              <SelectValue placeholder="Select a set">
                {selectedId === "new" ? "+ Create New Set" : sets.find(s => s.id === selectedId)?.name}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {sets.map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {s.name}
                </SelectItem>
              ))}
              <SelectItem value="new">+ Create New Set</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mb-8 rounded-lg border border-slate-800 bg-slate-900/40 p-6">
        <h2 className="mb-4 text-lg font-medium text-white">
          {selectedId === "new" ? "Create New Set" : "Edit Set"}
        </h2>
        <div className="space-y-6">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 max-w-md">
              <Label htmlFor="classification-set-name" className="mb-1 block text-sm text-slate-400">Set Name</Label>
              <Input
                id="classification-set-name"
                value={setName}
                onChange={(e) => setSetName(e.target.value)}
                placeholder="e.g. Default Classification Set"
              />
            </div>
            {selectedId !== "new" && (
              <>
                <Button
                  variant="destructive"
                  size="default"
                  onClick={() => { setDeleteDialogOpen(true); setDeleteError(null); }}
                >
                  Delete
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={onSeedDefaults}
                  className="border-amber-800/60 bg-amber-950/30 text-amber-100 hover:bg-amber-950/50"
                >
                  Seed Defaults
                </Button>
              </>
            )}
          </div>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-md font-medium text-white">Categories</h3>
              <Button
                type="button"
                variant="link"
                size="sm"
                onClick={addCategoryRow}
                className="text-blue-400 hover:text-blue-300"
              >
                + Add row
              </Button>
            </div>
            <div className="rounded-lg border border-slate-800">
              <Table>
                <TableHeader>
                  <TableRow className="border-b border-slate-800 bg-slate-900/50 text-slate-400">
                    <TableHead className="w-1/4">Name</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="w-20 text-right" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {categories.map((row, i) => (
                    <TableRow key={row.name || `new-row-${i}`} className="border-b border-slate-800/80">
                      <TableCell className="p-2 align-top">
                        <Input
                          aria-label={`Category name, row ${i + 1}`}
                          value={row.name}
                          onChange={(e) => {
                            const v = e.target.value;
                            setCategories((c) =>
                              c.map((x, j) => (j === i ? { ...x, name: v } : x))
                            );
                          }}
                        />
                      </TableCell>
                      <TableCell className="p-2 align-top">
                        <Textarea
                          aria-label={`Category description, row ${i + 1}`}
                          className="min-h-[80px] resize-y"
                          value={row.description}
                          onChange={(e) => {
                            const v = e.target.value;
                            setCategories((c) =>
                              c.map((x, j) => (j === i ? { ...x, description: v } : x))
                            );
                          }}
                        />
                      </TableCell>
                      <TableCell className="p-2 align-top text-right">
                        <Button
                          type="button"
                          variant="link"
                          size="xs"
                          onClick={() => removeCategoryRow(i)}
                          className="text-xs text-red-400 hover:text-red-300"
                        >
                          Remove
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>

          <div className="flex justify-end">
            <Button type="button" onClick={onSave}>
              {selectedId === "new" ? "Create Set" : "Save Changes"}
            </Button>
          </div>
        </div>
      </div>

      <AlertDialog
        open={deleteDialogOpen}
        onOpenChange={(open) => { if (!open) setDeleteDialogOpen(false); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete classification set?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The set and all its categories will be permanently deleted.
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
              onClick={() => void onDeleteSet()}
            >
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
