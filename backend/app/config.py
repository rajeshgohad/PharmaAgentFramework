"""Single source of truth for constants, thresholds, and simulation parameters.

Pharmaceutical manufacturing (solid oral dosage + sterile), GxP-constrained.
Change behaviour here, not inline in business logic.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
# PHARMA_DB_PATH lets deployments point SQLite at a persistent volume.
DB_PATH = Path(os.getenv("PHARMA_DB_PATH", str(BASE_DIR / "pharma.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Directory of the built frontend (set in deploy) to serve single-origin.
STATIC_DIR = os.getenv("PHARMA_STATIC_DIR", "").strip()

# --- LLM ---------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MODEL_COMPLEX = os.getenv("CLAUDE_MODEL_COMPLEX", "claude-opus-4-6")
LLM_ENABLED = bool(ANTHROPIC_API_KEY)
LLM_MAX_TOKENS = 2048
AGENT_MAX_STEPS = 8

# --- Simulation window -------------------------------------------------------
SIM_DAYS = 95  # >= 3 months of history
SIM_SEED = 42

# High-frequency tables downsampled to keep SQLite manageable while preserving
# the patterns agents reason over (Data.md raw volumes are ~12.5M step-log rows/yr).
TEMP_SAMPLE_MINUTES = 30    # controlled-environment logging cadence in history
CPP_SAMPLES_PER_STEP = 12   # PAT/CPP readings captured per manufacturing step

# --- Plant shape (per Data.md §13) ------------------------------------------
N_PRODUCTS = 20
N_MATERIALS = 150
N_SUPPLIERS = 40
N_EQUIPMENT = 85
BATCHES_PER_WORKDAY = 8

# --- GxP anomaly thresholds (drive the orchestrator) ------------------------
THRESHOLDS = {
    "yield_oos_low": 96.0,          # % — WM-P05 -> ME-P04
    "yield_oos_high": 102.0,
    "em_alert_multiple": 0.5,       # fraction of action limit that is "alert" level
    "temp_excursion_minutes": 15,   # WM-P04 significant excursion
    "cpp_prealarm_pct": 90.0,       # % of limit -> pre-alarm (ME-P03)
    "supplier_score_watch": 79.0,
    "supplier_score_conditional": 64.0,
    "supplier_score_suspend": 50.0,
    "qualification_expiry_days": 30,
    "capa_overdue_days": 14,
}

# --- Orchestrator ------------------------------------------------------------
ORCH_TICK_SECONDS = 6
ORCH_MINUTES_PER_TICK = 120     # each tick advances the sim clock by this much
ORCH_AUTOSTART = os.getenv("ORCH_AUTOSTART", "false").strip().lower() in ("1", "true", "yes", "on")
ORCH_AUTOSTART_MODE = os.getenv("ORCH_AUTOSTART_MODE", "DETERMINISTIC").upper()
