"use client";

import {
  Activity, AlertOctagon, AlertTriangle, ArrowDownRight, ArrowUpRight,
  BarChart3, BookOpenCheck, Boxes, Check, ChevronDown, CircleHelp,
  Clock3, Copy, Database, FileCheck2, FileClock, FileText, Gauge, GitBranch,
  GitMerge, Layers3, ListChecks, LockKeyhole, Menu, Moon, Sun, Plus, RefreshCw, Search,
  Shield, ShieldAlert, SlidersHorizontal, WalletCards, X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type SectionId = "overview" | "wallets" | "portfolios" | "execution" | "gates" | "release" | "evidence" | "playbook";
type Basis = "historical" | "prospective" | "paper" | "unknown";
type Wallet = {
  address: string; alias: string | null; sourceEquityUsd: string | null;
  eligibility: string; assessmentStatus: string; edgeDecay: string;
  drawdownPct: string | null; evidenceQuality: string; evidenceBasis: Basis;
  sourceRef: string | null; assessedAt: string | null; updatedAt: string; registryMetadataJson?: string;
};
type PositionItem = {
  instrument: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  entryPrice: number;
  markPrice: number;
  marketValue: number;
  unrealizedPnl: number;
};
type Portfolio = {
  id: string; name: string; state: string; strategy: string | null;
  walletAddressesJson: string; podCount: number | null; totalRiskUsd: string | null;
  evidenceBasis: Basis; evidenceQuality: string; sourceRef: string | null;
  detailsJson: string; updatedAt: string;
  strategyHealth?: string | null; advisoryStatus?: string | null;
  advisoryCalibration?: string | null; feeDragUsd?: string | null;
  prefectReportSha256?: string | null; prefectAssessedAt?: string | null;
  initialEquityUsd?: number | null; currentEquityUsd?: number | null;
  cashUsd?: number | null; realizedPnlUsd?: number | null;
  unrealizedPnlUsd?: number | null; totalPnlUsd?: number | null;
  totalPnlPct?: number | null; highWaterMarkUsd?: number | null;
  drawdownPct?: number | null; dailyLossUsd?: number | null;
  totalCostsUsd?: number | null; totalFundingUsd?: number | null;
  grossExposureUsd?: number | null; leverage?: number | null;
  openPositionsCount?: number | null; positions?: PositionItem[] | null;
  riskState?: string | null; haltReason?: string | null;
  killSwitchActivated?: boolean | null; paperStatus?: string | null;
  lastMarkAt?: string | null;
};
type OpsRecord = {
  id: string; category: string; title: string; status: string; basis: Basis;
  quality: string; severity: string; owner: string | null; sourceRef: string | null;
  details: string; createdAt: string; updatedAt: string;
};
type EventRow = { id: number; entityType: string; entityId: string; action: string; actor: string; createdAt: string };
type RegistrySyncReceipt = {
  snapshotId: string; status: string; producedAt: string; receivedAt: string; sourceObservedAt: string | null;
  sourceStatus: string; inventorySha256: string; releaseStatus: string | null; releaseRevision: string | null;
  databaseIntegrity: string | null; selectionKnownAt: string | null; selectionSha256: string | null;
  selectionState: string | null; paperRunning: string; scientificallyQualified: number; tradingAuthorized: number;
  walletTotal: number; walletSynced: number; walletUnresolved: number; portfolioCount: number; error: string | null;
};
type RegistrySyncState = { latestAttempt: RegistrySyncReceipt | null; latestAccepted: RegistrySyncReceipt | null };
type DataState = { wallets: Wallet[]; portfolios: Portfolio[]; records: OpsRecord[]; events: EventRow[]; registrySync: RegistrySyncState };
type FormKind = "paper_state" | "execution" | "risk_budget" | "acceptance_gate" | "blocker" | "grafana" | "release" | "deployment" | "rollback" | "followup" | "evidence" | "decision" | "approval" | "test_result";

const blankData: DataState = { wallets: [], portfolios: [], records: [], events: [], registrySync: { latestAttempt: null, latestAccepted: null } };
const navItems: { id: SectionId; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "wallets", label: "Wallet health", icon: WalletCards },
  { id: "portfolios", label: "Portfolios", icon: Layers3 },
  { id: "execution", label: "Paper & execution", icon: Activity },
  { id: "gates", label: "Gates & blockers", icon: ListChecks },
  { id: "release", label: "Release & runtime", icon: GitBranch },
  { id: "evidence", label: "Evidence & decisions", icon: FileCheck2 },
  { id: "playbook", label: "Operations playbook", icon: BookOpenCheck },
];
const formLabels: Record<FormKind, string> = {
  paper_state: "Paper-trading state",
  execution: "T+5 execution evidence", risk_budget: "Pod risk budget", acceptance_gate: "Acceptance gate",
  blocker: "Open blocker", grafana: "Grafana rollout", release: "Release / merge record",
  deployment: "Deployment / runtime record", rollback: "Rollback evidence", followup: "Post-deployment follow-up",
  evidence: "Evidence receipt", decision: "Production-readiness decision", approval: "Approval record",
  test_result: "Test result",
};
const statuses = ["pending", "in_progress", "blocked", "verified", "passed", "failed", "approved", "merged", "deployed", "rolled_back", "watch", "active", "candidate", "paper", "archived", "stale", "unknown"];
const bases: Basis[] = ["historical", "prospective", "paper", "unknown"];

const labelFor = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const asMoney = (value: string | number | null | undefined, digits = 2) => {
  if (value === null || value === undefined) return "—";
  const amount = typeof value === "number" ? value : Number(value);
  return Number.isFinite(amount) ? `$${amount.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}` : "—";
};
const asPnl = (pnl: number | string | null | undefined, pct: number | string | null | undefined) => {
  if (pnl === null || pnl === undefined) return { text: "—", tone: "muted" };
  const val = typeof pnl === "number" ? pnl : parseFloat(String(pnl));
  const p = pct !== null && pct !== undefined ? (typeof pct === "number" ? pct : parseFloat(String(pct))) : null;
  if (!Number.isFinite(val)) return { text: "—", tone: "muted" };
  const sign = val > 0 ? "+" : "";
  const pctStr = p !== null && Number.isFinite(p) ? ` (${sign}${p.toFixed(2)}%)` : "";
  const text = `${sign}$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${pctStr}`;
  const tone = val > 0.005 ? "good" : val < -0.005 ? "bad" : "muted";
  return { text, tone };
};
function parseJsonObject(value: string | null | undefined): Record<string, unknown> {
  try { const parsed: unknown = JSON.parse(value || "{}"); return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}; }
  catch { return {}; }
}
const statusClass = (status: string) => {
  if (["verified", "passed", "approved", "deployed", "active", "eligible", "stable", "recovered"].includes(status)) return "good";
  if (["blocked", "failed", "severe", "ineligible", "critical"].includes(status)) return "bad";
  if (["watch", "stale", "in_progress", "decaying", "paper"].includes(status)) return "warn";
  return "muted";
};

