import hashlib
from decimal import Decimal
from pathlib import Path

from app.catalog import SPEC
from app.correction.model import correction_summaries
from app.correction.service import apply as apply_corrections
from app.domain.calculate import calculate_rows
from app.domain.decision import decide_rows
from app.domain.prepare import prepare_rows
from app.intake.service import load_source, settle
from app.reconcile.ledger import build_ledger
from app.reconcile.view import build_correction_view


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def _stage(name):
    return SPEC["stages"].index(name) + 1


def pipeline(profile="dirty", path=None, upto="证据交付", corrections=None):
    corrections = corrections or []
    source = load_source(profile, path)
    _, _, _, original_dispositions = settle(source["records"])
    _, _, decisions, applied = apply_corrections(source, corrections)
    accepted, intake_issues, counts, dispositions = settle(applied)
    prepared, prepare_issues = [], []
    results = []
    ledger = None
    if _stage(upto) >= 2:
        prepared, prepare_issues = prepare_rows(accepted)
    if _stage(upto) >= 3:
        results = calculate_rows(prepared)
    if _stage(upto) >= 4:
        results = decide_rows(results)
    if _stage(upto) >= 5:
        ledger = build_ledger({"counts": counts}, accepted, prepare_issues, results)
        ledger["correction"] = build_correction_view(
            source["records"], applied, original_dispositions, dispositions,
            decisions, prepared, corrections)
        ledger["all_checks"] = ledger["all_checks"] and all(
            item["ok"] for item in ledger["correction"]["checks"])
    counts["prepared"] = len(prepared)
    counts["computed"] = len(results)
    issues = intake_issues + prepare_issues
    summary = {"PASS": 0, "REVIEW": 0, "REJECT": 0}
    for item in results:
        summary[item.get("verdict", "REVIEW")] = summary.get(item.get("verdict", "REVIEW"), 0) + 1
    chart_field = {"0840": "rolling", "0849": "mean", "0850": "settlement_cents"}.get(SPEC["code"], "metric")
    chart = [{"label": item.get("label", item.get(SPEC["key"], "")),
              "value": float(item.get(chart_field) or 0),
              "limit": float(item.get("limit") or 0)}
             for item in results[:12]]
    rows = []
    raw_stage = _stage(upto) <= 2
    if raw_stage:
        stage_rows = accepted if _stage(upto) == 1 else prepared
        rows = [{key: item.get(key) for key in SPEC["columns"]} for item in stage_rows[:18]]
    else:
        for item in results[:18]:
            rows.append({key: value for key, value in item.items()
                         if key in {"label", "verdict", "reason", "metric", "limit", "status", "state", "breakdown"}
                         or key in SPEC["columns"] or key in SPEC["result_columns"]})
    source_info = {"profile": profile, "filename": Path(source["path"]).name, "sha256": source["sha256"]}
    payload = {
        "project": SPEC["code"] + " " + SPEC["name"],
        "rule": SPEC["rule_short"],
        "profile": profile,
        "source": source_info,
        "counts": counts,
        "issues": issues[:60],
        "rows": rows,
        "row_kind": "source" if raw_stage else "result",
        "chart": chart,
        "summary": summary,
        "ledger": ledger,
        "corrections": correction_summaries(corrections),
        "stages": [{"id": "intake", "name": SPEC["stages"][0]},
                   {"id": "prepare", "name": SPEC["stages"][1]},
                   {"id": "calculate", "name": SPEC["stages"][2]},
                   {"id": "decision", "name": SPEC["stages"][3]},
                   {"id": "reconcile", "name": SPEC["stages"][4]}],
        "run_key": hashlib.sha256(
            (SPEC["code"] + profile + source["sha256"] + SPEC["rule"]).encode("utf-8")).hexdigest()[:24],
    }
    return jsonable(payload)
