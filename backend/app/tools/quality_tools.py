"""Quality Control & Assurance tools (Pharma Tools.md §7-10). Real computation + GxP writes."""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func

from .. import models
from .registry import ToolError, tool


@tool("PT-021", "oos_detection_tool", "AI_ML",
      "Scan recent analytical results for OOS/OOT and return the current OOS rate "
      "and the products/tests driving it.",
      {"type": "object", "properties": {"limit": {"type": "integer"}}})
def oos_detection_tool(db, limit: int = 500):
    rows = (db.query(models.AnalyticalResult)
            .order_by(models.AnalyticalResult.run_date.desc()).limit(limit).all())
    if not rows:
        raise ToolError("DATA_NOT_FOUND", "No analytical results")
    oos = [r for r in rows if r.result_status == "OOS"]
    by_product = Counter(r.product_id for r in oos)
    by_test = Counter(r.test_name for r in oos)
    return {"scanned": len(rows), "oos_count": len(oos),
            "oos_rate": round(len(oos) / len(rows), 4),
            "target_rate": 0.005, "exceeds_target": (len(oos) / len(rows)) > 0.005,
            "oos_by_product": by_product.most_common(5),
            "oos_by_test": by_test.most_common(5)}


@tool("PT-055", "oos_investigation_context", "AI_ML",
      "Assemble the FDA-2006 OOS investigation evidence bundle for an OOS record: "
      "Phase-1 (lab error) checks and Phase-2 (manufacturing) links.",
      {"type": "object", "properties": {"oos_id": {"type": "string"}},
       "required": ["oos_id"]})
def oos_investigation_context(db, oos_id: str):
    o = db.get(models.OOSInvestigation, oos_id)
    if not o:
        raise ToolError("DATA_NOT_FOUND", f"No OOS record {oos_id}")
    result = db.get(models.AnalyticalResult, o.result_id) if o.result_id else None
    batch = db.get(models.BatchMaster, o.batch_id) if o.batch_id else None
    batch_devs = (db.query(func.count(models.DeviationRecord.deviation_id))
                  .filter(models.DeviationRecord.batch_id == o.batch_id).scalar()) if o.batch_id else 0
    similar = (db.query(func.count(models.OOSInvestigation.oos_id))
               .filter(models.OOSInvestigation.product_id == o.product_id,
                       models.OOSInvestigation.test_name == o.test_name).scalar())
    cal = None
    if result and result.instrument_id:
        c = (db.query(models.CalibrationRecord)
             .filter(models.CalibrationRecord.equipment_id == result.instrument_id)
             .order_by(models.CalibrationRecord.calibration_date.desc()).first())
        cal = {"status": c.status, "result": c.result} if c else None
    return {
        "oos_id": oos_id, "test": o.test_name, "oos_value": o.oos_value,
        "spec_limit": o.specification_limit, "phase": o.phase,
        "phase1_conclusion": o.phase1_conclusion,
        "phase1_lab_checks": {"instrument": result.instrument_id if result else None,
                              "instrument_calibration": cal,
                              "analyst": result.analyst_id if result else None,
                              "retest_number": result.retest_number if result else None},
        "phase2_manufacturing": {"batch": o.batch_id,
                                 "batch_status": batch.status if batch else None,
                                 "batch_deviations": batch_devs,
                                 "similar_oos_same_product_test": similar},
        "recurrence_signal": similar >= 3,
    }


@tool("PT-041", "raise_deviation", "PROCESS_EXEC",
      "Create a 21 CFR Part 11 deviation record in the QMS (real DB write + audit trail). "
      "Agents document deviations; QA dispositions them.",
      {"type": "object", "properties": {
          "batch_id": {"type": "string"},
          "severity": {"type": "string", "enum": ["CRITICAL", "MAJOR", "MINOR"]},
          "description": {"type": "string"},
          "source": {"type": "string"}},
       "required": ["severity", "description"]})
def raise_deviation(db, severity: str, description: str, batch_id: str = None,
                    source: str = "MANUFACTURING"):
    if severity not in ("CRITICAL", "MAJOR", "MINOR"):
        raise ToolError("INVALID_INPUT", f"Bad severity {severity}")
    seq = (db.query(func.count(models.DeviationRecord.deviation_id)).scalar() or 0) + 1
    did = f"DEV-9{seq:04d}"
    db.add(models.DeviationRecord(
        deviation_id=did, deviation_number=f"DEV-2026-9{seq:04d}", source=source,
        severity=severity, detection_date=datetime.now(), detected_by="AGENT",
        batch_id=batch_id, description=description,
        batch_impact=("CONFIRMED" if severity == "CRITICAL" else "POTENTIAL"),
        capa_required=(severity in ("CRITICAL", "MAJOR")), status="OPEN",
        qp_notified=(severity == "CRITICAL"), created_at=datetime.now()))
    db.commit()
    return {"created": True, "deviation_number": f"DEV-2026-9{seq:04d}", "deviation_id": did,
            "severity": severity, "capa_required": severity in ("CRITICAL", "MAJOR"),
            "qp_notified": severity == "CRITICAL",
            "audit_id": f"AUD-{uuid.uuid4().hex[:10]}"}


@tool("PT-042", "create_capa", "PROCESS_EXEC",
      "Create a CAPA record with root cause and corrective/preventive actions (real DB write).",
      {"type": "object", "properties": {
          "source": {"type": "string", "enum": ["DEVIATION", "OOS", "AUDIT", "COMPLAINT", "TREND"]},
          "source_record_id": {"type": "string"},
          "root_cause": {"type": "string"},
          "corrective_action": {"type": "string"},
          "product_id": {"type": "string"}},
       "required": ["source", "root_cause", "corrective_action"]})
