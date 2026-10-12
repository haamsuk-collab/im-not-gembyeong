"""The single completion function (OUR-01, design 6.2).

approve() returns True only from executed G1 evidence. Every other input is veto-only:
a non-empty `vetoes` list blocks, and no input can add approval.
"""

from . import snapshot, state as state_mod


def approve(task, receipt, current_tree_digest, current_oracles, current_policy_digest, vetoes=()):
    """receipt: data of a verification_succeeded record. Returns (ok, reasons)."""
    reasons = []
    c = task["contract"]
    if receipt is None:
        return False, ["no receipt"]
    results = receipt.get("results") or {}
    if not state_mod.summarize_results(results):
        reasons.append("not all checks passed with executed evidence")
    if set(results) != set(state_mod.check_ids(c)):
        reasons.append("receipt does not cover every contract check")
    for k in c["checks"]:
        r = results.get(k["id"], {})
        if k["kind"] == "must_flip" and r.get("canary") != "sensitive":
            reasons.append(f"check {k['id']} has no sensitive canary")
    if receipt.get("tree_digest") != current_tree_digest:
        reasons.append("tree changed since the receipt")
    if receipt.get("contract_hash") != task["contract_hash"]:
        reasons.append("receipt is for another contract version")
    if current_oracles != task["oracle_hashes"]:
        reasons.append("oracle files differ from the pinned set")
    if receipt.get("policy_digest") != current_policy_digest or task["policy_digest"] != current_policy_digest:
        reasons.append("policy digest differs from admission")
    if not receipt.get("scope_ok", False):
        reasons.append("changed paths outside the allowed scope")
    if int(receipt.get("gap", 0)) != 0 or int(task.get("gap", 0)) != 0:
        reasons.append("observation gap")
    if task["status"] != "active":
        reasons.append(f"task status is {task['status']}")
    for v in vetoes:
        reasons.append(f"veto: {v}")
    return (not reasons), reasons


def completion_data(task, receipt_rec):
    return {"task": task["task"], "status": "complete",
            "verification_receipt_seq": receipt_rec["seq"], "verification_receipt_hash": receipt_rec["hash"]}
