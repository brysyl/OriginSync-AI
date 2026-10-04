"use client";

import { AgGridReact } from "ag-grid-react";
import { colorSchemeDark, themeQuartz, type ColDef } from "ag-grid-community";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const CACHE_KEY = "originsync.telemetry.v1";
const REFRESH_MS = 15_000;
const gridTheme = themeQuartz.withPart(colorSchemeDark).withParams({
  accentColor: "#43d9a3",
  backgroundColor: "#101923",
  borderColor: "#24313d",
  browserColorScheme: "dark",
  chromeBackgroundColor: "#141f2a",
  fontFamily: "Arial, Helvetica, sans-serif",
  fontSize: 13,
  foregroundColor: "#dce5eb",
  oddRowBackgroundColor: "#0d151e",
  rowHoverColor: "#17242e",
  selectedRowBackgroundColor: "#15382f",
});

interface TelemetryCase {
  trade_reference: string;
  goods: string;
  route: string;
  hs_code: string | null;
  cif_value: number;
  duty_exemption: number;
  rigs_score: number | null;
  settlement: string;
  status: string;
}

interface TelemetryMetrics {
  trade_cases_count: number;
  preferential_origin: number;
  active_settlements: number;
  avg_rigs: number;
}

function apiBaseUrl(): string | null {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!configured) return null;
  if (configured === "same-origin") return "";
  return /^https?:\/\//i.test(configured) ? configured.replace(/\/+$/, "") : `https://${configured}`;
}

function currency(value: number | string, code: string | null): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  if (!code) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(amount);
  }
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: code,
    maximumFractionDigits: 2,
  }).format(amount);
}

function readCachedRows(): { rows: TelemetryCase[]; cachedAt: string | null } {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return { rows: [], cachedAt: null };
    const value: unknown = JSON.parse(raw);
    if (isRecord(value) && Array.isArray(value.rows) && typeof value.cachedAt === "string") {
      const rows = value.rows.filter(isTelemetryCase);
      if (rows.length === value.rows.length && Number.isFinite(Date.parse(value.cachedAt))) {
        return { rows, cachedAt: value.cachedAt };
      }
    }
  } catch {
    return { rows: [], cachedAt: null };
  }
  return { rows: [], cachedAt: null };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isTelemetryCase(value: unknown): value is TelemetryCase {
  if (!isRecord(value)) return false;
  return (
    typeof value.trade_reference === "string" &&
    typeof value.goods === "string" &&
    typeof value.route === "string" &&
    (value.hs_code === null || typeof value.hs_code === "string") &&
    typeof value.cif_value === "number" &&
    Number.isFinite(value.cif_value) &&
    typeof value.duty_exemption === "number" &&
    Number.isFinite(value.duty_exemption) &&
    (value.rigs_score === null ||
      (typeof value.rigs_score === "number" && Number.isFinite(value.rigs_score))) &&
    typeof value.settlement === "string" &&
    typeof value.status === "string"
  );
}

function metricsFromCases(cases: TelemetryCase[]): TelemetryMetrics {
  const rigsScores = cases.flatMap((trade) =>
    trade.rigs_score === null ? [] : [trade.rigs_score],
  );
  return {
    trade_cases_count: cases.length,
    preferential_origin: cases.filter((trade) => trade.duty_exemption > 0).length,
    active_settlements: cases.filter((trade) =>
      ["PENDING", "PROCESSING"].includes(trade.settlement.toUpperCase()),
    ).length,
    avg_rigs: rigsScores.length
      ? rigsScores.reduce((sum, score) => sum + score, 0) / rigsScores.length
      : 0,
  };
}

function unwrapTelemetry(value: unknown): {
  cases: unknown[];
  metrics: Partial<TelemetryMetrics>;
} {
  const body = isRecord(value) && "data" in value ? value.data : value;
  const metricsSource = isRecord(body) ? body : isRecord(value) ? value : {};
  const cases = Array.isArray(body)
    ? body
    : isRecord(body) && Array.isArray(body.trade_cases)
      ? body.trade_cases
      : null;
  if (cases === null) {
    throw new Error("The API returned an invalid telemetry response.");
  }

  return {
    cases,
    metrics: {
      trade_cases_count:
        typeof metricsSource.trade_cases_count === "number"
          ? metricsSource.trade_cases_count
          : undefined,
      preferential_origin:
        typeof metricsSource.preferential_origin === "number"
          ? metricsSource.preferential_origin
          : undefined,
      active_settlements:
        typeof metricsSource.active_settlements === "number"
          ? metricsSource.active_settlements
          : undefined,
      avg_rigs:
        typeof metricsSource.avg_rigs === "number" ? metricsSource.avg_rigs : undefined,
    },
  };
}