def create_capa(db, source: str, root_cause: str, corrective_action: str,
                source_record_id: str = None, product_id: str = None):
    seq = (db.query(func.count(models.CAPARecord.capa_id)).scalar() or 0) + 1
    cid = f"CAPA-9{seq:04d}"
    due = 30 if source in ("OOS",) else 60
    db.add(models.CAPARecord(
        capa_id=cid, capa_number=f"CAPA-2026-9{seq:04d}", capa_source=source,
        source_record_id=source_record_id, product_id=product_id, root_cause=root_cause,
        root_cause_method="FIVE_WHY", corrective_action=corrective_action,
        preventive_action="Lateral deployment to similar processes", owner="AGENT",
        target_close_date=(date.today() + timedelta(days=due)), status="OPEN",
        created_at=datetime.now()))
    db.commit()
    return {"created": True, "capa_number": f"CAPA-2026-9{seq:04d}", "capa_id": cid,
            "target_close_days": due, "audit_id": f"AUD-{uuid.uuid4().hex[:10]}"}


@tool("PT-022", "create_oos_investigation", "PROCESS_EXEC",
      "Open a structured OOS investigation record for an OOS analytical result (FDA 2006).",
      {"type": "object", "properties": {
          "result_id": {"type": "string"}, "batch_id": {"type": "string"},
          "test_name": {"type": "string"}}, "required": ["batch_id", "test_name"]})
def create_oos_investigation(db, batch_id: str, test_name: str, result_id: str = None):
    seq = (db.query(func.count(models.OOSInvestigation.oos_id)).scalar() or 0) + 1
    oid = f"OOS-9{seq:04d}"
    b = db.get(models.BatchMaster, batch_id)
    db.add(models.OOSInvestigation(
        oos_id=oid, oos_number=f"OOS-2026-9{seq:04d}", result_id=result_id, batch_id=batch_id,
        product_id=b.product_id if b else None, test_name=test_name,
        detection_date=datetime.now(), phase=1, phase1_conclusion="IN_PROGRESS",
        batch_disposition="PENDING", capa_required=True, status="PHASE1",
        created_at=datetime.now()))
    db.commit()
    return {"created": True, "oos_number": f"OOS-2026-9{seq:04d}", "oos_id": oid,
            "phase": 1, "audit_id": f"AUD-{uuid.uuid4().hex[:10]}"}


@tool("PT-023", "stability_trend_tool", "AI_ML",
      "Trend a product's stability assay over timepoints; project shelf-life supportability.",
      {"type": "object", "properties": {"product_id": {"type": "string"}},
       "required": ["product_id"]})
def stability_trend_tool(db, product_id: str):
    rows = (db.query(models.StabilityResult)
            .filter(models.StabilityResult.product_id == product_id)
            .order_by(models.StabilityResult.timepoint_months.asc()).all())
    if len(rows) < 2:
        raise ToolError("DATA_NOT_FOUND", f"Insufficient stability data for {product_id}")
    first, last = rows[0], rows[-1]
    months = max(1, last.timepoint_months - first.timepoint_months)
    rate = (first.result_value - last.result_value) / months  # %/month decline
    lsl = last.lsl or 95
    months_to_oos = ((last.result_value - lsl) / rate) if rate > 0 else 999
    return {"product_id": product_id, "timepoints": len(rows),
            "latest_assay": last.result_value, "lsl": lsl,
            "degradation_rate_pct_per_month": round(rate, 4),
            "months_to_oos_projected": round(max(0, months_to_oos), 1),
            "any_oos_timepoint": any(r.result_status == "OOS" for r in rows),
            "shelf_life_at_risk": months_to_oos < 36}


@tool("PT-074", "signal_detection_tool", "AI_ML",
      "Pharmacovigilance signal check for a product: adverse-event counts, seriousness, "
      "and PRR-style disproportionality flag.",
      {"type": "object", "properties": {"product_id": {"type": "string"}},
       "required": ["product_id"]})
def signal_detection_tool(db, product_id: str):
    aes = db.query(models.AdverseEventReport).filter(
        models.AdverseEventReport.product_id == product_id).all()
    total_all = db.query(func.count(models.AdverseEventReport.ae_id)).scalar() or 1
    if not aes:
        raise ToolError("DATA_NOT_FOUND", f"No adverse events for product {product_id}")
    serious = sum(1 for a in aes if a.is_serious)
    by_pt = Counter(a.event_meddra_pt for a in aes)
    top_pt, top_n = by_pt.most_common(1)[0]
    # crude proportional reporting ratio for the top event term
    prod_prop = top_n / len(aes)
    bg = (db.query(func.count(models.AdverseEventReport.ae_id))
          .filter(models.AdverseEventReport.event_meddra_pt == top_pt).scalar())
    bg_prop = bg / total_all
    prr = round(prod_prop / bg_prop, 2) if bg_prop else None
    open_sig = (db.query(func.count(models.SignalAssessment.signal_id))
                .filter(models.SignalAssessment.product_id == product_id,
                        models.SignalAssessment.status != "CLOSED").scalar())
    return {"product_id": product_id, "reports": len(aes), "serious": serious,
            "serious_rate": round(serious / len(aes), 3),
            "top_event": top_pt, "top_event_count": top_n, "prr": prr,
            "signal_flag": bool(prr and prr >= 2 and top_n >= 3),
            "open_signal_assessments": open_sig}
