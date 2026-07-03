"""Unified Namespace (UNS) — Phase 1 (read-only projection over the existing DB).

Demonstrates data unification: the plant's siloed systems (on-prem OT/IT + cloud
SaaS) are projected into ONE ISA-95 hierarchical namespace, each value tagged with
its source system. No simulator changes — this derives the namespace from current
DB state on request. Maps to a real MQTT/Sparkplug B + OPC-UA bridge deployment.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from . import models
from .database import Base

ROOT = "PharmaCo/NJ-Plant"

# Which database tables each source system owns (the silos the UNS unifies).
SYSTEM_TABLES = {
    "mes": ["batch_master", "electronic_batch_record", "in_process_control_result",
            "batch_formula", "batch_formula_component", "critical_process_parameter"],
    "historian": ["manufacturing_step_log"],
    "lims": ["qc_test_order", "analytical_result", "oos_investigation",
             "stability_study", "stability_result"],
    "em": ["em_result"],
    "bms": ["temperature_humidity_log"],
    "scada": ["equipment_master", "calibration_record", "cleaning_record",
              "maintenance_work_order", "enterprise", "site", "manufacturing_area"],
    "erp": ["product_master", "material_master", "supplier_master", "coa_record",
            "approved_supplier_list", "inventory_balance", "dispensing_record",
            "material_reconciliation"],
    "qms": ["deviation_record", "capa_record", "change_control_record",
            "audit_record", "audit_finding", "document_master", "training_record"],
    "pv": ["adverse_event_report", "signal_assessment", "product_registration"],
    "lake": ["agent_run", "orchestration_event", "uns_event", "sim_clock"],
}

# The heterogeneous systems in a pharma plant — on-premise OT/IT + cloud SaaS.
# Each publishes part of the truth today in isolation; the UNS unifies them.
SYSTEMS = [
    {"id": "scada", "name": "SCADA / PLC (OT)", "layer": "on-prem", "color": "#fb7185",
     "protocol": "OPC-UA", "publishes": "Equipment state, sensors, alarms"},
    {"id": "historian", "name": "OSIsoft PI Historian", "layer": "on-prem", "color": "#22d3ee",
     "protocol": "OPC-UA", "publishes": "CPP / PAT time-series tags"},
    {"id": "mes", "name": "PAS-X MES / EBR", "layer": "on-prem", "color": "#f59e0b",
     "protocol": "OPC-UA / REST", "publishes": "Batch records, recipes, step status"},
    {"id": "lims", "name": "LabVantage LIMS", "layer": "on-prem", "color": "#34d399",
     "protocol": "REST", "publishes": "QC results, stability, OOS"},
    {"id": "em", "name": "EM / Particle Counters", "layer": "on-prem", "color": "#a78bfa",
     "protocol": "MQTT", "publishes": "Viable & particle counts"},
    {"id": "bms", "name": "Cold-chain / BMS", "layer": "on-prem", "color": "#60a5fa",
     "protocol": "MQTT", "publishes": "Temperature / humidity"},
    {"id": "erp", "name": "SAP S/4HANA (ERP)", "layer": "cloud", "color": "#eab308",
     "protocol": "SAP BTP / API", "publishes": "Materials, inventory, orders"},
    {"id": "qms", "name": "Veeva Vault QMS", "layer": "cloud", "color": "#9333ea",
     "protocol": "REST", "publishes": "Deviations, CAPA, change control"},
    {"id": "pv", "name": "Oracle Argus (PV)", "layer": "cloud", "color": "#f472b6",
     "protocol": "REST", "publishes": "Adverse events, safety signals"},
    {"id": "lake", "name": "Data Lake / AI + Agents", "layer": "cloud", "color": "#6366f1",
     "protocol": "Kafka / API", "publishes": "Analytics, digital twin, agents", "consumer": True},
]
SYS = {s["id"]: s for s in SYSTEMS}


def _ev(sim_time, tick, topic, source, value, status):
    return {"tick": tick, "sim_time": str(sim_time), "topic": topic,
            "source": source, "source_name": SYS[source]["name"],
            "color": SYS[source]["color"], "value": value, "status": status}


def publish_from_tick(db, sim_time, tick, window_minutes: int) -> list[dict]:
    """Translate the rows generated this tick into UNS events (each source system
    publishing its state to the namespace), persist them, and return them for
    live broadcast. This is the real-time unification layer."""
    ws = sim_time - timedelta(minutes=window_minutes)
    events: list[dict] = []

    for r in (db.query(models.AnalyticalResult)
              .filter(models.AnalyticalResult.run_date >= ws).limit(30).all()):
        events.append(_ev(sim_time, tick,
                          f"{ROOT}/QC-Lab/batch/{r.batch_id}/qc/{r.test_name}/result", "lims",
                          f"{r.reported_result} {r.uom or ''}".strip(), r.result_status))
    for r in (db.query(models.ManufacturingStepLog)
              .filter(models.ManufacturingStepLog.timestamp >= ws).limit(30).all()):
        events.append(_ev(sim_time, tick,
                          f"{ROOT}/Compression/{r.equipment_id}/cpp/{r.parameter_name.replace(' ','')}",
                          "historian", f"{r.value} {r.uom}",
                          "IN_SPEC" if r.within_par else "OUT_OF_DESIGN_SPACE"))
    for r in (db.query(models.EMResult)
              .filter(models.EMResult.sample_date >= ws).limit(20).all()):
        events.append(_ev(sim_time, tick,
                          f"{ROOT}/{r.area_id}/em/{r.sample_location}/cfu", "em",
                          f"{r.cfu_count} CFU", r.result_status))
    for r in (db.query(models.TemperatureHumidityLog)
              .filter(models.TemperatureHumidityLog.timestamp >= ws).limit(20).all()):
        events.append(_ev(sim_time, tick,
                          f"{ROOT}/ColdStore/{r.storage_unit_id}/temperature", "bms",
                          f"{r.temperature_c} °C", "IN_SPEC" if r.within_spec else "EXCURSION"))
    for r in (db.query(models.DeviationRecord)
              .filter(models.DeviationRecord.detection_date >= ws).limit(20).all()):
        events.append(_ev(sim_time, tick,
                          f"{ROOT}/QMS/batch/{r.batch_id}/deviation/{r.deviation_number}", "qms",
                          r.severity, r.status))

    if events:
        db.bulk_insert_mappings(models.UNSEvent, [
            {"tick": tick, "sim_time": sim_time, "topic": e["topic"], "source": e["source"],
             "value": e["value"], "status": e["status"]} for e in events])
        db.commit()
    return events


def recent_events(db, limit: int = 60):
    rows = (db.query(models.UNSEvent)
            .order_by(models.UNSEvent.id.desc()).limit(limit).all())
    return [{"topic": r.topic, "source": r.source, "source_name": SYS.get(r.source, {}).get("name", r.source),
             "color": SYS.get(r.source, {}).get("color", "#8ea2c4"), "value": r.value,
             "status": r.status, "tick": r.tick, "sim_time": str(r.sim_time)} for r in rows]


def systems(db=None):
    out = []
    for s in SYSTEMS:
        tables = []
        for name in SYSTEM_TABLES.get(s["id"], []):
            rows = None
            if db is not None and name in Base.metadata.tables:
                try:
                    rows = db.execute(
                        select(func.count()).select_from(Base.metadata.tables[name])).scalar()
                except Exception:  # noqa: BLE001
                    rows = None
            tables.append({"name": name, "rows": rows})
        out.append({**s, "tables": tables})
    on_prem = [s for s in SYSTEMS if s["layer"] == "on-prem"]
    cloud = [s for s in SYSTEMS if s["layer"] == "cloud"]
    return {"systems": out, "on_prem": len(on_prem), "cloud": len(cloud), "root": ROOT,
            "point_to_point_links": len(SYSTEMS) * (len(SYSTEMS) - 1) // 2,
            "uns_links": len(SYSTEMS)}


def stats(db):
    # rough topic estimate = distinct entities that would publish
    topics = (
        (db.query(func.count(models.EquipmentMaster.equipment_id)).scalar() or 0)
        + (db.query(func.count(models.BatchMaster.batch_id)).scalar() or 0)
        + (db.query(func.count(models.MaterialMaster.material_id)).scalar() or 0)
        + (db.query(func.count(models.ManufacturingArea.area_id)).scalar() or 0) * 4
    )
    published = db.query(func.count(models.UNSEvent.id)).scalar() or 0
    return {"systems_unified": len(SYSTEMS),
            "on_prem": len([s for s in SYSTEMS if s["layer"] == "on-prem"]),
            "cloud": len([s for s in SYSTEMS if s["layer"] == "cloud"]),
            "namespace_topics": topics,
            "messages_published": published,
            "point_to_point_links": len(SYSTEMS) * (len(SYSTEMS) - 1) // 2,
            "uns_links": len(SYSTEMS)}


def _node(name, source=None, value=None, status=None, topic=None, children=None):
    n = {"name": name}
    if source:
        n["source"] = source
        n["source_name"] = SYS[source]["name"]
        n["color"] = SYS[source]["color"]
    if value is not None:
        n["value"] = value
    if status:
        n["status"] = status
    if topic:
        n["topic"] = topic
    if children:
        n["children"] = children
    return n


def tree(db):
    """Bounded ISA-95 namespace with latest values from each source system."""
    areas = []

    # Compression area — CPP from Historian
    cpp = (db.query(models.ManufacturingStepLog)
           .order_by(models.ManufacturingStepLog.timestamp.desc()).first())
    if cpp:
        areas.append(_node("Compression", children=[
            _node(cpp.equipment_id or "COMP-01", children=[
                _node("cpp/MainCompressionForce", source="historian",
                      value=f"{cpp.value} {cpp.uom}",
                      status="IN_SPEC" if cpp.within_par else "OUT_OF_DESIGN_SPACE",
                      topic=f"{ROOT}/Compression/{cpp.equipment_id}/cpp/MainCompressionForce")])]))

    # QC Laboratory — latest result from LIMS
    ar = (db.query(models.AnalyticalResult)
          .order_by(models.AnalyticalResult.run_date.desc()).first())
    if ar:
        areas.append(_node("QC Laboratory", children=[
            _node(f"batch/{ar.batch_id}/qc/{ar.test_name}", source="lims",
                  value=f"{ar.reported_result} {ar.uom or ''}".strip(),
                  status=ar.result_status,
                  topic=f"{ROOT}/QC-Lab/batch/{ar.batch_id}/qc/{ar.test_name}/result")]))

    # Aseptic Filling — EM from EM system
    em = (db.query(models.EMResult).filter(models.EMResult.area_id == "AR-FILL")
          .order_by(models.EMResult.sample_date.desc()).first()) \
        or db.query(models.EMResult).order_by(models.EMResult.sample_date.desc()).first()
    if em:
        areas.append(_node("Aseptic Filling", children=[
            _node(f"em/{em.sample_location}/cfu", source="em",
                  value=f"{em.cfu_count} CFU", status=em.result_status,
                  topic=f"{ROOT}/AsepticFill/em/{em.sample_location}/cfu")]))

    # Cold Storage — temperatures from BMS
    units = (db.query(models.TemperatureHumidityLog.storage_unit_id)
             .distinct().limit(4).all())
    cold_children = []
    for (u,) in units:
        t = (db.query(models.TemperatureHumidityLog)
             .filter(models.TemperatureHumidityLog.storage_unit_id == u)
             .order_by(models.TemperatureHumidityLog.timestamp.desc()).first())
        if t:
            cold_children.append(_node(f"{u}/temperature", source="bms",
                value=f"{t.temperature_c} °C",
                status="IN_SPEC" if t.within_spec else "EXCURSION",
                topic=f"{ROOT}/ColdStore/{u}/temperature"))
    if cold_children:
        areas.append(_node("Cold Storage", children=cold_children))

    # Warehouse — inventory from SAP ERP
    short = (db.query(func.count(models.InventoryBalance.ib_id))
             .join(models.MaterialMaster,
                   models.MaterialMaster.material_id == models.InventoryBalance.material_id)
             .filter(models.InventoryBalance.qty_available <
                     models.MaterialMaster.safety_stock_qty).scalar())
    areas.append(_node("Warehouse", children=[
        _node("materials/below_safety_stock", source="erp", value=str(short),
              status="AT_RISK" if short else "OK",
              topic=f"{ROOT}/Warehouse/materials/below_safety_stock")]))

    # QMS (cloud) — open deviations from Veeva
    open_dev = (db.query(func.count(models.DeviationRecord.deviation_id))
                .filter(models.DeviationRecord.status != "CLOSED").scalar())
    open_capa = (db.query(func.count(models.CAPARecord.capa_id))
                 .filter(models.CAPARecord.status.notin_(["CLOSED", "VERIFIED_EFFECTIVE"])).scalar())
    areas.append(_node("Quality Systems", children=[
        _node("deviations/open", source="qms", value=str(open_dev),
              status="OPEN" if open_dev else "CLEAR",
              topic=f"{ROOT}/QMS/deviations/open"),
        _node("capa/open", source="qms", value=str(open_capa), status="OPEN",
              topic=f"{ROOT}/QMS/capa/open")]))

    # Pharmacovigilance (cloud) — signals from Argus
    open_sig = (db.query(func.count(models.SignalAssessment.signal_id))
                .filter(models.SignalAssessment.status != "CLOSED").scalar())
    areas.append(_node("Pharmacovigilance", children=[
        _node("signals/open", source="pv", value=str(open_sig), status="UNDER_ASSESSMENT",
              topic=f"{ROOT}/PV/signals/open")]))

    return {"name": "PharmaCo", "children": [{"name": "NJ-Plant", "children": areas}]}


def recent_batches(db, n: int = 12):
    rows = (db.query(models.BatchMaster)
            .order_by(models.BatchMaster.manufacturing_date.desc()).limit(n).all())
    return [{"batch_id": b.batch_id, "batch_number": b.batch_number,
             "product_id": b.product_id, "status": b.status} for b in rows]


def batch_360(db, batch_id: str):
    """Assemble ONE batch's complete cross-system state — the unification payoff."""
    b = db.get(models.BatchMaster, batch_id)
    if not b:
        return {"error": f"No batch {batch_id}"}
    p = db.get(models.ProductMaster, b.product_id)

    # MES / EBR
    steps = db.query(models.ElectronicBatchRecord).filter(
        models.ElectronicBatchRecord.batch_id == batch_id).all()
    cpp_breach = (db.query(func.count(models.ManufacturingStepLog.log_id))
                  .filter(models.ManufacturingStepLog.batch_id == batch_id,
                          models.ManufacturingStepLog.within_par.is_(False)).scalar())
    # LIMS
    ar = db.query(models.AnalyticalResult).filter(
        models.AnalyticalResult.batch_id == batch_id).all()
    oos = sum(1 for r in ar if r.result_status == "OOS")
    # QMS
    devs = db.query(models.DeviationRecord).filter(
        models.DeviationRecord.batch_id == batch_id).all()
    open_dev = sum(1 for d in devs if d.status != "CLOSED")
    oosi = db.query(func.count(models.OOSInvestigation.oos_id)).filter(
        models.OOSInvestigation.batch_id == batch_id).scalar()
    # ERP / reconciliation
    recon = db.query(models.MaterialReconciliation).filter(
        models.MaterialReconciliation.batch_id == batch_id).first()

    panels = [
        {"system": "mes", "name": SYS["mes"]["name"], "color": SYS["mes"]["color"],
         "layer": "on-prem", "items": [
             {"label": "EBR steps", "value": f"{sum(1 for s in steps if s.status=='COMPLETED')}/{len(steps)} complete"},
             {"label": "Batch status", "value": b.status},
             {"label": "Yield", "value": f"{b.yield_pct}%" if b.yield_pct else "—"}]},
        {"system": "historian", "name": SYS["historian"]["name"], "color": SYS["historian"]["color"],
         "layer": "on-prem", "items": [
             {"label": "CPP design-space breaches", "value": str(cpp_breach),
              "status": "OK" if not cpp_breach else "BREACH"}]},
        {"system": "lims", "name": SYS["lims"]["name"], "color": SYS["lims"]["color"],
         "layer": "on-prem", "items": [
             {"label": "Analytical results", "value": str(len(ar))},
             {"label": "OOS results", "value": str(oos), "status": "OOS" if oos else "OK"}]},
        {"system": "qms", "name": SYS["qms"]["name"], "color": SYS["qms"]["color"],
         "layer": "cloud", "items": [
             {"label": "Deviations (open)", "value": f"{open_dev} / {len(devs)}",
              "status": "OPEN" if open_dev else "CLEAR"},
             {"label": "OOS investigations", "value": str(oosi)}]},
        {"system": "erp", "name": SYS["erp"]["name"], "color": SYS["erp"]["color"],
         "layer": "cloud", "items": [
             {"label": "Yield within spec", "value": ("Yes" if recon and recon.yield_within_spec else "—" if not recon else "No")},
             {"label": "Disposition", "value": b.disposition or "PENDING"}]},
    ]
    return {"batch_id": batch_id, "batch_number": b.batch_number,
            "product": p.product_name if p else b.product_id,
            "namespace": f"{ROOT}/*/batch/{batch_id}", "panels": panels}
