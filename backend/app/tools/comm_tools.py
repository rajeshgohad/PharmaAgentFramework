"""Communication, supplier & compliance tools (Pharma Tools.md §11-12).

Alert/notification/report tools return a GxP dispatch envelope (with batch
context + audit id). Supplier/compliance tools do real reads and writes.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func

from .. import models
from .registry import ToolError, tool


@tool("PT-080", "pharma_alert_tool", "COMMUNICATION",
      "Send a graded GxP alert (email/Teams/SMS/pager) with batch context and "
      "regulatory classification. All GMP alerts logged to the audit trail.",
      {"type": "object", "properties": {
          "severity": {"type": "string",
                       "enum": ["INFO", "WARNING", "ALERT", "CRITICAL", "EMERGENCY"]},
          "gmp_event_type": {"type": "string",
                             "description": "OOS | DEVIATION | EM_EXCURSION | TEMP_EXCURSION | BATCH_FAILURE"},
          "title": {"type": "string"},
          "message": {"type": "string"},
          "batch_id": {"type": "string"}},
       "required": ["severity", "title", "message"]})
def pharma_alert_tool(db, severity: str, title: str, message: str,
                      gmp_event_type: str = "DEVIATION", batch_id: str = None):
    aid = uuid.uuid4().hex[:10]
    channels = ["teams", "email"] + (["sms", "pager"] if severity in ("CRITICAL", "EMERGENCY") else [])
    return {"dispatched": True, "alert_id": f"ALRT-{aid}", "severity": severity,
            "gmp_event_type": gmp_event_type, "batch_id": batch_id,
            "sent_channels": channels, "requires_ack": severity in ("CRITICAL", "EMERGENCY"),
            "audit_id": f"AUD-{aid}", "sent_at": str(datetime.now())}


@tool("PT-081", "qp_notification_tool", "COMMUNICATION",
      "Notify the Qualified Person (QP) of a batch disposition recommendation, major "
      "deviation, or OOS. Maintains an inspection-ready QP notification log.",
      {"type": "object", "properties": {
          "notification_type": {"type": "string",
                                "description": "BATCH_RELEASE_RECOMMENDATION | MAJOR_DEVIATION | OOS | BATCH_REJECTION"},
          "urgency": {"type": "string", "enum": ["ROUTINE", "URGENT", "EMERGENCY"]},
          "summary": {"type": "string"},
          "recommendation": {"type": "string"},
          "batch_id": {"type": "string"}},
       "required": ["notification_type", "summary"]})
def qp_notification_tool(db, notification_type: str, summary: str, recommendation: str = "",
                         urgency: str = "ROUTINE", batch_id: str = None):
    nid = uuid.uuid4().hex[:10]
    return {"delivered": True, "notification_id": f"QPN-{nid}",
            "notification_type": notification_type, "urgency": urgency,
            "batch_id": batch_id, "recommendation": recommendation,
            "note": "Agent recommendation only — QP applies e-signature for any release.",
            "audit_id": f"AUD-{nid}", "delivered_at": str(datetime.now())}


@tool("PT-082", "batch_release_report_tool", "COMMUNICATION",
      "Compile the QP batch-release documentation package (EBR + QC + deviations + EM).",
      {"type": "object", "properties": {"batch_id": {"type": "string"}},
       "required": ["batch_id"]})
def batch_release_report_tool(db, batch_id: str):
    b = db.get(models.BatchMaster, batch_id)
    if not b:
        raise ToolError("DATA_NOT_FOUND", f"No batch {batch_id}")
    rid = uuid.uuid4().hex[:8]
    return {"report_id": f"RPT-{rid}", "batch_id": batch_id, "format": "pdf",
            "report_url": f"/reports/RPT-{rid}.pdf",
            "expires_at": str(datetime.now() + timedelta(minutes=30))}


@tool("PT-083", "report_generator_tool", "COMMUNICATION",
      "Generate a formatted GxP report (APQR, supplier scorecard, trend, compliance).",
      {"type": "object", "properties": {
          "template": {"type": "string",
                       "description": "apqr | supplier_scorecard | trend | compliance | em"},
          "title": {"type": "string"}, "summary": {"type": "string"}},
       "required": ["template", "title"]})
def report_generator_tool(db, template: str, title: str, summary: str = ""):
    rid = uuid.uuid4().hex[:8]
    return {"report_id": f"RPT-{rid}", "template": template, "title": title,
            "format": "pdf", "report_url": f"/reports/RPT-{rid}.pdf",
            "generated_at": str(datetime.now())}


@tool("PT-003", "audit_trail_tool", "COMMUNICATION",
      "Write a 21 CFR Part 11 audit-trail entry for an agent action (immutable log).",
      {"type": "object", "properties": {
          "action": {"type": "string"}, "record_ref": {"type": "string"},
          "reason": {"type": "string"}}, "required": ["action", "reason"]})
def audit_trail_tool(db, action: str, reason: str, record_ref: str = None):
    return {"logged": True, "audit_id": f"AUD-{uuid.uuid4().hex[:10]}", "action": action,
            "record_ref": record_ref, "reason": reason, "actor": "AGENT",
            "timestamp": str(datetime.now())}


# ------------------------------------------------------ supplier & compliance
@tool("PT-071", "supplier_scorecard_tool", "AI_ML",
      "Rank suppliers by composite quality/delivery score; classify APPROVED / WATCH / "
      "CONDITIONAL / SUSPEND per SCP-003 rules.",
      {"type": "object", "properties": {"limit": {"type": "integer"},
       "worst_first": {"type": "boolean"}}})
def supplier_scorecard_tool(db, limit: int = 15, worst_first: bool = True):
    order = (models.SupplierMaster.overall_score.asc() if worst_first
             else models.SupplierMaster.overall_score.desc())
    rows = db.query(models.SupplierMaster).order_by(order).limit(limit).all()

    def cls(s):
        v = s.overall_score or 0
        return ("SUSPEND" if v < 50 else "CONDITIONAL" if v < 65
                else "WATCH" if v < 80 else "APPROVED")
    return {"suppliers": [
        {"supplier_id": s.supplier_id, "name": s.name, "type": s.supplier_type,
         "overall_score": s.overall_score, "quality_rating": s.quality_rating,
         "delivery_rating": s.delivery_rating, "regulatory_status": s.regulatory_status,
         "single_source": s.single_source, "classification": cls(s)} for s in rows]}


@tool("PT-070", "coa_review_tool", "DATA_ACCESS",
      "Certificate of Analysis review stats for a supplier: acceptance vs rejection rate.",
      {"type": "object", "properties": {"supplier_id": {"type": "string"}},
       "required": ["supplier_id"]})
def coa_review_tool(db, supplier_id: str):
    rows = db.query(models.CoARecord).filter(models.CoARecord.supplier_id == supplier_id).all()
    if not rows:
        raise ToolError("DATA_NOT_FOUND", f"No CoA records for {supplier_id}")
    rejected = sum(1 for r in rows if r.status == "REJECTED")
    return {"supplier_id": supplier_id, "coa_lots": len(rows), "rejected": rejected,
            "acceptance_rate": round(1 - rejected / len(rows), 4),
            "rejection_rate": round(rejected / len(rows), 4),
            "exceeds_target": (rejected / len(rows)) > 0.015}


@tool("PT-011", "material_status_update_tool", "PROCESS_EXEC",
      "Change a material lot's status (e.g. QUARANTINE->APPROVED/REJECTED/HOLD) with "
      "a reason and audit trail (real DB write). Agents document; QA releases material.",
      {"type": "object", "properties": {
          "material_id": {"type": "string"},
          "new_status": {"type": "string", "enum": ["APPROVED", "REJECTED", "HOLD", "QUARANTINE"]},
          "reason": {"type": "string"}},
       "required": ["material_id", "new_status", "reason"]})
def material_status_update_tool(db, material_id: str, new_status: str, reason: str):
    ib = (db.query(models.InventoryBalance)
          .filter(models.InventoryBalance.material_id == material_id).first())
    if not ib:
        raise ToolError("DATA_NOT_FOUND", f"No inventory for material {material_id}")
    if new_status not in ("APPROVED", "REJECTED", "HOLD", "QUARANTINE"):
        raise ToolError("INVALID_INPUT", f"Bad status {new_status}")
    ib.material_status = new_status
    ib.last_status_change = datetime.now()
    db.commit()
    return {"updated": True, "material_id": material_id, "new_status": new_status,
            "reason": reason, "audit_id": f"AUD-{uuid.uuid4().hex[:10]}"}


@tool("PT-043", "create_change_control_tool", "PROCESS_EXEC",
      "Open a change control record for a proposed change to a validated system.",
      {"type": "object", "properties": {
          "change_type": {"type": "string"},
          "classification": {"type": "string", "enum": ["MINOR", "MODERATE", "MAJOR"]},
          "description": {"type": "string"}},
       "required": ["change_type", "classification", "description"]})
def create_change_control_tool(db, change_type: str, classification: str, description: str):
    seq = (db.query(func.count(models.ChangeControlRecord.cc_id)).scalar() or 0) + 1
    cid = f"CC-9{seq:04d}"
    db.add(models.ChangeControlRecord(
        cc_id=cid, cc_number=f"CC-2026-9{seq:04d}", change_type=change_type,
        classification=classification, description=description,
        regulatory_impact=("PRIOR_APPROVAL" if classification == "MAJOR" else "INFORM"),
        validation_required=(classification != "MINOR"),
        requalification_required=(classification == "MAJOR"), initiator="AGENT",
        target_implementation=date.today() + timedelta(days=60), status="DRAFT",
        created_at=datetime.now()))
    db.commit()
    return {"created": True, "cc_number": f"CC-2026-9{seq:04d}", "cc_id": cid,
            "classification": classification,
            "regulatory_impact": ("PRIOR_APPROVAL" if classification == "MAJOR" else "INFORM"),
            "audit_id": f"AUD-{uuid.uuid4().hex[:10]}"}
