"use client";

import { useEffect, useState } from "react";
import "./owner-evidence.css";

const PORTFOLIOS = ["A", "B", "C", "Combo2", "regime.macro/TriadA", "regime.macro/TriadChop"] as const;
const DIMENSIONS = [
  "registry_integrity", "research_selection_proof", "portfolio_seal",
  "source_observation", "independent_executable_quotes", "mandate",
  "paper_finance", "risk", "guardian_authorization",
] as const;

type OwnerView = {
  schema: "cwsa_chapter2_site_owner_view_v1";
  source_schema: string;
  observed_at: string;
  assessment_asof: string;
  scope: {
    portfolio: string;
    inspection: string;
    epoch: string | null;
    version: number | null;
    selection_known_at: string | null;
    new_risk_source_status: string;
  };
  dimensions: Record<string, { state: string; owner: string; missing_or_stale_members?: string[] }>;
  generation_consistency: { state: string; reasons: string[] };
  fault_isolation: {
    affected_portfolios: string[];
    unaffected_source_portfolios: string[];
    shared_account_risk: { state: string; owner: string };
  };
  owner_heads: {
    registry?: { inventory_sha256?: string | null };
    portfolio_seal?: { definition_sha256?: string | null };
    source?: {
      head_sha256?: string | null;
      source_heads_by_wallet?: Record<string, string | null>;
      original_checkpoint_by_wallet_ms?: Record<string, number | null>;
      receipt_first_known_ms_by_wallet?: Record<string, number | null>;
      published_ms_by_wallet?: Record<string, number | null>;
    };
  };
  economics: {
    realized_pnl_usd: string | null;
    total_costs_usd: string | null;
    current_equity_usd: string | null;
    drawdown_usd: string | null;
  };
  blockers: { reason_code: string; owner: string; affected_portfolio: string }[];
  next_operation: { id: string; effect_class: "READ_ONLY"; auto_dispatched: false; required_arguments: string[] } | null;
  prior_to_current: { changed_wallets?: string[]; invalidated_conclusions?: string[] } | null;
  order_route: "NONE";
  trading_authorized: false;
  financially_active: boolean;
};

