import json

from app.correction.service import normalize_fixes, request_key, resolve, stored_corrections
from app.errors import DomainIssue
from app.intake.service import load_source
from app.review.service import serialize
from app.service import pipeline


def submit(store, run_id, fixes, comment=""):
    """Record a correction, recompute the run and invalidate any prior review.

    * Corrections are not gated on the review revision.  Two reviewers working
      from the same older reconciliation can both submit; corrections touching
      different temperature segments both take effect, while a later correction
      for a segment already claimed by an earlier one is rejected instead of
      overwriting that earlier result.
    * A retried submission is idempotent: it is stored once and never counted
      twice, and it does not advance the run revision again.
    """
    row = store.get(run_id)
    if row is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if not isinstance(comment, str):
        raise DomainIssue("BAD_REQUEST", detail="补正说明无效")
    normalized = normalize_fixes(fixes)
    key = request_key(run_id, normalized)

    def recompute(profile, stored):
        return pipeline(profile, corrections=stored_corrections(stored))

    run, correction, state = store.record_correction(
        run_id, key, row["revision"], comment.strip(), normalized, recompute)
    if state == "missing":
        raise DomainIssue("RUN_NOT_FOUND", 404)
    return serialize(run), _row(correction), state == "created"


def list_corrections(store, run_id):
    row = store.get(run_id)
    if row is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    corrections = stored_corrections(store.corrections(run_id))
    if not corrections:
        return []
    source = load_source(row["profile"])
    _, _, decisions = resolve(source, corrections)
    decided = {(item["correction_id"], item["line"]): item for item in decisions}
    result = []
    for correction in corrections:
        result.append(_row({**correction, "fixes": [
            {**fix, "status": (decided.get((correction["id"], int(fix["line"]))) or {}).get("status", "REJECTED"),
             "reason": (decided.get((correction["id"], int(fix["line"]))) or {}).get("reason", "REJECTED")}
            for fix in correction["fixes"]
        ]}))
    return result


def _row(row):
    if row is None:
        return None
    item = dict(row)
    if isinstance(item.get("fixes"), str):
        item["fixes"] = json.loads(item["fixes"])
    return item
