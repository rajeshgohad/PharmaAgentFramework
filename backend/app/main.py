"""FastAPI application: agent registry/catalog, toolkit, manual runner,
autonomous orchestrator, dashboards, and a live WebSocket event stream."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from . import dashboard, models, runtime, uns as uns_mod
from .agents.registry import AGENTS, DOMAINS, FRAMEWORKS, get_agent, domain_of
from .config import ORCH_AUTOSTART, ORCH_AUTOSTART_MODE, STATIC_DIR
from .database import Base, SessionLocal
from .orchestrator import orchestrator
from .reasoning import build_system_prompt, run_agent
from .simulator import build_database
from .tools import REGISTRY, catalog

app = FastAPI(title="PharmaAgentFramework", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


# ----------------------------------------------------------- WebSocket manager
class WSManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def _send_all(self, payload: dict):
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_threadsafe(self, payload: dict):
        """Called from the orchestrator's background thread."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._send_all(payload), self.loop)


ws_manager = WSManager()


@app.on_event("startup")
def _startup():
    ws_manager.loop = asyncio.get_event_loop()
    orchestrator._broadcast = ws_manager.broadcast_threadsafe
    build_database(force=False)  # build only if empty (never wipes existing data)

    # Correct any stale running flag left by an unclean shutdown, then optionally
    # resume live generation from the last saved sim clock.
    db = SessionLocal()
    try:
        clock = db.query(models.SimClock).first()
        if clock and clock.running:
            clock.running = False
            db.commit()
    finally:
        db.close()
    if ORCH_AUTOSTART:
        orchestrator.orchestrated_mode = ORCH_AUTOSTART_MODE
        orchestrator.start()


# ------------------------------------------------------------------- schemas
class RunRequest(BaseModel):
    prompt: str
    mode: Optional[str] = None   # "LLM" | "DETERMINISTIC" | None (=default)


class OrchStartRequest(BaseModel):
    mode: Optional[str] = "DETERMINISTIC"


class ApiKeyRequest(BaseModel):
    api_key: str


# --------------------------------------------------------------------- system
@app.get("/api/health")
def health():
    db = SessionLocal()
    try:
        clock = db.query(models.SimClock).first()
        enabled = runtime.llm_enabled()
        return {"status": "ok", "llm_enabled": enabled,
                "model": runtime.model() if enabled else None,
                "sim_time": str(clock.current_time) if clock else None,
                "tick": clock.tick if clock else 0}
    finally:
        db.close()


@app.post("/api/config/api-key")
def set_api_key(req: ApiKeyRequest):
    """Store an Anthropic key in server memory for this session (never persisted)."""
    key = (req.api_key or "").strip()
    if not key.startswith("sk-"):
        return {"ok": False, "llm_enabled": runtime.llm_enabled(),
                "error": "Key should start with 'sk-'."}
    runtime.set_api_key(key)
    return {"ok": True, "llm_enabled": runtime.llm_enabled(), "model": runtime.model()}


@app.delete("/api/config/api-key")
def clear_api_key():
    runtime.clear_api_key()
    return {"ok": True, "llm_enabled": False}


@app.post("/api/admin/build")
def admin_build(force: bool = False):
    return build_database(force=force)


@app.get("/api/frameworks")
def frameworks():
    return FRAMEWORKS


# --------------------------------------------------------------------- catalog
@app.get("/api/domains")
def domains():
    db = SessionLocal()
    try:
        return {"domains": dashboard.domain_kpis(db), "meta": DOMAINS}
    finally:
        db.close()


@app.get("/api/agents")
def agents():
    out = []
    for a in AGENTS:
        d = DOMAINS[a["domain"]]
        out.append({**a, "domain_name": d["name"], "domain_color": d["color"],
                    "tool_count": len(a["tools"])})
    return {"agents": out, "count": len(out)}


@app.get("/api/agents/{agent_id}")
def agent_detail(agent_id: str):
    a = get_agent(agent_id)
    if not a:
        return {"error": "not found"}
    d = DOMAINS[a["domain"]]
    tools = [{"name": n, "tool_id": REGISTRY[n].tool_id,
              "description": REGISTRY[n].description} for n in a["tools"] if n in REGISTRY]
    return {**a, "domain_name": d["name"], "domain_color": d["color"],
            "framework_desc": FRAMEWORKS.get(a["framework"]),
            "tools_detail": tools, "system_prompt": build_system_prompt(a)}


