"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "@/lib/api";
import type {
  InboxPick,
  ClassificationRow,
  ClassificationsResponse,
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

const PAGE_SIZE = 25;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ResultsPage() {
  /* -- inbox selector state ---------------------------------------- */
  const [inboxes, setInboxes] = useState<InboxPick[]>([]);
  const [selectedInboxId, setSelectedInboxId] = useState<number | null>(null);
  const [inboxesLoading, setInboxesLoading] = useState(true);

  /* -- classifications state --------------------------------------- */
  const [rows, setRows] = useState<ClassificationRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [dataLoading, setDataLoading] = useState(false);

  /* -- filter state ------------------------------------------------ */
  const [categoryFilter, setCategoryFilter] = useState<string>("__all__");
  const [distinctCategories, setDistinctCategories] = useState<string[]>([]);
  const [sinceDate, setSinceDate] = useState("");
  const [untilDate, setUntilDate] = useState("");

  /* -- AbortController ref for classifications --------------------- */
  const abortRef = useRef<AbortController | null>(null);

  /* ================================================================ */
  /*  Load inboxes list                                                */
  /* ================================================================ */

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiGet<{ items: InboxPick[]; total: number }>(
          "/api/inboxes?page=1&page_size=200"
        );
        if (!cancelled) {
          setInboxes(res.items);
          if (res.items.length > 0) {
            setSelectedInboxId(res.items[0]!.id);
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to load inboxes";
        if (!cancelled) toast.error(msg);
      } finally {
        if (!cancelled) setInboxesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ================================================================ */
  /*  Load categories (separate lightweight call)                      */
  /* ================================================================ */

  useEffect(() => {
    if (selectedInboxId === null) return;
    let cancelled = false;
    (async () => {
      try {
        const cats = await apiGet<string[]>(
          `/api/inboxes/${selectedInboxId}/classifications/categories`
        );
        if (!cancelled) {
          setDistinctCategories(cats);
        }
      } catch {
        // Non-critical: categories dropdown may be empty
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedInboxId]);

  /* ================================================================ */
  /*  Load classifications (server-side pagination)                     */
  /* ================================================================ */

  const loadClassifications = useCallback(async () => {
    if (selectedInboxId === null) return;

    // Abort any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setDataLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("page_size", String(PAGE_SIZE));
      if (categoryFilter !== "__all__") params.set("category", categoryFilter);
      if (sinceDate) params.set("since", sinceDate);
      if (untilDate) params.set("until", untilDate);

      const path = `/api/inboxes/${selectedInboxId}/classifications?${params.toString()}`;
      const res = await apiGet<ClassificationsResponse>(path, {
        signal: controller.signal,
      });
      setRows(res.items);
      setTotal(res.total);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      const msg = e instanceof Error ? e.message : "Failed to load classifications";
      toast.error(msg);
      setRows([]);
      setTotal(0);
    } finally {
      if (!controller.signal.aborted) {
        setDataLoading(false);
      }
    }
  }, [selectedInboxId, page, categoryFilter, sinceDate, untilDate]);

  useEffect(() => {
    loadClassifications();
    return () => {
      abortRef.current?.abort();
    };
  }, [loadClassifications]);

  // Reset page when filters change (but not when page itself changes)
  useEffect(() => {
    setPage(1);
  }, [selectedInboxId, categoryFilter, sinceDate, untilDate]);

  /* ================================================================ */
  /*  Helpers                                                          */
  /* ================================================================ */

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  /* ================================================================ */
  /*  Render: loading inboxes                                          */
  /* ================================================================ */

  if (inboxesLoading) {
    return (
      <div className="w-full space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  /* ================================================================ */
  /*  Render: no inboxes                                               */
  /* ================================================================ */

  if (inboxes.length === 0) {
    return (
      <div className="w-full">
        <h1 className="mb-8 text-2xl font-semibold text-white">Results</h1>
        <Alert>
          <AlertDescription className="text-amber-200">
            No inbox mappings configured yet. Create one on the Inboxes page first.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  /* ================================================================ */
  /*  Render: main                                                     */
  /* ================================================================ */

  return (
    <div className="w-full space-y-6">
      <h1 className="text-2xl font-semibold text-white">Classification Results</h1>

      {/* ---- Inbox selector ---- */}
      <div>
        <Label className="mb-1 block text-sm text-slate-400">Inbox</Label>
        <Select
          value={selectedInboxId !== null ? String(selectedInboxId) : ""}
          onValueChange={(val) => {
            if (val !== null) {
              setSelectedInboxId(Number(val));
              setCategoryFilter("__all__");
              setSinceDate("");
              setUntilDate("");
            }
          }}
        >
          <SelectTrigger className="w-full max-w-md">
            <SelectValue placeholder="Select inbox" />
          </SelectTrigger>
          <SelectContent>
            {inboxes.map((ib) => (
              <SelectItem key={ib.id} value={String(ib.id)}>
                {ib.mailbox_id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* ---- Filters ---- */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <Label className="mb-1 block text-sm text-slate-400">Category</Label>
          <Select
            value={categoryFilter}
            onValueChange={(val) => {
              if (val !== null) setCategoryFilter(val);
            }}
          >
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="All categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All categories</SelectItem>
              {distinctCategories.map((cat) => (
                <SelectItem key={cat} value={cat}>
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1 block text-sm text-slate-400">Since</Label>
          <Input
            type="date"
            value={sinceDate}
            onChange={(e) => setSinceDate(e.target.value)}
            className="w-[160px]"
          />
        </div>
        <div>
          <Label className="mb-1 block text-sm text-slate-400">Until</Label>
          <Input
            type="date"
            value={untilDate}
            onChange={(e) => setUntilDate(e.target.value)}
            className="w-[160px]"
          />
        </div>
        {(categoryFilter !== "__all__" || sinceDate || untilDate) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setCategoryFilter("__all__");
              setSinceDate("");
              setUntilDate("");
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      {/* ---- Results table ---- */}
      {dataLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : rows.length === 0 ? (
        <Alert>
          <AlertDescription className="text-slate-400">
            No classification results found
            {categoryFilter !== "__all__" || sinceDate || untilDate
              ? " for the current filters."
              : " for this inbox."}
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <Table className="min-w-[640px]">
              <TableHeader>
                <TableRow className="bg-slate-900/50 hover:bg-slate-900/50">
                  <TableHead className="text-slate-400">Subject</TableHead>
                  <TableHead className="text-slate-400">Sender</TableHead>
                  <TableHead className="text-slate-400">Category</TableHead>
                  <TableHead className="text-slate-400">Received At</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.id} className="hover:bg-slate-900/40">
                    <TableCell className="max-w-[300px] truncate text-slate-200">
                      {r.subject || "—"}
                    </TableCell>
                    <TableCell className="text-slate-300">{r.sender || "—"}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center rounded-md bg-indigo-500/15 px-2 py-0.5 text-xs font-medium text-indigo-300">
                        {r.category}
                      </span>
                    </TableCell>
                    <TableCell className="text-slate-400">
                      {r.received_at
                        ? new Date(r.received_at).toLocaleString()
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* ---- Pagination ---- */}
          {total > PAGE_SIZE && (
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400">
              <span>
                Showing {(page - 1) * PAGE_SIZE + 1}–
                {Math.min(page * PAGE_SIZE, total)} of {total}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
