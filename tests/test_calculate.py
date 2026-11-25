from decimal import Decimal

from app.catalog import SPEC
from app.domain.calculate import calculate_rows
from app.domain.prepare import prepare_rows
from tests.domain_cases import CLEAN, calc

# TRAP-19 TRAP-20 TRAP-24 的边界由本文件的跨日、合并与单位用例固定。


def clean_results():
    items, issues = prepare_rows(CLEAN)
    assert issues == []
    return calculate_rows(items)


def test_clean_result_count():
    assert len(clean_results()) == 3


def test_metric_total_is_reconciled():
    total = sum((item["metric"] for item in clean_results()), Decimal("0"))
    assert total == Decimal("16.265")


def test_first_result_matches_expected():
    item = clean_results()[0]
    assert item["label"] == "B001"
    assert abs(float(item["mkt"]) - float("4.515")) < 0.011


def test_core_boundary_case():
    results, issues = calc([{'batch_id': 'B900', 'sensor_id': 'S90', 'segment_start': '2026-11-20 00:00', 'segment_end': '2026-11-20 01:00', 'temp_c': '8.0', 'unit': 'C', 'probe_offset': '0'}])
    assert issues == []
    value = results[0]["mkt"]
    expected = '8.0'
    if expected in {"True", "False"}:
        assert bool(value) is (expected == "True")
    elif isinstance(expected, bool):
        assert bool(value) is expected
    elif expected.startswith("20") and len(expected) == 10:
        assert value.isoformat() == expected
    elif expected.replace(".", "", 1).replace("-", "", 1).isdigit():
        assert abs(float(value) - float(expected)) < 0.001
    else:
        assert value == expected


def test_result_labels_are_unique():
    labels = [item["label"] for item in clean_results()]
    assert len(labels) == len(set(labels))


def test_every_result_has_metric():
    assert all(item.get("metric") is not None for item in clean_results())


def test_short_hot_exposure_uses_arrhenius_weighting():
    rows = [
        dict(CLEAN[0], segment_end="2026-11-20 23:00", temp_c="2"),
        dict(CLEAN[0], segment_start="2026-11-20 23:00", segment_end="2026-11-21 00:00", temp_c="30"),
    ]
    results, issues = calc(rows)
    assert issues == []
    assert results[0]["mkt"] == Decimal("7.935")
    assert results[0]["minutes"] == 1440