@app.get("/api/tools")
def tools():
    return {"tools": catalog(), "count": len(REGISTRY)}


# ------------------------------------------------------------------ execution
@app.post("/api/agents/{agent_id}/run")
def run(agent_id: str, req: RunRequest):
    db = SessionLocal()
    try:
        return run_agent(db, agent_id, req.prompt, trigger_type="MANUAL",
                         force_mode=req.mode)
    finally:
        db.close()


@app.get("/api/runs")
def runs(agent_id: Optional[str] = None, orchestration_id: Optional[str] = None,
         limit: int = 30):
    db = SessionLocal()
    try:
        q = db.query(models.AgentRun)
        if agent_id:
            q = q.filter(models.AgentRun.agent_id == agent_id)
        if orchestration_id:
            q = q.filter(models.AgentRun.orchestration_id == orchestration_id)
        rows = q.order_by(models.AgentRun.started_at.desc()).limit(limit).all()
        return {"runs": [_run_summary(r) for r in rows]}
    finally:
        db.close()


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str):
    db = SessionLocal()
    try:
        r = db.get(models.AgentRun, run_id)
        if not r:
            return {"error": "not found"}
        a = get_agent(r.agent_id) or {}
        return {**_run_summary(r), "trace": r.trace, "result": r.result,
                "prompt": r.prompt, "agent_name": a.get("name")}
    finally:
        db.close()


# --------------------------------------------------------------- orchestrator
@app.get("/api/orchestrator/status")
def orch_status():
    return orchestrator.status()


@app.post("/api/orchestrator/start")
def orch_start(req: OrchStartRequest):
    orchestrator.orchestrated_mode = (req.mode or "DETERMINISTIC").upper()
    return orchestrator.start()


@app.post("/api/orchestrator/stop")
def orch_stop():
    return orchestrator.stop()


@app.post("/api/orchestrator/tick")
def orch_tick():
    return orchestrator.tick_once()


@app.get("/api/orchestrator/events")
def orch_events(limit: int = 40):
    db = SessionLocal()
    try:
        rows = (db.query(models.OrchestrationEvent)
                .order_by(models.OrchestrationEvent.tick.desc()).limit(limit).all())
        return {"events": [{
            "event_id": e.event_id, "tick": e.tick, "sim_time": str(e.sim_time),
            "signal_type": e.signal_type, "severity": e.severity,
            "description": e.description, "dispatched_agents": e.dispatched_agents,
            "source_ref": e.source_ref} for e in rows]}
    finally:
        db.close()


# ---------------------------------------------------------------- dashboards
@app.get("/api/dashboard/kpis")
def dashboard_kpis():
    db = SessionLocal()
    try:
        return dashboard.plant_kpis(db)
    finally:
        db.close()


# --------------------------------------------------------- Unified Namespace
@app.get("/api/uns/systems")
def uns_systems():
    db = SessionLocal()
    try:
        return uns_mod.systems(db)
    finally:
        db.close()


@app.get("/api/uns/stats")
def uns_stats():
    db = SessionLocal()
    try:
        return uns_mod.stats(db)
    finally:
        db.close()


@app.get("/api/uns/tree")
def uns_tree():
    db = SessionLocal()
    try:
        return uns_mod.tree(db)
    finally:
        db.close()


@app.get("/api/uns/events")
def uns_events(limit: int = 60):
    db = SessionLocal()
    try:
        return {"events": uns_mod.recent_events(db, limit)}
    finally:
        db.close()


@app.get("/api/uns/batches")
def uns_batches(n: int = 12):
    db = SessionLocal()
    try:
        return {"batches": uns_mod.recent_batches(db, n)}
    finally:
        db.close()


@app.get("/api/uns/batch/{batch_id}")
def uns_batch(batch_id: str):
    db = SessionLocal()
    try:
        return uns_mod.batch_360(db, batch_id)
    finally:
        db.close()


