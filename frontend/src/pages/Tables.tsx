import { useEffect, useState } from "react";
import { api } from "../api";

interface TableMeta { name: string; rows: number | null; columns: number; group: string; }
interface TableData { name: string; group: string; columns: string[]; rows: any[]; showing: number; total: number; }

export default function Tables() {
  const [tables, setTables] = useState<TableMeta[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [data, setData] = useState<TableData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.tables().then((d) => setTables(d.tables)); }, []);

  const open = (name: string) => {
    setActive(name); setData(null); setLoading(true);
    api.tableData(name).then((d) => { setData(d); setLoading(false); });
  };

  const groups = Array.from(new Set(tables.map((t) => t.group)));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Database Tables</h1>
        <p className="text-muted text-sm">
          The {tables.length} tables the tools run against. Click a table to preview its
          data (first 10 rows only).
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* table list */}
        <div className="space-y-4">
          {groups.map((g) => (
            <div key={g} className="card p-3">
              <div className="text-xs uppercase tracking-wide text-muted mb-2">{g}</div>
              <div className="space-y-1">
                {tables.filter((t) => t.group === g).map((t) => (
                  <button key={t.name} onClick={() => open(t.name)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-sm ${active === t.name ? "bg-indigo-600 text-white" : "hover:bg-panel2"}`}>
                    <span className="font-mono">{t.name}</span>
                    <span className="text-xs opacity-70 ml-auto">
                      {t.rows?.toLocaleString() ?? "—"} rows
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* data preview */}
        <div className="lg:col-span-2">
          <div className="card p-4 min-h-[300px]">
            {!active && <div className="text-muted text-sm">Select a table to preview its data.</div>}
            {active && (
              <>
                <div className="flex items-center gap-2 mb-3">
                  <h2 className="font-mono font-semibold text-cyan-300">{active}</h2>
                  {data && (
                    <span className="text-xs text-muted ml-auto">
                      showing {data.showing} of {data.total.toLocaleString()} rows · {data.columns.length} columns
                    </span>
                  )}
                </div>
                {loading && <div className="text-muted text-sm">Loading…</div>}
                {data && (
                  <div className="overflow-auto max-h-[65vh] border border-edge rounded-lg">
                    <table className="text-xs w-full">
                      <thead className="sticky top-0 bg-panel2">
                        <tr>
                          {data.columns.map((c) => (
                            <th key={c} className="text-left px-2 py-1.5 font-mono text-slate-300 border-b border-edge whitespace-nowrap">
                              {c}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {data.rows.map((r, i) => (
                          <tr key={i} className="odd:bg-ink/40 hover:bg-panel2/60">
                            {data.columns.map((c) => (
                              <td key={c} className="px-2 py-1 font-mono text-slate-200 border-b border-edge/40 max-w-[240px] truncate"
                                title={fmt(r[c])}>
                                {fmt(r[c])}
                              </td>
                            ))}
                          </tr>
                        ))}
                        {data.rows.length === 0 && (
                          <tr><td className="px-2 py-3 text-muted" colSpan={data.columns.length}>
                            (empty table)</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function fmt(v: any): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}