export default function OpsDashboard({ userName }: { userName: string }) {
  const [section, setSection] = useState<SectionId>("overview");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    try { const saved = localStorage.getItem("copytrade-ops-theme"); if (saved === "light" || saved === "dark") setTheme(saved); } catch { /* Preference storage is optional. */ }
  }, []);
  const toggleTheme = () => setTheme((current) => {
    const next = current === "dark" ? "light" : "dark";
    try { localStorage.setItem("copytrade-ops-theme", next); } catch { /* Keep the session preference. */ }
    return next;
  });
  const [data, setData] = useState<DataState>(blankData);
  const [dbStatus, setDbStatus] = useState<"loading" | "ready" | "pending">("loading");
  const [dbMessage, setDbMessage] = useState("");
  const [form, setForm] = useState<FormKind | null>(null);
  const [busy] = useState(false);
  const [toast, setToast] = useState("");
  const [query, setQuery] = useState("");
  const [basisFilter, setBasisFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [mobileNav, setMobileNav] = useState(false);

  const refresh = useCallback(async () => {
    setDbStatus("loading");
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
      const body = await response.json() as { error?: string; wallets?: Wallet[]; portfolios?: Portfolio[]; records?: OpsRecord[]; events?: EventRow[]; registrySync?: RegistrySyncState };
      if (!response.ok) throw new Error(body.error ?? "SQLite registry is not available.");
      setData({ wallets: body.wallets ?? [], portfolios: body.portfolios ?? [], records: body.records ?? [], events: body.events ?? [], registrySync: body.registrySync ?? { latestAttempt: null, latestAccepted: null } });
      setDbStatus("ready");
      setDbMessage("");
    } catch (error) {
      setDbStatus("pending");
      setDbMessage(error instanceof Error ? error.message : "SQLite registry is not available.");
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const openBlockers = data.records.filter((record) => record.category === "blocker" && !["verified", "archived", "passed"].includes(record.status)).length;
  const latestDecision = data.records.find((record) => record.category === "decision");
  // Public control center has no writer identity. Only an independent private
  // operator process may record or approve evidence; never call mutation API.
  const addRecord = async (_payload: Record<string, unknown>) => {
    setToast("Read-only observer: evidence writes are disabled.");
  };
  const setRecordStatus = async (_record: OpsRecord, _nextStatus: string) => {
    setToast("Read-only observer: status changes are disabled.");
  };

  return (
    <div className="app-shell" data-theme={theme}>
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={19} strokeWidth={2.4} /></div>
          <div><div className="brand-name">POD<span className="brand-slash">/</span>OPS</div><div className="brand-caption">CONTROL CENTER</div></div>
          <button className="mobile-close icon-button" aria-label="Close menu" onClick={() => setMobileNav(false)}><X size={18} /></button>
        </div>
        <div className="workspace-switch"><div className="workspace-dot" /><div><strong>copytrade-pm</strong><span>Operations workspace</span></div><ChevronDown size={15} /></div>
        <div className="nav-caption"><span>WORKSPACE</span><span>01 — 08</span></div>
        <nav className="side-nav" aria-label="Main navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            return <button key={item.id} className={`nav-link ${section === item.id ? "selected" : ""}`} onClick={() => { setSection(item.id); setMobileNav(false); }}><Icon size={17} /><span>{item.label}</span>{item.id === "gates" && openBlockers > 0 && <b className="nav-count">{openBlockers}</b>}</button>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="source-mini"><Database size={15} /><span>SQLite registry</span><i className={dbStatus === "ready" ? "dot-good" : "dot-pending"} /></div>
          <div className="sidebar-user"><div className="avatar">{userName.slice(0, 1).toUpperCase()}</div><div className="user-meta"><strong>{userName}</strong><span>Read-only access</span></div><SlidersHorizontal size={15} /></div>
        </div>
      </aside>

      {mobileNav && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMobileNav(false)} />}
      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu icon-button" aria-label="Open menu" onClick={() => setMobileNav(true)}><Menu size={20} /></button>
          <div className="breadcrumbs"><span>Operations</span><span className="crumb-sep">/</span><strong>{navItems.find((item) => item.id === section)?.label}</strong></div>
          <div className="topbar-actions">
            <div className={`connection-chip ${dbStatus === "ready" ? "connected" : "awaiting"}`}><span className="pulse-dot" />{dbStatus === "ready" ? "Site projection available" : dbStatus === "loading" ? "Checking registry" : "Registry pending"}</div>
            <button className="theme-toggle" type="button" aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"} onClick={toggleTheme}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}<span>{theme === "dark" ? "Light" : "Dark"}</span></button>
            <button className="icon-button" title="Refresh from SQLite" onClick={() => void refresh()}><RefreshCw size={16} /></button>
            <div className="avatar top-avatar">{userName.slice(0, 1).toUpperCase()}</div>
          </div>
        </header>
        <div className="page-scroll">
          <div className="page-container" key={section}>
            {section === "overview" && <Overview data={data} dbStatus={dbStatus} dbMessage={dbMessage} blockers={openBlockers} decision={latestDecision} onOpen={setForm} onNavigate={setSection} />}
            {section === "wallets" && <WalletsPage wallets={data.wallets} query={query} setQuery={setQuery} basis={basisFilter} setBasis={setBasisFilter} status={statusFilter} setStatus={setStatusFilter} />}
            {section === "portfolios" && <PortfoliosPage portfolios={data.portfolios} />}
            {section === "execution" && <ExecutionPage records={data.records} onOpen={setForm} onStatus={setRecordStatus} />}
            {section === "gates" && <GatesPage records={data.records} onOpen={setForm} onStatus={setRecordStatus} />}
            {section === "release" && <ReleasePage records={data.records} events={data.events} onOpen={setForm} onStatus={setRecordStatus} />}
            {section === "evidence" && <EvidencePage records={data.records} events={data.events} onOpen={setForm} basis={basisFilter} setBasis={setBasisFilter} />}
            {section === "playbook" && <PlaybookPage onOpen={setForm} blockers={data.records.filter((record) => record.category === "blocker" && !["verified", "archived", "passed"].includes(record.status))} />}
          </div>
        </div>
      </main>
      {form && <RecordModal kind={form} busy={busy} onClose={() => setForm(null)} onSave={addRecord} />}
      {toast && <div className="toast" role="status"><Check size={15} />{toast}</div>}
    </div>
  );
}

function PageHeading({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: React.ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{actions && <div className="heading-actions">{actions}</div>}</div>;
}
function Button({ children, onClick, variant = "primary", icon: Icon, disabled = false, type = "button" }: { children: React.ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "quiet"; icon?: LucideIcon; disabled?: boolean; type?: "button" | "submit" }) {
  if (typeof children === "string" && /^(Record|Add|Track|Log)\b/.test(children)) return null;
  return <button type={type} className={`button ${variant}`} onClick={onClick} disabled={disabled}>{Icon && <Icon size={15} />}{children}</button>;
}
function Badge({ children, tone }: { children: React.ReactNode; tone: string }) { return <span className={`badge ${tone}`}>{children}</span>; }
function EmptyState({ title, detail, action }: { title: string; detail: string; action?: React.ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><CircleHelp size={20} /></div><strong>{title}</strong><p>{detail}</p>{action}</div>;
}
function StatCard({ label, value, detail, icon: Icon, tone = "blue", pending = false }: { label: string; value: string; detail: string; icon: LucideIcon; tone?: string; pending?: boolean }) {
  return <article className="stat-card"><div className={`stat-icon ${tone}`}><Icon size={17} /></div><div className="stat-label">{label}</div><div className={`stat-value ${pending ? "pending-value" : ""}`}>{value}</div><div className="stat-detail">{detail}</div></article>;
}
function Overview({ data, dbStatus, dbMessage, blockers, decision, onOpen, onNavigate }: { data: DataState; dbStatus: string; dbMessage: string; blockers: number; decision?: OpsRecord; onOpen: (kind: FormKind) => void; onNavigate: (section: SectionId) => void }) {
  const active = data.portfolios.filter((item) => item.state === "active").length;
  const candidates = data.portfolios.filter((item) => item.state === "candidate").length;
  const deployed = data.records.find((item) => item.category === "deployment" && item.status === "deployed");
  const attempt = data.registrySync.latestAttempt;
  const sync = attempt;
  const accepted = data.registrySync.latestAccepted;
  const sourceCurrent = accepted && ["CURRENT", "FRESH", "READY", "AVAILABLE", "OK"].includes(accepted.sourceStatus);
  const registryLabel = attempt?.status === "failed" ? "VPS registry read failed" : accepted ? "Verified registry snapshot received" : attempt ? "Registry inventory loaded; provenance not verified" : "Awaiting VPS registry inventory";
  const registryDetail = sync
    ? `Received ${new Date(sync.receivedAt).toLocaleString()}; source observed ${sync.sourceObservedAt ? new Date(sync.sourceObservedAt).toLocaleString() : "time unknown"}. ${sync.walletSynced}/${sync.walletTotal} wallet identities resolved; ${sync.walletUnresolved} remain pending.`
    : "The VPS SQLite registry has not supplied a signed snapshot yet";
  return <>
    <PageHeading eyebrow="OPERATIONS / 01" title="Control center" description="A single evidence-first view of wallets, portfolios, execution, and release readiness." actions={<Button icon={Plus} onClick={() => onOpen("decision")}>Record decision</Button>} />
    <div className="registry-banner"><div className="banner-icon"><Database size={19} /></div><div className="banner-copy"><strong>{dbStatus === "ready" ? registryLabel : "Site SQLite is unavailable"}</strong><span>{dbStatus === "ready" ? registryDetail : dbMessage || "The Site projection could not be read."} The VPS SQLite remains authoritative; This is a read-only VPS projection.</span></div><Badge tone={dbStatus === "ready" && sourceCurrent ? "good" : "warn"}>{dbStatus === "ready" ? (sync ? `SOURCE ${labelFor(sync.sourceStatus.toLowerCase())}` : "SYNC PENDING") : "PENDING"}</Badge></div>
    <div className="stat-grid">
      <StatCard label="Registry wallet rows" value={sync ? String(sync.walletTotal) : "—"} detail={sync ? `${sync.walletUnresolved} unresolved aliases; health assessment pending` : "No VPS snapshot received"} icon={WalletCards} tone="blue" pending={!sync} />
      <StatCard label="Current portfolios" value={sync ? String(data.portfolios.length) : "—"} detail={sync ? `${active} active · ${candidates} candidate · ${data.portfolios.filter(p => p.strategyHealth || parseJsonObject(p.detailsJson).strategyHealth).length} assessed health` : "Current portfolio set unknown"} icon={Layers3} tone="violet" pending={!sync} />
      <StatCard label="Open blockers" value={dbStatus === "ready" ? String(blockers) : "Pending"} detail={dbStatus !== "ready" ? "Site records unavailable" : blockers ? "Needs an owner and next step" : "No blockers recorded yet"} icon={AlertTriangle} tone={dbStatus !== "ready" || blockers ? "amber" : "green"} pending={dbStatus !== "ready"} />
      <StatCard label="Production decision" value={decision ? labelFor(decision.status) : "Pending"} detail={decision ? decision.title : "No readiness decision recorded"} icon={Shield} tone="slate" pending={!decision} />
    </div>
    <div className="overview-grid">
      <section className="panel registry-panel">
        <PanelHeader title="System readiness" subtitle="Verified state, not remembered state" icon={Gauge} />
        <div className="readiness-list">
          <ReadinessRow icon={Database} label="VPS wallet & portfolio registry" detail={sync ? `SQLite integrity ${sync.databaseIntegrity || "unknown"}; scientific qualification ${sync.scientificallyQualified ? "reported" : "not established"}; trading authorization ${sync.tradingAuthorized ? "reported" : "not authorized"}` : "Waiting for registry inventory"} status={accepted && sourceCurrent ? "Verified" : "Unverified"} tone={sync && sourceCurrent ? "good" : "warn"} />
          <ReadinessRow icon={Activity} label="Paper trading & T+5 entry" detail="Capture the single-order delay behavior and observed fills" status={data.records.some((r) => r.category === "execution" || r.category === "paper_state") ? "Tracked" : "Pending"} tone={data.records.some((r) => r.category === "execution" || r.category === "paper_state") ? "good" : "warn"} />
          <ReadinessRow icon={GitBranch} label="Deployed revision & runtime" detail="Record deployed SHA, health evidence, and rollback identity" status={deployed ? "Deployed" : "Unknown"} tone={deployed ? "good" : "muted"} />
          {(() => {
            const prefectBatch = data.records.find((r) => r.id === "prefect-track-b-flow" || r.category === "prefect_flow");
            const isVerified = prefectBatch && (prefectBatch.status === "verified" || (prefectBatch as any).reportedStatus === "verified");
            return <ReadinessRow
              icon={Activity}
              label="Track B strategy health (Prefect)"
              detail={prefectBatch ? `${prefectBatch.title} · ${prefectBatch.details || "Flow published"}` : "Track B offline strategy health assessments"}
              status={prefectBatch ? (isVerified ? "Verified" : labelFor(prefectBatch.status)) : "Pending"}
              tone={isVerified ? "good" : "warn"}
            />;
          })()}
        </div>
        <div className="panel-foot"><span>Read-only by default</span><span>·</span><span>Trading controls are never invoked here</span></div>
      </section>
      <section className="panel attention-panel">
        <PanelHeader title="Needs attention" subtitle="Unknowns stay visible until evidence arrives" icon={AlertOctagon} />
        <div className="attention-list">
          <AttentionRow tone={sync && sourceCurrent ? "blue" : "amber"} title="VPS SQLite source freshness" detail={sync ? `${labelFor(sync.sourceStatus.toLowerCase())} · ${sync.walletUnresolved} unresolved wallet identities` : "No signed snapshot received"} onClick={() => onNavigate("wallets")} />
          <AttentionRow tone="blue" title="Acceptance gate baseline" detail={data.records.some((r) => r.category === "acceptance_gate") ? "Gate records exist; review open items" : "No gates have been recorded"} onClick={() => onNavigate("gates")} />
          <AttentionRow tone="slate" title="Runtime revision" detail={deployed ? `Recorded: ${deployed.title}` : "Deployed SHA and live runtime are unknown"} onClick={() => onNavigate("release")} />
        </div>
        <Button variant="quiet" onClick={() => onNavigate("gates")}>Review gates & blockers <ArrowUpRight size={14} /></Button>
      </section>
    </div>
    <div className="section-row"><div><div className="eyebrow">SYSTEM LINKS</div><h2>Connected codebases</h2><p>Wallets and current portfolios sync from VPS SQLite; release and runtime evidence remains separately verified.</p></div></div>
    <div className="repo-grid">
      <RepoCard name="copytrade-pm" purpose="Wallet registry · portfolio selection · copy engine" href="https://github.com/hzminhzz/copytrade-pm" />
      <RepoCard name="prop-production" purpose="Forward paper operations · Guardian · deployment" href="https://github.com/hzminhzz/prop-production" />
      <RepoCard name="trading-connector" purpose="Venue connectivity · execution transport" href="https://github.com/hzminhzz/trading-connector" />
    </div>
    <div className="overview-footer"><span><Clock3 size={14} /> Last VPS snapshot received {sync ? new Date(sync.receivedAt).toLocaleString() : "not yet"}</span><span><LockKeyhole size={14} /> Site access controlled by sharing settings · no trading controls</span></div>
  </>;
}
function PanelHeader({ title, subtitle, icon: Icon }: { title: string; subtitle: string; icon: LucideIcon }) { return <div className="panel-header"><div className="panel-heading-icon"><Icon size={17} /></div><div><h3>{title}</h3><p>{subtitle}</p></div></div>; }
function ReadinessRow({ icon: Icon, label, detail, status, tone }: { icon: LucideIcon; label: string; detail: string; status: string; tone: string }) { return <div className="readiness-row"><div className="readiness-icon"><Icon size={15} /></div><div className="readiness-text"><strong>{label}</strong><span>{detail}</span></div><Badge tone={tone}>{status}</Badge></div>; }
function AttentionRow({ tone, title, detail, onClick }: { tone: string; title: string; detail: string; onClick: () => void }) { return <button className="attention-row" onClick={onClick}><span className={`attention-dot ${tone}`} /><span className="attention-text"><strong>{title}</strong><small>{detail}</small></span><ArrowUpRight size={14} /></button>; }
function RepoCard({ name, purpose, href }: { name: string; purpose: string; href: string }) { return <a className="repo-card" href={href} target="_blank" rel="noreferrer"><div className="repo-icon"><GitBranch size={17} /></div><div><strong>{name}</strong><span>{purpose}</span></div><ArrowUpRight size={15} /></a>; }

function WalletsPage({ wallets, query, setQuery, basis, setBasis, status, setStatus }: { wallets: Wallet[]; query: string; setQuery: (v: string) => void; basis: string; setBasis: (v: string) => void; status: string; setStatus: (v: string) => void }) {
  const [sortKey, setSortKey] = useState<"alias" | "equity" | "eligibility" | "assessment" | "decay" | "memberships">("equity");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = (key: "alias" | "equity" | "eligibility" | "assessment" | "decay" | "memberships") => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir(key === "equity" || key === "decay" || key === "memberships" ? "desc" : "asc");
    }
  };

  const filtered = wallets.filter((wallet) => {
    const match = `${wallet.address} ${wallet.alias ?? ""}`.toLowerCase().includes(query.toLowerCase());
    return match && (basis === "all" || wallet.evidenceBasis === basis) && (status === "all" || wallet.eligibility === status);
  });

  const sorted = [...filtered].sort((a, b) => {
    let valA: number | string | null = 0;
    let valB: number | string | null = 0;
    if (sortKey === "equity") {
      valA = a.sourceEquityUsd == null ? null : Number(a.sourceEquityUsd);
      valB = b.sourceEquityUsd == null ? null : Number(b.sourceEquityUsd);
    } else if (sortKey === "alias") {
      valA = a.alias?.toLowerCase() ?? null;
      valB = b.alias?.toLowerCase() ?? null;
    } else if (sortKey === "eligibility") {
      valA = (a.eligibility || "").toLowerCase();
      valB = (b.eligibility || "").toLowerCase();
    } else if (sortKey === "assessment") {
      valA = (a.assessmentStatus || "").toLowerCase();
      valB = (b.assessmentStatus || "").toLowerCase();
    } else if (sortKey === "decay") {
      valA = a.drawdownPct == null ? null : Number(a.drawdownPct);
      valB = b.drawdownPct == null ? null : Number(b.drawdownPct);
    } else if (sortKey === "memberships") {
      const mA = parseJsonObject(a.registryMetadataJson);
      const mB = parseJsonObject(b.registryMetadataJson);
      valA = Array.isArray(mA.portfolioMemberships) ? mA.portfolioMemberships.length : 0;
      valB = Array.isArray(mB.portfolioMemberships) ? mB.portfolioMemberships.length : 0;
    }
    const missingA = valA === null || (typeof valA === "number" && !Number.isFinite(valA));
    const missingB = valB === null || (typeof valB === "number" && !Number.isFinite(valB));
    if (missingA || missingB) return missingA === missingB ? 0 : missingA ? 1 : -1;
    if (valA! < valB!) return sortDir === "asc" ? -1 : 1;
    if (valA! > valB!) return sortDir === "asc" ? 1 : -1;
    return 0;
  });

  const assessed = wallets.filter((wallet) => wallet.assessmentStatus === "current").length;
  const decayCount = wallets.filter((wallet) => ["watch", "decaying", "severe"].includes(wallet.edgeDecay)).length;
  const pendingEvidence = wallets.filter((wallet) => wallet.evidenceQuality !== "verified").length;
  return <>
    <PageHeading eyebrow="REGISTRY / 02" title="Wallet health" description="VPS SQLite identity and monitoring facts, with eligibility, equity, and edge decay left pending until assessed." />
    <div className="metric-strip"><Metric label="Resolved aliases" value={wallets.length ? String(wallets.filter((w) => Boolean(w.alias)).length) : "Pending"} /><Metric label="Health assessed" value={assessed ? String(assessed) : "Pending"} /><Metric label="Edge decay flagged" value={decayCount ? String(decayCount) : wallets.some((wallet) => wallet.edgeDecay !== "unknown") ? "0" : "Pending"} /><Metric label="Evidence pending" value={wallets.length ? String(pendingEvidence) : "Pending"} /></div>
    <section className="panel table-panel">
      <div className="table-toolbar">
        <div>
          <h3>Registry-linked wallet view</h3>
          <p>Addresses are withheld by the native VPS read interface. Registry membership does not establish current health or trading eligibility.</p>
        </div>
        <div className="filters">
          <label className="search-field">
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search wallet alias" />
          </label>
          <select aria-label="Filter by evidence basis" value={basis} onChange={(event) => setBasis(event.target.value)}>
            <option value="all">All evidence</option>
            {bases.map((item) => <option key={item}>{item}</option>)}
          </select>
          <select aria-label="Filter by eligibility" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">All eligibility</option>
            {["eligible", "watch", "ineligible", "paused", "pending"].map((item) => <option key={item}>{item}</option>)}
          </select>
          <select
            aria-label="Sort wallets"
            value={`${sortKey}:${sortDir}`}
            onChange={(e) => {
              const [k, d] = e.target.value.split(":") as [typeof sortKey, typeof sortDir];
              setSortKey(k);
              setSortDir(d);
            }}
          >
            <option value="equity:desc">Equity: High → Low</option>
            <option value="equity:asc">Equity: Low → High</option>
            <option value="alias:asc">Alias: A → Z</option>
            <option value="alias:desc">Alias: Z → A</option>
            <option value="eligibility:asc">Eligibility: A → Z</option>
            <option value="assessment:asc">Assessment: A → Z</option>
            <option value="decay:desc">Drawdown: High → Low</option>
            <option value="memberships:desc">Memberships: Most → Fewest</option>
          </select>
          <button
            type="button"
            className="button secondary"
            style={{ padding: "6px 10px", fontSize: "12px", minHeight: "36px" }}
            onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
            title={`Sort direction: currently ${sortDir === "asc" ? "Ascending" : "Descending"}`}
          >
            {sortDir === "asc" ? "▲ Ascending" : "▼ Descending"}
          </button>
        </div>
      </div>
      {sorted.length ? <div className="table-scroll"><table><thead><tr>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("alias")}>
          Wallet alias {sortKey === "alias" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("equity")}>
          Source equity {sortKey === "equity" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("eligibility")}>
          Eligibility {sortKey === "eligibility" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("assessment")}>
          Assessment {sortKey === "assessment" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("decay")}>
          Edge decay {sortKey === "decay" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("memberships")}>
          Registry facts {sortKey === "memberships" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th>Evidence</th>
      </tr></thead><tbody>{sorted.map((wallet) => {
        const metadata = parseJsonObject(wallet.registryMetadataJson);
        const cohorts = Array.isArray(metadata.cohorts) ? metadata.cohorts.map(String).join(", ") : "Unknown";
        const memberships = Array.isArray(metadata.portfolioMemberships) ? metadata.portfolioMemberships.length : 0;
        return <tr key={wallet.address}><td><strong>{wallet.alias || wallet.address}</strong><small className="mono">Canonical alias · address not exported</small></td><td>{asMoney(wallet.sourceEquityUsd)}</td><td><Badge tone={statusClass(wallet.eligibility)}>{labelFor(wallet.eligibility)}</Badge></td><td><Badge tone={statusClass(wallet.assessmentStatus)}>{labelFor(wallet.assessmentStatus)}</Badge></td><td><Badge tone={statusClass(wallet.edgeDecay)}>{labelFor(wallet.edgeDecay)}</Badge>{wallet.drawdownPct && <small className="table-sub">Drawdown {wallet.drawdownPct}%</small>}</td><td><span>{cohorts}</span><small className="table-sub">{memberships} saved portfolio memberships · receipt health {String(metadata.receiptHealth ?? "unknown")}</small></td><td><span>{labelFor(wallet.evidenceBasis)}</span><small className="table-sub">{labelFor(wallet.evidenceQuality)} · {wallet.sourceRef?.slice(-16) || "source receipt missing"}</small></td></tr>;
      })}</tbody></table></div> : <EmptyState title={wallets.length ? "No wallets match these filters" : "No VPS wallet snapshot loaded"} detail={wallets.length ? "Clear a filter or search a different alias." : "The VPS registry has not delivered a resolved wallet alias. Do not infer an assessment from an absent row."} />}
    </section>
    <div className="callout-row"><div className="callout-icon"><ShieldAlert size={17} /></div><div><strong>Registry metadata is not a health assessment</strong><p>Source equity, eligibility, drawdown, and edge-decay remain pending. The native wallet API redacts addresses and flags some registry identities as unresolved; no alias is manufactured for those rows.</p></div></div>
  </>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="metric-item"><span>{label}</span><strong>{value}</strong></div>; }

function PortfoliosPage({ portfolios }: { portfolios: Portfolio[] }) {
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [stateFilter, setStateFilter] = useState("all");
  const [campaignFilter, setCampaignFilter] = useState("all");
  const [portQuery, setPortQuery] = useState("");
  const [sortKey, setSortKey] = useState<"equity" | "pnl" | "risk" | "name" | "wallets" | "pods" | "state" | "positions">("equity");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selectedPortId, setSelectedPortId] = useState<string | null>(null);

  const addressCount = (row: Portfolio) => {
    try {
      return (JSON.parse(row.walletAddressesJson) as string[]).length;
    } catch {
      return 0;
    }
  };

  const handleSort = (key: typeof sortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir(["equity", "pnl", "risk", "positions", "pods", "wallets"].includes(key) ? "desc" : "asc");
    }
  };

  const filtered = portfolios.filter((portfolio) => {
    const matchState = stateFilter === "all" || portfolio.state === stateFilter;
    const matchCampaign =
      campaignFilter === "all" ||
      (campaignFilter === "cwsa" && portfolio.strategy === "CWSA Chapter 2") ||
      (campaignFilter === "v4" && portfolio.strategy === "Archived V4 — Historical") ||
      (campaignFilter === "candidate" && portfolio.state === "candidate");
    const matchQuery =
      !portQuery ||
      `${portfolio.name} ${portfolio.id} ${portfolio.strategy || ""}`.toLowerCase().includes(portQuery.toLowerCase());
    return matchState && matchCampaign && matchQuery;
  });

  const sorted = [...filtered].sort((a, b) => {
    let valA: number | string = 0;
    let valB: number | string = 0;
    if (sortKey === "equity") {
      valA = a.currentEquityUsd ?? -1;
      valB = b.currentEquityUsd ?? -1;
    } else if (sortKey === "pnl") {
      valA = a.totalPnlUsd ?? -999999;
      valB = b.totalPnlUsd ?? -999999;
    } else if (sortKey === "positions") {
      valA = a.openPositionsCount ?? -1;
      valB = b.openPositionsCount ?? -1;
    } else if (sortKey === "risk") {
      valA = a.totalRiskUsd ? parseFloat(a.totalRiskUsd) : -1;
      valB = b.totalRiskUsd ? parseFloat(b.totalRiskUsd) : -1;
      if (isNaN(valA as number)) valA = -1;
      if (isNaN(valB as number)) valB = -1;
    } else if (sortKey === "name") {
      valA = (a.name || "").toLowerCase();
      valB = (b.name || "").toLowerCase();
    } else if (sortKey === "state") {
      valA = (a.state || "").toLowerCase();
      valB = (b.state || "").toLowerCase();
    } else if (sortKey === "wallets") {
      valA = addressCount(a);
      valB = addressCount(b);
    } else if (sortKey === "pods") {
      valA = a.podCount != null ? a.podCount : -1;
      valB = b.podCount != null ? b.podCount : -1;
    }
    if (valA < valB) return sortDir === "asc" ? -1 : 1;
    if (valA > valB) return sortDir === "asc" ? 1 : -1;
    return 0;
  });

  const cwsaPortfolios = portfolios.filter((p) => p.strategy === "CWSA Chapter 2");
  const archivedPortfolios = portfolios.filter((p) => p.strategy === "Archived V4 — Historical");
  const activeCapital = cwsaPortfolios.reduce((acc, p) => acc + (p.currentEquityUsd ?? 0), 0);
  const activePnl = cwsaPortfolios.reduce((acc, p) => acc + (p.totalPnlUsd ?? 0), 0);
  const totalOpenPos = portfolios.reduce((acc, p) => acc + (p.openPositionsCount ?? 0), 0);

  const selectedPortfolio = portfolios.find((p) => p.id === selectedPortId);
  const leftPortfolio = portfolios.find((item) => item.id === left);
  const rightPortfolio = portfolios.find((item) => item.id === right);

  return <>
    <PageHeading eyebrow="PORTFOLIO / 03" title="Portfolio tracking & risk accounts" description="Explicit virtual portfolio accounting: real-time equities, P&L, free cash, peak drawdown, gross exposure, and open position inventories." />

    <div className="metric-strip" style={{ marginBottom: "16px" }}>
      <Metric label="CWSA Active Capital" value={asMoney(activeCapital)} />
      <Metric label="CWSA Session P&L" value={asPnl(activePnl, 0).text} />
      <Metric label="Total Open Positions" value={`${totalOpenPos} positions`} />
      <Metric label="Tracking Roster" value={`${cwsaPortfolios.length} active · ${archivedPortfolios.length} archived`} />
    </div>

    {selectedPortfolio && (
      <section className="panel" style={{ padding: "18px", marginBottom: "16px", border: "1px solid #77948c" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "14px", flexWrap: "wrap", gap: "10px" }}>
          <div>
            <div className="eyebrow">PORTFOLIO TRACKING INSPECTOR</div>
            <h3 style={{ margin: "4px 0 0", fontSize: "16px" }}>{selectedPortfolio.name} <Badge tone={selectedPortfolio.strategy === "CWSA Chapter 2" ? "blue" : "muted"}>{selectedPortfolio.strategy || "Candidate"}</Badge></h3>
            <p style={{ margin: "2px 0 0", fontSize: "12px", color: "var(--muted-foreground)" }}>ID: {selectedPortfolio.id} · State: {labelFor(selectedPortfolio.state)} · Risk: <Badge tone={statusClass(selectedPortfolio.riskState || selectedPortfolio.state)}>{selectedPortfolio.riskState || "NORMAL"}</Badge> · Kill switch: {selectedPortfolio.killSwitchActivated ? "ACTIVE" : "OFF"}</p>
          </div>
          <button className="button secondary" style={{ minHeight: "32px", fontSize: "12px" }} onClick={() => setSelectedPortId(null)}>Close inspector ✕</button>
        </div>

        <div className="metric-strip" style={{ marginBottom: "16px" }}>
          <Metric label="Account Value (Equity)" value={asMoney(selectedPortfolio.currentEquityUsd)} />
          <Metric label="Free Cash" value={asMoney(selectedPortfolio.cashUsd)} />
          <Metric label="Total P&L" value={asPnl(selectedPortfolio.totalPnlUsd, selectedPortfolio.totalPnlPct).text} />
          <Metric label="Max Drawdown" value={selectedPortfolio.drawdownPct != null ? `${selectedPortfolio.drawdownPct.toFixed(2)}%` : "0.00%"} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "10px", marginBottom: "16px", fontSize: "12px" }}>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>Starting Balance</span>
            <strong>{asMoney(selectedPortfolio.initialEquityUsd)}</strong>
          </div>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>Realized P&L</span>
            <strong>{asMoney(selectedPortfolio.realizedPnlUsd)}</strong>
          </div>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>Unrealized P&L</span>
            <strong>{asMoney(selectedPortfolio.unrealizedPnlUsd)}</strong>
          </div>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>High Water Mark</span>
            <strong>{asMoney(selectedPortfolio.highWaterMarkUsd)}</strong>
          </div>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>Gross Notional</span>
            <strong>{asMoney(selectedPortfolio.grossExposureUsd)}</strong>
          </div>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>Leverage</span>
            <strong>{selectedPortfolio.leverage != null ? `${selectedPortfolio.leverage.toFixed(2)}x` : "0.00x"}</strong>
          </div>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>Fees & Costs</span>
            <strong>{asMoney(selectedPortfolio.totalCostsUsd)}</strong>
          </div>
          <div style={{ background: "var(--accent)", padding: "10px", borderRadius: "6px" }}>
            <span className="mono" style={{ display: "block", color: "var(--muted-foreground)" }}>Funding Paid / Recv</span>
            <strong>{asMoney(selectedPortfolio.totalFundingUsd)}</strong>
          </div>
        </div>

        <div style={{ marginTop: "12px" }}>
          <h4 style={{ fontSize: "13px", marginBottom: "8px" }}>Open Positions ({selectedPortfolio.positions?.length ?? 0})</h4>
          {selectedPortfolio.positions && selectedPortfolio.positions.length > 0 ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Instrument / Symbol</th>
                    <th>Side</th>
                    <th>Quantity</th>
                    <th>Entry Price</th>
                    <th>Mark Price</th>
                    <th>Notional Value</th>
                    <th>Unrealized P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedPortfolio.positions.map((pos, idx) => {
                    const pnlPos = asPnl(pos.unrealizedPnl, pos.marketValue > 0 ? (pos.unrealizedPnl / pos.marketValue * 100) : 0);
                    return (
                      <tr key={idx}>
                        <td><strong>{pos.symbol}</strong><small className="mono">{pos.instrument}</small></td>
                        <td><Badge tone={pos.side === "LONG" ? "good" : "bad"}>{pos.side}</Badge></td>
                        <td>{pos.quantity}</td>
                        <td>{asMoney(pos.entryPrice)}</td>
                        <td>{asMoney(pos.markPrice)}</td>
                        <td>{asMoney(pos.marketValue)}</td>
                        <td><Badge tone={pnlPos.tone}>{pnlPos.text}</Badge></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ padding: "14px", background: "var(--accent)", borderRadius: "6px", fontSize: "12px", color: "var(--muted-foreground)" }}>
              Zero active virtual follower positions (clean prospective epoch baseline).
            </div>
          )}
        </div>
      </section>
    )}

    <section className="panel compare-panel"><div className="compare-heading"><div><div className="eyebrow">SIDE-BY-SIDE</div><h3>Portfolio comparison</h3><p>Compare recorded configuration, account equity, and evidence metadata.</p></div><div className="compare-selects"><select value={left} onChange={(event) => setLeft(event.target.value)} aria-label="First portfolio"><option value="">Choose portfolio A</option>{portfolios.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><span>vs</span><select value={right} onChange={(event) => setRight(event.target.value)} aria-label="Second portfolio"><option value="">Choose portfolio B</option>{portfolios.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div></div>
      {leftPortfolio && rightPortfolio ? <div className="comparison-grid"><CompareColumn row={leftPortfolio} addressCount={addressCount(leftPortfolio)} /><div className="compare-divider">COMPARE</div><CompareColumn row={rightPortfolio} addressCount={addressCount(rightPortfolio)} /></div> : <div className="compare-placeholder"><Boxes size={18} /><span>Select two portfolios to compare state, equities, cash, risk, and evidence basis.</span></div>}
    </section>

    <section className="panel table-panel">
      <div className="table-toolbar">
        <div>
          <h3>Portfolio tracking ledgers</h3>
          <p>Read-only projection from authentic VPS journals and sealed registry databases.</p>
        </div>
        <div className="filters">
          <label className="search-field">
            <Search size={15} />
            <input value={portQuery} onChange={(event) => setPortQuery(event.target.value)} placeholder="Search portfolio name or ID" />
          </label>
          <select className="filter-select" value={campaignFilter} onChange={(event) => setCampaignFilter(event.target.value)} aria-label="Filter by campaign">
            <option value="all">All campaigns</option>
            <option value="cwsa">CWSA Chapter 2 ({cwsaPortfolios.length} active)</option>
            <option value="v4">Archived V4 ({archivedPortfolios.length} historical)</option>
            <option value="candidate">Candidate selections</option>
          </select>
          <select className="filter-select" value={stateFilter} onChange={(event) => setStateFilter(event.target.value)} aria-label="Filter by state">
            <option value="all">All states</option>
            {["candidate", "active", "paper", "archived", "pending"].map((x) => <option key={x}>{x}</option>)}
          </select>
          <select
            aria-label="Sort portfolios"
            value={`${sortKey}:${sortDir}`}
            onChange={(e) => {
              const [k, d] = e.target.value.split(":") as [typeof sortKey, typeof sortDir];
              setSortKey(k);
              setSortDir(d);
            }}
          >
            <option value="equity:desc">Equity: High → Low</option>
            <option value="equity:asc">Equity: Low → High</option>
            <option value="pnl:desc">P&L: High → Low</option>
            <option value="pnl:asc">P&L: Low → High</option>
            <option value="positions:desc">Positions: Most → Fewest</option>
            <option value="positions:asc">Positions: Fewest → Most</option>
            <option value="name:asc">Name: A → Z</option>
            <option value="name:desc">Name: Z → A</option>
            <option value="risk:desc">Risk: High → Low</option>
          </select>
          <button
            type="button"
            className="button secondary"
            style={{ padding: "6px 10px", fontSize: "12px", minHeight: "36px" }}
            onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
            title={`Sort direction: currently ${sortDir === "asc" ? "Ascending" : "Descending"}`}
          >
            {sortDir === "asc" ? "▲ Ascending" : "▼ Descending"}
          </button>
        </div>
      </div>
      {sorted.length ? <div className="table-scroll"><table><thead><tr>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("name")}>
          Portfolio & Campaign {sortKey === "name" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("equity")}>
          Account Value (Equity) {sortKey === "equity" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("pnl")}>
          Total P&L {sortKey === "pnl" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th>Drawdown & Peak</th>
        <th>Gross & Lev</th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("positions")}>
          Open Positions {sortKey === "positions" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
        <th>Costs & Funding</th>
        <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => handleSort("state")}>
          Risk & Status {sortKey === "state" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </th>
      </tr></thead><tbody>{sorted.map((row) => {
        const details = parseJsonObject(row.detailsJson);
        const health = (row.strategyHealth ?? details.strategyHealth) as string | undefined;
        const pnlInfo = asPnl(row.totalPnlUsd, row.totalPnlPct);
        const isSelected = selectedPortId === row.id;

        return <tr key={row.id} style={{ background: isSelected ? "var(--accent)" : undefined }}>
          <td>
            <strong>{row.name}</strong>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "3px" }}>
              <Badge tone={row.strategy === "CWSA Chapter 2" ? "blue" : row.strategy === "Archived V4 — Historical" ? "muted" : "slate"}>
                {row.strategy === "CWSA Chapter 2" ? "CWSA Ch2" : row.strategy === "Archived V4 — Historical" ? "Archived V4" : "Research"}
              </Badge>
              <small className="table-sub" style={{ margin: 0 }}>{row.podCount != null ? `${row.podCount} pods` : ""}</small>
            </div>
            {health && (
              <small className="table-sub" style={{ marginTop: "2px" }}>Health: {health}</small>
            )}
          </td>
          <td>
            <strong>{asMoney(row.currentEquityUsd)}</strong>
            <small className="table-sub">Cash: {asMoney(row.cashUsd)} · Init: {asMoney(row.initialEquityUsd)}</small>
          </td>
          <td>
            <Badge tone={pnlInfo.tone}>{pnlInfo.text}</Badge>
            <small className="table-sub">Real: {asMoney(row.realizedPnlUsd)} · Unreal: {asMoney(row.unrealizedPnlUsd)}</small>
          </td>
          <td>
            <strong>{row.drawdownPct != null ? `${row.drawdownPct.toFixed(2)}%` : "0.00%"}</strong>
            <small className="table-sub">Peak: {asMoney(row.highWaterMarkUsd)}</small>
          </td>
          <td>
            <strong>{asMoney(row.grossExposureUsd)}</strong>
            <small className="table-sub">Lev: {row.leverage != null ? `${row.leverage.toFixed(2)}x` : "0.00x"}</small>
          </td>
          <td>
            <button
              className="button secondary"
              style={{ padding: "4px 8px", fontSize: "11px", minHeight: "26px", cursor: "pointer" }}
              onClick={() => setSelectedPortId(isSelected ? null : row.id)}
              title="Click to inspect open positions"
            >
              {row.openPositionsCount != null ? `${row.openPositionsCount} positions` : "0 positions"} {isSelected ? "▲" : "▼"}
            </button>
          </td>
          <td>
            <span>Costs: {asMoney(row.totalCostsUsd)}</span>
            <small className="table-sub">Funding: {asMoney(row.totalFundingUsd)}</small>
          </td>
          <td>
            <Badge tone={statusClass(row.riskState || row.state)}>{row.riskState || labelFor(row.state)}</Badge>
            <small className="table-sub">Kill switch: {row.killSwitchActivated ? "ACTIVE" : "OFF"}</small>
          </td>
        </tr>;
      })}</tbody></table></div> : <EmptyState title="No VPS portfolio selection loaded" detail="The Site has not received a signed current-selection snapshot matching your filter." />}</section>
  </>;
}
function CompareColumn({ row, addressCount }: { row: Portfolio; addressCount: number }) {
  const details = parseJsonObject(row.detailsJson);
  const health = (row.strategyHealth ?? details.strategyHealth) as string | undefined;
  const advisory = (row.advisoryStatus ?? details.advisoryStatus) as string | undefined;
  const feeDrag = (row.feeDragUsd ?? details.feeDragUsd) as string | undefined;
  const pnlInfo = asPnl(row.totalPnlUsd, row.totalPnlPct);
  return <div className="compare-column">
    <div className="compare-name"><strong>{row.name}</strong><Badge tone={statusClass(row.state)}>{labelFor(row.state)}</Badge></div>
    <CompareMetric label="Campaign" value={row.strategy || "Candidate"} />
    <CompareMetric label="Current Equity" value={asMoney(row.currentEquityUsd)} />
    <CompareMetric label="Available Cash" value={asMoney(row.cashUsd)} />
    <CompareMetric label="Total P&L" value={pnlInfo.text} />
    <CompareMetric label="Realized P&L" value={asMoney(row.realizedPnlUsd)} />
    <CompareMetric label="Unrealized P&L" value={asMoney(row.unrealizedPnlUsd)} />
    <CompareMetric label="Max Drawdown" value={row.drawdownPct != null ? `${row.drawdownPct.toFixed(2)}%` : "0.00%"} />
    <CompareMetric label="Gross Exposure" value={asMoney(row.grossExposureUsd)} />
    <CompareMetric label="Open Positions" value={String(row.openPositionsCount ?? 0)} />
    <CompareMetric label="Wallet count" value={addressCount ? String(addressCount) : "Pending"} />
    <CompareMetric label="Pod count" value={row.podCount === null ? "Pending" : String(row.podCount)} />
    <CompareMetric label="Total risk budget" value={asMoney(row.totalRiskUsd)} />
    <CompareMetric label="Strategy health" value={health || "Pending"} />
    <CompareMetric label="Advisory status" value={advisory || "Uncalibrated"} />
    {feeDrag && <CompareMetric label="Fee drag" value={`$${feeDrag}`} />}
    <CompareMetric label="Trading Costs" value={asMoney(row.totalCostsUsd)} />
    <CompareMetric label="Evidence basis" value={labelFor(row.evidenceBasis)} />
  </div>;
}
function CompareMetric({ label, value }: { label: string; value: string }) { return <div className="compare-metric"><span>{label}</span><strong>{value}</strong></div>; }

