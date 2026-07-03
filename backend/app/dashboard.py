"""Plant KPI aggregations for the dashboard view (pharma / GxP)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func

from . import models


def plant_kpis(db) -> dict:
    # batch success rate (of dispositioned batches)
    dispo = db.query(models.BatchMaster).filter(
        models.BatchMaster.status.in_(["APPROVED", "REJECTED"])).all()
    approved = sum(1 for b in dispo if b.status == "APPROVED")
    batch_success = round(approved / len(dispo), 4) if dispo else None

    # OOS rate (recent analytical results)
    ar = (db.query(models.AnalyticalResult)
          .order_by(models.AnalyticalResult.run_date.desc()).limit(4000).all())
    oos = sum(1 for r in ar if r.result_status == "OOS")
    oos_rate = round(oos / len(ar), 4) if ar else None
    rft = round(1 - sum(1 for r in ar if r.result_status in ("OOS", "OOT")) / len(ar), 4) if ar else None

    open_dev = (db.query(func.count(models.DeviationRecord.deviation_id))
                .filter(models.DeviationRecord.status != "CLOSED").scalar())
    open_capa = (db.query(func.count(models.CAPARecord.capa_id))
                 .filter(models.CAPARecord.status.notin_(["CLOSED", "VERIFIED_EFFECTIVE"])).scalar())
    open_oos = (db.query(func.count(models.OOSInvestigation.oos_id))
                .filter(models.OOSInvestigation.status != "CLOSED").scalar())

    # equipment qualification / calibration compliance
    equip = db.query(models.EquipmentMaster).all()
    qualified = sum(1 for e in equip if e.current_qualification_status == "QUALIFIED")
    qual_avail = round(qualified / len(equip), 4) if equip else None
    cals = db.query(models.CalibrationRecord).all()
    cal_ok = sum(1 for c in cals if c.status == "ACTIVE")
    cal_compliance = round(cal_ok / len(cals), 4) if cals else None
    requal_due = sum(1 for e in equip if e.current_qualification_status == "REQUALIFICATION_DUE")

    # supplier quality
    supq = db.query(func.avg(models.SupplierMaster.overall_score)).scalar()
    weak = (db.query(func.count(models.SupplierMaster.supplier_id))
            .filter(models.SupplierMaster.overall_score < 65).scalar())

    # EM excursion rate
    em = db.query(models.EMResult).order_by(models.EMResult.sample_date.desc()).limit(3000).all()
    em_excursion = sum(1 for e in em if e.result_status in ("ACTION_LEVEL", "ALERT_LEVEL"))
    em_rate = round(em_excursion / len(em), 4) if em else None

    return {
        "batch": {"success_rate": batch_success, "target": 0.98},
        "quality": {"oos_rate": oos_rate, "oos_target": 0.005,
                    "right_first_time": rft, "rft_target": 0.95,
                    "open_deviations": open_dev, "open_capas": open_capa, "open_oos": open_oos},
        "equipment": {"qualified_availability": qual_avail, "qual_target": 0.95,
                      "calibration_compliance": cal_compliance, "requalification_due": requal_due},
        "supply": {"avg_supplier_score": round(supq, 1) if supq else None,
                   "target": 85, "at_risk_suppliers": weak},
        "environmental": {"excursion_rate": em_rate},
    }


def domain_kpis(db) -> list[dict]:
    from .agents.registry import AGENTS, DOMAINS
    runs = dict(db.query(models.AgentRun.agent_id, func.count(models.AgentRun.run_id))
                .group_by(models.AgentRun.agent_id).all())
    out = []
    for code, meta in DOMAINS.items():
        agent_ids = [a["id"] for a in AGENTS if a["domain"] == code]
        out.append({"domain": code, "name": meta["name"], "color": meta["color"],
                    "goal": meta["goal"], "agent_count": len(agent_ids),
                    "total_runs": sum(runs.get(aid, 0) for aid in agent_ids)})
    return out
