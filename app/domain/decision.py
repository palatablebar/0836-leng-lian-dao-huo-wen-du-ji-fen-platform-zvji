from app.domain.helpers import D


def decide_rows(items):
    for item in items:
        if item.get("problem"):
            item["verdict"] = "REJECT"
            item["reason"] = item["problem"]
        elif item["mkt"] > D("8.0", "LIMIT"):
            item["verdict"] = "REJECT"
            item["reason"] = "MKT_OVER_8"
        elif item["max_c"] > D("12", "LIMIT"):
            item["verdict"] = "REVIEW"
            item["reason"] = "TEMP_SPIKE"
        else:
            item["verdict"] = "PASS"
            item["reason"] = "WITHIN_RANGE"
        item.setdefault("verdict", "PASS")
        item.setdefault("reason", "OK")
    return items