function ExecutionPage({ records, onOpen, onStatus }: { records: OpsRecord[]; onOpen: (kind: FormKind) => void; onStatus: (record: OpsRecord, status: string) => void }) {
  const paper = records.filter((r) => r.category === "paper_state"); const execution = records.filter((r) => r.category === "execution"); const risk = records.filter((r) => r.category === "risk_budget");
  return <>
    <PageHeading eyebrow="EXECUTION / 04" title="Paper & execution" description="Monitor T+300s source transitions, fixed-k native quantity, and independent pod budgets." actions={<Button icon={Plus} onClick={() => onOpen("execution")}>Record execution evidence</Button>} />
    <div className="principle-banner"><div className="principle-mark"><Clock3 size={18} /></div><div><strong>Follower entry contract: wait 5 minutes, then submit one market order</strong><span>Record observed order timing, fill price, split behavior, and venue response. The control center cannot place or alter orders.</span></div><Badge tone="warn">VERIFY IN PAPER</Badge></div>
    <div className="execution-grid">
      <ExecutionCard title="Paper account" detail="Account identity, balance source, and active shadow state" record={paper[0]} icon={Activity} onOpen={() => onOpen("paper_state")} onStatus={onStatus} />
      <ExecutionCard title="T+5 delayed entry" detail="Single T+5 order vs observed split or delayed fills" record={execution[0]} icon={Clock3} onOpen={() => onOpen("execution")} onStatus={onStatus} />
      <ExecutionCard title="Fixed-k native quantity" detail="Frozen per-pod k × native source position; follower risk limits apply" record={risk.find((r) => /equity|sizing/i.test(r.title)) ?? risk[0]} icon={WalletCards} onOpen={() => onOpen("risk_budget")} onStatus={onStatus} />
      <ExecutionCard title="Pod-level risk budgets" detail="Independent loss budget, gross cap, and concentration limits" record={risk.find((r) => /pod|budget/i.test(r.title)) ?? risk[1]} icon={Shield} onOpen={() => onOpen("risk_budget")} onStatus={onStatus} />
    </div>
    <section className="panel notes-panel"><PanelHeader title="What each evidence receipt should include" subtitle="Keep model assumptions separate from observed paper behavior" icon={FileText} /><div className="receipt-checks"><ReceiptCheck title="T+5 timestamp" detail="First source event time, eligibility time, and actual submit time" /><ReceiptCheck title="One order outcome" detail="Order count, partial-fill/split details, and market reference price" /><ReceiptCheck title="Sizing trace" detail="Source native position, source mark, frozen k, follower quote, and Guardian limits" /><ReceiptCheck title="Pod risk" detail="Pod loss budget, portfolio caps, and any rejected intent" /></div></section>
    <div className="planned-note"><ShieldAlert size={16} /><span>Emergency controls are documented in the playbook only. This page has no trading transport or broker command path.</span></div>
  </>;
}
function ExecutionCard({ title, detail, record, icon: Icon, onOpen: _onOpen, onStatus: _onStatus }: { title: string; detail: string; record?: OpsRecord; icon: LucideIcon; onOpen: () => void; onStatus: (r: OpsRecord, s: string) => void }) {
  return <article className="panel execution-card"><div className="execution-top"><div className="execution-icon"><Icon size={17} /></div><Badge tone={record ? statusClass(record.status) : "warn"}>{record ? labelFor(record.status) : "Pending"}</Badge></div><h3>{title}</h3><p>{detail}</p>{record ? <><div className="record-preview"><strong>{record.title}</strong><span>{record.details || "No details attached."}</span><small>{labelFor(record.basis)} · {labelFor(record.quality)}</small></div><Badge tone="warn">Read-only · unverified</Badge></> : <div className="pending-line"><CircleHelp size={14} />No verified receipt</div>}<span className="record-readonly">Evidence changes require a private authenticated writer</span></article>;
}
function ReceiptCheck({ title, detail }: { title: string; detail: string }) { return <div className="receipt-check"><div className="receipt-check-icon"><Check size={14} /></div><div><strong>{title}</strong><span>{detail}</span></div></div>; }

