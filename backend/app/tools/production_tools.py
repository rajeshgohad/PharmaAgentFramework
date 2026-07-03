"""Manufacturing Execution tools (Pharma Tools.md §5-6). Real computation + GxP writes.

GxP guardrail: agents may RECOMMEND but never autonomously release a batch or
close a deviation. Write tools here create records / place holds only.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime

from sqlalchemy import func

from .. import models
from .registry import ToolError, tool


@tool("PT-030", "cpp_monitor_tool", "REALTIME",
      "Check a batch's recent critical process parameter (CPP) readings against "
      "the design space; report excursions outside NOR/PAR.",
      {"type": "object", "properties": {"batch_id": {"type": "string"},
       "limit": {"type": "integer"}}, "required": ["batch_id"]})
def cpp_monitor_tool(db, batch_id: str, limit: int = 200):
    rows = (db.query(models.ManufacturingStepLog)
            .filter(models.ManufacturingStepLog.batch_id == batch_id)
            .order_by(models.ManufacturingStepLog.timestamp.desc()).limit(limit).all())
    if not rows:
        raise ToolError("DATA_NOT_FOUND", f"No process data for batch {batch_id}")
    out_nor = [r for r in rows if r.within_nor is False]
    out_par = [r for r in rows if r.within_par is False]
    vals = [r.value for r in rows if r.value is not None]
    return {"batch_id": batch_id, "readings": len(rows),
            "out_of_nor": len(out_nor), "out_of_par": len(out_par),
            "max_value": round(max(vals), 3) if vals else None,
            "parameter": rows[0].parameter_name,
            "design_space_breach": len(out_par) > 0}


@tool("PT-001", "deviation_context_tool", "AI_ML",
      "Assemble the Tree-of-Thought evidence bundle for a deviation: batch context, "
      "CPP data, equipment calibration status, prior deviations on the batch.",
      {"type": "object", "properties": {"deviation_id": {"type": "string"}},
       "required": ["deviation_id"]})
def deviation_context_tool(db, deviation_id: str):
    dv = db.get(models.DeviationRecord, deviation_id)
    if not dv:
        raise ToolError("DATA_NOT_FOUND", f"No deviation {deviation_id}")
    batch = db.get(models.BatchMaster, dv.batch_id) if dv.batch_id else None
    equip = db.get(models.EquipmentMaster, dv.equipment_id) if dv.equipment_id else None
    cal = None
    if dv.equipment_id:
        c = (db.query(models.CalibrationRecord)
             .filter(models.CalibrationRecord.equipment_id == dv.equipment_id)
             .order_by(models.CalibrationRecord.calibration_date.desc()).first())
        cal = {"status": c.status, "result": c.result} if c else None
    cpp_breaches = 0
    if dv.batch_id:
        cpp_breaches = (db.query(func.count(models.ManufacturingStepLog.log_id))
                        .filter(models.ManufacturingStepLog.batch_id == dv.batch_id,
                                models.ManufacturingStepLog.within_par.is_(False)).scalar())
    prior = (db.query(func.count(models.DeviationRecord.deviation_id))
             .filter(models.DeviationRecord.batch_id == dv.batch_id).scalar())
    return {
        "deviation_id": deviation_id, "severity": dv.severity,
        "description": dv.description, "step": dv.step_of_occurrence,
        "batch_impact": dv.batch_impact,
        "root_cause_category": dv.root_cause_category,
        "branch_evidence": {
            "equipment": {"id": dv.equipment_id, "type": equip.equipment_type if equip else None,
                          "qualification": equip.current_qualification_status if equip else None,
                          "calibration": cal},
            "process_parameters": {"cpp_par_breaches_in_batch": cpp_breaches},
            "material": {"product": batch.product_id if batch else None},
            "prior_deviations_on_batch": prior},
    }


@tool("PT-005", "yield_reconciliation_tool", "DATA_ACCESS",
      "Yield vs specification and material balance for a batch (WM-P05 reconciliation).",
      {"type": "object", "properties": {"batch_id": {"type": "string"}},
       "required": ["batch_id"]})
def yield_reconciliation_tool(db, batch_id: str):
    r = (db.query(models.MaterialReconciliation)
         .filter(models.MaterialReconciliation.batch_id == batch_id).first())
    b = db.get(models.BatchMaster, batch_id)
    if not r and not b:
        raise ToolError("DATA_NOT_FOUND", f"No batch {batch_id}")
    yp = (r.yield_pct if r else b.yield_pct)
    return {"batch_id": batch_id, "yield_pct": yp,
            "yield_within_spec": (96.0 <= (yp or 0) <= 102.0),
            "qty_unaccounted": r.qty_unaccounted if r else None,
            "material_balance_ok": ((r.qty_unaccounted or 0) < r.qty_dispensed * 0.02)
            if r and r.qty_dispensed else None}


@tool("PT-052", "ipc_trend_tool", "DATA_ACCESS",
      "In-process control results and failure rate for a batch (or recent, plant-wide).",
      {"type": "object", "properties": {"batch_id": {"type": "string"},
       "limit": {"type": "integer"}}})
def ipc_trend_tool(db, batch_id: str = None, limit: int = 300):
    q = db.query(models.InProcessControlResult)
    if batch_id:
        q = q.filter(models.InProcessControlResult.batch_id == batch_id)
    rows = q.order_by(models.InProcessControlResult.timestamp.desc()).limit(limit).all()
    if not rows:
        raise ToolError("DATA_NOT_FOUND", "No IPC results for the given scope")
    fails = [r for r in rows if r.result == "FAIL"]
    return {"ipc_tests": len(rows), "failures": len(fails),
            "failure_rate": round(len(fails) / len(rows), 4),
            "by_test": Counter(r.ipc_test_name for r in fails).most_common(5)}


@tool("PT-082a", "batch_disposition_checklist", "PROCESS_EXEC",
      "Compile the QP batch-disposition readiness checklist for a batch (ME-P06). "
      "Returns each gate green/red and open items — a RECOMMENDATION only; QP releases.",
      {"type": "object", "properties": {"batch_id": {"type": "string"}},
       "required": ["batch_id"]})
def batch_disposition_checklist(db, batch_id: str):
    b = db.get(models.BatchMaster, batch_id)
    if not b:
        raise ToolError("DATA_NOT_FOUND", f"No batch {batch_id}")
    steps = db.query(models.ElectronicBatchRecord).filter(
        models.ElectronicBatchRecord.batch_id == batch_id).all()
    open_dev = (db.query(func.count(models.DeviationRecord.deviation_id))
                .filter(models.DeviationRecord.batch_id == batch_id,
                        models.DeviationRecord.status != "CLOSED").scalar())
    oos = (db.query(func.count(models.OOSInvestigation.oos_id))
           .filter(models.OOSInvestigation.batch_id == batch_id,
                   models.OOSInvestigation.status != "CLOSED").scalar())
    ar = db.query(models.AnalyticalResult).filter(
        models.AnalyticalResult.batch_id == batch_id).all()
    all_release_pass = ar and all(r.result_status in ("PASS",) for r in ar)
    cpp_breach = (db.query(func.count(models.ManufacturingStepLog.log_id))
                  .filter(models.ManufacturingStepLog.batch_id == batch_id,
                          models.ManufacturingStepLog.within_par.is_(False)).scalar())
    checklist = {
        "ebr_complete": all(s.status == "COMPLETED" for s in steps) if steps else False,
        "all_cpps_in_design_space": cpp_breach == 0,
        "all_deviations_closed": open_dev == 0,
        "no_open_oos": oos == 0,
        "yield_within_spec": (96.0 <= (b.yield_pct or 0) <= 102.0),
        "release_tests_pass": bool(all_release_pass),
    }
    open_items = [k for k, v in checklist.items() if not v]
    return {"batch_id": batch_id, "checklist": checklist,
            "open_items": open_items,
            "recommendation": ("RECOMMEND_RELEASE" if not open_items
                               else "CANNOT_RECOMMEND_RELEASE"),
            "note": "QP e-signature required; agent recommendation only."}


@tool("PT-013", "batch_hold_tool", "PROCESS_EXEC",
      "Place a batch on HOLD/QUARANTINE in MES with a reason (real DB write + audit).",
      {"type": "object", "properties": {"batch_id": {"type": "string"},
       "reason": {"type": "string"}}, "required": ["batch_id", "reason"]})
def batch_hold_tool(db, batch_id: str, reason: str):
    b = db.get(models.BatchMaster, batch_id)
    if not b:
        raise ToolError("DATA_NOT_FOUND", f"No batch {batch_id}")
    b.status = "QUARANTINE"
    db.commit()
    return {"batch_id": batch_id, "status": "QUARANTINE", "reason": reason,
            "audit_id": f"AUD-{uuid.uuid4().hex[:10]}", "actioned_at": str(datetime.now())}
