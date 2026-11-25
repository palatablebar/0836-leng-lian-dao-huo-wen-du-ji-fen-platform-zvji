from collections import OrderedDict
from pathlib import Path

from app.catalog import SPEC
from app.config import SAMPLES
from app.errors import DomainIssue
from app.intake.limits import MAX_FILE, MAX_ROWS
from app.intake.reader import read_records

KEY_INDEX = SPEC["columns"].index(SPEC["key"])


def _path(profile: str, path: str | None):
    if path:
        return Path(path)
    if profile not in {"clean", "dirty"}:
        raise DomainIssue("SAMPLE_UNKNOWN")
    return SAMPLES / f"{profile}.csv"


def hydrate(record):
    """Build the row mapping for a raw record when it is structurally usable."""
    if record["blank"] or record["repeated"]:
        return None
    cells = record["cells"]
    if len(cells) != len(SPEC["columns"]):
        return None
    row = dict(zip(SPEC["columns"], cells))
    row["_line"] = record["line"]
    return row


def record_key(record) -> str:
    """Best-effort segment key for a source record, including malformed rows."""
    row = record.get("row")
    if row:
        return row.get(SPEC["key"], "")
    cells = record.get("cells") or []
    return cells[KEY_INDEX] if len(cells) > KEY_INDEX else ""


def load_source(profile: str, path: str | None = None):
    sample = _path(profile, path)
    if not sample.is_file():
        raise DomainIssue("SAMPLE_UNKNOWN")
    raw = sample.read_bytes()
    if len(raw) > MAX_FILE:
        raise DomainIssue("FILE_TOO_LARGE", 413)
    parsed = read_records(raw, SPEC["columns"], MAX_ROWS)
    records = []
    for record in parsed["records"]:
        records.append({
            "line": record["line"],
            "cells": record["cells"],
            "blank": record["blank"],
            "repeated": record["repeated"],
            "row": hydrate(record),
        })
    return {"profile": profile, "path": sample,
            "sha256": __import__("hashlib").sha256(raw).hexdigest(), "records": records}


def settle(records):
    """Resolve duplicate/conflict groups over a raw record list.

    Records are exactly what ``load_source`` produces, optionally with corrected
    ``row`` mappings.  Corrections do not bypass the conflict rule: a segment
    whose live rows still disagree stays isolated.
    """
    issues = []
    counts = {"input": len(records), "accepted": 0, "isolated": 0, "duplicates": 0, "ignored": 0}
    dispositions = {}
    valid = []
    for record in records:
        line = record["line"]
        if record["blank"]:
            counts["ignored"] += 1
            issues.append({"line": line, "key": "", "code": "BLANK_ROW"})
            dispositions[line] = {"kind": "ignored", "code": "BLANK_ROW"}
            continue
        if record["repeated"]:
            counts["ignored"] += 1
            issues.append({"line": line, "key": "", "code": "REPEATED_HEADER"})
            dispositions[line] = {"kind": "ignored", "code": "REPEATED_HEADER"}
            continue
        row = record["row"]
        if row is None:
            counts["isolated"] += 1
            key = record["cells"][0] if record["cells"] else ""
            issues.append({"line": line, "key": key, "code": "COLUMN_COUNT"})
            dispositions[line] = {"kind": "isolated", "code": "COLUMN_COUNT"}
            continue
        if not row.get(SPEC["key"]):
            counts["isolated"] += 1
            issues.append({"line": line, "key": "", "code": "KEY_MISSING"})
            dispositions[line] = {"kind": "isolated", "code": "KEY_MISSING"}
            continue
        valid.append(record)
    grouped = OrderedDict()
    for record in valid:
        grouped.setdefault(record["row"][SPEC["key"]], []).append(record)
    accepted = []
    for key, group in grouped.items():
        signatures = {tuple(record["row"][column] for column in SPEC["columns"]) for record in group}
        if len(signatures) == 1:
            accepted.append(group[0]["row"])
            counts["accepted"] += 1
            dispositions[group[0]["line"]] = {"kind": "accepted", "code": ""}
            for record in group[1:]:
                counts["duplicates"] += 1
                issues.append({"line": record["line"], "key": key, "code": "EXACT_DUPLICATE"})
                dispositions[record["line"]] = {"kind": "duplicate", "code": "EXACT_DUPLICATE"}
        else:
            counts["isolated"] += len(group)
            for record in group:
                issues.append({"line": record["line"], "key": key, "code": "CONFLICT_DUPLICATE"})
                dispositions[record["line"]] = {"kind": "isolated", "code": "CONFLICT_DUPLICATE"}
    accepted.sort(key=lambda row: row["_line"])
    return accepted, issues, counts, dispositions


def load(profile: str, path: str | None = None):
    source = load_source(profile, path)
    accepted, issues, counts, _ = settle(source["records"])
    return {"profile": profile, "path": source["path"], "sha256": source["sha256"],
            "rows": accepted, "issues": issues, "counts": counts}