function GatesPage({ records, onOpen, onStatus }: { records: OpsRecord[]; onOpen: (kind: FormKind) => void; onStatus: (record: OpsRecord, status: string) => void }) {
  const gates = records.filter((r) => r.category === "acceptance_gate"); const blockers = records.filter((r) => r.category === "blocker" && !["verified", "archived", "passed"].includes(r.status));
  return <>
    <PageHeading eyebrow="ACCEPTANCE / 05" title="Gates & blockers" description="Track acceptance evidence, failed checks, owners, and the next recovery action." actions={<><Button variant="secondary" icon={FileCheck2} onClick={() => onOpen("test_result")}>Record test result</Button><Button icon={Plus} onClick={() => onOpen("acceptance_gate")}>Add gate</Button></>} />
    <div className="split-panels">
      <section className="panel list-panel"><div className="table-toolbar"><div><h3>Acceptance checklist</h3><p>Close gates only when the linked receipt supports it.</p></div><Badge tone={gates.length ? "blue" : "warn"}>{gates.length} tracked</Badge></div>
        {gates.length ? <div className="ops-record-list">{gates.map((record) => <OpsRecordRow key={record.id} record={record} onStatus={onStatus} />)}</div> : <EmptyState title="No acceptance gates recorded" detail="Add evidence gates for source capture, live market data, batching, sizing, risk limits, reconciliation, and restart recovery." />}
      </section>
      <section className="panel list-panel"><div className="table-toolbar"><div><h3>Open blockers</h3><p>Every blocker needs a diagnosis and a next step.</p></div><Badge tone={blockers.length ? "warn" : "good"}>{blockers.length} open</Badge></div>
        {blockers.length ? <div className="ops-record-list">{blockers.map((record) => <OpsRecordRow key={record.id} record={record} onStatus={onStatus} />)}</div> : <EmptyState title="No open blockers recorded" detail="The current system blocker list has not been imported. This empty view is not a pass result." action={<Button variant="secondary" icon={Plus} onClick={() => onOpen("blocker")}>Add blocker</Button>} />}
        <span className="record-readonly">Blocker notes are read-only</span>
      </section>
    </div>
    <section className="recovery-strip"><div className="recovery-icon"><RefreshCw size={18} /></div><div><strong>Autonomous blocker recovery</strong><span>Diagnose → remedy → implement → verify → resume. Keep the evidence and invariants attached to the blocker record.</span></div><Button variant="secondary" onClick={() => onOpen("followup")}>Record recovery step</Button></section>
    <div className="inline-actions"><Button variant="secondary" icon={FileCheck2} onClick={() => onOpen("approval")}>Record approval</Button><Button variant="secondary" icon={Activity} onClick={() => onOpen("test_result")}>Record test outcome</Button><span>Imported notes are read-only. Only the source owners can authorize changes.</span></div>
  </>;
}
function OpsRecordRow({ record, onStatus: _onStatus }: { record: OpsRecord; onStatus: (r: OpsRecord, s: string) => void }) {
  const completed = ["verified", "passed", "approved", "merged", "deployed"].includes(record.status);
  return (
    <article className="ops-record-row">
      <div className={"record-status-icon " + statusClass(record.status)}>
        {completed ? <Check size={14} /> : <FileClock size={14} />}
      </div>
      <div className="ops-record-copy">
        <div className="ops-record-title">
          <strong>{record.title}</strong>
          <Badge tone={statusClass(record.status)}>{labelFor(record.status)}</Badge>
        </div>
        <p>{record.details || "No details attached."}</p>
        <div className="record-meta">
          <span>{labelFor(record.basis)}</span><span>·</span><span>{labelFor(record.quality)}</span>
          {record.owner ? <><span>·</span><span>{record.owner}</span></> : null}
        </div>
      </div>
      <Badge tone="warn">Unverified import</Badge>
    </article>
  );
}