# ------------------------------------------------------------- table browser
# Human-friendly grouping of the tables the tools query.
TABLE_GROUPS = {
    "enterprise": "Plant Hierarchy", "site": "Plant Hierarchy",
    "manufacturing_area": "Plant Hierarchy",
    "product_master": "Product & Formula", "material_master": "Product & Formula",
    "batch_formula": "Product & Formula", "batch_formula_component": "Product & Formula",
    "critical_process_parameter": "Product & Formula",
    "batch_master": "Manufacturing", "electronic_batch_record": "Manufacturing",
    "manufacturing_step_log": "Manufacturing", "in_process_control_result": "Manufacturing",
    "qc_test_order": "QC / LIMS", "analytical_result": "QC / LIMS",
    "oos_investigation": "QC / LIMS", "stability_study": "QC / LIMS",
    "stability_result": "QC / LIMS",
    "deviation_record": "QMS", "capa_record": "QMS", "change_control_record": "QMS",
    "audit_record": "QMS", "audit_finding": "QMS",
    "supplier_master": "Supply & Inventory", "coa_record": "Supply & Inventory",
    "approved_supplier_list": "Supply & Inventory", "inventory_balance": "Supply & Inventory",
    "dispensing_record": "Supply & Inventory", "material_reconciliation": "Supply & Inventory",
    "equipment_master": "Equipment", "calibration_record": "Equipment",
    "cleaning_record": "Equipment", "maintenance_work_order": "Equipment",
    "product_registration": "Regulatory & PV", "adverse_event_report": "Regulatory & PV",
    "signal_assessment": "Regulatory & PV",
    "em_result": "Environmental", "temperature_humidity_log": "Environmental",
    "document_master": "Training & Docs", "training_record": "Training & Docs",
    "agent_run": "Framework Runtime", "orchestration_event": "Framework Runtime",
    "sim_clock": "Framework Runtime",
}


@app.get("/api/tables")
def list_tables():
    db = SessionLocal()
    try:
        out = []
        for name, table in Base.metadata.tables.items():
            try:
                cnt = db.execute(select(func.count()).select_from(table)).scalar()
            except Exception:  # noqa: BLE001
                cnt = None
            out.append({"name": name, "rows": cnt,
                        "columns": len(table.columns),
                        "group": TABLE_GROUPS.get(name, "Other")})
        out.sort(key=lambda t: t["name"])
        return {"tables": out, "count": len(out)}
    finally:
        db.close()


@app.get("/api/tables/{name}")
def table_data(name: str, limit: int = 10):
    table = Base.metadata.tables.get(name)
    if table is None:
        return {"error": f"Unknown table '{name}'"}
    limit = max(1, min(limit, 10))   # hard cap: never more than 10 rows
    db = SessionLocal()
    try:
        cols = list(table.columns.keys())
        rows = db.execute(select(table).limit(limit)).mappings().all()
        data = [{c: _cell(r[c]) for c in cols} for r in rows]
        total = db.execute(select(func.count()).select_from(table)).scalar()
        return {"name": name, "group": TABLE_GROUPS.get(name, "Other"),
                "columns": cols, "rows": data, "showing": len(data), "total": total}
    finally:
        db.close()


def _cell(v):
    if v is None or isinstance(v, (int, float, bool, str)):
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    return str(v)


# ------------------------------------------------------------------ WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # keep-alive; client may ping
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


def _run_summary(r: models.AgentRun) -> dict:
    a = get_agent(r.agent_id) or {}
    return {"run_id": r.run_id, "agent_id": r.agent_id, "agent_name": a.get("name"),
            "domain": a.get("domain"), "framework": r.framework,
            "reasoning_mode": r.reasoning_mode, "trigger_type": r.trigger_type,
            "status": r.status, "tool_calls": r.tool_calls,
            "orchestration_id": r.orchestration_id,
            "started_at": str(r.started_at),
            "result_preview": (r.result or "")[:200]}


# ------------------------------------------------ single-origin static frontend
# When AAF_STATIC_DIR points at a built frontend (set in the Docker image), serve
# it from this same app so /api and /ws are same-origin. Registered LAST so the
# SPA catch-all never shadows the API/WebSocket routes above.
if STATIC_DIR and os.path.isdir(STATIC_DIR):
    _assets = os.path.join(STATIC_DIR, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}")
    def _spa(full_path: str):
        # API/WS are matched by their explicit routes first; anything else falls
        # through to here and returns the SPA shell (client-side routing).
        candidate = os.path.join(STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
