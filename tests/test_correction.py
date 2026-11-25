from app.correction.service import resolve
from app.intake.service import load_source


def clean_run(client):
    return client.post("/api/runs", json={"profile": "clean"}).get_json()


def dirty_run(client):
    return client.post("/api/runs", json={"profile": "dirty"}).get_json()


def correct(client, run, fixes, comment=""):
    return client.post(f"/api/runs/{run['run_id']}/corrections",
                       json={"fixes": fixes, "comment": comment})


def row_view(run, line):
    for item in run["ledger"]["correction"]["rows"]:
        if item["line"] == line:
            return item
    raise AssertionError("line %s not found" % line)


def test_retry_is_idempotent(client):
    run = dirty_run(client)
    fixes = [{"line": 8, "values": {"temp_c": "4.0"}}]
    first = correct(client, run, fixes, "补正温度")
    second = correct(client, run, fixes, "补正温度")
    assert first.status_code == second.status_code == 200
    assert first.get_json()["created"] is True
    assert second.get_json()["created"] is False
    assert first.get_json()["run"]["revision"] == second.get_json()["run"]["revision"]
    assert first.get_json()["run"]["counts"] == second.get_json()["run"]["counts"]
    assert len(client.get(f"/api/runs/{run['run_id']}/corrections").get_json()["corrections"]) == 1


def test_corrected_row_is_counted(client):
    run = dirty_run(client)
    before = run["counts"]["computed"]
    result = correct(client, run, [{"line": 8, "values": {"temp_c": "4.0"}}]).get_json()
    assert result["run"]["counts"]["computed"] == before + 1
    entry = row_view(result["run"], 8)
    assert entry["state"] == "counted"
    assert entry["corrected"] is True
    assert entry["original"]["temp_c"] == ""
    assert entry["current"]["temp_c"] == "4.0"


def test_partial_fix_of_disputed_segment_does_not_count(client):
    run = dirty_run(client)
    # lines 3 and 4 share segment 01:00; fixing only line 3 keeps them in dispute.
    result = correct(client, run, [{"line": 3, "values": {"temp_c": "7.0"}}]).get_json()
    assert row_view(result["run"], 3)["state"] == "isolated"
    assert row_view(result["run"], 4)["state"] == "isolated"


def test_fixing_all_rows_of_segment_clears_conflict(client):
    run = dirty_run(client)
    fixes = [{"line": 3, "values": {"temp_c": "6.0"}},
             {"line": 4, "values": {"temp_c": "6.0"}}]
    result = correct(client, run, fixes).get_json()
    states = (row_view(result["run"], 3)["state"], row_view(result["run"], 4)["state"])
    assert states == ("counted", "duplicate")


def test_different_segments_both_apply(client):
    run = dirty_run(client)
    first = correct(client, run, [{"line": 3, "values": {"temp_c": "6.0"}},
                                  {"line": 4, "values": {"temp_c": "6.0"}}], "甲")
    second = correct(client, run, [{"line": 10, "values": {"unit": "C"}}], "乙")
    assert first.get_json()["created"] and second.get_json()["created"]
    latest = second.get_json()["run"]
    assert row_view(latest, 10)["state"] == "counted"
    assert row_view(latest, 3)["state"] == "counted"


def test_same_segment_later_correction_cannot_overwrite(client):
    run = dirty_run(client)
    first = correct(client, run, [{"line": 3, "values": {"temp_c": "7.0"}}], "甲")
    second = correct(client, run, [{"line": 4, "values": {"temp_c": "7.0"}}], "乙")
    assert first.get_json()["created"] and second.get_json()["created"]
    latest = second.get_json()["run"]
    # The later correction touching the same segment (01:00) cannot take over;
    # line 3 keeps the first correction (7.0), so the pair stays in dispute.
    assert row_view(latest, 4)["correction"]["status"] == "REJECTED"
    assert row_view(latest, 4)["correction"]["reason"] == "SEGMENT_CLAIMED"
    assert row_view(latest, 4)["current"]["temp_c"] == "6.0"
    assert row_view(latest, 3)["state"] == "isolated"
    assert row_view(latest, 3)["current"]["temp_c"] == "7.0"