function ReleasePage({ records, events, onOpen, onStatus }: { records: OpsRecord[]; events: EventRow[]; onOpen: (kind: FormKind) => void; onStatus: (record: OpsRecord, status: string) => void }) {
  const releases = records.filter((r) => r.category === "release"); const deployments = records.filter((r) => r.category === "deployment"); const grafana = records.filter((r) => r.category === "grafana"); const rollbacks = records.filter((r) => r.category === "rollback"); const followups = records.filter((r) => r.category === "followup");
  const latestDeploy = deployments.find((r) => r.status === "deployed");
  return <>
    <PageHeading eyebrow="RELEASE / 06" title="Release & runtime" description="Follow merge state, Grafana rollout, deployed revision, health, rollback receipts, and follow-up work." actions={<><Button variant="secondary" icon={BarChart3} onClick={() => onOpen("grafana")}>Record Grafana status</Button><Button icon={GitBranch} onClick={() => onOpen("deployment")}>Track deployment</Button></>} />
    <div className="runtime-banner"><div className="runtime-symbol"><GitBranch size={18} /></div><div className="runtime-main"><div className="eyebrow">PRODUCTION RUNTIME</div><strong>{latestDeploy ? latestDeploy.title : "Deployed revision unknown"}</strong><span>{latestDeploy?.details || "No verified deployment record is available. Record the deployed SHA and health receipt after checking the live service."}</span></div><Badge tone={latestDeploy ? "good" : "muted"}>{latestDeploy ? "RECORDED" : "UNKNOWN"}</Badge></div>
    <div className="release-grid">
      <ReleaseColumn title="Merge & release" icon={GitMerge} records={releases} empty="No PR, merge SHA, or release state recorded." onAdd={() => onOpen("release")} onStatus={onStatus} />
      <ReleaseColumn title="Grafana rollout" icon={BarChart3} records={grafana} empty="Dashboard migration and alert rollout state are pending." onAdd={() => onOpen("grafana")} onStatus={onStatus} />
      <ReleaseColumn title="Deployments" icon={Activity} records={deployments} empty="Deployed revision, service state, and health receipt are not verified." onAdd={() => onOpen("deployment")} onStatus={onStatus} />
    </div>
    <div className="two-up-panels">
      <section className="panel"><PanelHeader title="Rollback evidence" subtitle="A rollback plan is not a verified rollback" icon={ArrowDownRight} />{rollbacks.length ? <div className="compact-records">{rollbacks.map((r) => <OpsRecordRow key={r.id} record={r} onStatus={onStatus} />)}</div> : <EmptyState title="No rollback receipt" detail="Attach the prior revision, restore procedure, operator, and post-rollback health result." action={<Button variant="secondary" onClick={() => onOpen("rollback")}>Add rollback evidence</Button>} />}</section>
      <section className="panel"><PanelHeader title="Post-deployment follow-ups" subtitle="Keep unresolved tasks visible after release" icon={FileClock} />{followups.length ? <div className="compact-records">{followups.map((r) => <OpsRecordRow key={r.id} record={r} onStatus={onStatus} />)}</div> : <EmptyState title="No follow-ups recorded" detail="Capture monitoring windows, delayed checks, and any work left open after rollout." action={<Button variant="secondary" onClick={() => onOpen("followup")}>Add follow-up</Button>} />}</section>
    </div>
    <div className="audit-tail"><span><FileText size={14} /> {events.length} recent audit events stored</span><span>Historical import metadata only; no operator write endpoint.</span></div>
  </>;
}
function ReleaseColumn({ title, icon: Icon, records, empty, onAdd: _onAdd, onStatus }: { title: string; icon: LucideIcon; records: OpsRecord[]; empty: string; onAdd: () => void; onStatus: (r: OpsRecord, s: string) => void }) { return <section className="panel release-column"><div className="release-col-head"><div className="panel-heading-icon"><Icon size={17} /></div><div><h3>{title}</h3><p>{records.length} records</p></div></div>{records.length ? <div className="compact-records">{records.slice(0, 4).map((r) => <OpsRecordRow key={r.id} record={r} onStatus={onStatus} />)}</div> : <div className="release-empty"><span>{empty}</span><span className="record-readonly">No independent record</span></div>}</section>; }

