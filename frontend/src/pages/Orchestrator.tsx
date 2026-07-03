import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type OrchEvent, type RunSummary } from "../api";
import TraceView from "../components/TraceView";

interface FeedItem { kind: string; text: string; ts: string; severity?: string; }

export default function Orchestrator() {
  const [status, setStatus] = useState<any>(null);
  const [events, setEvents] = useState<OrchEvent[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [mode, setMode] = useState("DETERMINISTIC");
  const [selected, setSelected] = useState<OrchEvent | null>(null);
  const [cascadeRuns, setCascadeRuns] = useState<RunSummary[]>([]);
  const [runDetail, setRunDetail] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = () => {
    api.orchStatus().then(setStatus).catch(() => {});
    api.orchEvents(30).then((d) => setEvents(d.events)).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      const p = JSON.parse(e.data);
      const now = new Date().toLocaleTimeString();
      if (p.type === "anomaly") {
        setFeed((f) => [{ kind: "anomaly", severity: p.severity,
          text: `⚠ ${p.signal_type} → ${p.cascade.join(" → ")} · ${p.description}`, ts: now }, ...f].slice(0, 60));
        refresh();
      } else if (p.type === "agent_run") {
        setFeed((f) => [{ kind: "run",
          text: `   ↳ ${p.agent_id} ran (${p.tool_calls} tools) — ${p.status}`, ts: now }, ...f].slice(0, 60));
      } else if (p.type === "tick") {
        setFeed((f) => [{ kind: "tick",
          text: `tick ${p.tick} · ${p.sim_time?.slice(0, 16)} · health↓${p.emitted.health_updates} downtime+${p.emitted.downtime} qFail+${p.emitted.quality_fails}`, ts: now }, ...f].slice(0, 60));
      }
    };
    const poll = setInterval(refresh, 4000);
    return () => { ws.close(); clearInterval(poll); };
  }, []);

  const openEvent = (e: OrchEvent) => {
    setSelected(e); setRunDetail(null);
    api.runs({ orchestration_id: e.event_id, limit: "10" }).then((d) => setCascadeRuns(d.runs));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold">Autonomous Orchestrator</h1>
          <p className="text-muted text-sm">
            A watcher agent advances the live plant simulation, detects anomalies, and dispatches
            the mapped agent cascades automatically.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <select value={mode} onChange={(e) => setMode(e.target.value)}
            className="bg-panel2 border border-edge rounded-lg px-2 py-1.5 text-sm">
            <option value="DETERMINISTIC">Deterministic (fast)</option>
            <option value="LLM">Claude (real reasoning)</option>
          </select>
          {status?.running ? (
            <button onClick={() => api.orchStop().then(refresh)} className="btn btn-ghost">■ Stop</button>
          ) : (
            <button onClick={() => api.orchStart(mode).then(refresh)} className="btn btn-primary">▶ Start</button>
          )}
          <button onClick={() => api.orchTick().then(refresh)} className="btn btn-ghost">⏭ Step</button>
        </div>
      </div>

      {/* status strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Status" value={status?.running ? "RUNNING" : "idle"}
          color={status?.running ? "#34d399" : "#8ea2c4"} />
        <Stat label="Sim time" value={status?.sim_time?.slice(0, 16) ?? "—"} />
        <Stat label="Tick" value={status?.tick ?? 0} />
        <Stat label="Anomalies handled" value={status?.total_events ?? 0} />
        <Stat label="Orchestrated runs" value={status?.total_orchestrated_runs ?? 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* live feed */}
        <div className="card p-4">
          <h2 className="font-semibold mb-2">Live event stream</h2>
          <div className="font-mono text-xs space-y-1 max-h-[420px] overflow-y-auto">
            {feed.length === 0 && <div className="text-muted">Start the orchestrator (or Step) to see live events…</div>}
            {feed.map((f, i) => (
              <div key={i} className={
                f.kind === "anomaly" ? "text-amber-300" :
                f.kind === "run" ? "text-cyan-300" : "text-muted"}>
                <span className="text-slate-600 mr-2">{f.ts}</span>{f.text}
              </div>
            ))}
          </div>
        </div>

        {/* events list */}
        <div className="card p-4">
          <h2 className="font-semibold mb-2">Anomaly → cascade log</h2>
          <div className="space-y-1 max-h-[420px] overflow-y-auto">
            {events.map((e) => (
              <button key={e.event_id} onClick={() => openEvent(e)}
                className={`w-full text-left border rounded-lg px-3 py-2 hover:border-indigo-500 ${selected?.event_id === e.event_id ? "border-indigo-500 bg-panel2" : "border-edge"}`}>
                <div className="flex items-center gap-2">
                  <span className={`chip ${sevColor(e.severity)}`}>{e.severity}</span>
                  <span className="font-mono text-xs text-slate-200">{e.signal_type}</span>
                  <span className="text-muted text-xs ml-auto">t{e.tick}</span>
                </div>
                <div className="text-xs text-muted mt-1">{e.description}</div>
                <div className="flex items-center gap-1 mt-1">
                  {e.dispatched_agents.map((a, i) => (
                    <span key={a} className="text-xs">
                      <span className="font-mono text-cyan-300">{a}</span>
                      {i < e.dispatched_agents.length - 1 && <span className="text-muted mx-0.5">→</span>}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* selected cascade detail */}
      {selected && (
        <div className="card p-4">
          <h2 className="font-semibold mb-1">Cascade {selected.event_id}</h2>
          <p className="text-muted text-sm mb-3">{selected.description}</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {cascadeRuns.slice().reverse().map((r) => (
              <button key={r.run_id} onClick={() => api.runDetail(r.run_id).then(setRunDetail)}
                className={`text-left card p-3 hover:border-indigo-500 ${runDetail?.run_id === r.run_id ? "border-indigo-500" : ""}`}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-cyan-300">{r.agent_id}</span>
                  <span className="text-muted text-xs ml-auto">{r.tool_calls} tools</span>
                </div>
                <div className="text-sm">{r.agent_name}</div>
                <div className="text-xs text-muted mt-1 line-clamp-2">{r.result_preview}</div>
              </button>
            ))}
          </div>
          {runDetail && (
            <div className="mt-4 border-t border-edge pt-3">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-semibold">{runDetail.agent_id} · {runDetail.agent_name}</h3>
                <Link to={`/agent/${runDetail.agent_id}`} className="text-xs text-indigo-300 hover:underline ml-auto">open agent →</Link>
              </div>
              <TraceView trace={runDetail.trace} />
              <pre className="mt-3 text-sm whitespace-pre-wrap bg-panel2/60 border border-edge rounded-lg px-3 py-2">
                {runDetail.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: any; color?: string }) {
  return (
    <div className="card p-3">
      <div className="text-muted text-xs">{label}</div>
      <div className="text-lg font-semibold" style={{ color: color ?? "#e6edf7" }}>{value}</div>
    </div>
  );
}
function sevColor(s: string) {
  return s === "CRITICAL" || s === "EMERGENCY" ? "border-rose-500 text-rose-300" :
    s === "ALERT" ? "border-amber-500 text-amber-300" : "border-edge text-muted";
}