def test_correction_after_approval_reopens_run(client):
    run = clean_run(client)
    client.post(f"/api/runs/{run['run_id']}/review",
                json={"decision": "APPROVED", "comment": "ok", "expected_revision": 0})
    result = correct(client, run, [{"line": 6, "values": {"temp_c": "7.0"}}]).get_json()
    assert result["run"]["status"] == "DRAFT"
    assert client.get(f"/api/runs/{run['run_id']}/evidence").status_code == 409


def test_correction_requires_known_line(client):
    run = clean_run(client)
    response = correct(client, run, [{"line": 999, "values": {"temp_c": "1"}}])
    assert response.status_code == 200
    correction = client.get(f"/api/runs/{run['run_id']}/corrections").get_json()["corrections"][0]
    assert correction["fixes"][0]["status"] == "REJECTED"
    assert correction["fixes"][0]["reason"] == "LINE_UNKNOWN"


def test_empty_fixes_are_rejected(client):
    run = clean_run(client)
    assert correct(client, run, []).status_code == 400


def test_unknown_run_is_not_found(client):
    response = client.post("/api/runs/nope/corrections", json={"fixes": [{"line": 2, "values": {"temp_c": "1"}}]})
    assert response.status_code == 404


def test_resolve_keeps_first_claim_per_segment():
    source = load_source("dirty")
    corrections = [
        {"id": "a", "seq": 1, "fixes": [{"line": 3, "values": {"temp_c": "6.0"}}]},
        {"id": "b", "seq": 2, "fixes": [{"line": 4, "values": {"temp_c": "5.0"}}]},
    ]
    accepted, claims, decisions = resolve(source, corrections)
    assert accepted[3]["correction_id"] == "a"
    assert 4 not in accepted
    assert claims["2026-11-20 01:00"] == "a"
    rejected = next(item for item in decisions if item["line"] == 4)
    assert rejected["status"] == "REJECTED"
    assert rejected["reason"] == "SEGMENT_CLAIMED"


def test_reconcile_view_tallies_every_source_line(client):
    run = dirty_run(client)
    view = run["ledger"]["correction"]
    total = view["counted"] + view["isolated"] + view["duplicates"] + view["ignored"]
    assert total == len(view["rows"]) == run["counts"]["input"]
    assert all(check["ok"] for check in view["checks"])


def test_evidence_carries_corrections(client):
    run = clean_run(client)
    result = correct(client, run, [{"line": 6, "values": {"temp_c": "7.5"}}]).get_json()
    client.post(f"/api/runs/{run['run_id']}/review",
                json={"decision": "APPROVED", "comment": "ok", "expected_revision": result["run"]["revision"]})
    artifact = client.get(f"/api/runs/{run['run_id']}/evidence").get_json()
    assert len(artifact["corrections"]) == 1
    assert artifact["corrections"][0]["lines"] == [6]


def test_stage_endpoint_accepts_run_corrections(client):
    run = dirty_run(client)
    correct(client, run, [{"line": 8, "values": {"temp_c": "4.0"}}])
    payload = client.post("/api/stages/reconcile", json={"run_id": run["run_id"]}).get_json()
    assert payload["ledger"]["correction"]["counted"] == run["ledger"]["correction"]["counted"] + 1


def test_correction_does_not_change_other_segments(client):
    run = dirty_run(client)
    before = {row["line"]: row["current"] for row in run["ledger"]["correction"]["rows"]}
    result = correct(client, run, [{"line": 10, "values": {"unit": "C"}}]).get_json()
    after = {row["line"]: row["current"] for row in result["run"]["ledger"]["correction"]["rows"]}
    for line in before:
        if line != 10:
            assert before[line] == after[line]


def test_duplicate_retry_from_two_clients_counts_once(client):
    run = dirty_run(client)
    fixes = [{"line": 8, "values": {"temp_c": "4.0"}}]
    first = correct(client, run, fixes, "补正").get_json()
    second = correct(client, run, fixes, "补正").get_json()
    assert first["created"] is True and second["created"] is False
    assert first["run"]["counts"] == second["run"]["counts"]
    assert len(client.get(f"/api/runs/{run['run_id']}/corrections").get_json()["corrections"]) == 1
