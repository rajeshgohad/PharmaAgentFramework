import { useEffect, useState } from "react";
import { api } from "../api";

const SS_KEY = "anthropic_api_key";

export default function ApiKeyModal({
  open, onClose, onChanged, enabled,
}: {
  open: boolean; onClose: () => void; onChanged: () => void; enabled: boolean;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (open) { setKey(sessionStorage.getItem(SS_KEY) || ""); setMsg(""); }
  }, [open]);

  if (!open) return null;

  const save = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await api.setApiKey(key.trim());
      if (r.ok) {
        sessionStorage.setItem(SS_KEY, key.trim());
        setMsg("Saved for this session.");
        onChanged();
        setTimeout(onClose, 500);
      } else {
        setMsg(r.error || "Could not save key.");
      }
    } catch (e: any) { setMsg("Request failed: " + e); }
    setBusy(false);
  };

  const clear = async () => {
    setBusy(true);
    try {
      await api.clearApiKey();
      sessionStorage.removeItem(SS_KEY);
      setKey(""); setMsg("Cleared."); onChanged();
    } catch (e: any) { setMsg("Request failed: " + e); }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60"
      onClick={onClose}>
      <div className="card p-5 w-[440px] max-w-[92vw]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-1">
          <h2 className="font-semibold">Anthropic API key</h2>
          <span className={`chip ml-auto ${enabled ? "border-emerald-500 text-emerald-300" : "border-amber-500 text-amber-300"}`}>
            {enabled ? "active" : "not set"}
          </span>
        </div>
        <p className="text-muted text-xs mb-3">
          Stored in memory for this session only — never written to disk. Enables the
          <span className="text-slate-200"> Claude</span> reasoning mode on agent runs and the orchestrator.
        </p>
        <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
          placeholder="sk-ant-…" autoFocus
          onKeyDown={(e) => e.key === "Enter" && save()}
          className="w-full bg-ink border border-edge rounded-lg px-3 py-2 text-sm font-mono" />
        {msg && <div className="text-xs mt-2 text-slate-300">{msg}</div>}
        <div className="flex items-center gap-2 mt-4">
          <button onClick={save} disabled={busy || !key.trim()} className="btn btn-primary disabled:opacity-50">
            {busy ? "Saving…" : "Save for session"}
          </button>
          {enabled && <button onClick={clear} disabled={busy} className="btn btn-ghost">Clear</button>}
          <button onClick={onClose} className="btn btn-ghost ml-auto">Cancel</button>
        </div>
      </div>
    </div>
  );
}
