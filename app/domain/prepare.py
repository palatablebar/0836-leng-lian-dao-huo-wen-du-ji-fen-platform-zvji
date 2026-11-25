from app.catalog import SPEC
from app.domain.helpers import D, DAY, I, M, TS, optional
from app.intake.normalize import canonical


PARSERS = {
    "money": lambda value, code: M(value, code),
    "decimal": lambda value, code: D(value, code),
    "decimal_optional": lambda value, code: optional(D, value, code),
    "int": lambda value, code: I(value, code),
    "int_positive": lambda value, code: positive(I(value, code)),
    "date": lambda value, code: DAY(value, code),
    "date_optional": lambda value, code: optional(DAY, value, code),
    "datetime": lambda value, code: TS(value, code),
}


def positive(value):
    if value <= 0:
        raise ValueError("BAD_POSITIVE")
    return value


def _typed(rows):
    typed, issues = [], []
    for raw in rows:
        item = dict(raw)
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            for field, kind in SPEC["types"].items():
                code = "INVALID_" + field.upper()
                item[field] = PARSERS[kind](item.get(field), code)
            typed.append(item)
        except ValueError as exc:
            issues.append({"line": raw.get("_line", 0), "key": raw.get(SPEC["key"], ""), "code": str(exc)})
    return typed, issues


def prepare_rows(rows):
    typed, issues = _typed(rows)
    rows = typed
    items = []
    for item in typed:
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            if item["unit"].upper() == "F":
                item["temp_c"] = (item["temp_c"] - D("32", "BAD_UNIT")) * D("5", "BAD_UNIT") / D("9", "BAD_UNIT")
            elif item["unit"].upper() != "C":
                raise ValueError("BAD_UNIT")
            item["temp_c"] = item["temp_c"] - (item["probe_offset"] or D("0", "BAD_OFFSET"))
            if item["temp_c"] <= D("-273.15", "TEMP_TOO_LOW"):
                raise ValueError("TEMP_TOO_LOW")
            if item["segment_end"] <= item["segment_start"]:
                raise ValueError("END_BEFORE_START")
            item["minutes"] = D(str((item["segment_end"] - item["segment_start"]).total_seconds() / 60), "BAD_SEGMENT")
            items.append(item)
        except ValueError as exc:
            issues.append({"line": item.get("_line", 0), "key": item.get(SPEC["key"], ""), "code": str(exc)})
    return items, issues
