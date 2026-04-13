"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type {
  FleetRow,
  FleetPage,
  TokenTrendPoint,
  ClassificationBreakdown,
  RunVolumePoint,
} from "@/lib/types";
import { toast } from "sonner";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  AreaChart,
  Area,
} from "recharts";

import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type TrendRange = 7 | 30;

const FLEET_PAGE_SIZE = 25;

/* ------------------------------------------------------------------ */
/*  Recharts tooltip – dark theme                                      */
/* ------------------------------------------------------------------ */

function ChartTooltipContent({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 shadow-lg">
      <p className="mb-1 font-medium text-slate-400">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value.toLocaleString()}
        </p>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Recharts shared prop constants (avoid recreating objects on render) */
/* ------------------------------------------------------------------ */

const TICK_STYLE = { fill: "#94a3b8", fontSize: 11 } as const;
const AXIS_LINE_STYLE = { stroke: "#334155" } as const;
const CURSOR_STROKE = { stroke: "#475569" } as const;
const CURSOR_FILL = { fill: "#1e293b" } as const;

/* ------------------------------------------------------------------ */
/*  Empty chart placeholder                                            */
/* ------------------------------------------------------------------ */

function ChartEmpty({ label }: { label: string }) {
  return (
    <div className="flex h-[200px] items-center justify-center text-sm text-slate-500">
      {label}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function FleetDashboardPage() {
  /* -- fleet state -------------------------------------------------- */
  const [rows, setRows] = useState<FleetRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  /* -- search / filter state --------------------------------------- */
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [searchInput, setSearchInput] = useState("");

  /* -- chart state ------------------------------------------------- */
  const [trendRange, setTrendRange] = useState<TrendRange>(7);
  const [tokenTrends, setTokenTrends] = useState<TokenTrendPoint[]>([]);
  const [classBreakdown, setClassBreakdown] = useState<ClassificationBreakdown>({});
  const [runVolume, setRunVolume] = useState<RunVolumePoint[]>([]);

  /* -- bulk selection state ---------------------------------------- */
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const selectedIdsRef = useRef<Set<number>>(new Set());
  /* Keep ref in sync so dialog callbacks always read current value */
  useEffect(() => {
    selectedIdsRef.current = selectedIds;
  }, [selectedIds]);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

  /* -- import dialog state ----------------------------------------- */
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);

  /* -- auto-refresh ------------------------------------------------ */
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ================================================================ */
  /*  Data loading                                                     */
  /* ================================================================ */

  const loadFleet = useCallback(async () => {
    setErr(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(FLEET_PAGE_SIZE),
      });
      if (search) params.set("search", search);
      if (activeFilter !== "all") params.set("is_active", activeFilter);

      const [f, g] = await Promise.all([
        apiGet<FleetPage>(`/api/inboxes?${params.toString()}`),
        apiGet<{ paused: boolean }>("/api/global-polling"),
      ]);
      setRows(f.items);
      setTotal(f.total);
      setPaused(g.paused);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load";
      setErr(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [page, search, activeFilter]);

  const loadStats = useCallback(async () => {
    try {
      const [t, c, v] = await Promise.all([
        apiGet<TokenTrendPoint[]>(
          `/api/stats/token-trends?days=${trendRange}`
        ),
        apiGet<ClassificationBreakdown>(
          `/api/stats/classification-breakdown?days=${trendRange}`
        ),
        apiGet<RunVolumePoint[]>(
          `/api/stats/run-volume?days=${trendRange}`
        ),
      ]);
      setTokenTrends(t);
      setClassBreakdown(c);
      setRunVolume(v);
    } catch {
      toast.error("Failed to load stats");
    }
  }, [trendRange]);

  const loadAll = useCallback(async () => {
    await Promise.all([loadFleet(), loadStats()]);
  }, [loadFleet, loadStats]);

  /* initial + page/filter change */
  useEffect(() => {
    loadAll();
  }, [loadAll]);

  /* auto-refresh every 30 s, paused when tab hidden */
  useEffect(() => {
    function startInterval() {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(() => {
        if (!document.hidden) loadAll();
      }, 30_000);
    }
    startInterval();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [loadAll]);

  /* ================================================================ */
  /*  Global pause toggle                                              */
  /* ================================================================ */

  async function toggleGlobalPause(next: boolean) {
    setErr(null);
    try {
      await apiSend("/api/global-polling", "PUT", { paused: next });
      setPaused(next);
      toast.success(next ? "Polling paused globally" : "Polling resumed globally");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Update failed";
      setErr(msg);
      toast.error(msg);
    }
  }

  /* ================================================================ */
  /*  Search handler (debounced)                                       */
  /* ================================================================ */

  function handleSearchChange(value: string) {
    setSearchInput(value);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      setSearch(value);
      setPage(1);
    }, 300);
  }

  function handleActiveFilterChange(value: string | null) {
    if (value !== null) {
      setActiveFilter(value);
      setPage(1);
    }
  }

  /* ================================================================ */
  /*  Bulk operations                                                  */
  /* ================================================================ */

  function toggleRow(id: number, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function toggleAll(checked: boolean) {
    if (checked) {
      setSelectedIds(new Set(rows.map((r) => r.id)));
    } else {
      setSelectedIds(new Set());
    }
  }

  async function handleBulkActivate() {
    if (selectedIds.size === 0) return;
    setBulkLoading(true);
    try {
      await apiSend("/api/inboxes/bulk-activate", "POST", {
        inbox_ids: Array.from(selectedIds),
        is_active: true,
      });
      toast.success(`Activated ${selectedIds.size} inbox(es)`);
      setSelectedIds(new Set());
      loadAll();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Bulk activate failed";
      toast.error(msg);
    } finally {
      setBulkLoading(false);
    }
  }

  async function handleBulkDelete() {
    const currentIds = selectedIdsRef.current;
    if (currentIds.size === 0) return;
    setBulkLoading(true);
    try {
      await apiSend("/api/inboxes/bulk-delete", "POST", {
        inbox_ids: Array.from(currentIds),
      });
      toast.success(`Deleted ${currentIds.size} inbox(es)`);
      setSelectedIds(new Set());
      setDeleteDialogOpen(false);
      loadAll();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Bulk delete failed";
      toast.error(msg);
    } finally {
      setBulkLoading(false);
    }
  }

  /* ================================================================ */
  /*  Export / Import                                                   */
  /* ================================================================ */

  async function handleExport() {
    try {
      const data = await apiGet<Record<string, unknown>>("/api/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "email-tagging-config.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Configuration exported");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Export failed";
      toast.error(msg);
    }
  }

  async function handleImport() {
    if (!importFile) return;
    setImportLoading(true);
    try {
      const text = await importFile.text();
      const data = JSON.parse(text);
      await apiSend("/api/import", "POST", data);
      toast.success("Configuration imported");
      setImportDialogOpen(false);
      setImportFile(null);
      loadAll();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Import failed";
      toast.error(msg);
    } finally {
      setImportLoading(false);
    }
  }

  /* ================================================================ */
  /*  Derived data                                                     */
  /* ================================================================ */

  const classBreakdownEntries = useMemo(
    () => Object.entries(classBreakdown),
    [classBreakdown]
  );
  const allChecked = useMemo(
    () => rows.length > 0 && rows.every((r) => selectedIds.has(r.id)),
    [rows, selectedIds]
  );
  const someChecked = useMemo(
    () => rows.some((r) => selectedIds.has(r.id)) && !allChecked,
    [rows, selectedIds, allChecked]
  );

  /* ================================================================ */
  /*  Render: loading                                                  */
  /* ================================================================ */

  if (loading) {
    return (
      <div className="w-full space-y-4">
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-4 w-64" />
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-[220px]" />
          <Skeleton className="h-[220px]" />
          <Skeleton className="h-[220px]" />
        </div>
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  /* ================================================================ */
  /*  Render: error                                                    */
  /* ================================================================ */

  if (err && rows.length === 0) {
    return (
      <div className="w-full space-y-4">
        <h1 className="text-2xl font-semibold text-white">Agents Dashboard</h1>
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{err}</AlertDescription>
        </Alert>
        <p className="text-sm text-muted-foreground">
          Start the API:{" "}
          <code className="rounded bg-slate-800 px-1">python run_api.py</code>
        </p>
      </div>
    );
  }

  /* ================================================================ */
  /*  Render: main                                                     */
  /* ================================================================ */

  return (
    <div className="w-full space-y-6">
      {/* ---- Header ---- */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-white">Agents Dashboard</h1>
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="outline" onClick={handleExport}>
            Export Config
          </Button>
          <Button variant="outline" onClick={() => setImportDialogOpen(true)}>
            Import Config
          </Button>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
            <Checkbox
              checked={paused}
              onCheckedChange={(checked) => toggleGlobalPause(!!checked)}
            />
            <span>Pause all polling (global kill-switch)</span>
          </label>
        </div>
      </div>

      {/* ---- Charts ---- */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* Token Spend */}
        <Card className="border-slate-800 bg-slate-950">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-slate-200">Token Spend</CardTitle>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant={trendRange === 7 ? "default" : "outline"}
                  className="h-7 px-2 text-xs"
                  onClick={() => setTrendRange(7)}
                >
                  7d
                </Button>
                <Button
                  size="sm"
                  variant={trendRange === 30 ? "default" : "outline"}
                  className="h-7 px-2 text-xs"
                  onClick={() => setTrendRange(30)}
                >
                  30d
                </Button>
              </div>
            </div>
            <CardDescription className="text-slate-500">
              Total tokens consumed per day
            </CardDescription>
          </CardHeader>
          <CardContent>
            {tokenTrends.length === 0 ? (
              <ChartEmpty label="No data yet" />
            ) : (
              <>
                <div aria-label="Token spend over time chart showing daily token usage" role="img">
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={tokenTrends}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#334155"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="date"
                        tick={TICK_STYLE}
                        axisLine={AXIS_LINE_STYLE}
                        tickLine={false}
                      />
                      <YAxis
                        tick={TICK_STYLE}
                        axisLine={AXIS_LINE_STYLE}
                        tickLine={false}
                        width={60}
                      />
                      <Tooltip
                        content={<ChartTooltipContent />}
                        cursor={CURSOR_STROKE}
                      />
                      <Line
                        type="monotone"
                        dataKey="total_tokens"
                        name="Tokens"
                        stroke="#38bdf8"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: "#38bdf8" }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="sr-only">
                  <table>
                    <caption>Token spend over time: daily total tokens consumed</caption>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Total Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tokenTrends.map((pt) => (
                        <tr key={pt.date}>
                          <td>{pt.date}</td>
                          <td>{pt.total_tokens.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Classification Breakdown */}
        <Card className="border-slate-800 bg-slate-950">
          <CardHeader>
            <CardTitle className="text-slate-200">Classifications</CardTitle>
            <CardDescription className="text-slate-500">
              Breakdown by category
            </CardDescription>
          </CardHeader>
          <CardContent>
            {classBreakdownEntries.length === 0 ? (
              <ChartEmpty label="No data yet" />
            ) : (
              <>
                <div aria-label="Classification breakdown chart showing counts per category" role="img">
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={classBreakdownEntries.map(([category, count]) => ({ category, count }))}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#334155"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="category"
                        tick={TICK_STYLE}
                        axisLine={AXIS_LINE_STYLE}
                        tickLine={false}
                        interval={0}
                        angle={-30}
                        textAnchor="end"
                        height={50}
                      />
                      <YAxis
                        tick={TICK_STYLE}
                        axisLine={AXIS_LINE_STYLE}
                        tickLine={false}
                        width={40}
                      />
                      <Tooltip
                        content={<ChartTooltipContent />}
                        cursor={CURSOR_FILL}
                      />
                      <Bar
                        dataKey="count"
                        name="Count"
                        fill="#818cf8"
                        radius={[4, 4, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="sr-only">
                  <table>
                    <caption>Classification breakdown by category</caption>
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {classBreakdownEntries.map(([category, count]) => (
                        <tr key={category}>
                          <td>{category}</td>
                          <td>{count.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Run Volume */}
        <Card className="border-slate-800 bg-slate-950">
          <CardHeader>
            <CardTitle className="text-slate-200">Run Volume</CardTitle>
            <CardDescription className="text-slate-500">
              Runs &amp; messages per day
            </CardDescription>
          </CardHeader>
          <CardContent>
            {runVolume.length === 0 ? (
              <ChartEmpty label="No data yet" />
            ) : (
              <>
                <div aria-label="Run volume chart showing daily runs and messages" role="img">
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={runVolume}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#334155"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="date"
                        tick={TICK_STYLE}
                        axisLine={AXIS_LINE_STYLE}
                        tickLine={false}
                      />
                      <YAxis
                        tick={TICK_STYLE}
                        axisLine={AXIS_LINE_STYLE}
                        tickLine={false}
                        width={40}
                      />
                      <Tooltip
                        content={<ChartTooltipContent />}
                        cursor={CURSOR_STROKE}
                      />
                      <Area
                        type="monotone"
                        dataKey="run_count"
                        name="Runs"
                        stroke="#34d399"
                        fill="#34d399"
                        fillOpacity={0.15}
                        strokeWidth={2}
                      />
                      <Area
                        type="monotone"
                        dataKey="message_count"
                        name="Messages"
                        stroke="#fbbf24"
                        fill="#fbbf24"
                        fillOpacity={0.1}
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <div className="sr-only">
                  <table>
                    <caption>Run volume over time: daily runs and messages</caption>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Runs</th>
                        <th>Messages</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runVolume.map((pt) => (
                        <tr key={pt.date}>
                          <td>{pt.date}</td>
                          <td>{pt.run_count.toLocaleString()}</td>
                          <td>{pt.message_count.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ---- Search / Filter bar ---- */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search inboxes…"
          value={searchInput}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="max-w-xs bg-slate-900/50"
        />
        <Select value={activeFilter} onValueChange={handleActiveFilterChange}>
          <SelectTrigger className="w-[140px] bg-slate-900/50">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="true">Active</SelectItem>
            <SelectItem value="false">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* ---- Bulk action bar ---- */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-slate-700 bg-slate-900/80 px-4 py-2">
          <span className="text-sm text-slate-300">
            {selectedIds.size} selected
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={bulkLoading}
            onClick={handleBulkActivate}
          >
            Activate
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={bulkLoading}
            onClick={() => setDeleteDialogOpen(true)}
          >
            Delete
          </Button>
          <AlertDialog
            open={deleteDialogOpen}
            onOpenChange={setDeleteDialogOpen}
          >
            <AlertDialogContent className="border-slate-700 bg-slate-950">
              <AlertDialogHeader>
                <AlertDialogTitle className="text-slate-200">
                  Confirm Delete
                </AlertDialogTitle>
                <AlertDialogDescription className="text-slate-400">
                  Are you sure you want to delete {selectedIds.size} inbox
                  {selectedIds.size > 1 ? "es" : ""}? This action cannot be
                  undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  disabled={bulkLoading}
                  onClick={handleBulkDelete}
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button
            size="sm"
            variant="ghost"
            className="text-slate-400"
            onClick={() => setSelectedIds(new Set())}
          >
            Clear selection
          </Button>
        </div>
      )}

      {/* ---- Fleet table ---- */}
      {total === 0 && !search && activeFilter === "all" ? (
        <p className="text-slate-400">No inbox mappings configured yet.</p>
      ) : total === 0 ? (
        <p className="text-slate-400">No inboxes match your filters.</p>
      ) : (
        <div className="rounded-lg border border-slate-800">
          <Table className="min-w-[900px]">
            <TableHeader>
              <TableRow className="bg-slate-900/50 hover:bg-slate-900/50">
                <TableHead className="w-[40px]">
                  {someChecked ? (
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked="mixed"
                      onClick={() => toggleAll(false)}
                      className="peer h-4 w-4 shrink-0 rounded-[4px] border border-primary ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground flex items-center justify-center bg-primary text-primary-foreground"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={3}
                        className="h-3 w-3"
                      >
                        <path d="M5 12h14" />
                      </svg>
                    </button>
                  ) : (
                    <Checkbox
                      checked={allChecked}
                      onCheckedChange={toggleAll}
                    />
                  )}
                </TableHead>
                <TableHead className="text-slate-400">Status</TableHead>
                <TableHead className="text-slate-400">Inbox Email</TableHead>
                <TableHead className="text-slate-400">Poll (min)</TableHead>
                <TableHead className="text-slate-400">Active</TableHead>
                <TableHead className="text-slate-400">Last Run</TableHead>
                <TableHead className="text-slate-400">Emails 24h</TableHead>
                <TableHead className="text-slate-400">Tokens 24h</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Checkbox
                      checked={selectedIds.has(r.id)}
                      onCheckedChange={(checked) => toggleRow(r.id, checked)}
                    />
                  </TableCell>
                  <TableCell>
                    {r.health_ok ? (
                      <Badge
                        className="bg-emerald-500/15 text-emerald-500 border-emerald-500/25"
                        title={
                          r.last_run_status
                            ? `Last run: ${r.last_run_status}`
                            : "No runs logged yet"
                        }
                      >
                        Healthy
                      </Badge>
                    ) : (
                      <Badge
                        variant="destructive"
                        title={
                          r.last_run_status
                            ? `Last run: ${r.last_run_status}`
                            : "No runs logged yet"
                        }
                      >
                        Unhealthy
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-slate-200">{r.mailbox_id}</TableCell>
                  <TableCell className="text-slate-300">
                    {r.polling_interval_minutes}
                  </TableCell>
                  <TableCell className="text-slate-300">
                    {r.is_active ? "yes" : "no"}
                  </TableCell>
                  <TableCell className="text-slate-400">
                    {r.last_run_at
                      ? new Date(r.last_run_at).toLocaleString()
                      : "—"}
                  </TableCell>
                  <TableCell className="text-slate-300">
                    {r.emails_processed_24h}
                  </TableCell>
                  <TableCell className="text-slate-300">{r.token_spend_24h}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* ---- Pagination ---- */}
      {total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400">
          <span>
            Showing {(page - 1) * FLEET_PAGE_SIZE + 1}–
            {Math.min(page * FLEET_PAGE_SIZE, total)} of {total}
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
              disabled={page * FLEET_PAGE_SIZE >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {/* ---- Import Config Dialog ---- */}
      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="border-slate-700 bg-slate-950">
          <DialogHeader>
            <DialogTitle className="text-slate-200">Import Configuration</DialogTitle>
            <DialogDescription className="text-slate-400">
              Select a JSON configuration file to import. This will overwrite existing settings.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="mb-1 block text-sm text-slate-400">Configuration file</Label>
              <Input
                type="file"
                accept=".json,application/json"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setImportFile(f);
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setImportDialogOpen(false);
                setImportFile(null);
              }}
            >
              Cancel
            </Button>
            <Button
              disabled={!importFile || importLoading}
              onClick={() => void handleImport()}
            >
              {importLoading ? "Importing…" : "Import"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
