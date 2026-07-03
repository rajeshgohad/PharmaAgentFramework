import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api";
import ApiKeyModal from "./ApiKeyModal";

const tabs = [
  { to: "/catalog", label: "Agent Catalog", icon: "▦" },
  { to: "/orchestrator", label: "Orchestrator", icon: "◎" },
  { to: "/dashboards", label: "Dashboards", icon: "📊" },
  { to: "/toolkit", label: "Toolkit", icon: "🛠" },
  { to: "/tables", label: "Tables", icon: "🗄" },
];

export default function Layout() {
  const [health, setHealth] = useState<any>(null);
  const [keyModal, setKeyModal] = useState(false);
  const load = () => api.health().then(setHealth).catch(() => {});

  useEffect(() => {
    // Re-apply a key saved earlier this browser session if the backend lost it
    // (e.g. after a backend restart).
    (async () => {
      const h = await api.health().catch(() => null);
      setHealth(h);
      const saved = sessionStorage.getItem("anthropic_api_key");
      if (saved && h && !h.llm_enabled) {
        try { await api.setApiKey(saved); load(); } catch { /* ignore */ }
      }
    })();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-edge bg-panel/80 backdrop-blur sticky top-0 z-20">
        <div className="max-w-[1400px] mx-auto px-5 py-3 flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-emerald-400 grid place-items-center font-bold text-ink">℞</div>
            <div>
              <div className="font-semibold leading-tight">PharmaAgent</div>
              <div className="text-[11px] text-muted leading-tight">Pharmaceutical Manufacturing Agentic Framework</div>
            </div>
          </div>
          <nav className="flex items-center gap-1">
            {tabs.map((t) => (
              <NavLink key={t.to} to={t.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm ${isActive ? "bg-indigo-600 text-white" : "text-slate-300 hover:bg-panel2"}`}>
                <span className="mr-1.5 opacity-70">{t.icon}</span>{t.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs">
            <button onClick={() => setKeyModal(true)}
              className={`chip cursor-pointer hover:brightness-125 ${health?.llm_enabled ? "border-emerald-500 text-emerald-300" : "border-amber-500 text-amber-300"}`}
              title="Click to enter or clear your Anthropic API key for this session">
              {health?.llm_enabled ? `Claude available (${health.model})` : "No API key · deterministic"}
            </button>
            <span className="text-muted">sim: {health?.sim_time?.slice(0, 16) ?? "—"} · t{health?.tick ?? 0}</span>
          </div>
        </div>
      </header>
      <main className="flex-1 max-w-[1400px] w-full mx-auto px-5 py-5">
        <Outlet />
      </main>
      <ApiKeyModal open={keyModal} onClose={() => setKeyModal(false)}
        onChanged={load} enabled={!!health?.llm_enabled} />
    </div>
  );
}