export function ControlRoom() {
  const apiUrl = useMemo(() => apiBaseUrl(), []);
  const [initialCache] = useState(readCachedRows);
  const [rows, setRows] = useState<TelemetryCase[]>(initialCache.rows);
  const [metrics, setMetrics] = useState<TelemetryMetrics>(() =>
    metricsFromCases(initialCache.rows),
  );
  const [cachedAt, setCachedAt] = useState<string | null>(initialCache.cachedAt);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [loading, setLoading] = useState(initialCache.rows.length === 0 && apiUrl !== null);
  const gridRef = useRef<AgGridReact<TelemetryCase>>(null);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js").catch(() => {
        setError("Offline shell could not be installed. Live API access is still available.");
      });
    }
  }, []);

  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (apiUrl === null) return;
    try {
      const response = await fetch(`${apiUrl}/api/v1/telemetry`, {
        cache: "no-store",
        signal,
      });
      const result: unknown = await response.json();
      if (!response.ok) {
        console.error("Trade telemetry API error:", { status: response.status, body: result });
        const errorBody =
          isRecord(result) && isRecord(result.error) ? result.error.message : undefined;
        throw new Error(
          typeof errorBody === "string" ? errorBody : `API returned ${response.status}`,
        );
      }
      const telemetry = unwrapTelemetry(result);
      if (!telemetry.cases.every(isTelemetryCase)) {
        throw new Error("The API returned an invalid telemetry response.");
      }
      const tradeCases = telemetry.cases;
      const calculatedMetrics = metricsFromCases(tradeCases);
      const nextMetrics: TelemetryMetrics = {
        trade_cases_count:
          telemetry.metrics.trade_cases_count ?? calculatedMetrics.trade_cases_count,
        preferential_origin:
          telemetry.metrics.preferential_origin ?? calculatedMetrics.preferential_origin,
        active_settlements:
          telemetry.metrics.active_settlements ?? calculatedMetrics.active_settlements,
        avg_rigs: telemetry.metrics.avg_rigs ?? calculatedMetrics.avg_rigs,
      };
      const timestamp = new Date().toISOString();
      setRows(tradeCases);
      setMetrics(nextMetrics);
      setLastUpdated(timestamp);
      setError(null);
      setLoading(false);
      if (tradeCases.length > 0) {
        setCachedAt(timestamp);
        window.localStorage.setItem(CACHE_KEY, JSON.stringify({ rows: tradeCases, cachedAt: timestamp }));
      }
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      console.warn("Trade telemetry refresh failed:", caught);
      setError(caught instanceof Error ? caught.message : "Telemetry refresh failed.");
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    if (apiUrl === null) return;
    const controller = new AbortController();
    const initialLoad = window.setTimeout(() => void refresh(controller.signal), 0);
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => {
      window.clearTimeout(initialLoad);
      controller.abort();
      window.clearInterval(timer);
    };
  }, [apiUrl, refresh]);

  const columns = useMemo<ColDef<TelemetryCase>[]>(
    () => [
      {
        field: "trade_reference",
        headerName: "Trade reference",
        minWidth: 150,
        valueFormatter: ({ value }) => value || "—",
      },
      {
        field: "goods",
        headerName: "Goods",
        minWidth: 230,
        flex: 1.5,
        tooltipField: "goods",
      },
      { field: "route", headerName: "Route", minWidth: 120 },
      {
        field: "hs_code",
        headerName: "HS code",
        minWidth: 105,
        valueFormatter: ({ value }) => value || "Pending",
      },
      {
        field: "cif_value",
        headerName: "CIF value",
        minWidth: 135,
        type: "rightAligned",
        valueFormatter: ({ value }) => currency(value, null),
      },
      {
        field: "duty_exemption",
        headerName: "Duty exemption",
        minWidth: 145,
        type: "rightAligned",
        valueFormatter: ({ value }) => currency(value, null),
      },
      {
        field: "rigs_score",
        headerName: "RIGS score",
        minWidth: 115,
        type: "rightAligned",
        valueFormatter: ({ value }) =>
          typeof value === "number" ? value.toFixed(1) : "—",
      },
      { field: "settlement", headerName: "Settlement", minWidth: 145 },
      { field: "status", headerName: "Case status", minWidth: 155 },
    ],
    [],
  );

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[1600px] flex-col gap-7 px-5 py-8 sm:px-8 lg:px-12">
      <header className="flex flex-wrap items-center justify-between gap-5 border-b border-line pb-6">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl border border-mint/30 bg-mint/10 text-lg font-bold text-mint">
            O
          </div>
          <div>
            <p className="text-sm font-semibold tracking-[0.18em] text-slate-100">ORIGINSYNC</p>
            <p className="mt-1 text-xs text-slate-500">TRADE CONTROL ROOM</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className={`h-2 w-2 rounded-full ${online ? "bg-mint" : "bg-amber-400"}`} />
          <span className="text-slate-300">{online ? "Network online" : "Offline mode"}</span>
        </div>
      </header>

      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-mint">Operations</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Trade telemetry</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
            Origin decisions, CIF exposure, trust signals, and settlement activity across your trade corridor.
          </p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <p>{lastUpdated ? `Live sync ${new Date(lastUpdated).toLocaleTimeString()}` : "Waiting for live sync"}</p>
          {cachedAt && <p className="mt-1">Offline snapshot {new Date(cachedAt).toLocaleString()}</p>}
        </div>
      </section>

      {apiUrl === null ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-sm text-amber-100">
          Configure NEXT_PUBLIC_API_BASE_URL to connect this control room.
        </div>
      ) : (
        <>
          {error && (
            <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              {error} {rows.length > 0 && "Showing the last saved snapshot."}
            </div>
          )}
          <section aria-label="Trade summary" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Trade cases" value={metrics.trade_cases_count.toLocaleString()} detail="Current snapshot" />
            <Metric label="Preferential origin" value={metrics.preferential_origin.toLocaleString()} detail="Verified under active rules" />
            <Metric label="Active settlements" value={metrics.active_settlements.toLocaleString()} detail="Pending or processing" />
            <Metric label="Average RIGS" value={metrics.avg_rigs.toFixed(1)} detail="Scored cases only" />
          </section>
          <section className="rounded-2xl border border-line bg-panel/80 p-3 sm:p-4">
            <div className="flex flex-wrap items-center justify-between gap-3 px-1 pb-4 pt-1">
              <div>
                <h2 className="text-sm font-semibold text-slate-100">Trade ledger</h2>
                <p className="mt-1 text-xs text-slate-500">Refreshes every 15 seconds · cached for offline review</p>
              </div>
              <button
                className="rounded-lg border border-line px-3 py-2 text-xs font-medium text-slate-200 hover:border-mint/60"
                onClick={() => gridRef.current?.api.exportDataAsCsv({ fileName: "originsync-trades.csv" })}
                type="button"
              >
                Export CSV
              </button>
            </div>
            <div className="ag-grid-shell h-[520px] w-full">
              <AgGridReact<TelemetryCase>
                columnDefs={columns}
                defaultColDef={{ sortable: true, resizable: true, filter: true }}
                loading={loading}
                onGridReady={(event) => event.api.sizeColumnsToFit()}
                ref={gridRef}
                rowData={rows}
                rowHeight={48}
                suppressCellFocus
                theme={gridTheme}
              />
            </div>
            {rows.length === 0 && !loading && (
              <p className="px-2 py-5 text-center text-sm text-slate-500">
                No trade cases are available for this organization yet.
              </p>
            )}
          </section>
        </>
      )}

      <footer className="mt-auto flex flex-wrap justify-between gap-3 border-t border-line pt-5 text-[11px] text-slate-600">
        <span>OriginSync AI · Organization-scoped telemetry</span>
        <span>Compliance decisions require active, sourced rules and documented evidence.</span>
      </footer>
    </main>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="rounded-xl border border-line bg-panel p-4">
      <p className="text-xs font-medium text-slate-400">{label}</p>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-white">{value}</p>
      <p className="mt-2 text-[11px] text-slate-500">{detail}</p>
    </article>
  );
}
