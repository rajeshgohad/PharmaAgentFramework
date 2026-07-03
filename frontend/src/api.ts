// Thin typed client over the FastAPI backend (proxied via Vite).
export interface Agent {
  id: string; name: string; domain: string; domain_name: string;
  domain_color: string; framework: string; depth: string; goal: string;
  triggers: string[]; tools: string[]; tool_count: number; escalation: string;
  sends_to: string[]; receives_from: string[];
}
export interface ToolInfo { tool_id: string; name: string; category: string; description: string; }
export interface TraceStep {
  type: string; content?: string; tool?: string; input?: any;
  observation?: any; success?: boolean; latency_ms?: number;
}
export interface RunResult {
  run_id: string; agent_id: string; framework: string; reasoning_mode: string;
  status: string; trace: TraceStep[]; result: string; tool_calls: number;
}
export interface RunSummary {
  run_id: string; agent_id: string; agent_name: string; domain: string;
  framework: string; reasoning_mode: string; trigger_type: string;
  status: string; tool_calls: number; orchestration_id: string | null;
  started_at: string; result_preview: string;
}
export interface OrchEvent {
  event_id: string; tick: number; sim_time: string; signal_type: string;
  severity: string; description: string; dispatched_agents: string[]; source_ref: string;
}

const j = async (r: Response) => { if (!r.ok) throw new Error(await r.text()); return r.json(); };

export const api = {
  health: () => fetch("/api/health").then(j),
  agents: () => fetch("/api/agents").then(j),
  agent: (id: string) => fetch(`/api/agents/${id}`).then(j),
  domains: () => fetch("/api/domains").then(j),
  tools: () => fetch("/api/tools").then(j),
  frameworks: () => fetch("/api/frameworks").then(j),
  run: (id: string, prompt: string, mode?: string): Promise<RunResult> =>
    fetch(`/api/agents/${id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, mode }),
    }).then(j),
  runs: (params: Record<string, string> = {}) =>
    fetch("/api/runs?" + new URLSearchParams(params)).then(j),
  runDetail: (runId: string) => fetch(`/api/runs/${runId}`).then(j),
  orchStatus: () => fetch("/api/orchestrator/status").then(j),
  orchStart: (mode: string) => fetch("/api/orchestrator/start", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  }).then(j),
  orchStop: () => fetch("/api/orchestrator/stop", { method: "POST" }).then(j),
  orchTick: () => fetch("/api/orchestrator/tick", { method: "POST" }).then(j),
  orchEvents: (limit = 40) => fetch(`/api/orchestrator/events?limit=${limit}`).then(j),
  kpis: () => fetch("/api/dashboard/kpis").then(j),
  setApiKey: (api_key: string) =>
    fetch("/api/config/api-key", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key }),
    }).then(j),
  clearApiKey: () => fetch("/api/config/api-key", { method: "DELETE" }).then(j),
  tables: () => fetch("/api/tables").then(j),
  tableData: (name: string) => fetch(`/api/tables/${name}`).then(j),
  unsSystems: () => fetch("/api/uns/systems").then(j),
  unsStats: () => fetch("/api/uns/stats").then(j),
  unsTree: () => fetch("/api/uns/tree").then(j),
  unsEvents: (limit = 60) => fetch(`/api/uns/events?limit=${limit}`).then(j),
  unsBatches: () => fetch("/api/uns/batches").then(j),
  unsBatch: (id: string) => fetch(`/api/uns/batch/${id}`).then(j),
};
