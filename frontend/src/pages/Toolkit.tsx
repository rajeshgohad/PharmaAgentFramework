import { useEffect, useState } from "react";
import { api, type ToolInfo } from "../api";

const CAT_COLOR: Record<string, string> = {
  DATA_ACCESS: "#60a5fa", PROCESS_EXEC: "#a78bfa", REALTIME: "#f59e0b",
  AI_ML: "#34d399", COMMUNICATION: "#22d3ee", INTEGRATION: "#fb7185",
};

export default function Toolkit() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  useEffect(() => { api.tools().then((d) => setTools(d.tools)); }, []);
  const cats = Array.from(new Set(tools.map((t) => t.category)));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Toolkit</h1>
        <p className="text-muted text-sm">
          {tools.length} executable tools agents call. Each runs real logic against the plant
          database and returns a standard ToolResponse (success, data, latency, error contract).
        </p>
      </div>
      {cats.map((c) => (
        <section key={c}>
          <div className="flex items-center gap-2 mb-2">
            <span className="w-3 h-3 rounded-full" style={{ background: CAT_COLOR[c] ?? "#8ea2c4" }} />
            <h2 className="font-semibold">{c}</h2>
            <span className="text-xs text-muted">{tools.filter((t) => t.category === c).length}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {tools.filter((t) => t.category === c).map((t) => (
              <div key={t.name} className="card p-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-cyan-300">{t.name}</span>
                  <span className="text-muted text-xs ml-auto">{t.tool_id}</span>
                </div>
                <div className="text-xs text-muted mt-1">{t.description}</div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
