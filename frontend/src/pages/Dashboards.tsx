import { useEffect, useState } from "react";

export default function Dashboards() {
  const [k, setK] = useState<any>(null);
  useEffect(() => {
    const load = () => fetch("/api/dashboard/kpis").then((r) => r.json()).then(setK);
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  if (!k) return <div className="text-muted">Loading…</div>;
  const pct = (v: number) => (v == null ? "—" : (v * 100).toFixed(2) + "%");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Plant Quality Dashboards</h1>
        <p className="text-muted text-sm">Live GxP KPIs the agents monitor and act upon.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Gauge label="Batch Success Rate" value={pct(k.batch.success_rate)}
          target={`target ${pct(k.batch.target)}`} good={k.batch.success_rate >= k.batch.target} />
        <Gauge label="OOS Rate" value={pct(k.quality.oos_rate)}
          target={`target ≤ ${pct(k.quality.oos_target)}`} good={k.quality.oos_rate <= k.quality.oos_target} />
        <Gauge label="Right First Time" value={pct(k.quality.right_first_time)}
          target={`target ${pct(k.quality.rft_target)}`} good={k.quality.right_first_time >= k.quality.rft_target} />
        <Gauge label="Qualified Equipment" value={pct(k.equipment.qualified_availability)}
          target={`target ${pct(k.equipment.qual_target)}`} good={k.equipment.qualified_availability >= k.equipment.qual_target} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Open quality events</h2>
          <div className="grid grid-cols-2 gap-3">
            <Metric label="Open deviations" value={k.quality.open_deviations} color="#f59e0b" />
            <Metric label="Open CAPAs" value={k.quality.open_capas} color="#a78bfa" />
            <Metric label="Open OOS investigations" value={k.quality.open_oos} color="#fb7185" />
            <Metric label="Requalification due" value={k.equipment.requalification_due} color="#22d3ee" />
          </div>
        </div>

        <div className="card p-4">
          <h2 className="font-semibold mb-3">Compliance & supply</h2>
          <div className="grid grid-cols-2 gap-3">
            <Metric label="Calibration compliance" value={pct(k.equipment.calibration_compliance)} color="#34d399" />
            <Metric label="Avg supplier score" value={k.supply.avg_supplier_score ?? "—"} color="#60a5fa" />
            <Metric label="At-risk suppliers" value={k.supply.at_risk_suppliers} color="#f59e0b" />
            <Metric label="EM excursion rate" value={pct(k.environmental.excursion_rate)} color="#fb7185" />
          </div>
        </div>
      </div>
    </div>
  );
}

function Gauge({ label, value, target, good }: any) {
  return (
    <div className="card p-4">
      <div className="text-muted text-xs">{label}</div>
      <div className={`text-2xl font-bold ${good ? "text-emerald-300" : "text-amber-300"}`}>{value}</div>
      <div className="text-xs text-muted mt-1">{target}</div>
    </div>
  );
}
function Metric({ label, value, color }: any) {
  return (
    <div className="bg-panel2/60 border border-edge rounded-lg p-3">
      <div className="text-2xl font-bold" style={{ color }}>{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}
