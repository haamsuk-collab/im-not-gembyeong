"""Stop policy over pass/fail vectors (design 8). Pure function of ledger state and the latest attempt."""

from . import state as state_mod

DEFAULT_BUDGET = 3


def decide(task, outcome_event, outcome, budget=DEFAULT_BUDGET):
    """Return {"decision": "stop"|"continue", "terminal": <reason>, "reason": <one line>}."""
    c = task["contract"]
    ids = state_mod.check_ids(c)
    vector = outcome.get("vector")
    if outcome_event == "verification_succeeded":
        return {"decision": "stop", "terminal": "complete_candidate", "reason": ""}
    reason_type = outcome.get("reason")
    if vector is None or reason_type in ("identity_changed", "oracle_changed", "policy_changed", "observation_gap",
                                         "insufficient_space", "scratch_copy_failed", "executable_changed",
                                         "executable_missing", "base_manifest_unavailable"):
        return {"decision": "stop", "terminal": "environment_unknown", "reason": f"G1: verification could not run ({reason_type})."}
    failing_now = set(state_mod.failing_ids(c, vector))
    if reason_type == "scope_violation":
        outside = outcome.get("outside_scope", [])[:3]
        return {"decision": "stop", "terminal": "scope_violation", "reason": f"G1: changes outside the contract scope: {outside}"}
    # previous completed attempts (excluding this one)
    prev_vectors = []
    seen = set()
    for a in task["attempts"]:
        r = a["result"]
        if r is None or r["data"].get("attempt") == outcome.get("attempt"):
            continue
        v = r["data"].get("vector")
        if v is not None:
            prev_vectors.append((tuple(v), r["data"].get("tree_digest")))
            seen.add((tuple(v), r["data"].get("tree_digest")))
    cur = (tuple(vector), outcome.get("tree_digest"))
    if cur in seen:
        return {"decision": "stop", "terminal": "oscillation", "reason": "G1: this tree and result were seen before."}
    if len(prev_vectors) >= 3:
        v = [p[0] for p in prev_vectors[-3:]] + [cur[0]]
        if v[-1] == v[-3] and v[-2] == v[-4]:
            return {"decision": "stop", "terminal": "oscillation", "reason": "G1: results alternate without progress."}
    if task["continuations"] >= budget:
        return {"decision": "stop", "terminal": "budget_exhausted", "reason": "G1: continuation budget used."}
    if prev_vectors:
        prev_failing = set(state_mod.failing_ids(c, list(prev_vectors[-1][0])))
        if not failing_now < prev_failing:
            return {"decision": "stop", "terminal": "no_progress", "reason": "G1: the failing set did not shrink."}
    # continue with exactly one next failing check
    nxt = next((k for k in c["checks"] if k["id"] in failing_now), None)
    if nxt is None:
        return {"decision": "stop", "terminal": "no_progress", "reason": "G1: no failing check identified."}
    passed = len(ids) - len(failing_now)
    from . import project
    cmd = project.quote(" ".join(nxt["argv"]), 300, 400)  # agent-written text, one escaped line (R3-11)
    return {"decision": "continue", "terminal": "continue",
            "reason": f"G1: {passed}/{len(ids)} checks pass. Next failing check {nxt['id']}: {cmd} must exit 0. Completion is decided by G1, not by your reply."}