function shown(value: number | string | null | undefined): string {
  return value === null || value === undefined || value === "" ? "UNKNOWN" : String(value);
}
function stateTone(state: string): string {
  if (state === "MIXED" || state === "BLOCKED" || state === "BLOCKED_EVIDENCE") return "bad";
  if (state === "VERIFIED" || state === "SOURCE_SCOPE_READY" || state === "OBSERVE_READY") return "blue";
  return "muted";
}
function State({ state }: { state: string }) {
  return <span className={`badge ${stateTone(state)}`}>{shown(state)}</span>;
}
function Cell({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div className="owner-cell"><span>{label}</span><strong>{shown(value)}</strong></div>;
}

/** Display the owner projection verbatim; no admission, risk or finance computation. */
export default function OwnerEvidencePanel() {
  const [portfolio, setPortfolio] = useState<string>("A");
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState<OwnerView | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "unknown">("loading");

  useEffect(() => {
    const controller = new AbortController();
    setView(null);
    setState("loading");
    const query = new URLSearchParams({ portfolio, inspection: "evidence" });
    void fetch(`/api/owner-view?${query}`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("OWNER_UNAVAILABLE");
        const candidate = await response.json() as OwnerView;
        if (
          candidate.schema !== "cwsa_chapter2_site_owner_view_v1" ||
          candidate.source_schema !== "cwsa_chapter2_task_explanation_v1" ||
          candidate.scope?.portfolio !== portfolio ||
          candidate.trading_authorized !== false ||
          candidate.order_route !== "NONE" ||
          (candidate.next_operation !== null && (
            candidate.next_operation?.effect_class !== "READ_ONLY" ||
            candidate.next_operation?.auto_dispatched !== false
          ))
        ) throw new Error("OWNER_SCOPE_OR_PERMISSION_UNVERIFIED");
        if (!controller.signal.aborted) { setView(candidate); setState("ready"); }
      })
      .catch(() => { if (!controller.signal.aborted) setState("unknown"); });
    return () => controller.abort();
  }, [portfolio, revision]);

  const heads = view?.owner_heads?.source;
  const aliases = Object.keys(heads?.original_checkpoint_by_wallet_ms ?? heads?.source_heads_by_wallet ?? {});
  return <section className="panel owner-evidence" aria-label="Chapter 2 owner evidence">
    <div className="owner-evidence-header">
      <div>
        <h3>Chapter 2 · native owner evidence</h3>
        <p>Same read-only projection as CLI. Source readiness does not clear finance, Guardian or running-release proof.</p>
      </div>
      <div className="owner-evidence-controls">
        <label htmlFor="owner-portfolio">Portfolio</label>
        <select id="owner-portfolio" aria-label="Chapter 2 portfolio" value={portfolio} onChange={event => setPortfolio(event.target.value)}>
          {PORTFOLIOS.map(id => <option key={id} value={id}>{id}</option>)}
        </select>
        <button type="button" className="button secondary" onClick={() => setRevision(i => i + 1)}>Refresh owner evidence</button>
      </div>
    </div>
    {state !== "ready" || !view ? <div className="owner-empty" role="status">
      {state === "loading" ? "Reading original owner evidence…" : "UNKNOWN — owner evidence unavailable. No source, finance or process readiness inferred."}
    </div> : <>
      <div className="owner-evidence-grid">
        <Cell label="Owner schema" value={view.schema} />
        <Cell label="Portfolio version" value={view.scope.version} />
        <Cell label="Seal known at (UTC)" value={view.scope.selection_known_at} />
        <Cell label="Assessment at (UTC)" value={view.assessment_asof} />
      </div>
      <div className="owner-evidence-states">
        <div><span>New-risk source scope</span><State state={view.scope.new_risk_source_status} /></div>
        <div><span>Generation coherence</span><State state={view.generation_consistency?.state ?? "UNKNOWN"} /></div>
        <div><span>Shared-account risk</span><State state={view.fault_isolation?.shared_account_risk?.state ?? "UNKNOWN"} /></div>
        <div><span>Installed / running revision proof</span><State state="UNKNOWN" /></div>
      </div>
      <div className="owner-evidence-grid">
        {DIMENSIONS.map(name => <div className="owner-dimension" key={name}>
          <span>{name.replaceAll("_", " ")}</span>
          <State state={view.dimensions?.[name]?.state ?? "UNKNOWN"} />
        </div>)}
      </div>
      <div className="owner-evidence-grid">
        <Cell label="Source head SHA-256" value={heads?.head_sha256} />
        <Cell label="Registry inventory SHA-256" value={view.owner_heads?.registry?.inventory_sha256} />
        <Cell label="Portfolio seal SHA-256" value={view.owner_heads?.portfolio_seal?.definition_sha256} />
        <Cell label="Original evidence inspection" value={view.scope.inspection} />
      </div>
      <div className="owner-evidence-section">
        <h4>Original wallet clocks (UTC epoch milliseconds)</h4>
        {aliases.length ? <div className="table-scroll"><table className="owner-clock-table"><thead><tr>
          <th>Wallet alias</th><th>Checkpoint</th><th>First known</th><th>Published</th><th>Source head</th>
        </tr></thead><tbody>{aliases.map(alias => <tr key={alias}>
          <td>{alias}</td><td>{shown(heads?.original_checkpoint_by_wallet_ms?.[alias])}</td>
          <td>{shown(heads?.receipt_first_known_ms_by_wallet?.[alias])}</td>
          <td>{shown(heads?.published_ms_by_wallet?.[alias])}</td>
          <td className="owner-hash">{shown(heads?.source_heads_by_wallet?.[alias])}</td>
        </tr>)}</tbody></table></div> : <p>UNKNOWN — original wallet clocks were not available from this owner read.</p>}
      </div>
      <div className="owner-evidence-grid owner-finance">
        <Cell label="Realized modeled P&L (USD)" value={view.economics?.realized_pnl_usd} />
        <Cell label="Total modeled costs (USD)" value={view.economics?.total_costs_usd} />
        <Cell label="Current modeled equity (USD)" value={view.economics?.current_equity_usd} />
        <Cell label="Modeled drawdown (USD)" value={view.economics?.drawdown_usd} />
      </div>
      <div className="owner-evidence-section">
        <h4>Scoped blockers · {view.blockers?.length ?? 0}</h4>
        {view.blockers?.length ? <ul className="owner-blockers">{view.blockers.map((blocker, i) =>
          <li key={`${blocker.reason_code}-${i}`}><strong>{blocker.reason_code}</strong> · {blocker.affected_portfolio} · {blocker.owner}</li>,
        )}</ul> : <p>No blockers returned for this scope; not a Guardian approval.</p>}
        <p>Affected source portfolios: {view.fault_isolation?.affected_portfolios?.join(", ") || "UNKNOWN"}</p>
        <p>Unaffected source portfolios: {view.fault_isolation?.unaffected_source_portfolios?.join(", ") || "UNKNOWN"} (source scope only)</p>
        <p>Generation reasons: {view.generation_consistency?.reasons?.join(", ") || "UNKNOWN"}</p>
        <p>Causal delta: {view.prior_to_current ? shown(view.prior_to_current.changed_wallets?.join(", ")) : "UNKNOWN — no prior owner snapshot"}</p>
      </div>
      <div className="owner-next-operation">
        Suggested READ_ONLY operation: {view.next_operation?.id ?? "UNKNOWN"} · never dispatched by this UI
      </div>
      <div className="record-readonly">No account access, broker or evidence-write action. Trading authorization: NO.</div>
    </>}
  </section>;
}
