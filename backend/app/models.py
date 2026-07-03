"""SQLAlchemy models — pharmaceutical manufacturing (Data.md subset).

Covers the plant hierarchy, product/formula, batch manufacturing + EBR, QC/LIMS,
suppliers, inventory, equipment, QMS (deviation/CAPA/change control), regulatory
& pharmacovigilance, environmental monitoring, and training — plus framework
runtime tables (agent runs, orchestration events). GMP records use status flags,
never hard deletes (ALCOA+).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
)

from .database import Base


# =============================================================== Plant hierarchy
class Enterprise(Base):
    __tablename__ = "enterprise"
    enterprise_id = Column(String, primary_key=True)
    name = Column(String)
    headquarters = Column(String)
    fda_reg_number = Column(String)


class Site(Base):
    __tablename__ = "site"
    site_id = Column(String, primary_key=True)
    enterprise_id = Column(String)
    site_code = Column(String)
    name = Column(String)
    site_type = Column(String)
    city = Column(String)
    country = Column(String)
    gmp_certificate_ref = Column(String)
    gmp_cert_expiry = Column(Date)


class ManufacturingArea(Base):
    __tablename__ = "manufacturing_area"
    area_id = Column(String, primary_key=True)
    site_id = Column(String)
    area_code = Column(String)
    name = Column(String)
    area_type = Column(String)
    iso_class = Column(String)
    gmp_grade = Column(String)
    cleanroom_cert_expiry = Column(Date)
    status = Column(String, default="ACTIVE")


# ============================================================= Product / formula
class ProductMaster(Base):
    __tablename__ = "product_master"
    product_id = Column(String, primary_key=True)
    product_code = Column(String)
    product_name = Column(String)
    dosage_form = Column(String)
    strength = Column(String)
    therapeutic_class = Column(String)
    api_name = Column(String)
    unit_dose_weight_mg = Column(Float)
    batch_size = Column(Float)
    batch_size_uom = Column(String)
    shelf_life_months = Column(Integer)
    storage_condition = Column(String)
    controlled_substance = Column(Boolean, default=False)
    dea_schedule = Column(String)
    oeb_level = Column(Integer)
    status = Column(String, default="ACTIVE")


class MaterialMaster(Base):
    __tablename__ = "material_master"
    material_id = Column(String, primary_key=True)
    material_code = Column(String)
    material_type = Column(String)          # API, EXCIPIENT, SOLVENT, PACKAGING_*, ...
    description = Column(String)
    grade = Column(String)
    uom = Column(String, default="KG")
    retest_period_months = Column(Integer)
    shelf_life_months = Column(Integer)
    storage_condition = Column(String)
    controlled_substance = Column(Boolean, default=False)
    oeb_level = Column(Integer)
    tse_bse_risk = Column(Boolean, default=False)
    safety_stock_qty = Column(Float)
    reorder_point = Column(Float)
    lead_time_days = Column(Integer)
    specification_number = Column(String)
    status = Column(String, default="APPROVED")


class BatchFormula(Base):
    __tablename__ = "batch_formula"
    formula_id = Column(String, primary_key=True)
    product_id = Column(String)
    formula_version = Column(String)
    batch_size = Column(Float)
    batch_size_uom = Column(String)
    theoretical_yield_pct = Column(Float)
    yield_spec_min_pct = Column(Float)
    yield_spec_max_pct = Column(Float)
    status = Column(String, default="APPROVED")


class BatchFormulaComponent(Base):
    __tablename__ = "batch_formula_component"
    component_id = Column(String, primary_key=True)
    formula_id = Column(String)
    line_number = Column(Integer)
    material_code = Column(String)
    material_description = Column(String)
    component_function = Column(String)     # API, DILUENT, BINDER, ...
    quantity_per_batch = Column(Float)
    uom = Column(String)
    overage_pct = Column(Float, default=0)
    tolerance_pct = Column(Float, default=2.0)
    is_critical = Column(Boolean, default=False)


# ============================================================ Batch manufacturing
class BatchMaster(Base):
    __tablename__ = "batch_master"
    batch_id = Column(String, primary_key=True)
    batch_number = Column(String)
    product_id = Column(String, index=True)
    formula_id = Column(String)
    batch_type = Column(String, default="COMMERCIAL")
    batch_size_planned = Column(Float)
    batch_size_actual = Column(Float)
    batch_size_uom = Column(String)
    manufacturing_date = Column(Date, index=True)
    expiry_date = Column(Date)
    manufacturing_area_id = Column(String)
    status = Column(String, default="IN_MANUFACTURE")
    # IN_MANUFACTURE, IN_QC, QC_COMPLETE, QP_REVIEW, APPROVED, REJECTED, QUARANTINE
    disposition = Column(String)            # RELEASE, REJECT, REWORK, DESTROY
    qp_release_date = Column(Date)
    yield_pct = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class ElectronicBatchRecord(Base):
    __tablename__ = "electronic_batch_record"
    ebr_id = Column(String, primary_key=True)
    batch_id = Column(String, index=True)
    step_number = Column(Integer)
    step_name = Column(String)
    step_type = Column(String)              # DISPENSING, GRANULATION, COMPRESSION, ...
    status = Column(String, default="PENDING")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    operator_id = Column(String)
    verifier_id = Column(String)
    equipment_id = Column(String)
    parameters_recorded = Column(JSON)
    ipc_result = Column(String)             # PASS, FAIL, N/A
    deviation_id = Column(String)
    locked = Column(Boolean, default=False)


class CriticalProcessParameter(Base):
    __tablename__ = "critical_process_parameter"
    cpp_id = Column(String, primary_key=True)
    product_id = Column(String)
    step_type = Column(String)
    parameter_name = Column(String)
    uom = Column(String)
    nor_low = Column(Float)                 # normal operating range
    nor_high = Column(Float)
    par_low = Column(Float)                 # proven acceptable range
    par_high = Column(Float)
    criticality = Column(String)            # CRITICAL, IMPORTANT, INFORMATIONAL
    pat_monitored = Column(Boolean, default=False)
    pre_alarm_pct = Column(Float, default=90)
    linked_cqa = Column(String)


class ManufacturingStepLog(Base):
    __tablename__ = "manufacturing_step_log"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String, index=True)
    equipment_id = Column(String)
    timestamp = Column(DateTime, index=True)
    parameter_name = Column(String)
    value = Column(Float)
    uom = Column(String)
    within_nor = Column(Boolean)
    within_par = Column(Boolean)
    data_source = Column(String)            # SCADA, PAT, MANUAL_ENTRY, BALANCE


class InProcessControlResult(Base):
    __tablename__ = "in_process_control_result"
    ipc_result_id = Column(String, primary_key=True)
    batch_id = Column(String, index=True)
    ebr_id = Column(String)
    step_type = Column(String)
    ipc_test_name = Column(String)
    timestamp = Column(DateTime)
    measured_value = Column(Float)
    usl = Column(Float)
    lsl = Column(Float)
    target = Column(Float)
    uom = Column(String)
    result = Column(String)                 # PASS, FAIL, BORDERLINE
    operator_id = Column(String)
    deviation_id = Column(String)


# ===================================================================== QC / LIMS
class QCTestOrder(Base):
    __tablename__ = "qc_test_order"
    test_order_id = Column(String, primary_key=True)
    test_order_number = Column(String)
    order_type = Column(String)             # INCOMING, IN_PROCESS, RELEASE, STABILITY, ...
    material_id = Column(String)
    batch_id = Column(String, index=True)
    lot_id = Column(String)
    priority = Column(String, default="NORMAL")
    assigned_analyst = Column(String)
    instrument_assigned = Column(String)
    status = Column(String, default="PENDING")
    requested_date = Column(DateTime, default=datetime.utcnow)
    required_by_date = Column(DateTime)
    results_posted = Column(DateTime)
    sla_hours = Column(Integer)
    sla_breached = Column(Boolean, default=False)


class AnalyticalResult(Base):
    __tablename__ = "analytical_result"
    result_id = Column(String, primary_key=True)
    test_order_id = Column(String, index=True)
    batch_id = Column(String, index=True)
    product_id = Column(String)
    test_name = Column(String)
    method_type = Column(String)            # HPLC, DISSOLUTION, KARL_FISCHER, ...
    instrument_id = Column(String)
    run_date = Column(DateTime, index=True)
    analyst_id = Column(String)
    reviewer_id = Column(String)
    reported_result = Column(Float)
    uom = Column(String)
    usl = Column(Float)
    lsl = Column(Float)
    result_status = Column(String)          # PASS, FAIL, OOS, OOT, VOID, PENDING_REVIEW
    is_invalidated = Column(Boolean, default=False)
    retest_number = Column(Integer, default=0)
    is_release_test = Column(Boolean, default=True)


class OOSInvestigation(Base):
    __tablename__ = "oos_investigation"
    oos_id = Column(String, primary_key=True)
    oos_number = Column(String)
    result_id = Column(String)
    batch_id = Column(String, index=True)
    product_id = Column(String)
    test_name = Column(String)
    oos_value = Column(Float)
    specification_limit = Column(Float)
    detection_date = Column(DateTime)
    phase = Column(Integer, default=1)
    phase1_conclusion = Column(String)      # LAB_ERROR_CONFIRMED, NO_ASSIGNABLE_CAUSE, IN_PROGRESS
    phase2_root_cause = Column(Text)
    phase2_conclusion = Column(String)      # INVALIDATED, GENUINE_OOS, INCONCLUSIVE
    batch_disposition = Column(String)      # REJECT, REWORK, RELEASE_WITH_DEVIATION, PENDING
    capa_required = Column(Boolean, default=False)
    capa_id = Column(String)
    status = Column(String, default="OPEN")
    created_at = Column(DateTime, default=datetime.utcnow)


class StabilityStudy(Base):
    __tablename__ = "stability_study"
    study_id = Column(String, primary_key=True)
    product_id = Column(String, index=True)
    batch_id = Column(String)
    study_type = Column(String)             # LONG_TERM, ACCELERATED, ...
    storage_condition = Column(String)
    start_date = Column(Date)
    status = Column(String, default="ONGOING")


class StabilityResult(Base):
    __tablename__ = "stability_result"
    stab_result_id = Column(String, primary_key=True)
    study_id = Column(String, index=True)
    product_id = Column(String)
    timepoint_months = Column(Integer)
    pull_date = Column(Date)
    test_name = Column(String)
    result_value = Column(Float)
    uom = Column(String)
    usl = Column(Float)
    lsl = Column(Float)
    result_status = Column(String)          # PASS, FAIL, OOS
    degradation_trend = Column(String)      # INCREASING, DECREASING, STABLE


# ================================================================ Supplier / SCM
class SupplierMaster(Base):
    __tablename__ = "supplier_master"
    supplier_id = Column(String, primary_key=True)
    supplier_code = Column(String)
    name = Column(String)
    supplier_type = Column(String)          # API_MANUFACTURER, EXCIPIENT_SUPPLIER, ...
    country = Column(String)
    regulatory_status = Column(String, default="APPROVED")
    gmp_cert_expiry = Column(Date)
    last_audit_date = Column(Date)
    last_audit_result = Column(String)
    next_audit_due = Column(Date)
    single_source = Column(Boolean, default=False)
    quality_rating = Column(Float)
    delivery_rating = Column(Float)
    overall_score = Column(Float)
    annual_spend_usd = Column(Float)


class CoARecord(Base):
    __tablename__ = "coa_record"
    coa_id = Column(String, primary_key=True)
    supplier_id = Column(String, index=True)
    material_id = Column(String)
    supplier_lot_number = Column(String)
    internal_lot_number = Column(String)
    manufacturing_date = Column(Date)
    release_date = Column(Date)
    tests = Column(JSON)
    all_tests_pass = Column(Boolean)
    status = Column(String, default="UNDER_REVIEW")  # UNDER_REVIEW, ACCEPTED, REJECTED


class ApprovedSupplierList(Base):
    __tablename__ = "approved_supplier_list"
    asl_id = Column(String, primary_key=True)
    supplier_id = Column(String, index=True)
    material_id = Column(String, index=True)
    qualification_date = Column(Date)
    qualification_type = Column(String)
    next_review_date = Column(Date)
    status = Column(String, default="APPROVED")


# ================================================================== Inventory
class InventoryBalance(Base):
    __tablename__ = "inventory_balance"
    ib_id = Column(String, primary_key=True)
    material_id = Column(String, index=True)
    lot_number = Column(String)
    warehouse_area_id = Column(String)
    qty_total = Column(Float)
    qty_quarantine = Column(Float, default=0)
    qty_approved = Column(Float, default=0)
    qty_rejected = Column(Float, default=0)
    qty_hold = Column(Float, default=0)
    qty_reserved = Column(Float, default=0)
    qty_available = Column(Float)
    uom = Column(String)
    material_status = Column(String, default="QUARANTINE")
    # QUARANTINE, APPROVED, REJECTED, HOLD, EXPIRED, DISPENSED
    expiry_date = Column(Date)
    retest_date = Column(Date)
    supplier_id = Column(String)
    last_status_change = Column(DateTime)


class DispensingRecord(Base):
    __tablename__ = "dispensing_record"
    dispensing_id = Column(String, primary_key=True)
    batch_id = Column(String, index=True)
    material_id = Column(String)
    lot_number = Column(String)
    theoretical_qty = Column(Float)
    tolerance_low = Column(Float)
    tolerance_high = Column(Float)
    actual_qty_dispensed = Column(Float)
    uom = Column(String)
    within_tolerance = Column(Boolean)
    balance_id = Column(String)
    primary_operator_id = Column(String)
    verifier_id = Column(String)
    dispensing_datetime = Column(DateTime)
    deviation_id = Column(String)


class MaterialReconciliation(Base):
    __tablename__ = "material_reconciliation"
    recon_id = Column(String, primary_key=True)
    batch_id = Column(String, index=True)
    material_id = Column(String)
    qty_dispensed = Column(Float)
    qty_waste = Column(Float)
    qty_unaccounted = Column(Float)
    theoretical_yield = Column(Float)
    actual_yield = Column(Float)
    yield_pct = Column(Float)
    yield_within_spec = Column(Boolean)
    reconciliation_status = Column(String, default="PENDING")
    reconciled_at = Column(DateTime)


# =============================================================== Equipment / CMMS
class EquipmentMaster(Base):
    __tablename__ = "equipment_master"
    equipment_id = Column(String, primary_key=True)
    equipment_tag = Column(String)
    equipment_name = Column(String)
    equipment_type = Column(String)
    manufacturer = Column(String)
    manufacturing_area_id = Column(String)
    criticality = Column(String)            # CRITICAL, MAJOR, MINOR
    dedicated_to_product = Column(String)
    current_qualification_status = Column(String, default="QUALIFIED")
    # QUALIFIED, REQUALIFICATION_DUE, OUT_OF_QUALIFICATION, NEW_UNQUALIFIED
    iq_date = Column(Date)
    oq_date = Column(Date)
    pq_date = Column(Date)
    pq_expiry_date = Column(Date)
    last_pm_date = Column(Date)
    next_pm_due = Column(Date)
    last_cleaned_batch = Column(String)
    computerised_system = Column(Boolean, default=False)
    status = Column(String, default="ACTIVE")


class CalibrationRecord(Base):
    __tablename__ = "calibration_record"
    cal_id = Column(String, primary_key=True)
    equipment_id = Column(String, index=True)
    calibration_type = Column(String)
    calibration_date = Column(Date)
    due_date = Column(Date)
    next_due = Column(Date)
    performed_by = Column(String)
    parameter_tested = Column(String)
    result = Column(String)                 # PASS, FAIL, ADJUSTED
    adjustment_made = Column(Boolean, default=False)
    status = Column(String, default="ACTIVE")  # ACTIVE, EXPIRED, OVERDUE


class CleaningRecord(Base):
    __tablename__ = "cleaning_record"
    cleaning_id = Column(String, primary_key=True)
    equipment_id = Column(String, index=True)
    previous_product = Column(String)
    next_product = Column(String)
    cleaning_sop_ref = Column(String)
    cleaning_date = Column(Date)
    operator_id = Column(String)
    supervisor_id = Column(String)
    visual_inspection = Column(String, default="PASS")
    cleaning_verification_type = Column(String)  # SWAB, RINSE, VISUAL_ONLY
    verification_result = Column(String)         # PASS, FAIL, PENDING
    line_clearance_issued = Column(Boolean, default=False)
    maco_limit = Column(Float)
    actual_carryover = Column(Float)
    deviation_id = Column(String)


class MaintenanceWorkOrder(Base):
    __tablename__ = "maintenance_work_order"
    mwo_id = Column(String, primary_key=True)
    wo_number = Column(String)
    equipment_id = Column(String, index=True)
    wo_type = Column(String)                # PM, CORRECTIVE, EMERGENCY, CALIBRATION, ...
    priority = Column(Integer)
    status = Column(String, default="OPEN")
    gmp_relevant = Column(Boolean, default=True)
    requalification_required = Column(Boolean, default=False)
    work_description = Column(Text)
    planned_start = Column(DateTime)
    planned_end = Column(DateTime)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    assigned_technician = Column(String)
    labor_hours_actual = Column(Float)
    parts_cost = Column(Float)
    labor_cost = Column(Float)
    production_impact_hrs = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================================================================== QMS
class DeviationRecord(Base):
    __tablename__ = "deviation_record"
    deviation_id = Column(String, primary_key=True)
    deviation_number = Column(String)
    source = Column(String)                 # MANUFACTURING, LABORATORY, WAREHOUSE, ...
    severity = Column(String)               # CRITICAL, MAJOR, MINOR
    detection_date = Column(DateTime, index=True)
    detected_by = Column(String)
    batch_id = Column(String, index=True)
    equipment_id = Column(String)
    description = Column(Text)
    step_of_occurrence = Column(String)
    batch_impact = Column(String)           # NONE, POTENTIAL, CONFIRMED
    root_cause_category = Column(String)
    root_cause_detail = Column(Text)
    capa_required = Column(Boolean, default=False)
    capa_id = Column(String)
    status = Column(String, default="OPEN")
    qp_notified = Column(Boolean, default=False)
    closed_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class CAPARecord(Base):
    __tablename__ = "capa_record"
    capa_id = Column(String, primary_key=True)
    capa_number = Column(String)
    capa_source = Column(String)            # DEVIATION, OOS, AUDIT, COMPLAINT, TREND
    source_record_id = Column(String)
    product_id = Column(String)
    root_cause = Column(Text)
    root_cause_method = Column(String)      # FIVE_WHY, FISHBONE, ...
    corrective_action = Column(Text)
    preventive_action = Column(Text)
    owner = Column(String)
    target_close_date = Column(Date)
    actual_close_date = Column(Date)
    status = Column(String, default="OPEN")
    # OPEN, IMPLEMENTING, PENDING_VERIFICATION, VERIFIED_EFFECTIVE, CLOSED, OVERDUE
    effectiveness_verified = Column(Boolean)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChangeControlRecord(Base):
    __tablename__ = "change_control_record"
    cc_id = Column(String, primary_key=True)
    cc_number = Column(String)
    change_type = Column(String)            # PROCESS, FORMULA, EQUIPMENT, ...
    classification = Column(String)         # MINOR, MODERATE, MAJOR
    description = Column(Text)
    regulatory_impact = Column(String)      # NONE, INFORM, PRIOR_APPROVAL
    validation_required = Column(Boolean, default=False)
    requalification_required = Column(Boolean, default=False)
    initiator = Column(String)
    target_implementation = Column(Date)
    status = Column(String, default="DRAFT")
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditRecord(Base):
    __tablename__ = "audit_record"
    audit_id = Column(String, primary_key=True)
    audit_number = Column(String)
    audit_type = Column(String)             # INTERNAL_GMP, SUPPLIER, ...
    area_audited = Column(String)
    supplier_audited = Column(String)
    audit_date_from = Column(Date)
    status = Column(String, default="PLANNED")
    overall_rating = Column(String)
    num_critical_findings = Column(Integer, default=0)
    num_major_findings = Column(Integer, default=0)
    num_minor_findings = Column(Integer, default=0)


class AuditFinding(Base):
    __tablename__ = "audit_finding"
    finding_id = Column(String, primary_key=True)
    audit_id = Column(String, index=True)
    regulatory_reference = Column(String)
    severity = Column(String)               # CRITICAL, MAJOR, MINOR, OBSERVATION
    description = Column(Text)
    capa_required = Column(Boolean, default=True)
    capa_id = Column(String)
    status = Column(String, default="OPEN")


# ================================================= Regulatory & pharmacovigilance
class ProductRegistration(Base):
    __tablename__ = "product_registration"
    registration_id = Column(String, primary_key=True)
    product_id = Column(String, index=True)
    market = Column(String)
    registration_type = Column(String)      # NDA, ANDA, MAA, ...
    application_number = Column(String)
    approval_date = Column(Date)
    approval_agency = Column(String)
    expiry_date = Column(Date)
    renewal_due = Column(Date)
    status = Column(String, default="APPROVED")


class AdverseEventReport(Base):
    __tablename__ = "adverse_event_report"
    ae_id = Column(String, primary_key=True)
    icsr_number = Column(String)
    source_type = Column(String)            # SPONTANEOUS, LITERATURE, ...
    report_date = Column(Date, index=True)
    receipt_date = Column(Date)
    product_id = Column(String, index=True)
    patient_age = Column(Integer)
    patient_sex = Column(String)
    event_meddra_pt = Column(String)        # MedDRA Preferred Term
    event_meddra_soc = Column(String)       # System Organ Class
    event_outcome = Column(String)          # FATAL, RECOVERED, ...
    is_serious = Column(Boolean, default=False)
    causality = Column(String)
    submission_deadline = Column(Date)
    submitted_to_fda = Column(Boolean, default=False)
    status = Column(String, default="OPEN")


class SignalAssessment(Base):
    __tablename__ = "signal_assessment"
    signal_id = Column(String, primary_key=True)
    signal_number = Column(String)
    product_id = Column(String, index=True)
    meddra_pt = Column(String)
    detection_method = Column(String)
    prr = Column(Float)
    ror = Column(Float)
    ic_value = Column(Float)
    number_of_cases = Column(Integer)
    detection_date = Column(Date)
    known_risk = Column(Boolean)
    validated_signal = Column(Boolean)
    action_required = Column(String)
    status = Column(String, default="OPEN")


# ========================================================= Environmental monitoring
class EMResult(Base):
    __tablename__ = "em_result"
    em_result_id = Column(String, primary_key=True)
    batch_id = Column(String)
    area_id = Column(String, index=True)
    sample_location = Column(String)
    monitoring_type = Column(String)        # VIABLE, NON_VIABLE, PARTICLE
    sample_date = Column(DateTime, index=True)
    cfu_count = Column(Float)
    action_limit_cfu = Column(Float)
    alert_limit_cfu = Column(Float)
    organism_identified = Column(String)
    result_status = Column(String)          # WITHIN_LIMIT, ALERT_LEVEL, ACTION_LEVEL
    particles_05um = Column(Integer)
    requires_investigation = Column(Boolean, default=False)


class TemperatureHumidityLog(Base):
    __tablename__ = "temperature_humidity_log"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    area_id = Column(String, index=True)
    storage_unit_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    temperature_c = Column(Float)
    humidity_pct = Column(Float)
    temperature_usl = Column(Float)
    temperature_lsl = Column(Float)
    within_spec = Column(Boolean)
    alert_triggered = Column(Boolean, default=False)


# ============================================================ Training & documents
class DocumentMaster(Base):
    __tablename__ = "document_master"
    doc_id = Column(String, primary_key=True)
    document_number = Column(String)
    document_type = Column(String)          # SOP, PROTOCOL, SPECIFICATION, ...
    title = Column(String)
    department = Column(String)
    current_version = Column(String)
    status = Column(String, default="EFFECTIVE")
    effective_date = Column(Date)
    next_review_date = Column(Date)
    owner = Column(String)
    training_required = Column(Boolean, default=False)


class TrainingRecord(Base):
    __tablename__ = "training_record"
    training_id = Column(String, primary_key=True)
    employee_id = Column(String, index=True)
    employee_name = Column(String)
    department = Column(String)
    role = Column(String)
    document_id = Column(String)
    training_type = Column(String)
    training_date = Column(Date)
    training_status = Column(String, default="COMPLETED")
    assessment_passed = Column(Boolean)
    next_due_date = Column(Date)
    training_compliance = Column(Boolean)


# ============================================================ Framework runtime
class AgentRun(Base):
    """One execution of an agent (manual or orchestrated), with full trace."""
    __tablename__ = "agent_run"
    run_id = Column(String, primary_key=True)
    agent_id = Column(String, index=True)
    trigger_type = Column(String)           # MANUAL, ORCHESTRATED
    prompt = Column(Text)
    status = Column(String, default="RUNNING")
    framework = Column(String)
    reasoning_mode = Column(String)         # LLM, DETERMINISTIC
    trace = Column(JSON)
    result = Column(Text)
    tool_calls = Column(Integer, default=0)
    orchestration_id = Column(String, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)


class OrchestrationEvent(Base):
    """One anomaly the orchestrator detected and how it dispatched agents."""
    __tablename__ = "orchestration_event"
    event_id = Column(String, primary_key=True)
    tick = Column(Integer, index=True)
    sim_time = Column(DateTime)
    signal_type = Column(String)            # OOS_DETECTED, CPP_BREACH, EM_ACTION, ...
    severity = Column(String)
    source_table = Column(String)
    source_ref = Column(String)
    description = Column(Text)
    dispatched_agents = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class SimClock(Base):
    """Single-row table tracking the live simulation cursor."""
    __tablename__ = "sim_clock"
    id = Column(Integer, primary_key=True)
    current_time = Column(DateTime)
    tick = Column(Integer, default=0)
    running = Column(Boolean, default=False)
