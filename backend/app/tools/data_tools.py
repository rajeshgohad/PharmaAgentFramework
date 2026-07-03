"""Data-access tools (Pharma Tools.md Category 1). Real reads against the GxP DB."""
from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import func

from .. import models
from .registry import ToolError, tool


@tool("PT-010", "material_availability_tool", "DATA_ACCESS",
      "Query approved stock, quarantine, and expiry for a material by id (FEFO context).",
      {"type": "object", "properties": {"material_id": {"type": "string"}},
       "required": ["material_id"]})
def material_availability_tool(db, material_id: str):
    rows = db.query(models.InventoryBalance).filter(
        models.InventoryBalance.material_id == material_id).all()
    if not rows:
        raise ToolError("DATA_NOT_FOUND", f"No inventory for material {material_id}")
    m = db.get(models.MaterialMaster, material_id)
    return {
        "material_id": material_id, "material_type": m.material_type if m else None,
        "qty_approved": round(sum(r.qty_approved or 0 for r in rows), 2),
        "qty_quarantine": round(sum(r.qty_quarantine or 0 for r in rows), 2),
        "qty_available": round(sum(r.qty_available or 0 for r in rows), 2),
        "safety_stock": m.safety_stock_qty if m else None,
        "reorder_point": m.reorder_point if m else None,
        "lead_time_days": m.lead_time_days if m else None,
        "earliest_expiry": str(min((r.expiry_date for r in rows if r.expiry_date), default=None)),
    }


@tool("PT-010b", "material_shortage_scan", "DATA_ACCESS",
      "List materials whose approved available stock is at or below safety stock.",
      {"type": "object", "properties": {"limit": {"type": "integer"}}})
def material_shortage_scan(db, limit: int = 15):
    q = (db.query(models.InventoryBalance, models.MaterialMaster)
         .join(models.MaterialMaster,
               models.MaterialMaster.material_id == models.InventoryBalance.material_id)
         .filter(models.InventoryBalance.qty_available <= models.MaterialMaster.safety_stock_qty)
         .limit(limit).all())
    return {"count": len(q), "materials": [
        {"material_id": m.material_id, "material_type": m.material_type,
         "qty_available": ib.qty_available, "safety_stock": m.safety_stock_qty,
         "lead_time_days": m.lead_time_days,
         "controlled_substance": m.controlled_substance} for ib, m in q]}


@tool("PT-011", "batch_record_query", "DATA_ACCESS",
      "Fetch a batch's master record plus EBR step completion and open deviations.",
      {"type": "object", "properties": {"batch_id": {"type": "string"}},
       "required": ["batch_id"]})
def batch_record_query(db, batch_id: str):
    b = db.get(models.BatchMaster, batch_id)
    if not b:
        raise ToolError("DATA_NOT_FOUND", f"No batch {batch_id}")
    steps = db.query(models.ElectronicBatchRecord).filter(
        models.ElectronicBatchRecord.batch_id == batch_id).all()
    open_dev = (db.query(func.count(models.DeviationRecord.deviation_id))
                .filter(models.DeviationRecord.batch_id == batch_id,
                        models.DeviationRecord.status != "CLOSED").scalar())
    ipc_fail = sum(1 for s in steps if s.ipc_result == "FAIL")
    p = db.get(models.ProductMaster, b.product_id)
    return {
        "batch_id": b.batch_id, "batch_number": b.batch_number,
        "product": p.product_name if p else b.product_id, "status": b.status,
        "disposition": b.disposition, "yield_pct": b.yield_pct,
        "manufacturing_date": str(b.manufacturing_date), "ebr_steps": len(steps),
        "ebr_steps_completed": sum(1 for s in steps if s.status == "COMPLETED"),
        "ipc_failures": ipc_fail, "open_deviations": open_dev,
    }


@tool("PT-020", "analytical_result_query", "DATA_ACCESS",
      "Recent analytical results, OOS/OOT counts and rate for a batch or product.",
      {"type": "object", "properties": {
          "batch_id": {"type": "string"}, "product_id": {"type": "string"},
          "limit": {"type": "integer"}}})
