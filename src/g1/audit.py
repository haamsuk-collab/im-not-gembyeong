"""Offline audit: re-derive everything from the ledger and evidence (RUN-41, ASC-55, OUR-46)."""

import os

from . import canon, complete as complete_mod, ledger as ledger_mod, paths, state as state_mod


def run(root):
    report = {"root": root, "ok": True, "findings": [], "notes": [], "records": 0, "tasks": {}}
    led = ledger_mod.Ledger(root)
    try:
        recs = led.verify()
    except Exception as e:
        report["ok"] = False
        report["findings"].append(f"chain: {e}")
        return report
    report["records"] = len(recs)
    by_seq = {r["seq"]: r for r in recs}
    s = state_mod.fold(recs)
    for cid, ch in s.get("challenges", {}).items():
        rec = by_seq.get(ch["seq"])
        base = (rec or {}).get("data", {}).get("baseline", {})
        if ch["verdict"] == "confirmed" and not (base and all(v.get("verdict") == "fail" for v in base.values())):
            report["ok"] = False
            report["findings"].append(f"challenge {cid}: confirmed without a failing baseline for every check")
        if ch["decision"] == "accepted" and not any(t.get("from_challenge") == cid for t in s["tasks"].values()):
            # a ledger from before round 4 could stop between the decision record and the contract (R4-02)
            report["ok"] = False
            report["findings"].append(f"challenge {cid}: accepted without a contract registered from it")
    for a in s.get("alerts", []):
        if a.get("kind") == "post_completion_change":
            report["notes"].append(f"seq {a['seq']}: the tree changed while a completion was being written (post_completion_change)")
    for tid, t in s["tasks"].items():
        lu = state_mod.liveness_unknown(t)
        if lu:
            report["notes"].append(f"task {tid}: the last attempt could not read the transcripts of {lu} conversation(s) (liveness_unknown)")
        fc = None
        reg = by_seq.get(t["registered_seq"])
        if reg is not None:
            fc = reg["data"].get("from_challenge")
        if fc is not None and (s.get("challenges", {}).get(fc) or {}).get("decision") != "accepted":
            report["ok"] = False
            report["findings"].append(f"task {tid}: registered from challenge {fc}, which was not accepted")
        tr = {"status": t["status"], "attempts": len(t["attempts"]), "findings": [], "liveness_unknown": lu}
        # every receipt's summary must equal the conjunction of its per-check results
        for a in t["attempts"]:
            r = a["result"]
            if r is None:
                tr["findings"].append(f"attempt {a['attempt']} has no terminal receipt")
                continue
            d = r["data"]
            if "results" in d:
                summary = state_mod.summarize_results(d["results"])
                if (r["event"] == "verification_succeeded") != (summary and d.get("scope_ok", False)):
                    tr["findings"].append(f"attempt {a['attempt']}: stored verdict is more favourable than its results")
                ev = d.get("evidence")
                if ev:
                    p = os.path.join(paths.ws_dir(root), ev)
                    bound = t["completion"] and t["completion"]["receipt_seq"] == r["seq"]
                    if not os.path.exists(p):
                        # tier B compaction removes bulk evidence of unbound attempts; the receipt keeps the digests
                        if bound:
                            tr["findings"].append(f"attempt {a['attempt']}: evidence of the completion receipt is missing ({ev})")
                        else:
                            tr["compacted"] = tr.get("compacted", 0) + 1
                    else:
                        with open(p, "r", encoding="utf-8") as f:
                            stored = canon.loads(f.read())
                        if stored.get("results") != d["results"]:
                            tr["findings"].append(f"attempt {a['attempt']}: evidence file differs from the receipt")
        # completion must bind an existing succeeded receipt for this task with the same contract hash
        if t["completion"]:
            c = t["completion"]
            rec = by_seq.get(c["receipt_seq"])
            if rec is None or rec["hash"] != c["receipt_hash"]:
                tr["findings"].append("completion binds a receipt that is not in the chain")
            elif rec["event"] != "verification_succeeded" or rec["data"].get("task") != tid:
                tr["findings"].append("completion binds a record that is not a passing receipt for this task")
            elif rec["data"].get("contract_hash") != t["contract_hash"]:
                tr["findings"].append("completion binds a receipt of another contract version")
            else:
                ok, why = complete_mod.approve(dict(t, status="active"), rec["data"], rec["data"]["tree_digest"],
                                               t["oracle_hashes"], t["policy_digest"])
                if not ok:
                    tr["findings"].append("completion predicate does not hold on replay: " + "; ".join(why))
            later = [r for r in recs if r["seq"] > c["receipt_seq"] and r["seq"] < c["seq"]
                     and r["data"].get("task") == tid and r["event"] in ("verification_started", "contract_superseded")]
            if later:
                tr["findings"].append("events for the task exist between the receipt and the completion")
        if tr["findings"]:
            report["ok"] = False
        report["tasks"][tid] = tr
    return report
