import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Agent } from "../api";

const FW_COLOR: Record<string, string> = {
  "ReAct": "border-sky-500 text-sky-300",
  "Plan-and-Execute": "border-violet-500 text-violet-300",
  "OODA": "border-amber-500 text-amber-300",
  "Tree-of-Thought": "border-rose-500 text-rose-300",
  "Generate-Critique-Revise": "border-emerald-500 text-emerald-300",
  "Reflect-and-Correct": "border-cyan-500 text-cyan-300",
};

export default function Catalog() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [domains, setDomains] = useState<any[]>([]);

  useEffect(() => {
    api.agents().then((d) => setAgents(d.agents));
    api.domains().then((d) => setDomains(d.domains));
  }, []);

  const byDomain = (code: string) => agents.filter((a) => a.domain === code);

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* main catalog */}
      <div className="flex-1 space-y-6 min-w-0">
      <div>
        <h1 className="text-xl font-semibold">Agent Catalog</h1>
        <p className="text-muted text-sm">
          31 GxP agents across 6 pharmaceutical function domains. Select an agent to run it with a
          prompt, or open the Orchestrator to watch them fire automatically on live GMP data.
        </p>
      </div>

      {domains.map((d) => (
        <section key={d.domain}>
          <div className="flex items-center gap-3 mb-2">
            <span className="w-3 h-3 rounded-full" style={{ background: d.color }} />
            <h2 className="font-semibold">{d.name}</h2>
            <span className="text-xs text-muted">{d.goal}</span>
            <span className="text-xs text-muted ml-auto">{d.total_runs} runs</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {byDomain(d.domain).map((a) => (
              <Link key={a.id} to={`/agent/${a.id}`}
                className="card p-3 hover:border-indigo-500 transition-colors group">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                    style={{ background: d.color + "22", color: d.color }}>{a.id}</span>
                  {a.depth === "full" && (
                    <span className="chip border-emerald-600 text-emerald-300">deep</span>
                  )}
                  <span className="text-muted text-xs ml-auto">{a.tool_count} tools</span>
                </div>
                <div className="font-medium text-sm group-hover:text-indigo-300">{a.name}</div>
                <div className="text-muted text-xs mt-1 line-clamp-2">{a.goal}</div>
                <div className="mt-2">
                  <span className={`chip ${FW_COLOR[a.framework] ?? "border-edge text-muted"}`}>
                    {a.framework}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
      </div>

      {/* side panel: what this plant makes */}
      <aside className="lg:w-80 shrink-0">
        <div className="card p-4 lg:sticky lg:top-20 space-y-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted">About this plant</div>
            <h2 className="font-semibold mt-0.5">What we manufacture</h2>
          </div>
          <p className="text-sm text-slate-300">
            A mid-size <span className="text-slate-100">Oral Solid Dosage (OSD)</span> pharmaceutical
            plant with a small sterile line — <span className="text-slate-100">20 drug products</span>,
            roughly <span className="text-slate-100">2,000 batches/year</span>, operating under FDA
            21 CFR 210/211/11 and ICH GMP.
          </p>
          <div>
            <div className="text-xs uppercase tracking-wide text-muted mb-1">Product mix</div>
            <ul className="text-sm text-slate-300 space-y-0.5">
              <li>• Tablets & coated (modified / enteric-release) tablets</li>
              <li>• Capsules · oral solutions · one sterile injectable</li>
              <li>• 5–1000 mg strengths · 3 controlled substances</li>
              <li>• 2 high-potency (OEB-4/5) APIs</li>
            </ul>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-muted mb-1">Process flow (tablet)</div>
            <div className="flex flex-wrap items-center gap-1 text-xs">
              {["Dispensing", "Granulation", "Drying", "Blending", "Compression",
                "Coating", "Inspection", "Packaging"].map((s, i, arr) => (
                <span key={s} className="flex items-center gap-1">
                  <span className="px-1.5 py-0.5 rounded bg-panel2 border border-edge text-slate-200">{s}</span>
                  {i < arr.length - 1 && <span className="text-muted">→</span>}
                </span>
              ))}
            </div>
          </div>
          <p className="text-xs text-muted">
            Every batch runs against an <span className="text-slate-300">Electronic Batch Record</span> with
            in-process controls and PAT; QC releases test results via <span className="text-slate-300">LIMS</span>;
            a <span className="text-slate-300">Qualified Person (QP)</span> grants final batch release. The
            agents here plan, execute, monitor, and assure that flow — but never release product autonomously.
          </p>
        </div>
      </aside>
    </div>
  );
}
