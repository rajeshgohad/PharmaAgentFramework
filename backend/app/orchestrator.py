"""Autonomous orchestrator.

A watcher agent that, each tick: advances the simulation clock, emits new live
transactions, scans them for anomalies, and dispatches the mapped agent cascade
(respecting Agent.md's cross-agent dependency graph) to achieve each domain goal.

Runs as a background thread; pushes events to subscribers (WebSocket) via a
callback. Orchestrated agent runs default to DETERMINISTIC mode to stay cheap
during continuous operation; the manual runner uses full Claude reasoning.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func

from . import models
from .config import ORCH_MINUTES_PER_TICK, ORCH_TICK_SECONDS, THRESHOLDS
from .database import SessionLocal
from .reasoning import run_agent
from .simulator import generate_tick

# anomaly signal -> ordered agent cascade (Agent.md cross-agent dependency graph)
CASCADES = {
    "OOS_DETECTED": ["QA-P01", "QA-P02", "QA-P03"],
    "CPP_BREACH": ["ME-P03", "ME-P04", "QA-P03"],
    "DEVIATION_CRITICAL": ["ME-P04", "QA-P03"],
    "EM_ACTION": ["REG-P02", "QA-P02"],
    "TEMP_EXCURSION": ["WM-P04", "QA-P02"],
}


class Orchestrator:
    def __init__(self, broadcast=None, orchestrated_mode: str = "DETERMINISTIC"):
        self._thread: threading.Thread | None = None
        self._running = False
        self._broadcast = broadcast          # callable(dict) -> None (thread-safe)
        self.orchestrated_mode = orchestrated_mode
        self.last_summary: dict = {}

    # ------------------------------------------------------------ lifecycle
    def start(self):
        if self._running:
            return {"running": True, "note": "already running"}
        self._running = True
        db = SessionLocal()
        clock = db.query(models.SimClock).first()
        if clock:
            clock.running = True
            db.commit()
        db.close()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._emit({"type": "orchestrator", "event": "started",
                    "mode": self.orchestrated_mode})
        return {"running": True, "mode": self.orchestrated_mode}

    def stop(self):
        self._running = False
        db = SessionLocal()
        clock = db.query(models.SimClock).first()
        if clock:
            clock.running = False
            db.commit()
        db.close()
        self._emit({"type": "orchestrator", "event": "stopped"})
        return {"running": False}

    def status(self):
        db = SessionLocal()
        try:
            clock = db.query(models.SimClock).first()
            events = db.query(func.count(models.OrchestrationEvent.event_id)).scalar()
            runs = (db.query(func.count(models.AgentRun.run_id))
                    .filter(models.AgentRun.trigger_type == "ORCHESTRATED").scalar())
            return {
                "running": self._running,
                "mode": self.orchestrated_mode,
                "sim_time": str(clock.current_time) if clock else None,
                "tick": clock.tick if clock else 0,
                "total_events": events,
                "total_orchestrated_runs": runs,
                "last_summary": self.last_summary,
            }
        finally:
            db.close()

    # ------------------------------------------------------------ main loop
    def _loop(self):
        while self._running:
            try:
                self.tick_once()
            except Exception as e:  # noqa: BLE001
                self._emit({"type": "error", "content": f"tick failed: {e}"})
            for _ in range(int(ORCH_TICK_SECONDS * 2)):
                if not self._running:
                    break
                time.sleep(0.5)

    def tick_once(self) -> dict:
        db = SessionLocal()
        try:
            clock = db.query(models.SimClock).first()
            if not clock:
                return {}
            sim_time = (clock.current_time or datetime.now()) + timedelta(
                minutes=ORCH_MINUTES_PER_TICK)
            tick = (clock.tick or 0) + 1
            clock.current_time = sim_time
            clock.tick = tick
            db.commit()

            emitted = generate_tick(db, sim_time, tick)
            self._emit({"type": "tick", "tick": tick, "sim_time": str(sim_time),
                        "emitted": emitted})

            signals = self._detect(db, sim_time, tick)
            dispatched = []
            for sig in signals:
                event = self._dispatch(db, sig, tick, sim_time)
                dispatched.append(event)

            self.last_summary = {"tick": tick, "sim_time": str(sim_time),
                                 "emitted": emitted, "signals": len(signals),
                                 "cascades": [d["signal_type"] for d in dispatched]}
            return self.last_summary
        finally:
            db.close()

    # ------------------------------------------------------------ detection
    def _detect(self, db, sim_time, tick) -> list[dict]:
        signals: list[dict] = []
        window_start = sim_time - timedelta(minutes=ORCH_MINUTES_PER_TICK)

        # 1) OOS analytical result this tick -> QC investigation cascade
        oos = (db.query(models.AnalyticalResult)
               .filter(models.AnalyticalResult.run_date >= window_start,
                       models.AnalyticalResult.result_status == "OOS").all())
        for r in oos:
            signals.append({
                "type": "OOS_DETECTED", "severity": "CRITICAL",
                "source_table": "analytical_result", "source_ref": r.result_id,
                "desc": (f"OOS on {r.test_name} for batch {r.batch_id} "
                         f"(result {r.reported_result}, limit {r.usl}) — investigation required."),
                "context": {"batch_id": r.batch_id, "product_id": r.product_id,
                            "test_name": r.test_name}})

        # 2) CPP design-space breach during manufacture -> deviation cascade
        cpp = (db.query(models.ManufacturingStepLog)
               .filter(models.ManufacturingStepLog.timestamp >= window_start,
                       models.ManufacturingStepLog.within_par.is_(False)).all())
        for c in cpp:
            signals.append({
                "type": "CPP_BREACH", "severity": "ALERT",
                "source_table": "manufacturing_step_log", "source_ref": c.batch_id,
                "desc": (f"CPP '{c.parameter_name}'={c.value}{c.uom} outside the design space "
                         f"on batch {c.batch_id}."),
                "context": {"batch_id": c.batch_id}})

        # 3) fresh CRITICAL deviation -> deviation + CAPA cascade
        devs = (db.query(models.DeviationRecord)
                .filter(models.DeviationRecord.detection_date >= window_start,
                        models.DeviationRecord.severity == "CRITICAL").all())
        for dv in devs:
            signals.append({
                "type": "DEVIATION_CRITICAL", "severity": "CRITICAL",
                "source_table": "deviation_record", "source_ref": dv.deviation_id,
                "desc": (f"CRITICAL deviation {dv.deviation_number} on batch {dv.batch_id} "
                         f"({dv.step_of_occurrence})."),
                "context": {"deviation_id": dv.deviation_id, "batch_id": dv.batch_id}})

        # 4) EM action-level excursion in a cleanroom -> EM + investigation
        em = (db.query(models.EMResult)
              .filter(models.EMResult.sample_date >= window_start,
                      models.EMResult.result_status == "ACTION_LEVEL").all())
        for e in em:
            signals.append({
                "type": "EM_ACTION", "severity": "CRITICAL",
                "source_table": "em_result", "source_ref": e.em_result_id,
                "desc": (f"EM ACTION level in {e.area_id} ({e.cfu_count} CFU, "
                         f"{e.organism_identified or 'organism TBD'})."),
                "context": {"area_id": e.area_id}})

        # 5) temperature excursion on a storage unit -> cold-chain cascade
        temp = (db.query(models.TemperatureHumidityLog)
                .filter(models.TemperatureHumidityLog.timestamp >= window_start,
                        models.TemperatureHumidityLog.within_spec.is_(False)).all())
        seen_units = set()
        for t in temp:
            if t.storage_unit_id in seen_units:
                continue
            seen_units.add(t.storage_unit_id)
            signals.append({
                "type": "TEMP_EXCURSION", "severity": "ALERT",
                "source_table": "temperature_humidity_log", "source_ref": t.storage_unit_id,
                "desc": (f"Temperature excursion on {t.storage_unit_id} "
                         f"({t.temperature_c}°C, limit {t.temperature_usl}°C)."),
                "context": {"area_id": t.area_id}})

        # de-duplicate within the tick, then suppress anything already handled
        # for the same source within the cooldown window (avoid re-firing a
        # known-critical asset every tick).
        cooldown_floor = tick - 24
        recent = {(e.signal_type, e.source_ref) for e in
                  db.query(models.OrchestrationEvent)
                  .filter(models.OrchestrationEvent.tick >= cooldown_floor).all()}
        uniq, keys = [], set()
        for s in signals:
            k = (s["type"], s["source_ref"])
            if k in keys or k in recent:
                continue
            keys.add(k)
            uniq.append(s)
        return uniq[:4]

    # ------------------------------------------------------------ dispatch
    def _dispatch(self, db, sig, tick, sim_time) -> dict:
        cascade = CASCADES.get(sig["type"], [])
        event_id = f"ORC-{uuid.uuid4().hex[:10]}"
        run_ids = []
        self._emit({"type": "anomaly", "event_id": event_id, "tick": tick,
                    "signal_type": sig["type"], "severity": sig["severity"],
                    "description": sig["desc"], "cascade": cascade,
                    "sim_time": str(sim_time)})

        for agent_id in cascade:
            prompt = self._prompt_for(agent_id, sig)
            result = run_agent(db, agent_id, prompt, trigger_type="ORCHESTRATED",
                               orchestration_id=event_id,
                               force_mode=self.orchestrated_mode)
            run_ids.append(result["run_id"])
            self._emit({"type": "agent_run", "event_id": event_id, "tick": tick,
                        "agent_id": agent_id, "run_id": result["run_id"],
                        "status": result["status"], "tool_calls": result["tool_calls"],
                        "result_preview": (result["result"] or "")[:240]})

        db.add(models.OrchestrationEvent(
            event_id=event_id, tick=tick, sim_time=sim_time, signal_type=sig["type"],
            severity=sig["severity"], source_table=sig["source_table"],
            source_ref=sig["source_ref"], description=sig["desc"],
            dispatched_agents=cascade, created_at=datetime.now()))
        db.commit()
        return {"event_id": event_id, "signal_type": sig["type"],
                "cascade": cascade, "run_ids": run_ids}

    def _prompt_for(self, agent_id: str, sig: dict) -> str:
        ctx = sig.get("context", {})
        hint = " ".join(f"{k}={v}" for k, v in ctx.items())
        return (f"AUTONOMOUS TRIGGER — {sig['type']} ({sig['severity']}). "
                f"{sig['desc']} Relevant entities: {hint}. "
                f"Act per your goal and escalation policy using your tools.")

    # ------------------------------------------------------------ helpers
    def _emit(self, payload: dict):
        if self._broadcast:
            try:
                self._broadcast(payload)
            except Exception:  # noqa: BLE001
                pass


# module-level singleton (wired with a broadcaster in main.py)
orchestrator = Orchestrator()
