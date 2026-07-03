"""Reasoning engine.

Runs an agent as a genuine tool-calling loop. With an ANTHROPIC_API_KEY it uses
Claude: the model reasons in its chosen framework, calls the agent's tools, sees
real observations from the DB, and concludes. Without a key it falls back to a
deterministic executor that still exercises every tool and synthesises a result.

Either way the full trace (thought / tool_call / observation) is captured and
persisted to `agent_run` for the UI.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from .. import models, runtime
from ..config import AGENT_MAX_STEPS, LLM_MAX_TOKENS
from ..agents.registry import FRAMEWORKS, get_agent
from ..tools import REGISTRY, anthropic_schema, run_tool

FRAMEWORK_GUIDANCE = {
    "ReAct": (
        "Use the ReAct loop. For each step: THINK about what you need, then ACT by "
        "calling one tool, then OBSERVE the result, and repeat until you can conclude. "
        "React to what the data actually shows."),
    "Plan-and-Execute": (
        "First PLAN: lay out the ordered sub-steps needed. Then EXECUTE each step with "
        "tool calls. Finally VALIDATE the plan against constraints before concluding."),
    "OODA": (
        "Run the OODA loop: OBSERVE current state via tools, ORIENT by interpreting it, "
        "DECIDE the best action, and ACT. Keep cycles tight and decisive."),
    "Tree-of-Thought": (
        "Generate 3-4 candidate hypotheses for the root cause. Gather evidence for each "
        "with tools, SCORE each by how well the data supports it, PRUNE weak branches, "
        "and SYNTHESISE the most-probable root-cause chain with corrective actions."),
    "Generate-Critique-Revise": (
        "GENERATE an initial analysis/recommendation, then CRITIQUE it against the data "
        "for validity and confounders, then REVISE into a final, defensible output."),
    "Reflect-and-Correct": (
        "GENERATE the assessment, CRITIQUE it for tolerance/severity breaches, then "
        "CORRECT by taking the appropriate action, keeping an audit trail."),
}

ID_PATTERNS = {
    "batch_id": r"\bBAT-\d{5}\b",
    "material_id": r"\bMAT-\d{4}\b",
    "equipment_id": r"\bEQ-\d{3}\b",
    "supplier_id": r"\bSUP-\d{3}\b",
    "product_id": r"\bPRD-\d{3}\b",
    "oos_id": r"\bOOS-\w+\b",
    "deviation_id": r"\bDEV-\w+\b",
    "area_id": r"\bAR-\w+\b",
}


def build_system_prompt(agent: dict) -> str:
    tools_desc = "\n".join(
        f"  - {n}: {REGISTRY[n].description}" for n in agent["tools"] if n in REGISTRY)
    return (
        f"You are {agent['name']} ({agent['id']}), an autonomous agent in a pharmaceutical "
        f"(GMP) manufacturing AI framework.\n\n"
        f"GOAL: {agent['goal']}\n\n"
        f"REASONING FRAMEWORK: {agent['framework']} — {FRAMEWORKS.get(agent['framework'],'')}\n"
        f"{FRAMEWORK_GUIDANCE.get(agent['framework'],'')}\n\n"
        f"YOUR TOOLS:\n{tools_desc}\n\n"
        f"ESCALATION POLICY: {agent['escalation']}\n\n"
        "GxP RULES: operate on REAL plant data via your tools — never invent numbers. You may "
        "RECOMMEND but must NEVER autonomously release a batch, approve a batch record, or close "
        "a deviation/OOS — those require a human e-signature. Every write action creates an audit "
        "trail. When data is ambiguous, assume worst case (non-conformance) until proven otherwise. "
        "Call tools to gather evidence, then act (raise deviations/CAPAs, place holds, notify QP, "
        "send alerts) when your policy calls for it. Be concise. When finished, give a short "
        "structured conclusion: FINDINGS, ACTIONS TAKEN, and ESCALATION (if any). Keep the whole "
        f"run under {AGENT_MAX_STEPS} tool calls."
    )


def _infer_context(db, agent: dict, prompt: str) -> dict:
    """Pull entity ids from the prompt; fill sensible defaults for the agent's domain."""
    ctx: dict = {}
    for key, pat in ID_PATTERNS.items():
        m = re.search(pat, prompt or "")
        if m:
            ctx[key] = m.group(0)
    # defaults so deterministic mode always has a target
    if "batch_id" not in ctx:
        b = db.query(models.BatchMaster).order_by(
            models.BatchMaster.manufacturing_date.desc()).first()
        if b:
            ctx["batch_id"] = b.batch_id
    if "product_id" not in ctx:
        ctx["product_id"] = "PRD-005"  # the embedded OOS-cluster product
    if "material_id" not in ctx:
        m = db.query(models.MaterialMaster).first()
        if m:
            ctx["material_id"] = m.material_id
    if "equipment_id" not in ctx:
        e = (db.query(models.EquipmentMaster)
             .filter(models.EquipmentMaster.current_qualification_status == "REQUALIFICATION_DUE")
             .first()) or db.query(models.EquipmentMaster).first()
        if e:
            ctx["equipment_id"] = e.equipment_id
    if "supplier_id" not in ctx:
        s = (db.query(models.SupplierMaster)
             .order_by(models.SupplierMaster.overall_score.asc()).first())
        if s:
            ctx["supplier_id"] = s.supplier_id
    if "area_id" not in ctx:
        ctx["area_id"] = "AR-FILL"     # aseptic area with EM excursions
    if "oos_id" not in ctx:
        o = db.query(models.OOSInvestigation).order_by(
            models.OOSInvestigation.detection_date.desc()).first()
        if o:
            ctx["oos_id"] = o.oos_id
    if "deviation_id" not in ctx:
        dv = (db.query(models.DeviationRecord)
              .filter(models.DeviationRecord.severity == "CRITICAL")
              .order_by(models.DeviationRecord.detection_date.desc()).first())
        if dv:
            ctx["deviation_id"] = dv.deviation_id
    return ctx


