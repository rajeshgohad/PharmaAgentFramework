"""Data-integrity & MES-LIMS integration tools.

Address the fragmentation pain: lab (LIMS) results, shop-floor (MES/EBR) records,
and QMS sit in silos with manual handoffs. These tools reconcile across those
systems and check ALCOA+ data integrity. Real reads against the GxP DB.
"""
from __future__ import annotations

from .. import models
from .registry import ToolError, tool


@tool("PT-011b", "lims_mes_reconciliation_tool", "PROCESS_EXEC",
      "Reconcile LIMS <-> MES: find OOS results with no OOS investigation opened, and "
      "batches whose release tests all passed in LIMS but were never advanced in MES.",
      {"type": "object", "properties": {"limit": {"type": "integer"}}})
def lims_mes_reconciliation_tool(db, limit: int = 15):
    # OOS in LIMS with no QMS investigation record (broken handoff)
    invest_result_ids = {r[0] for r in
                         db.query(models.OOSInvestigation.result_id)
                         .filter(models.OOSInvestigation.result_id.isnot(None)).all()}
    oos_results = (db.query(models.AnalyticalResult)
                   .filter(models.AnalyticalResult.result_status == "OOS").all())
    oos_no_inv = [r for r in oos_results if r.result_id not in invest_result_ids]

    # batches whose release tests all PASS but batch still sitting IN_QC (not advanced)
    in_qc = db.query(models.BatchMaster).filter(models.BatchMaster.status == "IN_QC").all()
    advance_gap = []
    for b in in_qc[:300]:
        res = (db.query(models.AnalyticalResult)
               .filter(models.AnalyticalResult.batch_id == b.batch_id,
                       models.AnalyticalResult.is_release_test.is_(True)).all())
        if res and all(r.result_status == "PASS" for r in res):
            advance_gap.append(b.batch_id)

    return {
        "oos_without_investigation": len(oos_no_inv),
        "oos_gap_samples": [{"result_id": r.result_id, "batch_id": r.batch_id,
                             "test": r.test_name} for r in oos_no_inv[:limit]],
        "passed_but_not_advanced": len(advance_gap),
        "advance_gap_batches": advance_gap[:limit],
        "handoff_gaps_total": len(oos_no_inv) + len(advance_gap),
        "handoff_clean": (len(oos_no_inv) + len(advance_gap)) == 0,
    }


@tool("PT-002b", "alcoa_integrity_scan_tool", "AI_ML",
      "Scan recent GMP records for ALCOA+ data-integrity issues: EBR steps completed but "
      "not locked, steps missing second-person verification, and analytical results with no "
      "reviewer (no independent review).",
      {"type": "object", "properties": {"sample": {"type": "integer"}}})
def alcoa_integrity_scan_tool(db, sample: int = 800):
    ebr = (db.query(models.ElectronicBatchRecord)
           .order_by(models.ElectronicBatchRecord.ebr_id.desc()).limit(sample).all())
    completed = [e for e in ebr if e.status == "COMPLETED"]
    unlocked = [e for e in completed if not e.locked]           # contemporaneous/immutable breach
    no_verifier = [e for e in completed if not e.verifier_id]   # missing dual verification

    ar = (db.query(models.AnalyticalResult)
          .order_by(models.AnalyticalResult.result_id.desc()).limit(sample).all())
    no_reviewer = [r for r in ar if not r.reviewer_id]          # no second-person review

    issues = {
        "ebr_completed_but_unlocked": len(unlocked),
        "ebr_missing_verifier": len(no_verifier),
        "results_missing_reviewer": len(no_reviewer),
    }
    total = sum(issues.values())
    return {"ebr_scanned": len(ebr), "results_scanned": len(ar),
            "issues": issues, "total_issues": total,
            "alcoa_compliant": total == 0,
            "worst_category": max(issues, key=issues.get) if total else None}


@tool("PT-021c", "cross_system_reconciliation_tool", "DATA_ACCESS",
      "Cross-system reconciliation: analytical results with no linked LIMS test order "
      "(orphaned), and completed batches missing a material reconciliation record.",
      {"type": "object", "properties": {"limit": {"type": "integer"}}})
def cross_system_reconciliation_tool(db, limit: int = 15):
    ar = (db.query(models.AnalyticalResult)
          .order_by(models.AnalyticalResult.result_id.desc()).limit(1500).all())
    orphaned = [r for r in ar if not r.test_order_id]

    approved = (db.query(models.BatchMaster)
                .filter(models.BatchMaster.status.in_(["APPROVED", "QC_COMPLETE"])).all())
    recon_batches = {r[0] for r in db.query(models.MaterialReconciliation.batch_id).all()}
    missing_recon = [b.batch_id for b in approved if b.batch_id not in recon_batches]

    total = len(orphaned) + len(missing_recon)
    return {
        "orphaned_results_no_test_order": len(orphaned),
        "orphaned_samples": [{"result_id": r.result_id, "batch_id": r.batch_id}
                             for r in orphaned[:limit]],
        "batches_missing_reconciliation": len(missing_recon),
        "missing_recon_samples": missing_recon[:limit],
        "reconciliation_gaps_total": total,
        "reconciled_clean": total == 0,
    }
