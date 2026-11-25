from app.catalog import SPEC
from app.intake.service import record_key

COLUMNS = SPEC["columns"]


def original_values(record):
    """Original column values of a source record, padded for short rows."""
    cells = record.get("cells") or []
    return {column: (cells[index] if index < len(cells) else "")
            for index, column in enumerate(COLUMNS)}


def segment_of(record):
    """Identity of the temperature segment a source row belongs to.

    ``segment_start`` is the primary key, so rows sharing it describe the same
    segment.  A row without a usable key cannot share a segment with anyone
    else and is treated as its own segment.
    """
    key = record_key(record)
    return key if key else "line:%s" % record["line"]


def corrected_record(record, values):
    """Return a copy of a source record with the verified correction applied."""
    row = original_values(record)
    for field, value in values.items():
        if field in COLUMNS:
            row[field] = value
    row["_line"] = record["line"]
    cells = [row.get(column, "") for column in COLUMNS]
    updated = dict(record)
    updated["cells"] = cells
    updated["row"] = row
    updated["blank"] = False
    updated["repeated"] = False
    return updated


def apply_fixes(records, accepted):
    """Apply the flat ``{line: values}`` map of accepted fixes to source records."""
    if not accepted:
        return list(records)
    return [corrected_record(record, accepted[record["line"]])
            if record["line"] in accepted else record for record in records]


def correction_summaries(corrections):
    return [{
        "id": correction.get("id"),
        "seq": correction.get("seq"),
        "base_revision": correction.get("base_revision"),
        "comment": correction.get("comment", ""),
        "submitted_at": correction.get("submitted_at"),
        "lines": sorted(int(fix["line"]) for fix in correction.get("fixes", [])),
    } for correction in corrections or []]