def analytical_result_query(db, batch_id: str = None, product_id: str = None, limit: int = 200):
    q = db.query(models.AnalyticalResult)
    if batch_id:
        q = q.filter(models.AnalyticalResult.batch_id == batch_id)
    if product_id:
        q = q.filter(models.AnalyticalResult.product_id == product_id)
    rows = q.order_by(models.AnalyticalResult.run_date.desc()).limit(limit).all()
    if not rows:
        raise ToolError("DATA_NOT_FOUND", "No analytical results for the given scope")
    oos = [r for r in rows if r.result_status == "OOS"]
    oot = [r for r in rows if r.result_status == "OOT"]
    by_test = Counter(r.test_name for r in oos)
    return {"tested": len(rows), "oos_count": len(oos), "oot_count": len(oot),
            "oos_rate": round(len(oos) / len(rows), 4),
            "oos_by_test": by_test.most_common(5),
            "latest": {"test": rows[0].test_name, "result": rows[0].reported_result,
                       "status": rows[0].result_status, "run_date": str(rows[0].run_date)}}


@tool("PT-050", "equipment_status_query", "DATA_ACCESS",
      "Equipment master + qualification status, calibration status, and next PM.",
      {"type": "object", "properties": {"equipment_id": {"type": "string"}},
       "required": ["equipment_id"]})
def equipment_status_query(db, equipment_id: str):
    e = db.get(models.EquipmentMaster, equipment_id)
    if not e:
        raise ToolError("DATA_NOT_FOUND", f"No equipment {equipment_id}")
    cal = (db.query(models.CalibrationRecord)
           .filter(models.CalibrationRecord.equipment_id == equipment_id)
           .order_by(models.CalibrationRecord.calibration_date.desc()).first())
    return {
        "equipment_id": e.equipment_id, "tag": e.equipment_tag, "type": e.equipment_type,
        "criticality": e.criticality, "qualification_status": e.current_qualification_status,
        "pq_expiry": str(e.pq_expiry_date), "next_pm_due": str(e.next_pm_due),
        "calibration_status": cal.status if cal else None,
        "calibration_due": str(cal.due_date) if cal else None,
        "computerised_system": e.computerised_system,
    }


@tool("PT-062", "em_result_query", "REALTIME",
      "Recent environmental monitoring results and action/alert counts for an area.",
      {"type": "object", "properties": {"area_id": {"type": "string"},
       "limit": {"type": "integer"}}, "required": ["area_id"]})
def em_result_query(db, area_id: str, limit: int = 200):
    rows = (db.query(models.EMResult).filter(models.EMResult.area_id == area_id)
            .order_by(models.EMResult.sample_date.desc()).limit(limit).all())
    if not rows:
        raise ToolError("DATA_NOT_FOUND", f"No EM results for area {area_id}")
    action = [r for r in rows if r.result_status == "ACTION_LEVEL"]
    alert = [r for r in rows if r.result_status == "ALERT_LEVEL"]
    organisms = Counter(r.organism_identified for r in rows if r.organism_identified)
    return {"area_id": area_id, "samples": len(rows), "action_level": len(action),
            "alert_level": len(alert),
            "excursion_rate": round((len(action) + len(alert)) / len(rows), 4),
            "top_organisms": organisms.most_common(5)}


@tool("PT-040", "supplier_query_tool", "DATA_ACCESS",
      "Supplier master record: qualification status, quality/delivery score, audit dates.",
      {"type": "object", "properties": {"supplier_id": {"type": "string"}},
       "required": ["supplier_id"]})
def supplier_query_tool(db, supplier_id: str):
    s = db.get(models.SupplierMaster, supplier_id)
    if not s:
        raise ToolError("DATA_NOT_FOUND", f"No supplier {supplier_id}")
    coa = db.query(models.CoARecord).filter(models.CoARecord.supplier_id == supplier_id).all()
    rejected = sum(1 for c in coa if c.status == "REJECTED")
    return {"supplier_id": s.supplier_id, "name": s.name, "type": s.supplier_type,
            "regulatory_status": s.regulatory_status, "overall_score": s.overall_score,
            "quality_rating": s.quality_rating, "delivery_rating": s.delivery_rating,
            "single_source": s.single_source, "gmp_cert_expiry": str(s.gmp_cert_expiry),
            "next_audit_due": str(s.next_audit_due),
            "coa_lots": len(coa), "coa_rejected": rejected,
            "coa_rejection_rate": round(rejected / len(coa), 4) if coa else None}