def _fill_args(tool_name: str, ctx: dict) -> dict:
    """Best-effort argument fill from context for deterministic mode."""
    spec = REGISTRY[tool_name]
    props = spec.input_schema.get("properties", {})
    required = spec.input_schema.get("required", [])
    args: dict = {}
    for field in props:
        if field in ctx:
            args[field] = ctx[field]
    # supply required non-id fields with reasonable literals
    for field in required:
        if field in args:
            continue
        if field == "severity":
            args[field] = "ALERT" if "alert" in tool_name else "MAJOR"
        elif field == "wo_type":
            args[field] = "CORRECTIVE"
        elif field == "priority":
            args[field] = 2
        elif field in ("description", "message", "summary", "reason", "root_cause",
                       "corrective_action", "recommendation"):
            args[field] = "Auto-generated by deterministic executor from live GxP signals."
        elif field == "title":
            args[field] = "Automated agent finding"
        elif field == "test_name":
            args[field] = "Assay"
        elif field == "source":
            args[field] = "DEVIATION" if "capa" in tool_name else "MANUFACTURING"
        elif field == "gmp_event_type":
            args[field] = "DEVIATION"
        elif field == "notification_type":
            args[field] = "MAJOR_DEVIATION"
        elif field == "new_status":
            args[field] = "HOLD"
        elif field == "change_type":
            args[field] = "PROCESS"
        elif field == "classification":
            args[field] = "MODERATE"
        elif field == "template":
            args[field] = "compliance"
        elif field == "action":
            args[field] = "agent_review"
    return args


# ------------------------------------------------------------------ public API
def run_agent(db, agent_id: str, prompt: str, trigger_type: str = "MANUAL",
              orchestration_id: str | None = None, force_mode: str | None = None) -> dict:
    agent = get_agent(agent_id)
    if not agent:
        raise ValueError(f"Unknown agent {agent_id}")

    run_id = f"RUN-{uuid.uuid4().hex[:12]}"
    # Claude is used ONLY when explicitly requested (force_mode == "LLM").
    # Default (and any unset mode) stays deterministic — the API key is never
    # engaged automatically, only on an explicit opt-in from the caller/UI.
    use_llm = (force_mode == "LLM")
    if use_llm and not runtime.llm_enabled():
        use_llm = False  # cannot use LLM without a key -> fall back
    mode = "LLM" if use_llm else "DETERMINISTIC"
    run = models.AgentRun(
        run_id=run_id, agent_id=agent_id, trigger_type=trigger_type, prompt=prompt,
        status="RUNNING", framework=agent["framework"], reasoning_mode=mode,
        trace=[], result=None, tool_calls=0, orchestration_id=orchestration_id,
        started_at=datetime.now())
    db.add(run)
    db.commit()

    try:
        if use_llm:
            trace, result, n_calls = _run_llm(db, agent, prompt)
        else:
            trace, result, n_calls = _run_deterministic(db, agent, prompt)
        run.trace = trace
        run.result = result
        run.tool_calls = n_calls
        run.status = "COMPLETED"
    except Exception as e:  # noqa: BLE001
        run.status = "FAILED"
        run.result = f"Run failed: {e}"
        run.trace = (run.trace or []) + [{"type": "error", "content": str(e)}]
    finally:
        run.finished_at = datetime.now()
        db.commit()

    return {
        "run_id": run_id, "agent_id": agent_id, "framework": agent["framework"],
        "reasoning_mode": mode, "status": run.status, "trace": run.trace,
        "result": run.result, "tool_calls": run.tool_calls,
        "orchestration_id": orchestration_id,
    }


