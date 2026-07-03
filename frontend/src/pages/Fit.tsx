import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

// Industry pain vectors (generalised) mapped to the agents that address them,
// with a live metric pulled from the running simulation.
type Cov = "covered" | "partial" | "proposed";

interface Pain {
  tag: string;
  title: string;
  desc: string;
  impact: string;
  agents: string[];
  coverage: Cov;
  metric: (k: any) => { label: string; value: string; tone: "good" | "warn" | "muted" };
}

const pct = (v: number | null) => (v == null ? "—" : (v * 100).toFixed(1) + "%");

const PAINS: Pain[] = [
  {
    tag: "Manufacturing · GxP validation",
    title: "Validating digital tools is the bottleneck",
    desc: "The hard part of digital manufacturing isn't building tools — it's qualifying them for GxP. Risk-based validation, change control, and system re-qualification slow every multi-site rollout.",
    impact: "Every change triggers IQ/OQ/PQ re-work across sites",
    agents: ["EQ-P01", "QA-P04", "EQ-P04"],
    coverage: "partial",
    metric: (k) => ({ label: "equipment awaiting requalification",
      value: String(k?.equipment?.requalification_due ?? "—"),
      tone: (k?.equipment?.requalification_due ?? 0) > 0 ? "warn" : "good" }),
  },
  {
    tag: "Quality · OOS & deviation burden",
    title: "Quality events consume QA capacity",
    desc: "OOS/OOT results and deviations demand structured investigation (FDA 2006), root-cause analysis, and CAPA — a heavy manual load that gates batch release and Right-First-Time.",
    impact: "OOS investigations + CAPAs delay disposition",
    agents: ["QA-P01", "QA-P02", "QA-P03", "ME-P04"],
    coverage: "covered",
    metric: (k) => ({ label: "current OOS rate (target ≤ 0.5%)",
      value: pct(k?.quality?.oos_rate), tone: (k?.quality?.oos_rate ?? 0) > 0.005 ? "warn" : "good" }),
  },
  {
    tag: "Supply chain · resilience & forecasting",
    title: "Unpredictable demand & material risk",
    desc: "Complex, personalised therapies and volatile demand push supply resilience to the top of the agenda — material shortages and weak suppliers threaten batch schedules.",
    impact: "At-risk suppliers threaten continuity",
    agents: ["SCP-005", "SCP-001", "SCP-003", "WM-P01"],
    coverage: "covered",
    metric: (k) => ({ label: "suppliers below risk threshold",
      value: String(k?.supply?.at_risk_suppliers ?? "—"),
      tone: (k?.supply?.at_risk_suppliers ?? 0) > 0 ? "warn" : "good" }),
  },
  {
    tag: "Manufacturing · batch release cycle time",
    title: "Slow, manual batch disposition",
    desc: "Compiling the batch package (EBR, QC, deviations, EM) for QP review is manual and slow. Faster right-first-time disposition frees capacity and shortens release cycle time.",
    impact: "Manual disposition checklists gate QP release",
    agents: ["ME-P06", "QA-P01", "WM-P05"],
    coverage: "covered",
    metric: (k) => ({ label: "batch success rate (target 98%)",
      value: pct(k?.batch?.success_rate), tone: (k?.batch?.success_rate ?? 0) >= 0.98 ? "good" : "warn" }),
  },
  {
    tag: "Sterility · environmental monitoring",
    title: "Cleanroom excursions & contamination risk",
    desc: "Aseptic operations require continuous EM; action-level excursions and particulate events must be investigated and linked to affected batches before release.",
    impact: "EM action-levels can hold sterile batches",
    agents: ["REG-P02", "WM-P04"],
    coverage: "covered",
    metric: (k) => ({ label: "EM excursion rate (recent)",
      value: pct(k?.environmental?.excursion_rate),
      tone: (k?.environmental?.excursion_rate ?? 0) > 0.03 ? "warn" : "good" }),
  },
  {
    tag: "Data · fragmentation & integrity",
    title: "Siloed LIMS ↔ MES ↔ ERP data",
    desc: "Lab, shop-floor, and enterprise data sit in silos; QC decisions are manual handoffs between LIMS and MES, creating delays and ALCOA+ data-integrity risk. Now closed by a dedicated agent that reconciles across systems and enforces ALCOA+.",
    impact: "Manual LIMS↔MES handoffs risk data integrity",
    agents: ["QA-P06"],
    coverage: "covered",
    metric: (k) => ({ label: "handoff / integrity agent live (QA-P06)", value: "✓", tone: "good" }),
  },
  {
    tag: "Pharmacovigilance · safety-case efficiency",
    title: "Manual ICSR & signal processing",
    desc: "Post-market safety case processing (ICSR triage, MedDRA coding, expedited reporting) is manual; automation targets large efficiency gains while holding reporting SLAs.",
    impact: "Expedited (7/15-day) reporting deadlines",
    agents: ["REG-P05"],
    coverage: "partial",
    metric: (k) => ({ label: "open CAPAs (quality signals)",
      value: String(k?.quality?.open_capas ?? "—"), tone: "muted" }),
  },
  {
    tag: "Enterprise AI · pilots → scale",
    title: "Isolated AI pilots don't reach the floor",
    desc: "The challenge is moving from isolated pilots to enterprise-wide agents across supply, manufacturing, quality, and regulatory — plugged into existing compute, not replacing it.",
    impact: "This framework IS that orchestration layer",
    agents: ["ME-P02", "ME-P03", "QA-P02", "REG-P02"],
    coverage: "covered",
    metric: (k) => ({ label: "GxP agents live across 6 domains", value: "31", tone: "good" }),
  },
];

