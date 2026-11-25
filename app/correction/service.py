import hashlib
import json

from app.catalog import SPEC
from app.correction.model import apply_fixes, segment_of
from app.errors import DomainIssue
from app.intake.normalize import canonical

COLUMNS = SPEC["columns"]


def normalize_fixes(fixes):
    """Validate a submitted fix list into the canonical stored form."""
    if not isinstance(fixes, list) or not fixes:
        raise DomainIssue("BAD_REQUEST", detail="补正至少需要一行")
    normalized, seen = [], set()
    for fix in fixes:
        if not isinstance(fix, dict):
            raise DomainIssue("BAD_REQUEST", detail="补正行格式无效")
        try:
            line = int(fix.get("line"))
        except (TypeError, ValueError):
            raise DomainIssue("BAD_REQUEST", detail="补正行号无效")
        values = fix.get("values")
        if not isinstance(values, dict) or not values:
            raise DomainIssue("BAD_REQUEST", detail="补正行缺少字段值")
        cleaned = {field: canonical(value) for field, value in values.items() if field in COLUMNS}
        if not cleaned:
            raise DomainIssue("BAD_REQUEST", detail="补正字段不在字段表内")
        if line in seen:
            raise DomainIssue("BAD_REQUEST", detail="同一行重复补正")
        seen.add(line)
        normalized.append({"line": line, "values": cleaned})
    return sorted(normalized, key=lambda fix: fix["line"])


def request_key(run_id, fixes):
    body = json.dumps({"run": run_id, "fixes": fixes}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def resolve(source, corrections):
    """Resolve submitted corrections into a flat set of accepted fixes.

    Corrections are ordered by the server-assigned ``seq``.  A temperature
    segment belongs to the first correction that claims it: a later correction
    touching the same segment is rejected instead of overwriting the earlier
    result, while a correction touching a different segment still applies.  A
    single correction may fix several rows of its segment (needed to clear a
    conflicting pair).  Retrying a correction must not add a second claim, so
    identical requests share one stored correction.

    Returns ``(accepted, claims, decisions)`` where ``accepted`` maps a line to
    ``{"values", "correction_id"}`` and ``decisions`` lists one entry per
    submitted fix, keyed by ``(correction_id, line)`` for later reporting.
    """
    by_line = {record["line"]: record for record in source["records"]}
    claims, accepted, decisions = {}, {}, []
    for correction in sorted(corrections, key=lambda item: item.get("seq", 0)):
        correction_id = correction.get("id")
        for fix in correction.get("fixes") or []:
            line = int(fix["line"])
            record = by_line.get(line)
            entry = {"correction_id": correction_id, "seq": correction.get("seq"), "line": line}
            if record is None:
                decisions.append(dict(entry, segment="", status="REJECTED", reason="LINE_UNKNOWN"))
                continue
            segment = segment_of(record)
            entry["segment"] = segment
            owner = claims.get(segment)
            if owner is not None and owner != correction_id:
                decisions.append(dict(entry, status="REJECTED", reason="SEGMENT_CLAIMED", winner=owner))
                continue
            claims[segment] = correction_id
            if line not in accepted:
                accepted[line] = {"values": fix["values"], "correction_id": correction_id}
            decisions.append(dict(entry, status="APPLIED", reason=""))
    return accepted, claims, decisions


def apply(source, corrections):
    accepted, claims, decisions = resolve(source, corrections)
    fixes = {line: item["values"] for line, item in accepted.items()}
    return accepted, claims, decisions, apply_fixes(source["records"], fixes)


def stored_corrections(rows):
    """Adapt store rows into the correction shape used by the pipeline."""
    parsed = []
    for row in rows:
        item = dict(row)
        item["fixes"] = json.loads(item["fixes"])
        parsed.append(item)
    return parsed
