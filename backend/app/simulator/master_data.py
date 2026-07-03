"""Seed static master data: hierarchy, products, materials, suppliers, equipment.

Deterministic (seeded RNG) so every rebuild produces the same plant. Embeds the
GxP patterns agents reason over: a weak supplier tail, equipment nearing
qualification/calibration expiry, potent (OEB) products, controlled substances.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .. import models
from ..config import N_EQUIPMENT, N_MATERIALS, N_PRODUCTS, N_SUPPLIERS, SIM_SEED

rng = random.Random(SIM_SEED)

AREAS = [
    ("AR-DISP", "DISP-01", "Dispensing Suite", "DISPENSING", "ISO8", "D"),
    ("AR-GRAN", "GRAN-01", "Granulation Suite", "GRANULATION", "ISO8", "D"),
    ("AR-COMP", "COMP-01", "Compression Suite", "COMPRESSION", "ISO8", "D"),
    ("AR-COAT", "COAT-01", "Coating Suite", "COATING", "ISO8", "D"),
    ("AR-ENCAP", "ENCAP-01", "Encapsulation Suite", "ENCAPSULATION", "ISO8", "D"),
    ("AR-FILL", "FILL-01", "Aseptic Filling", "ASEPTIC_FILLING", "ISO5", "A"),
    ("AR-PKG", "PKG-01", "Primary Packaging", "PACKAGING", "ISO8", "D"),
    ("AR-QCL", "QCL-01", "QC Laboratory", "QC_LABORATORY", None, None),
    ("AR-WHQL", "WH-QL", "Quarantine Warehouse", "QUARANTINE", None, None),
    ("AR-WHRM", "WH-RM", "Raw Material Store", "WAREHOUSE", None, None),
    ("AR-WHFG", "WH-FG", "Finished Goods Store", "WAREHOUSE", None, None),
]

DOSAGE_FORMS = (["TABLET"] * 8 + ["CAPSULE"] * 5 + ["COATED_TABLET"] * 4
                + ["ORAL_SOLUTION"] * 2 + ["INJECTABLE_SOLUTION"] * 1)
THERAPEUTIC = ["Analgesic", "Antihypertensive", "Statin", "Antibiotic", "PPI",
               "Antifungal", "Antidiabetic", "Antihistamine", "Anticoagulant"]
API_NAMES = ["Paracetamol", "Amlodipine", "Atorvastatin", "Amoxicillin",
             "Omeprazole", "Fluconazole", "Metformin", "Cetirizine",
             "Warfarin", "Ibuprofen", "Losartan", "Simvastatin"]

# CPPs for tablet manufacturing (Data.md §4.3)
CPPS = [
    ("GRANULATION", "Impeller Speed", "RPM", 100, 200),
    ("GRANULATION", "Granule LOD", "%", 2.0, 4.5),
    ("DRYING", "Product Temp", "C", 35, 45),
    ("DRYING", "LOD Target", "%", 1.0, 2.5),
    ("COMPRESSION", "Main Compression Force", "kN", 8.0, 18.0),
    ("COMPRESSION", "Tablet Weight", "mg", 485, 515),
    ("COATING", "Inlet Air Temperature", "C", 50, 65),
    ("COATING", "Coating Weight Gain", "%", 2.0, 4.5),
]

EQUIP_TYPES = ["FLUID_BED_DRYER", "HIGH_SHEAR_GRANULATOR", "TABLET_PRESS",
               "COATING_PAN", "CAPSULE_FILLER", "BLENDER", "HPLC",
               "DISSOLUTION_TESTER", "BALANCE", "KARL_FISCHER", "REFRIGERATOR",
               "FREEZER", "AUTOCLAVE", "ISOLATOR", "CIP_SYSTEM"]

MATERIAL_TYPES = (["API"] * 20 + ["EXCIPIENT"] * 70 + ["SOLVENT"] * 15
                  + ["PACKAGING_PRIMARY"] * 20 + ["PACKAGING_SECONDARY"] * 15
                  + ["REAGENT"] * 10)

TODAY = date(2026, 7, 1)


def seed_master(db):
    db.add(models.Enterprise(enterprise_id="ENT-PH01",
                             name="PharmaCo Manufacturing Ltd.",
                             headquarters="New Jersey, USA", fda_reg_number="FEI-1234567"))
    db.add(models.Site(site_id="SITE-PH1", enterprise_id="ENT-PH01", site_code="PLT-NJ",
                       name="New Jersey OSD Plant", site_type="ORAL_SOLID",
                       city="Princeton", country="US", gmp_certificate_ref="GMP-NJ-2024",
                       gmp_cert_expiry=TODAY + timedelta(days=300)))

    area_ids, em_locations = [], []
    for aid, code, name, atype, iso, grade in AREAS:
        area_ids.append(aid)
        db.add(models.ManufacturingArea(
            area_id=aid, site_id="SITE-PH1", area_code=code, name=name,
            area_type=atype, iso_class=iso, gmp_grade=grade,
            cleanroom_cert_expiry=TODAY + timedelta(days=rng.randint(120, 400)) if iso else None))
        if iso:  # classified areas get EM sample locations
            for j in range(1, 5):
                em_locations.append((aid, f"{code}-LOC{j}", iso))

    # -- Products -----------------------------------------------------------
    product_ids = []
    for i in range(N_PRODUCTS):
        pid = f"PRD-{i:03d}"
        product_ids.append(pid)
        form = DOSAGE_FORMS[i % len(DOSAGE_FORMS)]
        controlled = i < 3
        oeb = 5 if i in (18, 19) else rng.randint(1, 3)
        udw = rng.choice([250, 500, 750, 1000, 100, 50, 5, 10, 20, 40])
        db.add(models.ProductMaster(
            product_id=pid, product_code=f"P{i:03d}",
            product_name=f"{rng.choice(API_NAMES)} {udw}mg {form.title().replace('_',' ')}",
            dosage_form=form, strength=f"{udw} mg",
            therapeutic_class=rng.choice(THERAPEUTIC), api_name=rng.choice(API_NAMES),
            unit_dose_weight_mg=udw, batch_size=rng.choice([200, 300, 400, 500]),
            batch_size_uom="KG", shelf_life_months=rng.choice([24, 36]),
            storage_condition=rng.choice(["25C/60%RH", "2-8C"]),
            controlled_substance=controlled,
            dea_schedule=(rng.choice(["II", "III", "IV"]) if controlled else None),
            oeb_level=oeb))
        db.add(models.BatchFormula(
            formula_id=f"FRM-{i:03d}", product_id=pid, formula_version="02",
            batch_size=rng.choice([200, 300, 400, 500]), batch_size_uom="KG",
            theoretical_yield_pct=99.1, yield_spec_min_pct=96.0, yield_spec_max_pct=102.0))
        if form in ("TABLET", "COATED_TABLET"):
            for j, (step, pname, uom, lo, hi) in enumerate(CPPS):
                db.add(models.CriticalProcessParameter(
                    cpp_id=f"CPP-{i:03d}-{j:02d}", product_id=pid, step_type=step,
                    parameter_name=pname, uom=uom, nor_low=lo, nor_high=hi,
                    par_low=lo * 0.9, par_high=hi * 1.1,
                    criticality=rng.choice(["CRITICAL", "IMPORTANT"]),
                    pat_monitored=True, pre_alarm_pct=90,
                    linked_cqa=rng.choice(["Assay", "Dissolution", "Content Uniformity"])))
        for j, fn in enumerate(["API", "DILUENT", "BINDER", "DISINTEGRANT", "LUBRICANT"]):
            db.add(models.BatchFormulaComponent(
                component_id=f"BFC-{i:03d}-{j}", formula_id=f"FRM-{i:03d}", line_number=j + 1,
                material_code=f"M{rng.randint(0, N_MATERIALS-1):04d}",
                material_description=f"{fn} material", component_function=fn,
                quantity_per_batch=round(rng.uniform(1, 200), 3), uom="KG",
                overage_pct=rng.choice([0, 0, 1, 2]), tolerance_pct=rng.choice([1.0, 2.0]),
                is_critical=(fn == "API")))
        db.add(models.ProductRegistration(
            registration_id=f"REG-{i:03d}", product_id=pid, market="USA",
            registration_type=rng.choice(["NDA", "ANDA"]),
            application_number=f"ANDA-{200000 + i}", approval_date=date(2020, 1, 1),
            approval_agency="FDA", renewal_due=TODAY + timedelta(days=rng.randint(60, 700)),
            status="APPROVED"))
        # long-term stability study per product
        db.add(models.StabilityStudy(
            study_id=f"STB-{i:03d}", product_id=pid, batch_id=None,
            study_type="LONG_TERM", storage_condition="25C/60%RH",
            start_date=TODAY - timedelta(days=rng.randint(200, 700)), status="ONGOING"))

    # -- Suppliers (weak tail) ----------------------------------------------
    supplier_ids = []
    for i in range(N_SUPPLIERS):
        sid = f"SUP-{i:03d}"
        supplier_ids.append(sid)
        if i < 6:
            qual, deliv, status = rng.uniform(90, 99), rng.uniform(90, 99), "APPROVED"
        elif i >= N_SUPPLIERS - 5:
            qual, deliv = rng.uniform(55, 70), rng.uniform(55, 72)
            status = rng.choice(["CONDITIONAL", "AUDIT_DUE"])
        else:
            qual, deliv, status = rng.uniform(72, 92), rng.uniform(75, 95), "APPROVED"
        last_audit = TODAY - timedelta(days=rng.randint(60, 400))
        db.add(models.SupplierMaster(
            supplier_id=sid, supplier_code=f"S{i:03d}",
            name=f"{rng.choice(['Aurobindo','Hetero','Divis','BASF','DFE','Roquette','Colorcon'])} "
                 f"{rng.choice(['API','Pharma','Excipients','Labs'])} {i}",
            supplier_type=rng.choice(["API_MANUFACTURER", "EXCIPIENT_SUPPLIER",
                                      "PACKAGING_SUPPLIER", "TESTING_LAB"]),
            country=rng.choice(["US", "IN", "DE", "CN", "IT"]),
            regulatory_status=status,
            gmp_cert_expiry=TODAY + timedelta(days=rng.randint(-20, 400)),
            last_audit_date=last_audit, last_audit_result=rng.choice(
                ["SATISFACTORY", "SATISFACTORY", "CONDITIONAL"]),
            next_audit_due=last_audit + timedelta(days=365),
            single_source=(i % 12 == 0), quality_rating=round(qual, 1),
            delivery_rating=round(deliv, 1), overall_score=round(0.5 * qual + 0.5 * deliv, 1),
            annual_spend_usd=round(rng.uniform(50_000, 8_000_000), 2)))

    # -- Materials + ASL ----------------------------------------------------
    material_ids = []
    for i in range(N_MATERIALS):
        mid = f"MAT-{i:04d}"
        material_ids.append(mid)
        mtype = MATERIAL_TYPES[i % len(MATERIAL_TYPES)]
        db.add(models.MaterialMaster(
            material_id=mid, material_code=f"M{i:04d}", material_type=mtype,
            description=f"{mtype.replace('_',' ').title()} {i}",
            grade=rng.choice(["USP", "EP", "PHARMA_GRADE"]), uom="KG",
            retest_period_months=rng.choice([12, 24, 36]),
            shelf_life_months=rng.choice([24, 36, 48]),
            storage_condition=rng.choice(["15-25C", "2-8C", "Protect from light"]),
            controlled_substance=(mtype == "API" and i % 15 == 0),
            oeb_level=(5 if (mtype == "API" and i % 17 == 0) else rng.randint(1, 3)),
            tse_bse_risk=(i % 40 == 0), safety_stock_qty=rng.randint(50, 500),
            reorder_point=rng.randint(100, 800), lead_time_days=rng.randint(14, 120),
            specification_number=f"SPEC-{i:04d}"))
        for k in range(rng.randint(1, 2)):
            db.add(models.ApprovedSupplierList(
                asl_id=f"ASL-{i:04d}-{k}", supplier_id=rng.choice(supplier_ids),
                material_id=mid, qualification_date=TODAY - timedelta(days=rng.randint(90, 700)),
                qualification_type="FULL_QUALIFICATION",
                next_review_date=TODAY + timedelta(days=rng.randint(30, 365)), status="APPROVED"))

    # -- Equipment (some with expiring qual / overdue cal) ------------------
    equipment_ids = []
    n_at_risk = max(2, int(N_EQUIPMENT * 0.08))
    for i in range(N_EQUIPMENT):
        eid = f"EQ-{i:03d}"
        equipment_ids.append(eid)
        etype = EQUIP_TYPES[i % len(EQUIP_TYPES)]
        crit = "CRITICAL" if i < 12 else ("MAJOR" if i < 45 else "MINOR")
        at_risk = i < n_at_risk
        pq = TODAY - timedelta(days=rng.randint(60, 340))
        pq_expiry = (TODAY + timedelta(days=rng.randint(3, 28))) if at_risk else pq + timedelta(days=365)
        db.add(models.EquipmentMaster(
            equipment_id=eid, equipment_tag=f"{etype[:4]}-{i:03d}",
            equipment_name=f"{etype.replace('_',' ').title()} {i}", equipment_type=etype,
            manufacturer=rng.choice(["GEA", "Glatt", "Fette", "Bosch", "Agilent", "Waters"]),
            manufacturing_area_id=rng.choice(area_ids), criticality=crit,
            current_qualification_status=("REQUALIFICATION_DUE" if at_risk else "QUALIFIED"),
            iq_date=pq - timedelta(days=60), oq_date=pq - timedelta(days=30), pq_date=pq,
            pq_expiry_date=pq_expiry, last_pm_date=TODAY - timedelta(days=rng.randint(5, 60)),
            next_pm_due=TODAY + timedelta(days=rng.randint(-5, 60)),
            computerised_system=(etype in ("HPLC", "TABLET_PRESS", "DISSOLUTION_TESTER"))))
        cal_date = TODAY - timedelta(days=rng.randint(30, 360))
        overdue = at_risk and rng.random() < 0.5
        due = (TODAY - timedelta(days=rng.randint(1, 20))) if overdue else cal_date + timedelta(days=365)
        db.add(models.CalibrationRecord(
            cal_id=f"CAL-{i:03d}", equipment_id=eid, calibration_type="EXTERNAL_ACCREDITED",
            calibration_date=cal_date, due_date=due, next_due=due, performed_by="MetroLab",
            parameter_tested="Accuracy", result="PASS",
            status=("OVERDUE" if overdue else "ACTIVE")))

    # -- SOPs (some overdue for review) -------------------------------------
    for i in range(60):
        db.add(models.DocumentMaster(
            doc_id=f"DOC-{i:03d}",
            document_number=f"SOP-{rng.choice(['QA','MFG','QC','ENG'])}-{i:04d}",
            document_type="SOP", title=f"Standard Operating Procedure {i}",
            department=rng.choice(["QA", "Manufacturing", "QC", "Engineering"]),
            current_version=f"0{rng.randint(1,5)}", status="EFFECTIVE",
            effective_date=TODAY - timedelta(days=rng.randint(100, 700)),
            next_review_date=TODAY + timedelta(days=rng.randint(-30, 400)),
            owner=f"USR-{rng.randint(1,40):03d}", training_required=True))

    db.commit()
    return {
        "area_ids": area_ids, "product_ids": product_ids, "supplier_ids": supplier_ids,
        "material_ids": material_ids, "equipment_ids": equipment_ids,
        "storage_units": ["FRIDGE-01", "FRIDGE-02", "FREEZER-01", "WH-FG-ROOM",
                          "WH-RM-ROOM", "STAB-CHAMBER-25", "STAB-CHAMBER-40"],
        "em_locations": em_locations,
    }