function EvidencePage({ records, events, onOpen, basis, setBasis }: { records: OpsRecord[]; events: EventRow[]; onOpen: (kind: FormKind) => void; basis: string; setBasis: (value: string) => void }) {
  const evidenceKinds = new Set(["evidence", "decision", "approval", "test_result", "rollback"]);
  const evidence = records.filter((r) => evidenceKinds.has(r.category) && (basis === "all" || r.basis === basis));
  const decisions = records.filter((r) => r.category === "decision");
  return <>
    <PageHeading eyebrow="PROVENANCE / 07" title="Evidence & decisions" description="Keep historical results, prospective cohorts, paper outcomes, and unknowns in separate lanes." actions={<><Button variant="secondary" icon={FileCheck2} onClick={() => onOpen("evidence")}>Add evidence receipt</Button><Button icon={Plus} onClick={() => onOpen("decision")}>Add decision</Button></>} />
    <div className="evidence-lanes">{bases.map((item) => <button key={item} className={`evidence-lane ${basis === item ? "lane-active" : ""}`} onClick={() => setBasis(basis === item ? "all" : item)}><span>{labelFor(item)}</span><strong>{records.filter((r) => r.basis === item).length}</strong><small>{item === "historical" ? "Completed past window" : item === "prospective" ? "Predeclared forward cohort" : item === "paper" ? "Observed shadow account" : "Not yet classified"}</small></button>)}</div>
    <div className="two-up-panels evidence-panels"><section className="panel"><div className="table-toolbar"><div><h3>Evidence ledger</h3><p>Receipts retain source, basis, quality, and status.</p></div><select className="filter-select" value={basis} onChange={(e) => setBasis(e.target.value)}><option value="all">All evidence bases</option>{bases.map((x) => <option key={x}>{x}</option>)}</select></div>{evidence.length ? <div className="ops-record-list">{evidence.map((r) => <EvidenceRow key={r.id} record={r} />)}</div> : <EmptyState title="No matching evidence receipts" detail="Add the immutable source, data window, trial family, cohort, and result before setting a gate to verified." />}</section>
      <section className="panel"><PanelHeader title="Decision log" subtitle="Readiness calls need an explicit author and proof" icon={Shield} />{decisions.length ? <div className="ops-record-list">{decisions.map((r) => <EvidenceRow key={r.id} record={r} />)}</div> : <EmptyState title="No production-readiness decision" detail="Leave readiness pending until the acceptance evidence and current runtime are reviewed." action={<Button variant="secondary" onClick={() => onOpen("decision")}>Record decision</Button>} />}<div className="decision-note"><AlertTriangle size={14} /><span>Passing engineering checks does not by itself establish follower economics or authorize live trading.</span></div></section></div>
    <section className="panel audit-panel"><PanelHeader title="Recent change receipts" subtitle="Append-only metadata log" icon={FileClock} />{events.length ? <div className="audit-table"><div className="audit-head"><span>Entity</span><span>Change</span><span>Actor</span><span>Time</span></div>{events.slice(0, 12).map((event) => <div className="audit-row" key={event.id}><span>{labelFor(event.entityType)}</span><span>{event.action}</span><span>{event.actor}</span><span>{new Date(event.createdAt).toLocaleString()}</span></div>)}</div> : <div className="small-empty">No change events yet. New records and status updates will append here.</div>}</section>
  </>;
}
function EvidenceRow({ record }: { record: OpsRecord }) { return <article className="evidence-row"><div className="evidence-file-icon"><FileText size={15} /></div><div className="evidence-row-main"><div className="evidence-title"><strong>{record.title}</strong><Badge tone={statusClass(record.status)}>{labelFor(record.status)}</Badge></div><p>{record.details || "No summary recorded."}</p><div className="record-meta"><span>{labelFor(record.basis)}</span><span>·</span><span>Quality: {labelFor(record.quality)}</span><span>·</span><span>{labelFor(record.category)}</span></div></div>{record.sourceRef && <a className="icon-link" aria-label="Open evidence source" href={record.sourceRef.startsWith("http") ? record.sourceRef : undefined} target="_blank" rel="noreferrer"><ArrowUpRight size={14} /></a>}</article>; }

