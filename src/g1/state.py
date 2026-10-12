"""Task state as a pure fold over ledger records (ASC-26, OUR-46).

Nothing here is stored; every caller recomputes from the ledger.
"""

from . import canon


def empty():
    return {"tasks": {}, "active": None, "alerts": [], "host_unverified": False, "host_fp": None, "seq": -1, "head": None,
            "challenges": {}}


def fold(records):
    s = empty()
    for rec in records:
        s["seq"] = rec["seq"]
        s["head"] = rec["hash"]
        ev, d = rec["event"], rec["data"]
        if ev == "contract_registered":
            tid = d["task"]
            s["tasks"][tid] = {
                "task": tid, "contract": d["contract"], "contract_hash": d["contract_hash"],
                "registered_seq": rec["seq"], "status": "active", "attempts": [], "continuations": 0,
                "baseline": d.get("baseline"), "oracle_hashes": d.get("oracle_hashes", {}),
                "policy_digest": d.get("policy_digest"), "base_tree": d.get("tree_digest"),
                "completion": None, "last_vector": None, "paused": None, "blocked": None, "gap": 0, "exec_hashes": d.get("exec_hashes", {}),
                "from_challenge": d.get("from_challenge"),
            }
            s["active"] = tid
            ch = s["challenges"].get(d.get("from_challenge") or "")
            if ch and ch["decision"] is None:
                # the acceptance travels in the contract record (one record, R4-02); older ledgers carry a
                # challenge_decided record before it, which the branch below has already applied
                dec = d.get("decision") or {}
                ch["decision"], ch["decided_seq"], ch["reason"], ch["run_by"] = "accepted", rec["seq"], dec.get("reason"), dec.get("run_by")
        elif ev == "contract_superseded":
            t = s["tasks"].get(d["task"])
            if t:
                t["status"] = "superseded"
                if s["active"] == d["task"]:
                    s["active"] = None
        elif ev == "contract_invalidated":
            t = s["tasks"].get(d["task"])
            if t:
                t["status"] = "invalidated"
                if s["active"] == d["task"]:
                    s["active"] = None
        elif ev == "verification_started":
            t = s["tasks"].get(d["task"])
            if t:
                t["attempts"].append({"attempt": d["attempt"], "started_seq": rec["seq"], "result": None})
        elif ev in ("verification_succeeded", "verification_failed"):
            t = s["tasks"].get(d["task"])
            if t:
                for a in t["attempts"]:
                    if a["attempt"] == d["attempt"] and a["result"] is None:
                        a["result"] = {"event": ev, "seq": rec["seq"], "hash": rec["hash"], "data": d}
                        break
                if "vector" in d:
                    t["last_vector"] = d["vector"]
                t["gap"] = max(t["gap"], int(d.get("gap", 0)))
        elif ev == "continuation_issued":
            t = s["tasks"].get(d["task"])
            if t:
                t["continuations"] = max(t["continuations"], int(d["n"]))
        elif ev == "task_status_changed":
            t = s["tasks"].get(d["task"])
            if t:
                t["status"] = d["status"]
                t["paused"] = d.get("reason")
                if d["status"] == "complete":
                    t["completion"] = {"receipt_seq": d["verification_receipt_seq"], "receipt_hash": d["verification_receipt_hash"], "seq": rec["seq"]}
                    if s["active"] == d["task"]:
                        s["active"] = None
                elif d["status"] == "active":
                    s["active"] = d["task"]
                    t["blocked"] = None
                elif d["status"] == "paused" and d.get("reason") == "blocked":
                    t["blocked"] = {"item": d.get("item", ""), "why": d.get("why", ""), "options": list(d.get("options") or []),
                                    "seq": rec["seq"]}
        elif ev == "challenge_recorded":
            s["challenges"][d["id"]] = {"id": d["id"], "claim": d.get("claim", ""), "by": d.get("by", ""), "verdict": d.get("verdict"),
                                        "seq": rec["seq"], "contract": d.get("contract"), "contract_hash": d.get("contract_hash"),
                                        "baseline": d.get("baseline") or {}, "reasons": d.get("reasons") or [],
                                        "decision": None, "decided_seq": None, "reason": None, "run_by": None}
        elif ev == "challenge_decided":
            ch = s["challenges"].get(d["id"])
            if ch:
                ch["decision"], ch["decided_seq"], ch["reason"] = d.get("decision"), rec["seq"], d.get("reason")
                ch["run_by"] = d.get("run_by")
        elif ev == "integrity_alert":
            s["alerts"].append({"seq": rec["seq"], "kind": d.get("kind"), "detail": d.get("detail")})
        elif ev == "host_contract_observed":
            s["host_fp"] = d.get("fingerprint")
            if d.get("status") == "unverified":
                s["host_unverified"] = True
            elif d.get("status") == "verified":
                s["host_unverified"] = False
    return s