const COV: Record<Cov, { label: string; cls: string }> = {
  covered: { label: "Covered", cls: "border-emerald-500 text-emerald-300" },
  partial: { label: "Partial", cls: "border-amber-500 text-amber-300" },
  proposed: { label: "Proposed agent", cls: "border-indigo-500 text-indigo-300" },
};

const SYSTEMS = [
  ["MES / EBR", "electronic batch records, recipe mgmt"],
  ["LIMS", "QC testing, results, stability"],
  ["QMS", "deviations, CAPA, change control"],
  ["ERP", "materials, batches, supply planning"],
  ["PV system", "adverse events, signals, ICSR"],
  ["Historian / PAT", "CPP time-series, process analytics"],
];

export default function Fit() {
  const [k, setK] = useState<any>(null);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});

  useEffect(() => {
    const load = () => api.kpis().then(setK).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    api.agents().then((d: any) => {
      const m: Record<string, string> = {};
      d.agents.forEach((a: any) => (m[a.id] = a.name));
      setAgentNames(m);
    });
    return () => clearInterval(t);
  }, []);

  const covered = PAINS.filter((p) => p.coverage === "covered").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Strategic Fit</h1>
        <p className="text-muted text-sm max-w-3xl">
          Where this agentic framework maps onto the pain points that dominate modern pharma
          manufacturing — each vector wired to the agents that address it, with a live metric from
          the running plant. {covered} of {PAINS.length} vectors are covered today; the rest are
          partial or flagged for a proposed agent.
        </p>
      </div>

      {/* positioning banner */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="card p-4 border-l-2 border-l-emerald-500">
          <div className="text-emerald-300 font-semibold text-sm">Validated by design</div>
          <p className="text-muted text-xs mt-1">
            Every agent action writes an immutable audit trail, and agents <span className="text-slate-200">recommend
            but never autonomously release a batch or close a deviation</span> — the GxP guardrail that
            answers "validating tools is the bottleneck" head-on.
          </p>
        </div>
        <div className="card p-4 border-l-2 border-l-indigo-500">
          <div className="text-indigo-300 font-semibold text-sm">Plugs into your stack</div>
          <p className="text-muted text-xs mt-1">
            The framework is an orchestration layer over your existing systems — not a rip-and-replace.
            The simulated plant maps to a real MES / LIMS / QMS / ERP / PV landscape:
          </p>
          <div className="flex flex-wrap gap-1 mt-2">
            {SYSTEMS.map(([s, d]) => (
              <span key={s} className="chip border-edge text-slate-300" title={d}>{s}</span>
            ))}
          </div>
        </div>
      </div>

      {/* pain → agent map */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {PAINS.map((p) => {
          const m = k ? p.metric(k) : { label: "…", value: "—", tone: "muted" as const };
          const tone = m.tone === "good" ? "text-emerald-300"
            : m.tone === "warn" ? "text-amber-300" : "text-slate-300";
          return (
            <div key={p.title} className="card p-4 flex flex-col">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] uppercase tracking-wide text-muted font-mono">{p.tag}</span>
                <span className={`chip ml-auto ${COV[p.coverage].cls}`}>{COV[p.coverage].label}</span>
              </div>
              <h3 className="font-medium">{p.title}</h3>
              <p className="text-muted text-xs mt-1 flex-1">{p.desc}</p>
              <div className="text-amber-200 text-xs mt-2">⚠ {p.impact}</div>

              {/* live metric */}
              <div className="mt-3 bg-panel2/60 border border-edge rounded-lg px-3 py-2 flex items-baseline gap-2">
                <span className={`text-xl font-bold ${tone}`}>{m.value}</span>
                <span className="text-xs text-muted">{m.label}</span>
              </div>

              {/* agents that address it */}
              <div className="mt-3">
                <div className="text-[10px] uppercase tracking-wide text-muted mb-1">
                  {p.agents.length ? "Addressed by" : "Gap — no agent yet"}
                </div>
                <div className="flex flex-wrap gap-1">
                  {p.agents.map((id) => (
                    <Link key={id} to={`/agent/${id}`}
                      title={agentNames[id] || id}
                      className="chip border-edge text-cyan-300 hover:border-indigo-500">
                      {id}
                    </Link>
                  ))}
                  {!p.agents.length && (
                    <span className="chip border-indigo-500 text-indigo-300">
                      + Data-Integrity agent (proposed)
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