function PlaybookPage({ onOpen, blockers }: { onOpen: (kind: FormKind) => void; blockers: OpsRecord[] }) {
  const [copied, setCopied] = useState(false);
  const handoff = `Copytrade-pm operations handoff\n\nObjective: recover the open blocker without changing scope or silently lowering acceptance criteria.\n\nRequired sequence: diagnose → remedy → implement → verify → resume.\n\nBefore acting: inspect the current branch, dirty worktree, source of truth, deployed revision, and relevant evidence. Preserve unrelated work. Keep historical and prospective/paper results separate. If a required value is unknown, leave it pending.\n\nBlocker summary: ${blockers.length ? blockers.map((r) => `- ${r.title} [${r.status}] — ${r.details || "no details"}`).join("\n") : "No blockers are currently recorded; verify the source tracker before declaring clear."}\n\nReport exact changed files, test/build results, evidence receipts, remaining blockers, and whether anything was merged or deployed. Do not invoke HALT, emergency cut risk, force stop, or force close from this handoff.`;
  const copy = async () => { try { await navigator.clipboard.writeText(handoff); setCopied(true); window.setTimeout(() => setCopied(false), 2000); } catch { setCopied(false); } };
  return <>
    <PageHeading eyebrow="RUNBOOK / 08" title="Operations playbook" description="Autonomous blocker recovery and planned emergency controls, documented without command execution." actions={<Button icon={Copy} variant="secondary" onClick={() => void copy()}>{copied ? "Copied" : "Copy handoff prompt"}</Button>} />
    <section className="panel recovery-panel"><PanelHeader title="Blocker recovery loop" subtitle="Every recovery step should leave a reviewable receipt" icon={RefreshCw} /><div className="recovery-steps">{[["01", "Diagnose", "Capture the failure, scope, cause, and affected invariant."], ["02", "Remedy", "Choose the smallest safe fix and state rollback conditions."], ["03", "Implement", "Make the change in an isolated research worktree; preserve main."], ["04", "Verify", "Run the acceptance checks and attach exact outputs or receipts."], ["05", "Resume", "Continue from the blocked frontier only after evidence is recorded."]].map(([number, title, detail]) => <div className="recovery-step" key={number}><span>{number}</span><strong>{title}</strong><p>{detail}</p></div>)}</div><div className="recovery-cta"><span>Open blockers: <strong>{blockers.length}</strong>. No blocker recovery is automated by this page.</span><Button variant="secondary" onClick={() => onOpen("followup")}>Log recovery step</Button></div></section>
    <section className="panel control-panel"><div className="control-panel-head"><div><div className="eyebrow">PLANNED CONTROL PROCEDURES</div><h3>Emergency controls are documentation only</h3><p>These labels are not buttons and are not connected to trading or runtime systems.</p></div><div className="control-lock"><LockKeyhole size={18} /><span>READ ONLY</span></div></div><div className="control-grid">{[["HALT", "Stop new intents at the supervised control plane; verify latch and state reconciliation."], ["Emergency cut risk", "Execute the approved risk-reduction procedure only through the authorized system and operator."], ["Force stop", "Stop the relevant process using its runbook; preserve logs and confirm no restart loop."], ["Force close", "Use the explicitly authorized venue path; record source price, execution receipt, and residual exposure."]].map(([title, detail]) => <div className="control-item" key={title}><div className="control-item-top"><ShieldAlert size={15} /><strong>{title}</strong><Badge tone="muted">PLANNED</Badge></div><p>{detail}</p></div>)}</div><div className="control-foot">No control transport, exchange credentials, or action endpoint is configured in this Site.</div></section>
    <section className="panel handoff-panel"><div className="handoff-head"><div><div className="eyebrow">AGENT HANDOFF</div><h3>Evidence-aware recovery prompt</h3><p>Includes the current blockers without turning unknown status into a pass.</p></div><Button icon={Copy} onClick={() => void copy()}>{copied ? "Copied" : "Copy prompt"}</Button></div><pre>{handoff}</pre></section>
  </>;
}

