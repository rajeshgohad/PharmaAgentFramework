import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type RunResult, type RunSummary } from "../api";
import TraceView from "../components/TraceView";

export default function AgentPage() {
  const { id } = useParams();
  const [agent, setAgent] = useState<any>(null);
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<string>("DETERMINISTIC");
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [recent, setRecent] = useState<RunSummary[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!id) return;
    api.agent(id).then((a) => {
      setAgent(a);
      setPrompt(defaultPrompt(a));
    });
    api.runs({ agent_id: id, limit: "8" }).then((d) => setRecent(d.runs));
    api.health().then((h) => setLlmEnabled(!!h.llm_enabled)).catch(() => {});
  }, [id]);

  const doRun = async () => {
    if (!id) return;
    setRunning(true); setErr(""); setResult(null);
    try {
      const r = await api.run(id, prompt, mode);
      setResult(r);
      api.runs({ agent_id: id, limit: "8" }).then((d) => setRecent(d.runs));
    } catch (e: any) { setErr(String(e)); }
    setRunning(false);
  };

  if (!agent) return <div className="text-muted">Loading…</div>;
  const color = agent.domain_color;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
      {/* left: spec */}
      <div className="space-y-4">
        <Link to="/catalog" className="text-muted text-sm hover:text-white">← Catalog</Link>
        <div className="card p-4">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs px-1.5 py-0.5 rounded"
              style={{ background: color + "22", color }}>{agent.id}</span>
            <span className="chip border-edge text-muted">{agent.domain_name}</span>
          </div>
          <h1 className="text-lg font-semibold mt-2">{agent.name}</h1>
          <p className="text-sm text-slate-300 mt-1">{agent.goal}</p>
          <div className="mt-3 text-sm">
            <div className="text-muted text-xs uppercase tracking-wide mb-1">Reasoning framework</div>
            <div className="font-medium">{agent.framework}</div>
            <div className="text-muted text-xs">{agent.framework_desc}</div>
          </div>
          <div className="mt-3">
            <div className="text-muted text-xs uppercase tracking-wide mb-1">Triggers</div>
            <div className="flex flex-wrap gap-1">
              {agent.triggers.map((t: string) => (
                <span key={t} className="chip border-edge text-slate-300">{t}</span>
              ))}
            </div>
          </div>
          <div className="mt-3">
            <div className="text-muted text-xs uppercase tracking-wide mb-1">
              Tools ({agent.tools_detail.length})</div>
            <div className="space-y-1">
              {agent.tools_detail.map((t: any) => (
                <div key={t.name} className="text-xs">
                  <span className="font-mono text-cyan-300">{t.name}</span>
                  <span className="text-muted"> · {t.tool_id}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-muted uppercase tracking-wide mb-1">Sends to</div>
              {agent.sends_to.length ? agent.sends_to.map((s: string) => (
                <Link key={s} to={`/agent/${s}`} className="block text-indigo-300 hover:underline">{s}</Link>
              )) : <span className="text-muted">—</span>}
            </div>
            <div>
              <div className="text-muted uppercase tracking-wide mb-1">Receives from</div>
              {agent.receives_from.length ? agent.receives_from.map((s: string) => (
                <Link key={s} to={`/agent/${s}`} className="block text-indigo-300 hover:underline">{s}</Link>
              )) : <span className="text-muted">—</span>}
            </div>
          </div>
          <div className="mt-3 text-xs">
            <div className="text-muted uppercase tracking-wide mb-1">Escalation</div>
            <div className="text-amber-200">{agent.escalation}</div>
          </div>
        </div>
      </div>

      {/* right: runner */}
      <div className="lg:col-span-2 space-y-4">
        <div className="card p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-semibold">Run agent</h2>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted">reasoning</span>
              <button onClick={() => setMode("DETERMINISTIC")}
                className={`btn ${mode === "DETERMINISTIC" ? "btn-primary" : "btn-ghost"}`}>
                Deterministic
              </button>
              <button onClick={() => llmEnabled && setMode("LLM")} disabled={!llmEnabled}
                title={llmEnabled ? "Use the Claude API for this run" : "Set ANTHROPIC_API_KEY in backend/.env to enable"}
                className={`btn ${mode === "LLM" ? "btn-primary" : "btn-ghost"} ${!llmEnabled ? "opacity-40 cursor-not-allowed" : ""}`}>
                Claude{!llmEnabled && " (no key)"}
              </button>
            </div>
          </div>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
            className="w-full bg-ink border border-edge rounded-lg px-3 py-2 text-sm resize-y"
            placeholder="Give the agent a task…" />
          <div className="flex items-center gap-3 mt-2">
            <button onClick={doRun} disabled={running} className="btn btn-primary disabled:opacity-50">
              {running ? "Running…" : "▶ Run"}
            </button>
            {result && (
              <span className="text-xs text-muted">
                {result.reasoning_mode} · {result.tool_calls} tool calls · {result.status}
              </span>
            )}
          </div>
          {err && <div className="text-rose-300 text-sm mt-2">{err}</div>}
        </div>

        {result && (
          <div className="card p-4">
            <h3 className="font-semibold mb-2">Reasoning trace</h3>
            <TraceView trace={result.trace} />
            <div className="mt-4">
              <h3 className="font-semibold mb-1">Conclusion</h3>
              <pre className="text-sm text-slate-200 whitespace-pre-wrap bg-panel2/60 border border-edge rounded-lg px-3 py-2">
                {result.result}
              </pre>
            </div>
          </div>
        )}

        <div className="card p-4">
          <h3 className="font-semibold mb-2">Recent runs</h3>
          {recent.length === 0 && <div className="text-muted text-sm">No runs yet.</div>}
          <div className="space-y-1">
            {recent.map((r) => (
              <div key={r.run_id} className="flex items-center gap-2 text-xs border-b border-edge/50 py-1">
                <span className={`chip ${r.trigger_type === "ORCHESTRATED" ? "border-cyan-600 text-cyan-300" : "border-edge text-muted"}`}>
                  {r.trigger_type}
                </span>
                <span className="text-muted">{r.reasoning_mode}</span>
                <span className="text-slate-300">{r.tool_calls} calls</span>
                <span className="text-muted ml-auto">{r.started_at?.slice(0, 19)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function defaultPrompt(a: any): string {
  const map: Record<string, string> = {
    "ME-P04": "A CRITICAL deviation occurred during compression on the latest batch. Investigate the root cause and act.",
    "QA-P02": "An OOS assay result was flagged on product PRD-005. Run the FDA-2006 OOS investigation.",
    "QA-P01": "Scan recent analytical results for OOS and initiate investigations where needed.",
    "QA-P05": "Trend the stability data for PRD-005 and flag any shelf-life risk.",
    "ME-P06": "Compile the batch disposition readiness checklist for the latest batch and recommend go/no-go.",
    "EQ-P01": "Find equipment with qualification expiring soon and recommend action.",
    "SCP-003": "Score suppliers and flag any at risk of disqualification.",
    "REG-P02": "Review environmental monitoring in the aseptic filling area and act on any action-level excursions.",
    "REG-P05": "Check post-market safety signals for PRD-005 and recommend action.",
  };
  return map[a.id] ?? `As the ${a.name}, ${a.goal.split(".")[0].toLowerCase()}.`;
}
