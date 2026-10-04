"use client";

import Link from "next/link";
import { useState } from "react";

const features = [
  {
    number: "01",
    title: "AfCFTA Tariff Engine",
    description:
      "Deterministic Rules of Origin evaluation across regional trade corridors, built for clear and explainable decisions.",
    detail: "VA 40%  ·  CTH 2 / 4 / 6 digit  ·  WO",
    icon: "⌘",
    id: "compliance-rules",
  },
  {
    number: "02",
    title: "RIGS Trust Scoring",
    description:
      "Qualify counterparties against live Risk, Intent, Growth, and Stakeholder telemetry before trade moves forward.",
    detail: "Risk  ·  Intent  ·  Growth  ·  Stakeholders",
    icon: "◎",
    id: "rigs-framework",
  },
  {
    number: "03",
    title: "Trust-Gated Settlements",
    description:
      "Protect liquidity with idempotent payouts and automated circuit breakers when trust falls below the 75.0 threshold.",
    detail: "75.0 minimum trust score",
    icon: "↗",
    id: "settlements",
  },
  {
    number: "04",
    title: "Audit & Telemetry Export",
    description:
      "Keep every decision reviewable with an immutable trade ledger, validation checks, and compliance-ready snapshots.",
    detail: "64-point validation  ·  CSV export",
    icon: "▤",
    id: "audit",
  },
];