function RecordModal({ kind, busy, onClose, onSave }: { kind: FormKind; busy: boolean; onClose: () => void; onSave: (payload: Record<string, unknown>) => Promise<void> }) {
  const [form, setForm] = useState<Record<string, string>>({ kind, status: "pending", basis: "unknown", quality: "missing", severity: "normal" });
  const [formError, setFormError] = useState("");
  const set = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const input = (name: string, label: string, placeholder = "", type = "text") => <label className="form-field"><span>{label}</span><input type={type} value={form[name] ?? ""} placeholder={placeholder} onChange={(e) => set(name, e.target.value)} /></label>;
  const select = (name: string, label: string, options: string[]) => <label className="form-field"><span>{label}</span><select value={form[name] ?? options[0]} onChange={(e) => set(name, e.target.value)}>{options.map((option) => <option key={option} value={option}>{labelFor(option)}</option>)}</select></label>;
  const textarea = (name: string, label: string, placeholder: string) => <label className="form-field full-field"><span>{label}</span><textarea value={form[name] ?? ""} placeholder={placeholder} rows={4} onChange={(e) => set(name, e.target.value)} /></label>;
  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault(); setFormError("");
    if (!form.title?.trim()) { setFormError("Add a short title."); return; }
    await onSave(form);
  };
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="record-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header className="modal-header"><div><div className="eyebrow">SQLITE REGISTRY / NEW ENTRY</div><h2 id="modal-title">{formLabels[kind]}</h2><p>Records are append-audited. Unknown values stay pending.</p></div><button className="icon-button" aria-label="Close" onClick={onClose}><X size={19} /></button></header>
    <form onSubmit={(event) => void onSubmit(event)}><div className="modal-body">
        {input("title", "Title *", kind === "decision" ? "Decision and scope" : `${formLabels[kind]} summary`)}
        <div className="form-two">{select("status", "Status", statuses)}{select("basis", "Evidence basis", bases)}</div>
        <div className="form-two">{select("quality", "Evidence quality", ["missing", "unverified", "partial", "verified"])}{select("severity", "Severity", ["low", "normal", "high", "critical"])}</div>
        <div className="form-two">{input("owner", "Owner", "Person / team")}{input("sourceRef", "Evidence / PR / deploy reference", "URL, SHA, report, or log path")}</div>
        {textarea("details", "Details and acceptance evidence", kind === "execution" ? "Submit time, order count, fill price, delay, and venue evidence" : "What was observed, how it was verified, and what remains unknown")}
      {formError && <div className="form-error"><AlertTriangle size={14} />{formError}</div>}
    </div><footer className="modal-footer"><span><LockKeyhole size={13} /> Record only · no trading control action</span><div><Button variant="quiet" onClick={onClose}>Cancel</Button><Button type="submit" disabled={busy} icon={busy ? RefreshCw : Check}>{busy ? "Saving…" : "Save to SQLite"}</Button></div></footer></form></section></div>;
}
