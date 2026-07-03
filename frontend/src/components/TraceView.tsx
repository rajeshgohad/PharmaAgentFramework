import { useState } from "react";
import type { TraceStep } from "../api";

export default function TraceView({ trace }: { trace: TraceStep[] }) {
  if (!trace?.length) return <div className="text-muted text-sm">No trace.</div>;
  return (
    <div className="space-y-2">
      {trace.map((s, i) => <Step key={i} step={s} idx={i} />)}
    </div>
  );
}

function Step({ step, idx }: { step: TraceStep; idx: number }) {
  const [open, setOpen] = useState(false);
  if (step.type === "thought") {
    return (
      <div className="flex gap-2">
        <div className="text-indigo-400 text-xs font-mono mt-0.5 w-6 shrink-0">{idx}</div>
        <div className="text-sm text-slate-200 whitespace-pre-wrap bg-panel2/60 border border-edge rounded-lg px-3 py-2 flex-1">
          <span className="text-indigo-300 text-xs font-semibold mr-2">THINK</span>
          {step.content}
        </div>
      </div>
    );
  }
  if (step.type === "tool_call") {
    const ok = step.success;
    return (
      <div className="flex gap-2">
        <div className="text-cyan-400 text-xs font-mono mt-0.5 w-6 shrink-0">{idx}</div>
        <div className="flex-1 border border-edge rounded-lg overflow-hidden">
          <button onClick={() => setOpen(!open)}
            className="w-full flex items-center gap-2 px-3 py-2 bg-panel2 hover:bg-edge text-left">
            <span className={`chip ${ok ? "border-emerald-500 text-emerald-300" : "border-rose-500 text-rose-300"}`}>
              {ok ? "✓" : "✕"}
            </span>
            <span className="text-cyan-300 text-xs font-semibold">ACT</span>
            <span className="font-mono text-sm text-slate-100">{step.tool}</span>
            <span className="text-muted text-xs ml-auto">{step.latency_ms}ms · {open ? "▲" : "▼"}</span>
          </button>
          {open && (
            <div className="px-3 py-2 bg-ink/60 space-y-2 text-xs font-mono">
              <div>
                <div className="text-muted mb-1">input</div>
                <pre className="text-slate-300 overflow-x-auto">{JSON.stringify(step.input, null, 2)}</pre>
              </div>
              <div>
                <div className="text-muted mb-1">observation</div>
                <pre className="text-emerald-200 overflow-x-auto max-h-64 overflow-y-auto">
                  {JSON.stringify(step.observation?.data ?? step.observation, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="text-rose-300 text-sm border border-rose-800 rounded-lg px-3 py-2">
      {step.content}
    </div>
  );
}