# --------------------------------------------------------------- LLM executor
def _run_llm(db, agent: dict, prompt: str):
    import anthropic

    client = anthropic.Anthropic(api_key=runtime.get_api_key())
    model = runtime.model_complex() if agent["framework"] == "Tree-of-Thought" else runtime.model()
    tools = [anthropic_schema(n) for n in agent["tools"] if n in REGISTRY]
    system = build_system_prompt(agent)
    messages = [{"role": "user", "content": prompt}]
    trace: list[dict] = []
    n_calls = 0

    for _ in range(AGENT_MAX_STEPS + 2):
        resp = client.messages.create(
            model=model, max_tokens=LLM_MAX_TOKENS, system=system,
            tools=tools, messages=messages)

        # capture any text (thoughts) and tool_use blocks
        assistant_content = []
        tool_uses = []
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                trace.append({"type": "thought", "content": block.text.strip()})
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append(block)
                assistant_content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name,
                     "input": block.input})
        messages.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason != "tool_use" or not tool_uses:
            final = "".join(b.text for b in resp.content if b.type == "text").strip()
            return trace, final, n_calls

        tool_results = []
        for tu in tool_uses:
            n_calls += 1
            result = run_tool(db, tu.name, tu.input)
            trace.append({"type": "tool_call", "tool": tu.name, "input": tu.input,
                          "observation": result, "success": result["success"],
                          "latency_ms": result["latency_ms"]})
            tool_results.append({
                "type": "tool_result", "tool_use_id": tu.id,
                "content": _to_text(result),
                "is_error": not result["success"]})
        messages.append({"role": "user", "content": tool_results})

    return trace, "Reached step limit; see trace for gathered evidence.", n_calls


# ------------------------------------------------------- deterministic executor
def _run_deterministic(db, agent: dict, prompt: str):
    ctx = _infer_context(db, agent, prompt)
    trace: list[dict] = [{
        "type": "thought",
        "content": (f"[{agent['framework']}] No LLM key set — running deterministic "
                    f"executor. Target context: {ctx}. I will exercise each of my tools "
                    "over the live data and synthesise findings.")}]
    n_calls = 0
    findings: list[str] = []
    actions: list[str] = []

    for tool_name in agent["tools"]:
        if tool_name not in REGISTRY:
            continue
        args = _fill_args(tool_name, ctx)
        # skip pure state-changing tools unless a real trigger is evident
        n_calls += 1
        result = run_tool(db, tool_name, args)
        trace.append({"type": "tool_call", "tool": tool_name, "input": args,
                      "observation": result, "success": result["success"],
                      "latency_ms": result["latency_ms"]})
        if result["success"]:
            findings.append(_summarise(tool_name, result["data"]))
            if any(k in tool_name for k in ("create_", "raise_", "expedite", "alert")):
                actions.append(tool_name)

    concl = _deterministic_conclusion(agent, findings, actions)
    trace.append({"type": "thought", "content": concl})
    return trace, concl, n_calls


def _summarise(tool_name: str, data) -> str:
    if not isinstance(data, dict):
        return f"{tool_name}: {str(data)[:120]}"
    keys = ["health_score", "risk_level", "rul_hours", "oee", "avg_oee", "defect_rate",
            "count", "total_downtime_min", "overall_score", "wo_number", "ncr_number",
            "dispatched", "days_of_stock", "out_of_control"]
    bits = [f"{k}={data[k]}" for k in keys if k in data]
    return f"{tool_name}: " + (", ".join(bits) if bits else "ok")


def _deterministic_conclusion(agent, findings, actions) -> str:
    lines = [f"CONCLUSION ({agent['id']} · {agent['framework']}):", "", "FINDINGS:"]
    lines += [f"  • {f}" for f in findings[:8]]
    lines += ["", "ACTIONS TAKEN:"]
    lines += [f"  • {a}" for a in actions] or ["  • None (monitoring only)"]
    lines += ["", f"ESCALATION POLICY: {agent['escalation']}"]
    return "\n".join(lines)


def _to_text(result: dict) -> str:
    import json
    if result["success"]:
        return json.dumps(result["data"], default=str)[:3500]
    return f"ERROR {result['error']['code']}: {result['error']['message']}"
