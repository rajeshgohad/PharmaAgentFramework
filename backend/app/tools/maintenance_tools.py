"""Equipment & Compliance tools (Pharma Tools.md §7 equipment). Real reads + GxP writes."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func

from .. import models
from ..config import THRESHOLDS
from .registry import ToolError, tool


@tool("PT-050a", "qualification_status_tool", "DATA_ACCESS",
      "List equipment whose IQ/OQ/PQ qualification is expiring within N days or already lapsed.",
      {"type": "object", "properties": {"days": {"type": "integer"}, "limit": {"type": "integer"}}})
def qualification_status_tool(db, days: int = 30, limit: int = 20):
    cutoff = date.today() + timedelta(days=days)
    rows = (db.query(models.EquipmentMaster)
            .filter(models.EquipmentMaster.pq_expiry_date <= cutoff)
            .order_by(models.EquipmentMaster.pq_expiry_date.asc()).limit(limit).all())
    return {"within_days": days, "count": len(rows), "equipment": [
        {"equipment_id": e.equipment_id, "tag": e.equipment_tag, "type": e.equipment_type,
         "criticality": e.criticality, "qualification_status": e.current_qualification_status,
         "pq_expiry": str(e.pq_expiry_date)} for e in rows]}


@tool("PT-050b", "calibration_schedule_tool", "DATA_ACCESS",
      "List instruments with overdue or soon-due calibrations (metrology compliance).",
      {"type": "object", "properties": {"days": {"type": "integer"}, "limit": {"type": "integer"}}})
def calibration_schedule_tool(db, days: int = 14, limit: int = 25):
    cutoff = date.today() + timedelta(days=days)
    rows = (db.query(models.CalibrationRecord)
            .filter(models.CalibrationRecord.due_date <= cutoff)
            .order_by(models.CalibrationRecord.due_date.asc()).limit(limit).all())
    out = []
    for c in rows:
        overdue = c.due_date and c.due_date < date.today()
        out.append({"equipment_id": c.equipment_id, "due_date": str(c.due_date),
                    "status": c.status, "overdue": bool(overdue)})
    return {"within_days": days, "count": len(out),
            "overdue_count": sum(1 for x in out if x["overdue"]), "instruments": out}


@tool("PT-051", "pm_schedule_tool", "PROCESS_EXEC",
      "List equipment with preventive maintenance due within N days.",
      {"type": "object", "properties": {"days": {"type": "integer"}}})
def pm_schedule_tool(db, days: int = 14):
    cutoff = date.today() + timedelta(days=days)
    rows = (db.query(models.EquipmentMaster)
            .filter(models.EquipmentMaster.next_pm_due <= cutoff)
            .order_by(models.EquipmentMaster.next_pm_due.asc()).limit(30).all())
    return {"within_days": days, "count": len(rows), "equipment": [
        {"equipment_id": e.equipment_id, "tag": e.equipment_tag,
         "next_pm_due": str(e.next_pm_due), "criticality": e.criticality} for e in rows]}


@tool("PT-053", "cleaning_verification_tool", "DATA_ACCESS",
      "Recent cleaning verification results and failures (cross-contamination control).",
      {"type": "object", "properties": {"equipment_id": {"type": "string"},
       "limit": {"type": "integer"}}})
def cleaning_verification_tool(db, equipment_id: str = None, limit: int = 200):
    q = db.query(models.CleaningRecord)
    if equipment_id:
        q = q.filter(models.CleaningRecord.equipment_id == equipment_id)
    rows = q.order_by(models.CleaningRecord.cleaning_date.desc()).limit(limit).all()
    if not rows:
        raise ToolError("DATA_NOT_FOUND", "No cleaning records for scope")
    fails = [r for r in rows if r.verification_result == "FAIL"]
    over_maco = [r for r in rows if r.actual_carryover and r.maco_limit
                 and r.actual_carryover > r.maco_limit]
    return {"records": len(rows), "verification_failures": len(fails),
            "over_maco_limit": len(over_maco),
            "line_clearance_issued": sum(1 for r in rows if r.line_clearance_issued),
            "failure_rate": round(len(fails) / len(rows), 4)}


@tool("PT-050c", "mtbf_reliability_tool", "AI_ML",
      "Compute failure count, corrective/emergency rate, and cost for an asset from CMMS history.",
      {"type": "object", "properties": {"equipment_id": {"type": "string"}},
       "required": ["equipment_id"]})
def mtbf_reliability_tool(db, equipment_id: str):
    wos = db.query(models.MaintenanceWorkOrder).filter(
        models.MaintenanceWorkOrder.equipment_id == equipment_id).all()
    if not wos:
        raise ToolError("DATA_NOT_FOUND", f"No work orders for {equipment_id}")
    corrective = [w for w in wos if w.wo_type in ("CORRECTIVE", "EMERGENCY")]
    total_cost = sum((w.parts_cost or 0) + (w.labor_cost or 0) for w in wos)
    downtime = sum(w.production_impact_hrs or 0 for w in wos)
    e = db.get(models.EquipmentMaster, equipment_id)
    return {"equipment_id": equipment_id, "work_orders": len(wos),
            "corrective_emergency": len(corrective),
            "failure_rate": round(len(corrective) / len(wos), 3),
            "total_maintenance_cost": round(total_cost, 2),
            "production_impact_hrs": round(downtime, 1),
            "criticality": e.criticality if e else None,
            "qualification_status": e.current_qualification_status if e else None}


@tool("PT-050d", "create_maintenance_wo", "PROCESS_EXEC",
      "Create a GMP maintenance work order in the CMMS (real DB write).",
      {"type": "object", "properties": {
          "equipment_id": {"type": "string"},
          "wo_type": {"type": "string", "enum": ["PM", "CORRECTIVE", "EMERGENCY", "CALIBRATION"]},
          "priority": {"type": "integer"},
          "description": {"type": "string"}},
       "required": ["equipment_id", "wo_type", "priority", "description"]})
def create_maintenance_wo(db, equipment_id: str, wo_type: str, priority: int, description: str):
    e = db.get(models.EquipmentMaster, equipment_id)
    if not e:
        raise ToolError("DATA_NOT_FOUND", f"No equipment {equipment_id}")
    if wo_type not in ("PM", "CORRECTIVE", "EMERGENCY", "CALIBRATION"):
        raise ToolError("INVALID_INPUT", f"Bad wo_type {wo_type}")
    seq = (db.query(func.count(models.MaintenanceWorkOrder.mwo_id)).scalar() or 0) + 1
    mid = f"MWO-9{seq:05d}"
    now = datetime.now()
    db.add(models.MaintenanceWorkOrder(
        mwo_id=mid, wo_number=f"WO9{seq:05d}", equipment_id=equipment_id, wo_type=wo_type,
        priority=priority, status="OPEN", gmp_relevant=True,
        requalification_required=(wo_type == "EMERGENCY"), work_description=description,
        planned_start=now, planned_end=now + timedelta(hours=4),
        assigned_technician="AGENT-ASSIGNED", created_at=now))
    db.commit()
    return {"created": True, "wo_number": f"WO9{seq:05d}", "mwo_id": mid,
            "wo_type": wo_type, "requalification_required": wo_type == "EMERGENCY",
            "audit_id": f"AUD-{uuid.uuid4().hex[:10]}"}