const workflow = [
  { number: "01", title: "Trade Ingestion", detail: "Structured trade payload" },
  { number: "02", title: "Tariff & HS Code", detail: "Rules of Origin checks" },
  { number: "03", title: "RIGS Trust Score", detail: "Counterparty telemetry" },
  { number: "04", title: "Liquidity & Settlement", detail: "Trust-gated execution" },
];

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="h-4 w-4">
      <path d="M4 10h12m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);

  return (
    <main className="landing-shell min-h-screen overflow-hidden bg-[#0b0f17] text-slate-100">
      <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-[#0b0f17]/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-5 py-4 sm:px-8">
          <Link href="/" className="flex shrink-0 items-center gap-3" aria-label="OriginSync home">
            <span className="grid h-9 w-9 place-items-center rounded-xl border border-emerald-400/20 bg-emerald-400/10 font-mono text-lg font-bold text-emerald-300">
              O
            </span>
            <span className="text-[17px] font-semibold tracking-tight text-white">OriginSync</span>
          </Link>

          <div className="hidden items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-400/[0.06] px-3 py-1.5 text-[11px] font-medium tracking-wide text-emerald-300 lg:flex">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            AfCFTA MAINNET ONLINE
          </div>

          <nav aria-label="Main navigation" className="hidden items-center gap-7 text-[13px] text-slate-400 md:flex">
            <a className="transition hover:text-white" href="#features">Features</a>
            <a className="transition hover:text-white" href="#compliance-rules">Compliance Rules</a>
            <a className="transition hover:text-white" href="#rigs-framework">RIGS Framework</a>
            <a className="transition hover:text-white" href="#api-docs">API Docs</a>
          </nav>

          <Link
            href="/control-room"
            className="hidden items-center gap-2 rounded-lg bg-emerald-400 px-4 py-2.5 text-[13px] font-semibold text-[#07130e] shadow-[0_0_22px_rgba(16,185,129,0.18)] transition hover:bg-emerald-300 md:inline-flex"
          >
            Launch Control Room <ArrowIcon />
          </Link>

          <button
            type="button"
            aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
            className="grid h-10 w-10 place-items-center rounded-lg border border-slate-700 text-slate-200 md:hidden"
          >
            <span className="text-xl leading-none">{menuOpen ? "×" : "☰"}</span>
          </button>
        </div>
        {menuOpen && (
          <nav aria-label="Mobile navigation" className="border-t border-slate-800 px-5 py-4 md:hidden">
            <div className="mx-auto flex max-w-7xl flex-col gap-1">
              {[
                ["Features", "#features"],
                ["Compliance Rules", "#compliance-rules"],
                ["RIGS Framework", "#rigs-framework"],
                ["API Docs", "#api-docs"],
              ].map(([label, href]) => (
                <a key={href} href={href} onClick={closeMenu} className="rounded-lg px-3 py-3 text-sm text-slate-300 hover:bg-slate-800/60">
                  {label}
                </a>
              ))}
              <Link href="/control-room" onClick={closeMenu} className="mt-2 rounded-lg bg-emerald-400 px-4 py-3 text-center text-sm font-semibold text-[#07130e]">
                Launch Control Room
              </Link>
            </div>
          </nav>
        )}
      </header>

      <section className="relative">
        <div aria-hidden="true" className="landing-hero-grid pointer-events-none absolute inset-0 opacity-50" />
        <div className="pointer-events-none absolute -top-32 left-1/2 h-[34rem] w-[54rem] -translate-x-1/2 rounded-full bg-emerald-500/[0.08] blur-[120px]" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-14 px-5 pb-20 pt-20 sm:px-8 sm:pb-24 sm:pt-28 lg:grid-cols-[1.12fr_0.88fr] lg:gap-12 lg:pb-28 lg:pt-32">
          <div className="max-w-3xl">
            <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.07] px-3.5 py-2 text-[11px] font-semibold uppercase tracking-[0.13em] text-emerald-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              AfCFTA Phase II Compliant Infrastructure
            </div>
            <h1 className="max-w-3xl text-[2.65rem] font-semibold leading-[1.08] tracking-[-0.045em] text-white sm:text-5xl lg:text-[3.65rem]">
              Autonomous trade compliance &amp; settlement control room
              <span className="text-emerald-300"> for intra-African commerce.</span>
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-400 sm:text-lg sm:leading-8">
              Accelerate cross-border trade clearance from days to milliseconds. Automate Rules of Origin tariff classification, evaluate counterparty trust via RIGS telemetry, and execute trust-gated liquidity settlements.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/control-room"
                className="inline-flex min-h-13 items-center justify-center gap-2 rounded-xl bg-emerald-400 px-6 py-4 text-sm font-bold text-[#07130e] shadow-[0_0_32px_rgba(16,185,129,0.2)] transition hover:-translate-y-0.5 hover:bg-emerald-300"
              >
                Launch Trade Control Room <ArrowIcon />
              </Link>
              <a
                href="#api-docs"
                className="inline-flex min-h-13 items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/60 px-6 py-4 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:bg-slate-800/70"
              >
                Explore API Specs <span className="text-slate-500">↓</span>
              </a>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-500">
              <span className="inline-flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Rules-based origin decisions</span>
              <span className="inline-flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Trust-gated settlement rails</span>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-[520px]">
            <div className="absolute -inset-5 rounded-[2rem] bg-emerald-400/[0.04] blur-2xl" />
            <div className="relative overflow-hidden rounded-2xl border border-slate-700/80 bg-[#0e151f]/95 shadow-2xl shadow-black/40">
              <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">Trade decision / live</div>
                  <div className="mt-1.5 text-sm font-semibold text-slate-100">Origin qualification</div>
                </div>
                <span className="rounded-md border border-emerald-400/20 bg-emerald-400/[0.08] px-2.5 py-1 font-mono text-[10px] font-medium tracking-wider text-emerald-300">VERIFIED</span>
              </div>
              <div className="space-y-5 p-5">
                <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-[#0a1018] p-4">
                  <div>
                    <div className="text-xs text-slate-500">Corridor</div>
                    <div className="mt-1.5 text-sm font-medium text-slate-200">GH → KE <span className="text-slate-600">/</span> AfCFTA</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-500">HS code</div>
                    <div className="mt-1.5 font-mono text-sm text-slate-200">1806.32</div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-slate-800 bg-[#0a1018] p-4">
                    <div className="text-[11px] text-slate-500">Value addition</div>
                    <div className="mt-3 flex items-end justify-between">
                      <span className="font-mono text-2xl font-medium text-white">46.8<span className="text-sm text-slate-500">%</span></span>
                      <span className="mb-1 text-[10px] text-emerald-300">+6.8% above rule</span>
                    </div>
                    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full w-[72%] rounded-full bg-emerald-400" /></div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-[#0a1018] p-4">
                    <div className="text-[11px] text-slate-500">RIGS trust score</div>
                    <div className="mt-3 flex items-end justify-between">
                      <span className="font-mono text-2xl font-medium text-white">88.5</span>
                      <span className="mb-1 text-[10px] text-emerald-300">QUALIFIED</span>
                    </div>
                    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full w-[88.5%] rounded-full bg-gradient-to-r from-emerald-500 to-teal-300" /></div>
                  </div>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.05] p-4">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-emerald-400/10 text-emerald-300">✓</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-emerald-200">Settlement eligible</div>
                    <div className="mt-1 text-[10px] text-slate-500">Origin verified · counterparty qualified</div>
                  </div>
                  <span className="font-mono text-[10px] text-slate-500">0.42s</span>
                </div>
              </div>
              <div className="flex items-center justify-between border-t border-slate-800 px-5 py-3 text-[10px] text-slate-600">
                <span>ORIGINSYNC / DECISION ENGINE</span><span className="font-mono">TX-8F2A19</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section aria-label="Network telemetry" className="border-y border-slate-800/90 bg-[#0d141d]/90">
        <div className="mx-auto grid max-w-7xl grid-cols-2 divide-x divide-y divide-slate-800/80 px-5 sm:px-8 lg:grid-cols-4 lg:divide-y-0">
          {[
            ["$3.4T", "AfCFTA corridor capacity"],
            ["<1.0s", "Origin decision latency"],
            ["40.0%", "Value addition threshold"],
            ["84.5", "Average RIGS trust score"],
          ].map(([value, label]) => (
            <div key={label} className="px-4 py-6 first:pl-0 sm:px-7 sm:py-7 lg:first:pl-4">
              <div className="font-mono text-2xl font-semibold tracking-tight text-white sm:text-3xl">{value}</div>
              <div className="mt-2 text-[11px] text-slate-500 sm:text-xs">{label}</div>
            </div>
          ))}
        </div>
      </section>

      <section id="features" className="scroll-mt-24 px-5 py-20 sm:px-8 sm:py-28">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-2xl">
            <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-300">One trusted trade layer</div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Infrastructure to move trade forward.</h2>
            <p className="mt-4 text-sm leading-6 text-slate-400 sm:text-base">From origin qualification to final settlement, every decision is explainable, measurable, and ready to act on.</p>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {features.map((feature) => (
              <article id={feature.id} key={feature.number} className="scroll-mt-28 rounded-2xl border border-slate-800 bg-[#0e151e]/80 p-6 transition hover:border-slate-700 hover:bg-[#111b26]">
                <div className="flex items-start justify-between">
                  <span className="grid h-11 w-11 place-items-center rounded-xl border border-emerald-400/15 bg-emerald-400/[0.06] text-xl text-emerald-300">{feature.icon}</span>
                  <span className="font-mono text-xs text-slate-700">{feature.number}</span>
                </div>
                <h3 className="mt-6 text-base font-semibold text-slate-100">{feature.title}</h3>
                <p className="mt-3 min-h-[5.5rem] text-sm leading-6 text-slate-400">{feature.description}</p>
                <div className="mt-5 border-t border-slate-800 pt-4 font-mono text-[10px] leading-5 text-emerald-300/80">{feature.detail}</div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-slate-800/80 bg-[#0d141d]/55 px-5 py-20 sm:px-8 sm:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-12 lg:grid-cols-[1fr_0.9fr] lg:items-center">
            <div>
              <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-300">From shipment to settlement</div>
              <h2 className="mt-4 max-w-xl text-3xl font-semibold tracking-tight text-white sm:text-4xl">A clear path from trade data to trusted execution.</h2>
              <div className="mt-9 space-y-0">
                {workflow.map((step, index) => (
                  <div key={step.number} className="relative flex gap-4 pb-7 last:pb-0">
                    {index < workflow.length - 1 && <span aria-hidden="true" className="absolute left-[17px] top-10 h-[calc(100%-1.25rem)] w-px bg-slate-800" />}
                    <span className="relative z-10 grid h-9 w-9 shrink-0 place-items-center rounded-full border border-emerald-400/20 bg-[#101922] font-mono text-[10px] text-emerald-300">{step.number}</span>
                    <div className="pt-0.5">
                      <h3 className="text-sm font-semibold text-slate-100">{step.title}</h3>
                      <p className="mt-1 text-xs text-slate-500">{step.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div id="api-docs" className="scroll-mt-28 overflow-hidden rounded-2xl border border-slate-800 bg-[#080d13] shadow-2xl shadow-black/20">
              <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-red-400/70" /><span className="h-2 w-2 rounded-full bg-amber-300/70" /><span className="h-2 w-2 rounded-full bg-emerald-400/80" />
                  <span className="ml-3 font-mono text-[10px] text-slate-500">POST /v1/trades/evaluate</span>
                </div>
                <span className="rounded border border-slate-700 px-2 py-1 font-mono text-[9px] text-slate-500">JSON</span>
              </div>
              <pre className="overflow-x-auto p-5 text-[11px] leading-[1.9] sm:p-7 sm:text-xs"><code><span className="text-slate-600">{"{"}</span>{"\n"}  <span className="text-sky-300">&quot;trade_id&quot;</span><span className="text-slate-400">: </span><span className="text-emerald-300">&quot;txn_8f2a19&quot;</span>,{"\n"}  <span className="text-sky-300">&quot;agreement&quot;</span><span className="text-slate-400">: </span><span className="text-emerald-300">&quot;AfCFTA&quot;</span>,{"\n"}  <span className="text-sky-300">&quot;origin_status&quot;</span><span className="text-slate-400">: </span><span className="text-emerald-300">&quot;VERIFIED&quot;</span>,{"\n"}  <span className="text-sky-300">&quot;rules&quot;</span><span className="text-slate-400">: {"{"}</span>{"\n"}    <span className="text-sky-300">&quot;va_percentage&quot;</span><span className="text-slate-400">: </span><span className="text-amber-200">46.8</span>,{"\n"}    <span className="text-sky-300">&quot;hs_code&quot;</span><span className="text-slate-400">: </span><span className="text-emerald-300">&quot;1806.32&quot;</span>{"\n"}  <span className="text-slate-400">{"}"}</span>,{"\n"}  <span className="text-sky-300">&quot;rigs_score&quot;</span><span className="text-slate-400">: </span><span className="text-amber-200">88.5</span>,{"\n"}  <span className="text-sky-300">&quot;settlement_eligible&quot;</span><span className="text-slate-400">: </span><span className="text-violet-300">true</span>{"\n"}<span className="text-slate-600">{"}"}</span></code></pre>
              <div className="flex flex-col gap-3 border-t border-slate-800 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-xs text-slate-500">Integrate origin checks in your trade flow.</span>
                <Link href="/control-room" className="inline-flex items-center gap-2 text-xs font-semibold text-emerald-300 hover:text-emerald-200">View live control room <ArrowIcon /></Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-5 py-20 sm:px-8 sm:py-24">
        <div className="relative mx-auto max-w-7xl overflow-hidden rounded-3xl border border-emerald-400/20 bg-[#0e1c1a] px-6 py-12 sm:px-12 sm:py-16">
          <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-32 h-80 w-80 rounded-full bg-emerald-400/10 blur-[90px]" />
          <div className="relative flex flex-col items-start justify-between gap-8 md:flex-row md:items-center">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-emerald-300/80">Built for Africa&apos;s next trade chapter</div>
              <h2 className="mt-4 max-w-2xl text-3xl font-semibold tracking-tight text-white sm:text-4xl">Ready to orchestrate regional trade at machine speed?</h2>
            </div>
            <Link href="/control-room" className="inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-xl bg-emerald-400 px-5 py-3.5 text-sm font-bold text-[#07130e] transition hover:bg-emerald-300">
              Open Control Room Dashboard <ArrowIcon />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-800/80 px-5 py-8 sm:px-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <Link href="/" className="flex items-center gap-2.5 text-sm font-semibold text-slate-200">
            <span className="grid h-7 w-7 place-items-center rounded-lg border border-emerald-400/20 bg-emerald-400/10 font-mono text-sm text-emerald-300">O</span>
            OriginSync
          </Link>
          <nav aria-label="Footer navigation" className="flex flex-wrap gap-x-6 gap-y-3 text-xs text-slate-500">
            <Link href="/control-room" className="hover:text-slate-200">System Status</Link>
            <a href="https://au-afcfta.org/" target="_blank" rel="noreferrer" className="hover:text-slate-200">AfCFTA Documentation</a>
            <a href="#api-docs" className="hover:text-slate-200">API References</a>
            <a href="https://github.com/brysyl/OriginSync-AI" target="_blank" rel="noreferrer" className="hover:text-slate-200">GitHub Repository</a>
          </nav>
        </div>
        <div className="mx-auto mt-6 max-w-7xl border-t border-slate-800/70 pt-5 text-[10px] text-slate-600">© {new Date().getFullYear()} OriginSync. Trade infrastructure for the continent.</div>
      </footer>
    </main>
  );
}
