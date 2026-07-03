"""Live simulation tick: emit new GxP transactions at the current sim cursor.

Called by the orchestrator each tick. Injects fresh analytical results (some
OOS), CPP excursions, EM action-level events, temperature excursions, and
deviations for the watcher to react to.
"""
from __future__ import annotations

import random
from datetime import datetime

from .. import models

rng = random.Random()  # live randomness (not reproducible by design)

RELEASE_TESTS = [("Assay", "HPLC", 95.0, 105.0, 100.0),
                 ("Dissolution", "DISSOLUTION", 80.0, 100.0, 92.0),
                 ("Related Substances", "HPLC", 0.0, 2.0, 0.4)]
ORGANISMS = ["Staphylococcus epidermidis", "Micrococcus spp.", "Bacillus spp.",
             "Penicillium spp.", "Aspergillus spp."]


def _next(db, id_col, prefix, width):
    last = db.query(id_col).order_by(id_col.desc()).first()
    n = 0
    if last and last[0] and "-" in last[0]:
        try:
            n = int(last[0].rsplit("-", 1)[1])
        except ValueError:
            n = 0
    return n + 1, f"{prefix}-{n + 1:0{width}d}"


def generate_tick(db, sim_time: datetime, tick: int) -> dict:
    summary = {"analytical": 0, "oos": 0, "cpp_breach": 0, "em_action": 0,
               "temp_excursion": 0, "deviations": 0}

    batches = db.query(models.BatchMaster).order_by(
        models.BatchMaster.manufacturing_date.desc()).limit(50).all()
    equipment = [e[0] for e in db.query(models.EquipmentMaster.equipment_id).all()]
    if not batches or not equipment:
        return summary

    # --- release testing with occasional OOS -------------------------------
    if rng.random() < 0.7:
        batch = rng.choice(batches)
        n_ar, _ = _next(db, models.AnalyticalResult.result_id, "AR", 7)
        cluster = batch.product_id == "PRD-005"
        for (tname, mtype, lsl, usl, tgt) in RELEASE_TESTS:
            is_oos = rng.random() < (0.25 if cluster else 0.05)
            val = usl + abs(rng.gauss(0, 0.6)) if is_oos else rng.gauss(tgt, (usl - lsl) / 12)
            rid = f"AR-{n_ar:07d}"
            n_ar += 1
            rstatus = "OOS" if is_oos else "PASS"
            db.add(models.AnalyticalResult(
                result_id=rid, batch_id=batch.batch_id, product_id=batch.product_id,
                test_name=tname, method_type=mtype, instrument_id=rng.choice(equipment),
                run_date=sim_time, analyst_id=f"AN-{rng.randint(1,15):03d}",
                reported_result=round(val, 4), uom="%", usl=usl, lsl=lsl,
                result_status=rstatus, is_release_test=True))
            summary["analytical"] += 1
            if is_oos:
                summary["oos"] += 1

    # --- CPP excursion during manufacture ----------------------------------
    if rng.random() < 0.4:
        batch = rng.choice(batches)
        breach = rng.random() < 0.5
        val = round(rng.uniform(8, 18) * (1.2 if breach else 1.0), 3)
        db.add(models.ManufacturingStepLog(
            batch_id=batch.batch_id, equipment_id=rng.choice(equipment), timestamp=sim_time,
            parameter_name="Main Compression Force", value=val, uom="kN",
            within_nor=not breach, within_par=not breach, data_source="PAT"))
        if breach:
            summary["cpp_breach"] += 1

    # --- EM action-level events --------------------------------------------
    if rng.random() < 0.5:
        aseptic = rng.random() < 0.4
        r = rng.random()
        if r < (0.25 if aseptic else 0.05):
            cfu, rstatus = rng.uniform(10, 30), "ACTION_LEVEL"
        elif r < 0.4:
            cfu, rstatus = rng.uniform(3, 9), "ALERT_LEVEL"
        else:
            cfu, rstatus = rng.uniform(0, 2), "WITHIN_LIMIT"
        _, emid = _next(db, models.EMResult.em_result_id, "EM", 6)
        db.add(models.EMResult(
            em_result_id=emid, area_id=("AR-FILL" if aseptic else "AR-COMP"),
            sample_location=f"LOC{rng.randint(1,4)}", monitoring_type="VIABLE",
            sample_date=sim_time, cfu_count=round(cfu, 1),
            action_limit_cfu=(1 if aseptic else 10), alert_limit_cfu=(0.5 if aseptic else 5),
            organism_identified=(rng.choice(ORGANISMS) if cfu > 2 else None),
            result_status=rstatus, particles_05um=rng.randint(100, 3000),
            requires_investigation=(rstatus == "ACTION_LEVEL")))
        if rstatus == "ACTION_LEVEL":
            summary["em_action"] += 1

    # --- temperature excursion ---------------------------------------------
    if rng.random() < 0.4:
        excursion = rng.random() < 0.4
        temp = round(8 + rng.uniform(1, 4) if excursion else 5 + rng.uniform(-1.5, 1.5), 2)
        db.add(models.TemperatureHumidityLog(
            area_id="AR-WHFG", storage_unit_id=rng.choice(["FRIDGE-01", "FRIDGE-02"]),
            timestamp=sim_time, temperature_c=temp, humidity_pct=round(rng.uniform(40, 60), 1),
            temperature_usl=8, temperature_lsl=2, within_spec=not excursion,
            alert_triggered=excursion))
        if excursion:
            summary["temp_excursion"] += 1

    # --- occasional fresh deviation ----------------------------------------
    if rng.random() < 0.25:
        batch = rng.choice(batches)
        sev = rng.choices(["CRITICAL", "MAJOR", "MINOR"], weights=[15, 35, 50])[0]
        n_dev, devid = _next(db, models.DeviationRecord.deviation_id, "DEV", 5)
        db.add(models.DeviationRecord(
            deviation_id=devid, deviation_number=f"DEV-2026-{n_dev:05d}", source="MANUFACTURING",
            severity=sev, detection_date=sim_time, detected_by=f"OP-{rng.randint(1,40):03d}",
            batch_id=batch.batch_id, equipment_id=rng.choice(equipment),
            description=f"Live {sev} deviation detected during manufacture",
            step_of_occurrence="COMPRESSION",
            batch_impact=("CONFIRMED" if sev == "CRITICAL" else "POTENTIAL"),
            root_cause_category="Process parameter drift",
            capa_required=(sev in ("CRITICAL", "MAJOR")), status="OPEN",
            qp_notified=(sev == "CRITICAL"), created_at=sim_time))
        summary["deviations"] += 1

    db.commit()
    return summary
