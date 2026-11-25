from app.catalog import SPEC
from app.correction.model import original_values
from app.intake.service import record_key


def build_correction_view(source_records, applied_records, original_dispositions,
                          dispositions, decisions, prepared, corrections):
    """Expose everything the reconcile stage needs about corrections.

    ``rows`` keeps every original source line with its original values, its
    current (post-correction) values, its disposition and whether a correction
    was applied, so the workbench can show original rows, rows that remain
    isolated, and the rows that were actually counted after correction.
    """
    decision_by_line = {}
    for item in decisions:
        if item["status"] == "APPLIED" or item["line"] not in decision_by_line:
            decision_by_line[item["line"]] = item
    applied_by_line = {record["line"]: record for record in applied_records}
    prepared_lines = {item.get("_line") for item in prepared}
    corrected_lines = {line for line, item in decision_by_line.items() if item["status"] == "APPLIED"}
    entries = []
    tally = {"counted": 0, "isolated": 0, "duplicate": 0, "ignored": 0}
    for record in source_records:
        line = record["line"]
        original = original_dispositions.get(line, {"kind": "ignored", "code": ""})
        current = dispositions.get(line, original)
        if current["kind"] == "accepted" and line in prepared_lines:
            state = "counted"
        elif current["kind"] == "isolated" or (current["kind"] == "accepted" and line not in prepared_lines):
            state = "isolated"
        else:
            state = current["kind"]
        tally[state] = tally.get(state, 0) + 1
        decision = decision_by_line.get(line)
        entries.append({
            "line": line,
            "key": record_key(record),
            "state": state,
            "code": current.get("code", ""),
            "original_code": original.get("code", ""),
            "corrected": line in corrected_lines,
            "correction": None if decision is None else {
                "status": decision["status"], "reason": decision["reason"],
                "correction_id": decision["correction_id"], "seq": decision["seq"],
            },
            "original": original_values(record),
            "current": _current(applied_by_line.get(line, record)),
        })
    corrections_log = []
    decided = {(item["correction_id"], item["line"]): item for item in decisions}
    for correction in sorted(corrections, key=lambda item: item.get("seq", 0)):
        fixes = []
        for fix in correction.get("fixes") or []:
            line = int(fix["line"])
            decision = decided.get((correction.get("id"), line)) or {}
            fixes.append({
                "line": line,
                "values": fix["values"],
                "status": decision.get("status", "REJECTED"),
                "reason": decision.get("reason", "REJECTED"),
            })
        corrections_log.append({
            "id": correction.get("id"),
            "seq": correction.get("seq"),
            "base_revision": correction.get("base_revision"),
            "comment": correction.get("comment", ""),
            "submitted_at": correction.get("submitted_at"),
            "fixes": fixes,
        })
    checks = [
        {"id": "source_preserved", "label": "原始行保留", "ok": len(entries) == len(source_records)},
        {"id": "reconciled", "label": "补正后计入", "ok": sum(tally.values()) == len(source_records)},
    ]
    return {"rows": entries, "counted": tally["counted"], "isolated": tally["isolated"],
            "duplicates": tally["duplicate"], "ignored": tally["ignored"],
            "corrections": corrections_log, "checks": checks}


def _current(record):
    row = record.get("row") or {}
    return {column: row.get(column, "") for column in SPEC["columns"]}
