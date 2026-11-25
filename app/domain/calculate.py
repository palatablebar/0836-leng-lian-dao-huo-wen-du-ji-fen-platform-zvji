from datetime import date, timedelta
from app.catalog import SPEC
from app.domain.helpers import *  # noqa: F401,F403


def calculate_rows(items):
    out = []
    rows = items
    groups = {}
    zero = D("0", "CALC")
    kelvin_offset = D("273.15", "CALC")
    activation_over_gas_constant = D("10000", "CALC")
    for item in items:
        groups.setdefault(item["batch_id"], []).append(item)
    for batch_id, segments in groups.items():
        max_c = max(item["temp_c"] for item in segments)
        minutes = sum((item["minutes"] for item in segments), zero)
        hottest_exponent = -activation_over_gas_constant / (max_c + kelvin_offset)
        weighted_factors = sum((
            item["minutes"] * (-activation_over_gas_constant / (item["temp_c"] + kelvin_offset)
                               - hottest_exponent).exp()
            for item in segments
        ), zero)
        log_mean_factor = hottest_exponent + (weighted_factors / minutes).ln()
        mkt = (-activation_over_gas_constant / log_mean_factor - kelvin_offset).quantize(D("0.001", "CALC"))
        out.append({"label": batch_id, "minutes": minutes, "max_c": max_c,
                    "mkt": mkt, "metric": mkt, "limit": D("8.0", "LIMIT")})
    for item in out:
        item.setdefault("label", str(item.get(SPEC["key"], "")))
    return out