def active_task(s):
    tid = s.get("active")
    if tid is None:
        return None
    t = s["tasks"].get(tid)
    return t if t and t["status"] == "active" else None


def last_result(t):
    for a in reversed(t["attempts"]):
        if a["result"] is not None:
            return a["result"]
    return None


def check_ids(contract):
    return [c["id"] for c in contract["checks"]]


def vector_of(contract, results):
    """Pass/fail vector in contract order. Unknown counts as 0."""
    return [1 if results.get(cid, {}).get("verdict") == "pass" else 0 for cid in check_ids(contract)]


def failing_ids(contract, vector):
    return [cid for cid, v in zip(check_ids(contract), vector) if v == 0]


def summarize_results(results):
    """Recompute the summary from per-check tuples; an empty vector is never all-pass (OUR-03)."""
    if not results:
        return False
    return all(r.get("verdict") == "pass" and r.get("executed") is True for r in results.values())


def task_view(t):
    """A small, serializable view used by projections and status."""
    r = last_result(t)
    return {
        "task": t["task"], "status": t["status"], "contract_hash": t["contract_hash"][:16],
        "objective": t["contract"].get("objective", "")[:200],
        "checks": check_ids(t["contract"]),
        "last_vector": t["last_vector"], "continuations": t["continuations"], "paused": t["paused"], "blocked": t.get("blocked"),
        "last_result_seq": r["seq"] if r else None, "completion": t["completion"], "gap": t["gap"],
        # conversations whose transcripts were gone at the last attempt: a completion with this set is not the same as
        # a clean one, and the user must be able to see it after the task is done (R3-18)
        "liveness_unknown": liveness_unknown(t),
    }


def liveness_unknown(t):
    r = last_result(t)
    return int(r["data"].get("liveness_unknown", 0)) if r else 0


def cached_summary(root):
    """The summary cached beside the ledger head, or None when it is missing or bound to another head. Two small
    reads and no chain walk: this is the PreToolUse path (design 7.2). The caller falls back to the full fold."""
    import os
    from . import paths
    try:
        with open(os.path.join(paths.ws_dir(root), "ledger.head.json"), "r", encoding="utf-8") as f:
            head = canon.loads(f.read())
        with open(paths.summary_path(root), "r", encoding="utf-8") as f:
            c = canon.loads(f.read())
    except (OSError, ValueError):
        return None
    if isinstance(c, dict) and isinstance(head, dict) and c.get("seq") == head.get("seq") and c.get("hash") == head.get("hash") \
            and isinstance(c.get("summary"), dict):
        return c["summary"]
    return None


def summary(s):
    """The facts the per-call hooks need, small enough to cache beside the head (workspace.Workspace.summary):
    the active scope for PreToolUse and the projection lines for SessionStart and PreInvocation."""
    t = active_task(s)
    act = None
    if t is not None:
        r = last_result(t)
        v = t["last_vector"]
        act = {"task": t["task"], "contract_hash": t["contract_hash"], "objective": t["contract"].get("objective", ""),
               "checks": check_ids(t["contract"]), "last_vector": v,
               "failing": failing_ids(t["contract"], v) if v is not None else None,
               "last_reason": r["data"].get("reason") if r else None, "last_seq": r["seq"] if r else None,
               "liveness_unknown": liveness_unknown(t),
               "allowed_paths": list(t["contract"]["allowed_paths"]), "oracle_files": list(t["contract"]["oracle_files"]),
               # the commands of the checks not yet passing: an agent that did not write the contract (a fresh session,
               # a contract from a challenge or the command line) must see what G1 will run
               "open_checks": [{"id": k["id"], "cmd": " ".join(k["argv"])[:600]} for k in t["contract"]["checks"]
                               if v is None or k["id"] in failing_ids(t["contract"], v)][:4]}
        ch = (s.get("challenges") or {}).get(t.get("from_challenge") or "")
        if ch:
            act["challenge"] = {"id": ch["id"], "claim": ch["claim"][:300]}
    done = [x for x in s["tasks"].values() if x["status"] == "complete"]
    paused = [x for x in s["tasks"].values() if x["status"] == "paused"]
    alert = s["alerts"][-1] if s["alerts"] else None
    waiting = [c for c in s.get("challenges", {}).values() if c["verdict"] == "confirmed" and c["decision"] is None]
    return {
        "challenges_waiting": len(waiting),
        "seq": s["seq"], "head": s["head"],
        "alert": {"kind": alert["kind"], "seq": alert["seq"]} if alert else None,
        "host_unverified": bool(s.get("host_unverified")),
        "active": act,
        "last_complete": {"task": done[-1]["task"], "receipt_seq": done[-1]["completion"]["receipt_seq"],
                          "liveness_unknown": liveness_unknown(done[-1])} if done else None,
        "last_paused": {"task": paused[-1]["task"], "reason": paused[-1]["paused"], "blocked": paused[-1].get("blocked")} if paused else None,
    }

