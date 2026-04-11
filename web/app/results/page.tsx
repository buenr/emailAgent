"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
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

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type InboxSummary = { id: number; mailbox_id: string };

type ClassificationRow = {
  id: number;
  run_log_id: number;
  email_id: string;
  subject: string;
  sender: string;
  category: string;
  received_at: string;
  created_at: string;
};

type ClassificationsResponse = {
  items: ClassificationRow[];
  total: number;
};

const PAGE_SIZE = 25;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ResultsPage() {
  /* -- inbox selector state ---------------------------------------- */
  const [inboxes, setInboxes] = useState<InboxSummary[]>([]);
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

  /* ================================================================ */
  /*  Load inboxes list                                                */
  /* ================================================================ */

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiGet<{ items: InboxSummary[]; total: number }>(
          "/api/inboxes?page=1&page_size=200"
        );
        if (!cancelled) {
          setInboxes(res.items);
          if (res.items.length > 0) {
            setSelectedInboxId(res.items[0].id);
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
  /*  Load classifications                                             */
  /* ================================================================ */

  const loadClassifications = useCallback(async () => {
    if (selectedInboxId === null) return;
    setDataLoading(true);
    try {
      const params = new URLSearchParams();
      if (categoryFilter !== "__all__") params.set("category", categoryFilter);
      if (sinceDate) params.set("since", sinceDate);
      if (untilDate) params.set("until", untilDate);

      const qs = params.toString();
      const path = `/api/inboxes/${selectedInboxId}/classifications${qs ? `?${qs}` : ""}`;
      const res = await apiGet<ClassificationsResponse>(path);
      setRows(res.items);
      setTotal(res.total);

      // Derive distinct categories from data (only when no category filter applied)
      if (categoryFilter === "__all__") {
        const cats = Array.from(
          new Set(res.items.map((r) => r.category).filter(Boolean))
        ).sort();
        setDistinctCategories(cats);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load classifications";
      toast.error(msg);
      setRows([]);
      setTotal(0);
    } finally {
      setDataLoading(false);
    }
  }, [selectedInboxId, categoryFilter, sinceDate, untilDate]);

  useEffect(() => {
    loadClassifications();
  }, [loadClassifications]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [selectedInboxId, categoryFilter, sinceDate, untilDate]);

  /* ================================================================ */
  /*  Helpers                                                          */
  /* ================================================================ */

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pagedRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

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
                {pagedRows.map((r) => (
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
