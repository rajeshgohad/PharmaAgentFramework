# PharmaAgentFramework — Pharmaceutical Manufacturing Agentic Framework

A runnable **GxP agentic framework** for a pharmaceutical (solid oral dosage +
sterile) plant. It implements the three specs in `Functional Agents/Pharma/`
(`Pharma_Agent.md`, `Pharma_Data.md`, `Pharma_Tools.md`) as a live web application:
an **Agent Registry**, a browsable **Agent Catalog**, an executable **Toolkit**,
and an **autonomous Orchestrator** that watches live GMP data and dispatches agent
cascades on the anomalies it detects.

Agents run as genuine tool-calling loops in their assigned reasoning framework
(ReAct, Plan-and-Execute, OODA, Tree-of-Thought, Generate-Critique-Revise,
Reflect-and-Correct). With an Anthropic API key they reason with Claude; without
one they fall back to a deterministic executor that still exercises every tool.

**GxP guardrail:** agents may *recommend* but never autonomously release a batch,
approve a batch record, or close a deviation/OOS — those require a human
e-signature. Every write action creates an audit-trail entry.

## Stack

- **Backend** — Python · FastAPI · SQLAlchemy · SQLite · `anthropic` SDK · WebSocket
- **Frontend** — React 18 · Vite · TypeScript · Tailwind
- **Data** — ~40 tables from `Pharma_Data.md`; a simulator seeds products,
  materials, suppliers, equipment, and generates **95 days** of batch/QC/QMS
  history with embedded patterns (an OOS cluster, temperature excursions, EM
  action-levels, weak-supplier CoA rejections, stability degradation).

## Run it

```bash
# 1. Backend (port 8010)  — builds + seeds the DB on first startup
cd PharmaAgentFramework/backend
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8010

# 2. Frontend (port 5181)
cd PharmaAgentFramework/frontend
npm install
npm run dev
```

Open http://localhost:5181.

### Enable real Claude reasoning (optional)

Click the header badge and paste an `sk-ant-…` key (stored in server memory for
the session only), or set `ANTHROPIC_API_KEY` in `backend/.env`. Claude is used
only when you explicitly select the **Claude** mode per run.

## The two execution modes

1. **Manual** — In the **Agent Catalog**, pick any of the 31 agents, give it a
   prompt, and watch it reason step-by-step, call real tools against the DB, take
   GxP actions (raise deviations/CAPAs, open OOS investigations, place batch
   holds, notify the QP), and conclude.
2. **Autonomous** — In the **Orchestrator**, press **Start** (or **Step**). Each
   tick the simulator emits new transactions; the watcher detects anomalies and
   dispatches the mapped cascade per `Agent.md`'s dependency graph, e.g.
   `OOS_DETECTED → QA-P01 → QA-P02 → QA-P03` or
   `CPP_BREACH → ME-P03 → ME-P04 → QA-P03`. Every run's full trace is browsable.

## Layout

```
backend/app/
  models.py          # ~40 SQLAlchemy tables (Pharma_Data.md subset)
  simulator/         # master_data (seed) · history (95d) · live (per-tick)
  tools/             # 35 GxP tools with the Tools.md ToolResponse contract
  agents/registry.py # 31 agents: goal, framework, tools, triggers, dependencies
  reasoning/engine.py# 6 framework executors · Claude loop · deterministic fallback
  orchestrator.py    # watcher: detect anomalies → dispatch cascades
  dashboard.py       # plant quality KPI aggregations
  main.py            # FastAPI REST + WebSocket + single-origin static serving
frontend/src/
  pages/             # Catalog · AgentPage (runner) · Orchestrator · Dashboards · Toolkit · Tables
  components/        # Layout · TraceView · ApiKeyModal
```

## Vertical slice

**Manufacturing Execution (ME)** and **Quality (QA)** are the deep slice — the
richest tool wiring and the primary orchestrator cascades (the GMP batch loop:
batch → EBR → deviation → OOS → CAPA → disposition). The other four domains
(Supply Chain, Warehouse, Equipment, Regulatory/PV) are fully catalogued and
runnable with real tools.

## Data fidelity note

`Pharma_Data.md`'s raw volumes are huge (manufacturing step-log at ~12.5M rows/yr;
temperature logs at 8,640/day). These are downsampled — CPP readings per step,
temperature logging at 30-min cadence — to keep SQLite responsive while
preserving the signals agents reason over. Tune in `config.py`
(`TEMP_SAMPLE_MINUTES`, `CPP_SAMPLES_PER_STEP`, `SIM_DAYS`, thresholds).
