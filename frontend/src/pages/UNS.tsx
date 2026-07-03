import { useEffect, useMemo, useState } from "react";

interface Sys { id: string; name: string; layer: string; color: string; protocol: string; publishes: string; consumer?: boolean; tables?: { name: string; rows: number | null }[]; }

export default function UNS() {
  const [systems, setSystems] = useState<Sys[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [tree, setTree] = useState<any>(null);
  const [batches, setBatches] = useState<any[]>([]);
  const [sel, setSel] = useState<string>("");
  const [b360, setB360] = useState<any>(null);
  const [mode, setMode] = useState<"uns" | "p2p">("uns");
  const [feed, setFeed] = useState<any[]>([]);
  const [live, setLive] = useState(false);
  const [selSys, setSelSys] = useState<Sys | null>(null);
  const [tblName, setTblName] = useState("");
  const [tblData, setTblData] = useState<any>(null);

  const openTable = (name: string) => {
    setTblName(name); setTblData(null);
    fetch(`/api/tables/${name}`).then((r) => r.json()).then(setTblData);
  };

  const refreshLatest = () => {
    fetch("/api/uns/stats").then((r) => r.json()).then(setStats);
    fetch("/api/uns/tree").then((r) => r.json()).then(setTree);
  };

  useEffect(() => {
    fetch("/api/uns/systems").then((r) => r.json()).then((d) => setSystems(d.systems));
    fetch("/api/uns/batches").then((r) => r.json()).then((d) => {
      setBatches(d.batches); if (d.batches?.[0]) setSel(d.batches[0].batch_id);
    });
    fetch("/api/uns/events").then((r) => r.json()).then((d) => setFeed(d.events || []));
    refreshLatest();

    // live: subscribe to the namespace over WebSocket
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage = (e) => {
      const p = JSON.parse(e.data);
      if (p.type === "uns" && p.events?.length) {
        setLive(true);
        setFeed((f) => [...p.events, ...f].slice(0, 80));
        refreshLatest();
        setTimeout(() => setLive(false), 800);
      }
    };
    const poll = setInterval(refreshLatest, 5000);
    return () => { ws.close(); clearInterval(poll); };
  }, []);

  useEffect(() => {
    if (sel) fetch(`/api/uns/batch/${sel}`).then((r) => r.json()).then(setB360);
  }, [sel]);

  const onPrem = systems.filter((s) => s.layer === "on-prem");
  const cloud = systems.filter((s) => s.layer === "cloud");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Unified Namespace</h1>
        <p className="text-muted text-sm max-w-3xl">
          The plant's systems — on-premise OT/IT and cloud SaaS — publish their state into one
          ISA-95 hierarchical namespace. Instead of brittle point-to-point integrations, every
          system talks through a single source of truth that agents, dashboards, and a digital twin
          all subscribe to.
        </p>
      </div>

      {/* connectivity diagram */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <h2 className="font-semibold">How the systems talk</h2>
          <div className="ml-auto flex items-center gap-2 text-xs">
            <button onClick={() => setMode("p2p")}
              className={`btn ${mode === "p2p" ? "btn-primary" : "btn-ghost"}`}>Point-to-point (today)</button>
            <button onClick={() => setMode("uns")}
              className={`btn ${mode === "uns" ? "btn-primary" : "btn-ghost"}`}>Unified Namespace</button>
          </div>
        </div>
        <Diagram onPrem={onPrem} cloud={cloud} mode={mode}
          onSelect={(s) => { setSelSys(s); setTblName(""); setTblData(null); }} />
        <div className="text-xs text-muted mt-2">
          {mode === "p2p" ? (
            <><span className="text-rose-300">Today:</span> {stats?.point_to_point_links ?? "—"} brittle
            point-to-point links between {systems.length} systems (grows with the square of systems).
            Lab, shop-floor, and enterprise data stay siloed; QC decisions are manual handoffs.</>
          ) : (
            <><span className="text-emerald-300">With a UNS:</span> just {stats?.uns_links ?? systems.length}
            {" "}connections — each system publishes once to the namespace; any consumer subscribes.
            One live, contextualised source of truth feeding agents and the digital twin.</>
          )}
        </div>
        <div className="text-[11px] text-muted mt-2">
          Tip: click any system above to open its own database tables — the silo behind the namespace.
        </div>
      </div>

      {/* drill-down: a selected system's own tables + data */}
      {selSys && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-3 h-3 rounded" style={{ background: selSys.color }} />
            <h2 className="font-semibold" style={{ color: selSys.color }}>Inside {selSys.name}</h2>
            <span className="chip border-edge text-muted text-[10px]">{selSys.layer}</span>
            <span className="chip border-edge text-muted text-[10px]">{selSys.protocol}</span>
            <button onClick={() => { setSelSys(null); setTblData(null); }}
              className="btn btn-ghost ml-auto text-xs">✕ close</button>
          </div>
          <p className="text-muted text-xs mb-3">
            {selSys.publishes}. This system's own tables — the silo the UNS unifies. Click a table to
            preview its data (first 10 rows).
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            {selSys.tables?.map((t) => (
              <button key={t.name} onClick={() => openTable(t.name)}
                className={`chip ${tblName === t.name ? "border-indigo-500 text-indigo-300" : "border-edge text-slate-300 hover:border-indigo-500"}`}>
                <span className="font-mono">{t.name}</span>
                <span className="text-muted ml-1">{t.rows?.toLocaleString() ?? "—"}</span>
              </button>
            ))}
          </div>
          {tblData && (
            <>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-sm text-cyan-300">{tblData.name}</span>
                <span className="text-xs text-muted">
                  showing {tblData.showing} of {tblData.total?.toLocaleString?.()} rows · {tblData.columns?.length} columns
                </span>
              </div>
              <div className="overflow-auto max-h-[50vh] border border-edge rounded-lg">
                <table className="text-xs w-full">
                  <thead className="sticky top-0 bg-panel2">
                    <tr>{tblData.columns.map((c: string) => (
                      <th key={c} className="text-left px-2 py-1.5 font-mono text-slate-300 border-b border-edge whitespace-nowrap">{c}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {tblData.rows.map((r: any, i: number) => (
                      <tr key={i} className="odd:bg-ink/40 hover:bg-panel2/60">
                        {tblData.columns.map((c: string) => (
                          <td key={c} className="px-2 py-1 font-mono text-slate-200 border-b border-edge/40 max-w-[220px] truncate"
                            title={cell(r[c])}>{cell(r[c])}</td>
                        ))}
                      </tr>
                    ))}
                    {tblData.rows.length === 0 && (
                      <tr><td className="px-2 py-3 text-muted" colSpan={tblData.columns.length}>(empty table)</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Systems unified" value={stats?.systems_unified ?? "—"} />
        <Stat label="On-premise" value={stats?.on_prem ?? "—"} color="#22d3ee" />
        <Stat label="Cloud" value={stats?.cloud ?? "—"} color="#6366f1" />
        <Stat label="Messages published" value={stats?.messages_published?.toLocaleString?.() ?? "—"} color="#34d399" />
        <Stat label="Integration links" value={`${stats?.point_to_point_links ?? "—"} → ${stats?.uns_links ?? "—"}`}
          color="#34d399" />
      </div>

      {/* live event stream */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-2">
          <h2 className="font-semibold">Live namespace stream</h2>
          <span className={`chip ${live ? "border-emerald-500 text-emerald-300" : "border-edge text-muted"}`}>
            {live ? "● publishing" : "idle"}
          </span>
          <span className="text-muted text-xs ml-auto">
            report-by-exception · run the Orchestrator to see systems publish
          </span>
        </div>
        <div className="font-mono text-[11px] space-y-0.5 max-h-64 overflow-y-auto">
          {feed.length === 0 && <div className="text-muted">No messages yet — start the Orchestrator (Start / Step).</div>}
          {feed.map((e, i) => (
            <div key={i} className="flex items-center gap-2 py-0.5 border-b border-edge/30">
              <span className="px-1.5 rounded text-[10px] shrink-0"
                style={{ color: e.color, border: `1px solid ${e.color}55` }}>{e.source_name}</span>
              <span className="text-slate-300 truncate">{e.topic}</span>
              <span className="ml-auto text-slate-100 shrink-0">{e.value}</span>
              {e.status && <span className={`chip text-[10px] shrink-0 ${statusCls(e.status)}`}>{e.status}</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* live namespace tree */}
        <div className="card p-4">
          <h2 className="font-semibold mb-1">Namespace <span className="text-muted text-xs font-normal">(ISA-95 · latest values)</span></h2>
          <div className="font-mono text-xs mt-2 max-h-[420px] overflow-y-auto">
            {tree ? <TreeNode node={tree} depth={0} /> : <span className="text-muted">Loading…</span>}
          </div>
        </div>

        {/* batch-360 */}
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <h2 className="font-semibold">Batch 360°</h2>
            <span className="text-muted text-xs">one batch, every system</span>
            <select value={sel} onChange={(e) => setSel(e.target.value)}
              className="ml-auto bg-panel2 border border-edge rounded-lg px-2 py-1 text-xs">
              {batches.map((b) => <option key={b.batch_id} value={b.batch_id}>{b.batch_number}</option>)}
            </select>
          </div>
          {b360?.namespace && (
            <div className="font-mono text-[11px] text-muted mb-2">{b360.namespace}</div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {b360?.panels?.map((p: any) => (
              <div key={p.system} className="border border-edge rounded-lg p-2"
                style={{ borderLeft: `3px solid ${p.color}` }}>
                <div className="flex items-center gap-1 mb-1">
                  <span className="text-xs font-medium" style={{ color: p.color }}>{p.name}</span>
                  <span className="chip ml-auto border-edge text-muted text-[10px]">{p.layer}</span>
                </div>
                {p.items.map((it: any, i: number) => (
                  <div key={i} className="flex items-baseline gap-2 text-xs py-0.5">
                    <span className="text-muted">{it.label}</span>
                    <span className="ml-auto text-slate-200">{it.value}</span>
                    {it.status && (
                      <span className={`chip text-[10px] ${statusCls(it.status)}`}>{it.status}</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted mt-2">
            One batch's full state — MES, historian, LIMS, QMS, ERP — assembled from the namespace
            in one place. This is the data-isolation problem, solved.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── connectivity SVG ────────────────────────────────────────────────────────
function Diagram({ onPrem, cloud, mode, onSelect }:
  { onPrem: Sys[]; cloud: Sys[]; mode: string; onSelect: (s: Sys) => void }) {
  const W = 880, boxW = 170, boxH = 38, top = 64, step = 62;
  const rows = Math.max(onPrem.length, cloud.length);
  const H = top + rows * step + 20;
  const leftX = 18, rightX = W - 18 - boxW;
  const hubW = 132, hubH = 74, hubX = (W - hubW) / 2, hubY = H / 2 - hubH / 2;
  const ly = (i: number) => top + i * step;
  const posL = onPrem.map((s, i) => ({ s, x: leftX, y: ly(i), cx: leftX + boxW, cy: ly(i) + boxH / 2 }));
  const posR = cloud.map((s, i) => ({ s, x: rightX, y: ly(i), cx: rightX, cy: ly(i) + boxH / 2 }));
  const hubL = { x: hubX, y: hubY + hubH / 2 }, hubR = { x: hubX + hubW, y: hubY + hubH / 2 };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 460 }}>
      {/* column labels */}
      <text x={leftX} y={40} fill="#22d3ee" fontSize="11" fontFamily="monospace">◇ ON-PREMISE · OT / IT</text>
      <text x={rightX} y={40} fill="#6366f1" fontSize="11" fontFamily="monospace">☁ CLOUD · SaaS</text>

      {/* links */}
      {mode === "p2p"
        ? posL.flatMap((a) => posR.map((b) => (
            <line key={a.s.id + b.s.id} x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy}
              stroke="#f87171" strokeWidth="1" opacity="0.18" />)))
        : [...posL.map((a) => (
            <line key={"l" + a.s.id} x1={a.cx} y1={a.cy} x2={hubL.x} y2={hubL.y}
              stroke={a.s.color} strokeWidth="1.5" opacity="0.55" />)),
           ...posR.map((b) => (
            <line key={"r" + b.s.id} x1={b.cx} y1={b.cy} x2={hubR.x} y2={hubR.y}
              stroke={b.s.color} strokeWidth="1.5" opacity="0.55" />))]}

      {/* hub */}
      {mode === "uns" && (
        <g>
          <rect x={hubX} y={hubY} width={hubW} height={hubH} rx="10"
            fill="#141E30" stroke="#34d399" strokeWidth="1.5" />
          <text x={hubX + hubW / 2} y={hubY + 28} fill="#34d399" fontSize="14"
            fontWeight="600" textAnchor="middle" fontFamily="monospace">UNS</text>
          <text x={hubX + hubW / 2} y={hubY + 46} fill="#8ea2c4" fontSize="9"
            textAnchor="middle">Unified Namespace</text>
          <text x={hubX + hubW / 2} y={hubY + 60} fill="#4A6080" fontSize="8"
            textAnchor="middle" fontFamily="monospace">MQTT / Sparkplug B</text>
        </g>
      )}

      {/* nodes (clickable → drill into the system's tables) */}
      {[...posL, ...posR].map(({ s, x, y }) => (
        <g key={s.id} onClick={() => onSelect(s)} style={{ cursor: "pointer" }}>
          <title>{`${s.name} — click to open its tables`}</title>
          <rect x={x} y={y} width={boxW} height={boxH} rx="7" fill="#192338"
            stroke={s.color} strokeWidth="1" opacity="0.95" />
          <rect x={x} y={y} width="3" height={boxH} rx="1.5" fill={s.color} />
          <text x={x + 10} y={y + 16} fill="#E8EEF8" fontSize="10.5" fontWeight="500">{s.name}</text>
          <text x={x + 10} y={y + 29} fill="#8898B0" fontSize="8.5" fontFamily="monospace">{s.protocol}</text>
          <text x={x + boxW - 8} y={y + 24} fill="#4A6080" fontSize="12" textAnchor="end">⤢</text>
        </g>
      ))}
    </svg>
  );
}

function TreeNode({ node, depth }: { node: any; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const hasKids = node.children?.length;
  return (
    <div>
      <div className="flex items-center gap-1 py-0.5 hover:bg-panel2/40 rounded"
        style={{ paddingLeft: depth * 12 }}>
        {hasKids ? (
          <button onClick={() => setOpen(!open)} className="text-muted w-3">{open ? "▾" : "▸"}</button>
        ) : <span className="w-3" />}
        <span className="text-slate-300">{node.name}</span>
        {node.value !== undefined && (
          <span className="ml-2 text-slate-100">{node.value}</span>
        )}
        {node.status && (
          <span className={`chip ml-1 text-[10px] ${statusCls(node.status)}`}>{node.status}</span>
        )}
        {node.source_name && (
          <span className="ml-auto text-[10px] px-1.5 rounded"
            style={{ color: node.color, border: `1px solid ${node.color}55` }}>{node.source_name}</span>
        )}
      </div>
      {open && hasKids && node.children.map((c: any, i: number) => (
        <TreeNode key={i} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}

function Stat({ label, value, color }: any) {
  return (
    <div className="card p-3">
      <div className="text-muted text-xs">{label}</div>
      <div className="text-lg font-semibold" style={{ color: color ?? "#e6edf7" }}>{value}</div>
    </div>
  );
}
function cell(v: any): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}
function statusCls(s: string) {
  const bad = ["OUT_OF_DESIGN_SPACE", "EXCURSION", "ACTION_LEVEL", "OOS", "OPEN", "AT_RISK", "BREACH"];
  const warn = ["ALERT_LEVEL", "UNDER_ASSESSMENT", "PENDING"];
  if (bad.includes(s)) return "border-rose-500 text-rose-300";
  if (warn.includes(s)) return "border-amber-500 text-amber-300";
  return "border-emerald-600 text-emerald-300";
}
