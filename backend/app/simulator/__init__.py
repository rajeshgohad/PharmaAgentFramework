"""Simulator package: build the database and drive live ticks."""
from __future__ import annotations

from .. import models
from ..database import Base, SessionLocal, engine
from .history import generate_history
from .live import generate_tick
from .master_data import seed_master

__all__ = ["build_database", "generate_tick"]


def build_database(force: bool = False) -> dict:
    """Create schema, seed master data, generate history. Idempotent unless force."""
    if force:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        already = db.query(models.ProductMaster).first()
        if already and not force:
            clock = db.query(models.SimClock).first()
            return {"status": "exists", "sim_time": clock.current_time if clock else None}

        seeds = seed_master(db)
        end_time = generate_history(db, seeds)

        db.query(models.SimClock).delete()
        db.add(models.SimClock(id=1, current_time=end_time, tick=0, running=False))
        db.commit()

        counts = {
            "products": db.query(models.ProductMaster).count(),
            "materials": db.query(models.MaterialMaster).count(),
            "suppliers": db.query(models.SupplierMaster).count(),
            "equipment": db.query(models.EquipmentMaster).count(),
            "batches": db.query(models.BatchMaster).count(),
            "ebr_steps": db.query(models.ElectronicBatchRecord).count(),
            "step_logs": db.query(models.ManufacturingStepLog).count(),
            "analytical_results": db.query(models.AnalyticalResult).count(),
            "oos_investigations": db.query(models.OOSInvestigation).count(),
            "deviations": db.query(models.DeviationRecord).count(),
            "capas": db.query(models.CAPARecord).count(),
            "em_results": db.query(models.EMResult).count(),
            "temp_logs": db.query(models.TemperatureHumidityLog).count(),
            "adverse_events": db.query(models.AdverseEventReport).count(),
        }
        return {"status": "built", "sim_time": end_time, "counts": counts}
    finally:
        db.close()
