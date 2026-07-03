"""Generate 95 days of transactional history over the seeded master data.

Embeds the GxP signals agents act on:
  * batches with occasional CPP excursions, deviations, and yield OOS;
  * analytical results with an OOS cluster on one product;
  * temperature excursions on one cold-storage unit;
  * EM action-level events in the aseptic area;
  * CoA rejections from the weak suppliers;
  * stability degradation trending over time.

High-volume tables use bulk inserts for speed.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .. import models
from ..config import CPP_SAMPLES_PER_STEP, SIM_DAYS, SIM_SEED, TEMP_SAMPLE_MINUTES

rng = random.Random(SIM_SEED + 1)

STEP_TYPES = ["DISPENSING", "GRANULATION", "DRYING", "BLENDING", "COMPRESSION",
              "COATING", "INSPECTION", "PACKAGING"]
RELEASE_TESTS = [("Assay", "HPLC", 95.0, 105.0, 100.0),
                 ("Dissolution", "DISSOLUTION", 80.0, 100.0, 92.0),
                 ("Water Content", "KARL_FISCHER", 0.0, 5.0, 2.5),
                 ("Related Substances", "HPLC", 0.0, 2.0, 0.4),
                 ("Uniformity of Dosage", "HPLC", 85.0, 115.0, 100.0)]
ORGANISMS = ["Staphylococcus epidermidis", "Micrococcus spp.", "Bacillus spp.",
             "Penicillium spp.", "Aspergillus spp.", "Other/Mixed"]
MEDDRA_PT = ["Nausea", "Headache", "Rash", "Dizziness", "Hepatic enzyme increased",
             "Hypersensitivity", "Vomiting", "Pruritus"]
DEV_CATEGORIES = ["Equipment failure", "Process parameter drift", "Human error",
                  "Material non-conformance", "Environmental"]


def generate_history(db, seeds: dict) -> datetime:
    end = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=SIM_DAYS)

    products = seeds["product_ids"]
    materials = seeds["material_ids"]
    suppliers = seeds["supplier_ids"]
    equipment = seeds["equipment_ids"]
    areas = seeds["area_ids"]
    storage_units = seeds["storage_units"]
    em_locations = seeds["em_locations"]

    oos_cluster_product = "PRD-005"        # embedded OOS cluster
    excursion_unit = "FRIDGE-02"           # embedded temp excursions

    ebr_rows, msl_rows, ipc_rows, ar_rows, oos_rows = [], [], [], [], []
    dev_rows, capa_rows, disp_rows, recon_rows = [], [], [], []
    tqo_rows, coa_rows, em_rows, thl_rows = [], [], [], []
    clean_rows, mwo_rows, stab_rows, ae_rows, sig_rows = [], [], [], [], []
    batch_rows, ib_rows = [], []

    seq = {k: 0 for k in ["batch", "ebr", "ipc", "ar", "oos", "dev", "capa", "disp",
                          "recon", "tqo", "coa", "em", "clean", "mwo", "stab", "ae", "sig"]}

    # -- batches over the window --------------------------------------------
    for d in range(SIM_DAYS):
        day = start + timedelta(days=d)
        if day.weekday() >= 5:             # 2-shift, 5-day plant
            continue
        for _ in range(rng.randint(6, 10)):
            seq["batch"] += 1
            b = seq["batch"]
            pid = rng.choice(products)
            batch_id = f"BAT-{b:05d}"
            mfg = day
            status = rng.choices(
                ["APPROVED", "IN_QC", "QP_REVIEW", "REJECTED", "IN_MANUFACTURE"],
                weights=[72, 12, 8, 3, 5])[0]
            yield_pct = round(rng.gauss(99.1, 0.9), 3)
            yield_oos = yield_pct < 96 or yield_pct > 102
            batch_rows.append(dict(
                batch_id=batch_id, batch_number=f"{pid}-2026-{b:05d}", product_id=pid,
                formula_id=f"FRM-{pid[-3:]}", batch_type="COMMERCIAL",
                batch_size_planned=400, batch_size_actual=round(400 * yield_pct / 100, 1),
                batch_size_uom="KG", manufacturing_date=mfg.date(),
                expiry_date=(mfg + timedelta(days=730)).date(),
                manufacturing_area_id=rng.choice(areas[:7]),
                status=status, disposition=("REJECT" if status == "REJECTED" else
                                            ("RELEASE" if status == "APPROVED" else None)),
                qp_release_date=mfg.date() + timedelta(days=6) if status == "APPROVED" else None,
                yield_pct=yield_pct, created_at=mfg))

            for s_idx, stype in enumerate(rng.sample(STEP_TYPES, k=rng.randint(4, 6))):
                seq["ebr"] += 1
                st = mfg + timedelta(hours=s_idx * 3)
                cpp_breach = rng.random() < 0.04
                ebr_rows.append(dict(
                    ebr_id=f"EBR-{seq['ebr']:06d}", batch_id=batch_id, step_number=s_idx + 1,
                    step_name=f"{stype.title()} step", step_type=stype, status="COMPLETED",
                    started_at=st, completed_at=st + timedelta(hours=2),
                    operator_id=f"OP-{rng.randint(1,40):03d}",
                    verifier_id=f"OP-{rng.randint(1,40):03d}",
                    equipment_id=rng.choice(equipment), parameters_recorded={"ok": True},
                    ipc_result=rng.choice(["PASS", "PASS", "PASS", "FAIL"]), locked=True))
                for k in range(CPP_SAMPLES_PER_STEP):
                    breach = cpp_breach and k > CPP_SAMPLES_PER_STEP - 3
                    val = round(rng.uniform(8, 18) * (1.15 if breach else 1.0), 3)
                    msl_rows.append(dict(
                        batch_id=batch_id, equipment_id=rng.choice(equipment),
                        timestamp=st + timedelta(minutes=k * 10),
                        parameter_name="Main Compression Force", value=val, uom="kN",
                        within_nor=not breach, within_par=not breach, data_source="PAT"))
                seq["ipc"] += 1
                ipc_fail = rng.random() < 0.02
                ipc_rows.append(dict(
                    ipc_result_id=f"IPC-{seq['ipc']:06d}", batch_id=batch_id,
                    ebr_id=f"EBR-{seq['ebr']:06d}", step_type=stype,
                    ipc_test_name="Tablet Weight", timestamp=st + timedelta(hours=1),
                    measured_value=round(rng.gauss(500, 6), 2), usl=515, lsl=485, target=500,
                    uom="mg", result="FAIL" if ipc_fail else "PASS",
                    operator_id=f"OP-{rng.randint(1,40):03d}"))

            if status in ("APPROVED", "IN_QC", "QP_REVIEW", "REJECTED"):
                seq["tqo"] += 1
                tqo_rows.append(dict(
                    test_order_id=f"TQO-{seq['tqo']:06d}",
                    test_order_number=f"LT-2026-{seq['tqo']:06d}", order_type="RELEASE",
                    batch_id=batch_id, priority="NORMAL",
                    assigned_analyst=f"AN-{rng.randint(1,15):03d}", status="APPROVED",
                    requested_date=mfg + timedelta(days=3), sla_hours=48))
                base_oos = 0.12 if pid == oos_cluster_product else 0.01
                for (tname, mtype, lsl, usl, tgt) in RELEASE_TESTS:
                    is_oos = rng.random() < base_oos
                    val = (usl + abs(rng.gauss(0, 0.5)) if is_oos and rng.random() < 0.5
                           else (lsl - abs(rng.gauss(0, 0.5)) if is_oos
                                 else rng.gauss(tgt, (usl - lsl) / 12)))
                    seq["ar"] += 1
                    rid = f"AR-{seq['ar']:07d}"
                    rstatus = "OOS" if is_oos else ("OOT" if rng.random() < 0.02 else "PASS")
                    ar_rows.append(dict(
                        result_id=rid, test_order_id=f"TQO-{seq['tqo']:06d}", batch_id=batch_id,
                        product_id=pid, test_name=tname, method_type=mtype,
                        instrument_id=rng.choice(equipment),
                        run_date=mfg + timedelta(days=3, hours=rng.randint(0, 40)),
                        analyst_id=f"AN-{rng.randint(1,15):03d}",
                        reviewer_id=f"AN-{rng.randint(1,15):03d}",
                        reported_result=round(val, 4), uom="%", usl=usl, lsl=lsl,
                        result_status=rstatus, is_release_test=True))
                    if rstatus == "OOS":
                        seq["oos"] += 1
                        oos_rows.append(dict(
                            oos_id=f"OOS-{seq['oos']:05d}", oos_number=f"OOS-2026-{seq['oos']:05d}",
                            result_id=rid, batch_id=batch_id, product_id=pid, test_name=tname,
                            oos_value=round(val, 4), specification_limit=usl,
                            detection_date=mfg + timedelta(days=3), phase=rng.choice([1, 2]),
                            phase1_conclusion=rng.choice(
                                ["LAB_ERROR_CONFIRMED", "NO_ASSIGNABLE_CAUSE", "IN_PROGRESS"]),
                            batch_disposition=rng.choice(
                                ["PENDING", "REJECT", "RELEASE_WITH_DEVIATION"]),
                            capa_required=True, status=rng.choice(["OPEN", "PHASE2", "CLOSED"])))

            for sev, prob in [("CRITICAL", 0.02), ("MAJOR", 0.12), ("MINOR", 0.35)]:
                if rng.random() < prob:
                    seq["dev"] += 1
                    dev_rows.append(dict(
                        deviation_id=f"DEV-{seq['dev']:05d}",
                        deviation_number=f"DEV-2026-{seq['dev']:05d}", source="MANUFACTURING",
                        severity=sev, detection_date=mfg + timedelta(hours=rng.randint(1, 40)),
                        detected_by=f"OP-{rng.randint(1,40):03d}", batch_id=batch_id,
                        equipment_id=rng.choice(equipment),
                        description=f"{sev} deviation during manufacture",
                        step_of_occurrence=rng.choice(STEP_TYPES),
                        batch_impact=rng.choice(["NONE", "POTENTIAL", "CONFIRMED"]),
                        root_cause_category=rng.choice(DEV_CATEGORIES),
                        capa_required=(sev in ("CRITICAL", "MAJOR")),
                        status=rng.choice(["OPEN", "UNDER_INVESTIGATION", "CLOSED", "CLOSED"]),
                        qp_notified=(sev == "CRITICAL"), created_at=mfg))
                    if sev in ("CRITICAL", "MAJOR"):
                        seq["capa"] += 1
                        capa_rows.append(dict(
                            capa_id=f"CAPA-{seq['capa']:05d}",
                            capa_number=f"CAPA-2026-{seq['capa']:05d}", capa_source="DEVIATION",
                            source_record_id=f"DEV-{seq['dev']:05d}", product_id=pid,
                            root_cause="Under investigation" if rng.random() < 0.3
                            else "Process drift identified",
                            root_cause_method=rng.choice(["FIVE_WHY", "FISHBONE"]),
                            corrective_action="Adjust parameters and retrain",
                            preventive_action="Update SOP and add in-process check",
                            owner=f"ENG-{rng.randint(1,20):03d}",
                            target_close_date=(mfg + timedelta(days=30)).date(),
                            actual_close_date=(mfg + timedelta(days=rng.randint(10, 50))).date()
                            if rng.random() < 0.6 else None,
                            status=rng.choice(
                                ["CLOSED", "IMPLEMENTING", "PENDING_VERIFICATION", "OVERDUE"]),
                            effectiveness_verified=rng.random() < 0.6, created_at=mfg))

            seq["recon"] += 1
            recon_rows.append(dict(
                recon_id=f"REC-{seq['recon']:05d}", batch_id=batch_id,
                material_id=rng.choice(materials), qty_dispensed=400,
                qty_waste=round(400 * (100 - yield_pct) / 100, 2),
                qty_unaccounted=round(abs(rng.gauss(0, 1.0)), 2), theoretical_yield=400,
                actual_yield=round(400 * yield_pct / 100, 2), yield_pct=yield_pct,
                yield_within_spec=not yield_oos, reconciliation_status="COMPLETE",
                reconciled_at=mfg + timedelta(days=5)))

            for _ in range(rng.randint(2, 4)):
                seq["disp"] += 1
                th = round(rng.uniform(1, 200), 3)
                fail = rng.random() < 0.02
                act = round(th * (1.05 if fail else rng.uniform(0.99, 1.01)), 3)
                disp_rows.append(dict(
                    dispensing_id=f"DSP-{seq['disp']:06d}", batch_id=batch_id,
                    material_id=rng.choice(materials), lot_number=f"L{rng.randint(1000,9999)}",
                    theoretical_qty=th, tolerance_low=th * 0.98, tolerance_high=th * 1.02,
                    actual_qty_dispensed=act, uom="KG", within_tolerance=not fail,
                    balance_id=f"BAL-{rng.randint(1,10):02d}",
                    primary_operator_id=f"OP-{rng.randint(1,40):03d}",
                    verifier_id=f"OP-{rng.randint(1,40):03d}",
                    dispensing_datetime=mfg + timedelta(hours=rng.randint(0, 8))))

    for i, mid in enumerate(materials):
        approved = rng.randint(0, 2000)
        quarantine = rng.randint(0, 300)
        reserved = rng.randint(0, min(approved, 200))
        low = rng.random() < 0.12
        ib_rows.append(dict(
            ib_id=f"IB-{i:05d}", material_id=mid, lot_number=f"L{i:05d}",
            warehouse_area_id="AR-WHRM", qty_total=approved + quarantine,
            qty_quarantine=quarantine, qty_approved=(50 if low else approved),
            qty_reserved=reserved, qty_available=(50 - reserved if low else approved - reserved),
            uom="KG", material_status="APPROVED",
            expiry_date=(end + timedelta(days=rng.randint(-10, 700))).date(),
            supplier_id=rng.choice(suppliers),
            last_status_change=end - timedelta(days=rng.randint(1, 60))))

    weak = set(suppliers[-5:])
    for i in range(700):
        sup = rng.choice(suppliers)
        rej = rng.random() < (0.10 if sup in weak else 0.01)
        seq["coa"] += 1
        coa_rows.append(dict(
            coa_id=f"COA-{seq['coa']:06d}", supplier_id=sup, material_id=rng.choice(materials),
            supplier_lot_number=f"SL{rng.randint(10000,99999)}",
            internal_lot_number=f"L{rng.randint(10000,99999)}",
            manufacturing_date=(start + timedelta(days=rng.randint(0, SIM_DAYS))).date(),
            release_date=(start + timedelta(days=rng.randint(0, SIM_DAYS))).date(),
            tests=[{"test": "Assay", "pass": not rej}], all_tests_pass=not rej,
            status="REJECTED" if rej else "ACCEPTED"))

    for d in range(SIM_DAYS):
        day = start + timedelta(days=d)
        for (aid, loc, iso) in em_locations:
            if rng.random() < 0.5:
                continue
            aseptic = aid == "AR-FILL"
            action_p = 0.03 if aseptic else 0.005
            r = rng.random()
            if r < action_p:
                cfu, rstatus = rng.uniform(10, 30), "ACTION_LEVEL"
            elif r < action_p + 0.06:
                cfu, rstatus = rng.uniform(3, 9), "ALERT_LEVEL"
            else:
                cfu, rstatus = rng.uniform(0, 2), "WITHIN_LIMIT"
            seq["em"] += 1
            em_rows.append(dict(
                em_result_id=f"EM-{seq['em']:06d}", area_id=aid, sample_location=loc,
                monitoring_type="VIABLE", sample_date=day.replace(hour=rng.randint(6, 20)),
                cfu_count=round(cfu, 1), action_limit_cfu=(1 if aseptic else 10),
                alert_limit_cfu=(0.5 if aseptic else 5),
                organism_identified=(rng.choice(ORGANISMS) if cfu > 2 else None),
                result_status=rstatus, particles_05um=rng.randint(100, 3000),
                requires_investigation=(rstatus == "ACTION_LEVEL")))

    samples_per_day = max(1, (24 * 60) // TEMP_SAMPLE_MINUTES)
    for d in range(SIM_DAYS):
        day = start + timedelta(days=d)
        for unit in storage_units:
            lsl, usl = (2, 8) if "FRIDGE" in unit else (
                (-25, -15) if "FREEZER" in unit else (15, 25))
            excursion_day = unit == excursion_unit and rng.random() < 0.15
            for s in range(samples_per_day):
                ts = day + timedelta(minutes=s * TEMP_SAMPLE_MINUTES)
                temp = (usl + lsl) / 2 + rng.uniform(-1.5, 1.5)
                if excursion_day and samples_per_day // 3 < s < samples_per_day // 3 + 6:
                    temp = usl + rng.uniform(1, 4)
                within = lsl <= temp <= usl
                thl_rows.append(dict(
                    area_id="AR-WHFG", storage_unit_id=unit, timestamp=ts,
                    temperature_c=round(temp, 2), humidity_pct=round(rng.uniform(40, 60), 1),
                    temperature_usl=usl, temperature_lsl=lsl, within_spec=within,
                    alert_triggered=not within))

    for i in range(400):
        seq["clean"] += 1
        fail = rng.random() < 0.03
        clean_rows.append(dict(
            cleaning_id=f"CLN-{seq['clean']:05d}", equipment_id=rng.choice(equipment),
            previous_product=rng.choice(products), next_product=rng.choice(products),
            cleaning_sop_ref=f"SOP-CLN-{rng.randint(1,20):03d}",
            cleaning_date=(start + timedelta(days=rng.randint(0, SIM_DAYS))).date(),
            operator_id=f"OP-{rng.randint(1,40):03d}",
            supervisor_id=f"SUP-{rng.randint(1,10):03d}", visual_inspection="PASS",
            cleaning_verification_type=rng.choice(["SWAB", "RINSE", "VISUAL_ONLY"]),
            verification_result="FAIL" if fail else "PASS", line_clearance_issued=not fail,
            maco_limit=round(rng.uniform(1, 50), 4),
            actual_carryover=round(rng.uniform(0.1, 60 if fail else 20), 4)))
    for a in equipment:
        for _ in range(rng.randint(2, 5)):
            seq["mwo"] += 1
            wt = rng.choices(["PM", "CORRECTIVE", "EMERGENCY", "CALIBRATION"],
                             weights=[50, 30, 10, 10])[0]
            fdate = start + timedelta(days=rng.randint(0, SIM_DAYS - 1))
            mwo_rows.append(dict(
                mwo_id=f"MWO-{seq['mwo']:06d}", wo_number=f"WO{seq['mwo']:06d}",
                equipment_id=a, wo_type=wt, priority=rng.randint(1, 5), status="COMPLETED",
                gmp_relevant=True, requalification_required=(wt == "EMERGENCY"),
                work_description=f"{wt} activity", planned_start=fdate, actual_start=fdate,
                actual_end=fdate + timedelta(hours=rng.uniform(1, 6)),
                assigned_technician=f"TECH-{rng.randint(1,20):03d}",
                labor_hours_actual=round(rng.uniform(1, 6), 1),
                parts_cost=round(rng.uniform(50, 4000), 2),
                labor_cost=round(rng.uniform(85, 600), 2),
                production_impact_hrs=round(rng.uniform(0, 8), 1), created_at=fdate))

    for i, pid in enumerate(products):
        marginal = i % 10 == 0
        for tp in [0, 3, 6, 9, 12, 18, 24]:
            assay = 100.0 - (0.30 * tp) - (0.15 * tp if marginal else 0) + rng.uniform(-0.5, 0.5)
            seq["stab"] += 1
            stab_rows.append(dict(
                stab_result_id=f"STR-{seq['stab']:05d}", study_id=f"STB-{i:03d}", product_id=pid,
                timepoint_months=tp, pull_date=(end - timedelta(days=(24 - tp) * 30)).date(),
                test_name="Assay", result_value=round(assay, 3), uom="%", usl=105, lsl=95,
                result_status="OOS" if assay < 95 else "PASS", degradation_trend="DECREASING"))

    for i in range(SIM_DAYS // 7 * 8):
        seq["ae"] += 1
        serious = rng.random() < 0.15
        rd = start + timedelta(days=rng.randint(0, SIM_DAYS - 1))
        ae_rows.append(dict(
            ae_id=f"AE-{seq['ae']:05d}", icsr_number=f"US-PHARMACO-2026-{seq['ae']:06d}",
            source_type=rng.choice(["SPONTANEOUS", "LITERATURE", "SOLICITED"]),
            report_date=rd.date(), receipt_date=rd.date(), product_id=rng.choice(products),
            patient_age=rng.randint(18, 85), patient_sex=rng.choice(["M", "F"]),
            event_meddra_pt=rng.choice(MEDDRA_PT), event_meddra_soc="General disorders",
            event_outcome=rng.choice(["RECOVERED", "NOT_RECOVERED", "UNKNOWN"]),
            is_serious=serious, causality=rng.choice(["POSSIBLE", "PROBABLE", "UNLIKELY"]),
            submission_deadline=(rd + timedelta(days=15 if serious else 90)).date(),
            submitted_to_fda=rng.random() < 0.9, status=rng.choice(["OPEN", "CLOSED"])))
    for i in range(6):
        seq["sig"] += 1
        prr = round(rng.uniform(1.0, 4.5), 2)
        sig_rows.append(dict(
            signal_id=f"SIG-{seq['sig']:04d}", signal_number=f"SIG-2026-{seq['sig']:04d}",
            product_id=rng.choice(products), meddra_pt=rng.choice(MEDDRA_PT),
            detection_method="STATISTICAL", prr=prr, ror=round(prr * rng.uniform(0.9, 1.2), 2),
            ic_value=round(rng.uniform(-0.5, 2.5), 2), number_of_cases=rng.randint(3, 40),
            detection_date=(end - timedelta(days=rng.randint(1, 60))).date(),
            known_risk=rng.random() < 0.5, validated_signal=(prr >= 2 and rng.random() < 0.5),
            action_required=rng.choice(["NONE", "LABEL_UPDATE", "REGULATORY_REPORT"]),
            status=rng.choice(["OPEN", "UNDER_ASSESSMENT", "CLOSED"])))

    for i in range(20):
        ncrit = rng.choices([0, 1], weights=[85, 15])[0]
        audit_id = f"AUD-{i:04d}"
        db.add(models.AuditRecord(
            audit_id=audit_id, audit_number=f"AUD-2026-{i:04d}",
            audit_type=rng.choice(["INTERNAL_GMP", "SUPPLIER", "MOCK_INSPECTION"]),
            area_audited=rng.choice(areas),
            supplier_audited=rng.choice(suppliers) if i % 3 == 0 else None,
            audit_date_from=(start + timedelta(days=rng.randint(0, SIM_DAYS))).date(),
            status="CLOSED", overall_rating=rng.choice(["SATISFACTORY", "CONDITIONAL"]),
            num_critical_findings=ncrit, num_major_findings=rng.randint(0, 3),
            num_minor_findings=rng.randint(0, 6)))
        for f in range(rng.randint(0, 4)):
            db.add(models.AuditFinding(
                finding_id=f"FND-{i:04d}-{f}", audit_id=audit_id,
                regulatory_reference=rng.choice(["21 CFR 211.68", "21 CFR 211.100", "EU GMP 4.19"]),
                severity=rng.choice(["MAJOR", "MINOR", "OBSERVATION"]),
                description="Finding identified during audit", capa_required=True,
                status=rng.choice(["OPEN", "CLOSED"])))

    for i in range(30):
        db.add(models.ChangeControlRecord(
            cc_id=f"CC-{i:04d}", cc_number=f"CC-2026-{i:04d}",
            change_type=rng.choice(["PROCESS", "EQUIPMENT", "METHOD", "SPECIFICATION"]),
            classification=rng.choice(["MINOR", "MODERATE", "MAJOR"]),
            description="Proposed change to validated system",
            regulatory_impact=rng.choice(["NONE", "INFORM", "PRIOR_APPROVAL"]),
            validation_required=rng.random() < 0.5, requalification_required=rng.random() < 0.3,
            initiator=f"ENG-{rng.randint(1,20):03d}",
            target_implementation=(end + timedelta(days=rng.randint(10, 120))).date(),
            status=rng.choice(["DRAFT", "UNDER_REVIEW", "APPROVED", "IMPLEMENTING", "CLOSED"])))

    for i in range(400):
        db.add(models.TrainingRecord(
            training_id=f"TR-{i:05d}", employee_id=f"USR-{rng.randint(1,60):03d}",
            employee_name=f"Employee {rng.randint(1,60)}",
            department=rng.choice(["QA", "Manufacturing", "QC", "Engineering"]),
            role=rng.choice(["Operator", "Analyst", "Supervisor", "Engineer"]),
            document_id=f"DOC-{rng.randint(0,59):03d}",
            training_type=rng.choice(["READ_AND_UNDERSTOOD", "CLASSROOM", "E_LEARNING", "ASSESSMENT"]),
            training_date=(start + timedelta(days=rng.randint(0, SIM_DAYS))).date(),
            training_status=rng.choice(["COMPLETED", "COMPLETED", "OVERDUE"]),
            assessment_passed=rng.random() < 0.95,
            next_due_date=(end + timedelta(days=rng.randint(-20, 400))).date(),
            training_compliance=rng.random() < 0.92))

    _bulk(db, models.BatchMaster, batch_rows)
    _bulk(db, models.ElectronicBatchRecord, ebr_rows)
    _bulk(db, models.ManufacturingStepLog, msl_rows)
    _bulk(db, models.InProcessControlResult, ipc_rows)
    _bulk(db, models.QCTestOrder, tqo_rows)
    _bulk(db, models.AnalyticalResult, ar_rows)
    _bulk(db, models.OOSInvestigation, oos_rows)
    _bulk(db, models.DeviationRecord, dev_rows)
    _bulk(db, models.CAPARecord, capa_rows)
    _bulk(db, models.DispensingRecord, disp_rows)
    _bulk(db, models.MaterialReconciliation, recon_rows)
    _bulk(db, models.InventoryBalance, ib_rows)
    _bulk(db, models.CoARecord, coa_rows)
    _bulk(db, models.EMResult, em_rows)
    _bulk(db, models.TemperatureHumidityLog, thl_rows)
    _bulk(db, models.CleaningRecord, clean_rows)
    _bulk(db, models.MaintenanceWorkOrder, mwo_rows)
    _bulk(db, models.StabilityResult, stab_rows)
    _bulk(db, models.AdverseEventReport, ae_rows)
    _bulk(db, models.SignalAssessment, sig_rows)

    db.commit()
    return end


def _bulk(db, model, rows):
    if rows:
        db.bulk_insert_mappings(model, rows)
