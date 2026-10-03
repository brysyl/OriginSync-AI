"use client";

import { AgGridReact } from "ag-grid-react";
import { colorSchemeDark, themeQuartz, type ColDef } from "ag-grid-community";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { FormEvent } from "react";
import type { Session } from "@supabase/supabase-js";

import { getSupabaseClient, subscribeToSupabaseConfig } from "@/lib/supabase";
import type { TradePage, TradeRecord } from "@/lib/types";

const CACHE_KEY = "originsync.telemetry.v1";
const ORGANIZATION_KEY = "originsync.organization.v1";
const REFRESH_MS = 15_000;
const TRADE_STATUSES = [
  "received",
  "processing",
  "verified",
  "review_required",
  "rejected",
  "settlement_pending",
  "settled",
  "settlement_failed",
] as const;
const SETTLEMENT_STATUSES = ["not_eligible", "pending", "processing", "completed", "failed"] as const;
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

function readCachedRows(): { rows: TradeRecord[]; cachedAt: string | null } {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return { rows: [], cachedAt: null };
    const value: unknown = JSON.parse(raw);
    if (isRecord(value) && Array.isArray(value.rows) && typeof value.cachedAt === "string") {
      const rows = value.rows.filter(isTradeRecord);
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

function isOneOf<const Values extends readonly string[]>(
  value: unknown,
  values: Values,
): value is Values[number] {
  return typeof value === "string" && values.includes(value);
}

function isTradeRecord(value: unknown): value is TradeRecord {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    isOneOf(value.status, TRADE_STATUSES) &&
    typeof value.goods_description === "string" &&
    (value.external_reference === null || typeof value.external_reference === "string") &&
    (value.hs_code === null || typeof value.hs_code === "string") &&
    (value.hs_code_confidence === null || typeof value.hs_code_confidence === "number") &&
    typeof value.origin_country === "string" &&
    typeof value.destination_country === "string" &&
    (typeof value.cif_amount === "string" || typeof value.cif_amount === "number") &&
    (value.currency === null || typeof value.currency === "string") &&
    (value.origin_eligible === null || typeof value.origin_eligible === "boolean") &&
    (value.preferential_margin === undefined ||
      value.preferential_margin === null ||
      typeof value.preferential_margin === "number" ||
      typeof value.preferential_margin === "string") &&
    isRecord(value.origin_decision) &&
    (value.rigs_score === null || typeof value.rigs_score === "number") &&
    isRecord(value.rigs_components) &&
    isOneOf(value.settlement_status, SETTLEMENT_STATUSES) &&
    (value.paypal_payout_batch_id === null || typeof value.paypal_payout_batch_id === "string") &&
    (value.error_code === null || typeof value.error_code === "string") &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string" &&
    Number.isFinite(Date.parse(value.created_at)) &&
    Number.isFinite(Date.parse(value.updated_at))
  );
}

export function ControlRoom() {
  const [session, setSession] = useState<Session | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState(
    () => window.localStorage.getItem(ORGANIZATION_KEY) ?? "",
  );
  const [initialCache] = useState(readCachedRows);
  const [rows, setRows] = useState<TradeRecord[]>(initialCache.rows);
  const [cachedAt, setCachedAt] = useState<string | null>(initialCache.cachedAt);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [loading, setLoading] = useState(initialCache.rows.length === 0);
  const gridRef = useRef<AgGridReact<TradeRecord>>(null);
  const supabase = useSyncExternalStore(
    subscribeToSupabaseConfig,
    getSupabaseClient,
    () => null,
  );
  const apiUrl = useMemo(() => apiBaseUrl(), []);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js").catch(() => {
        setError("Offline shell could not be installed. Live API access is still available.");
      });
    }
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });
    return () => data.subscription.unsubscribe();
  }, [supabase]);

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
    if (!supabase || !session || !organizationId || apiUrl === null) return;
    try {
      const { data, error: sessionError } = await supabase.auth.getSession();
      if (sessionError) throw sessionError;
      const accessToken = data.session?.access_token;
      if (!accessToken) throw new Error("Your session has expired. Sign in again.");
      const response = await fetch(`${apiUrl}/api/v1/trades?limit=100`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "X-Organization-ID": organizationId,
        },
        cache: "no-store",
        signal,
      });
      const result = (await response.json()) as TradePage | { error?: { message?: string } };
      if (!response.ok) {
        console.error("Trade telemetry API error:", { status: response.status, body: result });
        throw new Error(
          "error" in result ? result.error?.message ?? `API returned ${response.status}` : `API returned ${response.status}`,
        );
      }
      if (
        !("items" in result) ||
        !Array.isArray(result.items) ||
        !result.items.every(isTradeRecord)
      ) {
        throw new Error("The API returned an invalid telemetry response.");
      }
      const timestamp = new Date().toISOString();
      setRows(result.items);
      setCachedAt(timestamp);
      setLastUpdated(timestamp);
      setError(null);
      setLoading(false);
      window.localStorage.setItem(CACHE_KEY, JSON.stringify({ rows: result.items, cachedAt: timestamp }));
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      console.warn("Trade telemetry refresh failed:", caught);
      setError(caught instanceof Error ? caught.message : "Telemetry refresh failed.");
      setLoading(false);
    }
  }, [apiUrl, organizationId, session, supabase]);

  useEffect(() => {
    if (!session || !organizationId || apiUrl === null) return;
    const controller = new AbortController();
    const initialLoad = window.setTimeout(() => void refresh(controller.signal), 0);
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => {
      window.clearTimeout(initialLoad);
      controller.abort();
      window.clearInterval(timer);
    };
  }, [apiUrl, organizationId, refresh, session]);

  const signIn = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setAuthError(null);
    const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (signInError) {
      setAuthError(signInError.message);
      return;
    }
    setSession(data.session);
    setPassword("");
  };

  const saveOrganization = (value: string) => {
    setOrganizationId(value.trim());
    if (value.trim()) window.localStorage.setItem(ORGANIZATION_KEY, value.trim());
    else window.localStorage.removeItem(ORGANIZATION_KEY);
  };

  const signOut = async () => {
    if (!supabase) return;
    const { error: signOutError } = await supabase.auth.signOut();
    if (signOutError) setAuthError(signOutError.message);
    else setSession(null);
  };

  const columns = useMemo<ColDef<TradeRecord>[]>(
    () => [
      {
        field: "external_reference",
        headerName: "Trade reference",
        minWidth: 150,
        valueFormatter: ({ value }) => value || "—",
      },
      {
        field: "goods_description",
        headerName: "Goods",
        minWidth: 230,
        flex: 1.5,
        tooltipField: "goods_description",
      },
      {
        headerName: "Route",
        minWidth: 100,
        valueGetter: ({ data }) =>
          data ? `${data.origin_country} → ${data.destination_country}` : "—",
      },
      {
        field: "hs_code",
        headerName: "HS code",
        minWidth: 105,
        valueFormatter: ({ value }) => value || "Pending",
      },
      {
        field: "cif_amount",
        headerName: "CIF value",
        minWidth: 135,
        type: "rightAligned",
        valueFormatter: ({ data, value }) =>
          data ? currency(value, data.currency) : "—",
      },
      {
        field: "origin_eligible",
        headerName: "Duty exemption",
        minWidth: 145,
        valueFormatter: ({ value }) =>
          value === true ? "Preferential" : value === false ? "Not verified" : "In review",
      },
      {
        field: "rigs_score",
        headerName: "RIGS score",
        minWidth: 115,
        type: "rightAligned",
        valueFormatter: ({ value }) =>
          typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—",
      },
      {
        field: "settlement_status",
        headerName: "Settlement",
        minWidth: 145,
        valueFormatter: ({ value }) => String(value ?? "unknown").replaceAll("_", " "),
      },
      {
        field: "status",
        headerName: "Case status",
        minWidth: 155,
        valueFormatter: ({ value }) => String(value ?? "unknown").replaceAll("_", " "),
      },
    ],
    [],
  );

  const avgRigs =
    rows.reduce((sum, trade) => sum + (trade.rigs_score ?? 0), 0) /
    (rows.filter((trade) => trade.rigs_score !== null).length || 1);
  const verified = rows.filter((trade) => trade.origin_eligible === true).length;
  const pending = rows.filter((trade) =>
    ["pending", "processing"].includes(trade.settlement_status),
  ).length;

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
          {session && (
            <button
              className="ml-2 rounded-lg border border-line px-3 py-2 text-slate-300 hover:border-slate-500"
              onClick={() => void signOut()}
              type="button"
            >
              Sign out
            </button>
          )}
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

      {!supabase || apiUrl === null ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-sm text-amber-100">
          Configure NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, and
          NEXT_PUBLIC_API_BASE_URL to connect this control room.
        </div>
      ) : !session ? (
        <section className="w-full max-w-md rounded-2xl border border-line bg-panel p-6">
          <h2 className="text-lg font-semibold text-white">Sign in</h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Use your organization account to access protected trade telemetry.
          </p>
          <form className="mt-5 space-y-4" onSubmit={(event) => void signIn(event)}>
            <label className="block text-xs font-medium text-slate-300">
              Email
              <input
                autoComplete="username"
                className="mt-2 w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-sm text-white outline-none focus:border-mint"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </label>
            <label className="block text-xs font-medium text-slate-300">
              Password
              <input
                autoComplete="current-password"
                className="mt-2 w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-sm text-white outline-none focus:border-mint"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <label className="block text-xs font-medium text-slate-300">
              Organization ID
              <input
                className="mt-2 w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-sm text-white outline-none focus:border-mint"
                onChange={(event) => saveOrganization(event.target.value)}
                placeholder="UUID from your administrator"
                required
                value={organizationId}
              />
            </label>
            {authError && <p role="alert" className="text-sm text-rose-300">{authError}</p>}
            <button
              className="w-full rounded-lg bg-mint px-4 py-2.5 text-sm font-semibold text-ink transition hover:bg-emerald-300 disabled:opacity-50"
              disabled={busy}
              type="submit"
            >
              {busy ? "Signing in…" : "Continue"}
            </button>
          </form>
        </section>
      ) : (
        <>
          {error && (
            <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              {error} {rows.length > 0 && "Showing the last saved snapshot."}
            </div>
          )}
          {!organizationId && (
            <label className="max-w-lg text-xs font-medium text-slate-300">
              Organization ID
              <input
                className="mt-2 w-full rounded-lg border border-line bg-panel px-3 py-2.5 text-sm text-white outline-none focus:border-mint"
                onChange={(event) => saveOrganization(event.target.value)}
                placeholder="UUID from your administrator"
                value={organizationId}
              />
            </label>
          )}
          <section aria-label="Trade summary" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Trade cases" value={rows.length.toLocaleString()} detail="Current snapshot" />
            <Metric label="Preferential origin" value={verified.toLocaleString()} detail="Verified under active rules" />
            <Metric label="Active settlements" value={pending.toLocaleString()} detail="Pending or processing" />
            <Metric label="Average RIGS" value={`${(avgRigs * 100).toFixed(1)}%`} detail="Scored cases only" />
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
              <AgGridReact<TradeRecord>
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
