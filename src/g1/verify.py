"""Verification attempts and receipts (design 6.1)."""

import os


import time

from . import canon, contract as contract_mod, ledger as ledger_mod, paths, runner, snapshot, state as state_mod

CANARY_BYTES = b"\x00\xff G1-CANARY \xfe\x00 this file was replaced by G1 to test the check \x00"


def write_evidence(root, attempt, name, obj):
    d = os.path.join(paths.evidence_dir(root), attempt)
    os.makedirs(d, mode=0o700, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(canon.dumps(obj))
    return os.path.relpath(p, paths.ws_dir(root))


def _run_checks(contract, tree, env, only=None):
    results = {}
    for k in contract["checks"]:
        if only is not None and k["id"] not in only:
            continue
        argv = list(k["argv"])
        if "/" in argv[0]:
            argv[0] = os.path.join(tree, argv[0])
        r = runner.run(argv, tree, env, k["timeout_s"])
        results[k["id"]] = {
            "verdict": runner.verdict_of(r), "executed": r["executed"], "exit": r["exit"],
            "timed_out": r["timed_out"], "truncated": r["truncated"], "duration_ms": r["duration_ms"],
            "stdout_sha256": r["stdout_sha256"], "stderr_sha256": r["stderr_sha256"],
            "stdout_tail": r["stdout_tail"][-1500:], "stderr_tail": r["stderr_tail"][-1500:],
        }
    return results


def _scratch_file(tree, rel):
    """The target's path inside the scratch tree if it is a regular file there, reached without any symbolic
    link; otherwise None. G1 writes canary bytes only to such files, never through a link out of the copy."""
    real_tree = os.path.realpath(tree)
    p = os.path.join(tree, rel)
    if os.path.realpath(p) != os.path.join(real_tree, os.path.normpath(rel)):
        return None  # some component is a symbolic link
    try:
        st = os.lstat(p)
    except OSError:
        return None
    import stat
    return p if stat.S_ISREG(st.st_mode) else None


def _canary(root, contract, results):
    """For each passing must_flip check: corrupt its targets in a fresh scratch copy and re-run. A check that
    still passes does not depend on the work (OUR-13). A target that is missing, not a regular file, or reached
    through a symbolic link is never written; if no target can be corrupted the check fails."""
    todo = [k for k in contract["checks"] if k["kind"] == "must_flip" and results.get(k["id"], {}).get("verdict") == "pass"]
    if not todo:
        return
    scratch = runner.scratch_copy(root, "canary", required=contract_mod.required_paths(contract))
    try:
        tree = os.path.join(scratch, "tree")
        env = runner.scrubbed_env(os.path.join(scratch, "home"))
        for k in todo:
            originals, missing, irregular = {}, [], []
            for t in k.get("targets") or []:
                p = _scratch_file(tree, t)
                if p is None:
                    # a target the work never created is allowed; one that exists as anything but a regular file
                    # reached without a link (a symbolic link, a directory, a link in a parent) is not
                    (irregular if os.path.lexists(os.path.join(tree, t)) else missing).append(t)
                    continue
                fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as f:
                    originals[p] = f.read()
                fd = os.open(p, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
                with os.fdopen(fd, "wb") as f:
                    f.write(CANARY_BYTES)
            r = _run_checks(contract, tree, env, only={k["id"]})[k["id"]] if originals else None
            for p, b in originals.items():
                fd = os.open(p, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
                with os.fdopen(fd, "wb") as f:
                    f.write(b)
            if missing:
                results[k["id"]]["canary_missing"] = missing[:10]
            if irregular:
                results[k["id"]]["verdict"] = "fail"
                results[k["id"]]["canary"] = "target_not_regular"
                results[k["id"]]["canary_irregular"] = irregular[:10]
            elif not originals:
                results[k["id"]]["verdict"] = "fail"
                results[k["id"]]["canary"] = "targets_missing"
            elif r["verdict"] == "pass":
                results[k["id"]]["verdict"] = "fail"
                results[k["id"]]["canary"] = "insensitive"
            else:
                results[k["id"]]["canary"] = "sensitive"
    finally:
        runner.remove_scratch(scratch)


def _leaves_workspace(root, rel, entry):
    """True for a symbolic link whose target text points outside the workspace root (absolute, or '..' past it)."""
    if not entry or entry.get("kind") != "symlink":
        return False
    target = entry.get("target", "")
    if os.path.isabs(target):
        real_root = os.path.realpath(root)
        t = os.path.normpath(target)
        return not (t == real_root or t.startswith(real_root + os.sep))
    joined = os.path.normpath(os.path.join(os.path.dirname(rel), target))
    return joined == ".." or joined.startswith("../") or joined.startswith("/")


def _copy_reason(e):
    return "insufficient_space" if "insufficient space" in str(e) else "scratch_copy_failed"


def load_base_manifest(root, task):
    p = os.path.join(paths.evidence_dir(root), f"base-{task['task']}.json")
    with open(p, "r", encoding="utf-8") as f:
        man = canon.loads(f.read())
    if snapshot.digest(man) != task["base_tree"]:
        raise RuntimeError("base manifest digest mismatch")
    return man


def run_attempt(root, task, policy_digest, gap=0, liveness_unknown=0):
    """Run one verification attempt for the active task. Returns (event, data). liveness_unknown counts the
    conversations whose transcripts are gone; it is recorded in the receipt and does not refuse completion."""
    c = task["contract"]
    attempt = ledger_mod.token_hex(6)
    t_start = time.monotonic()
    out = {"task": task["task"], "attempt": attempt, "contract_hash": task["contract_hash"], "policy_digest": policy_digest, "gap": int(gap)}
    if liveness_unknown:
        out["liveness_unknown"] = int(liveness_unknown)
    # identity before
    man_before = snapshot.manifest(root)
    td = snapshot.digest(man_before)
    out["tree_digest"] = td
    oracles = snapshot.file_hashes(root, c["oracle_files"])
    out["oracle_hashes"] = oracles
    if oracles != task["oracle_hashes"]:
        out["reason"] = "oracle_changed"
        out["detail"] = sorted(k for k in oracles if oracles[k] != task["oracle_hashes"].get(k))
        return "verification_failed", out
    if policy_digest != task["policy_digest"]:
        out["reason"] = "policy_changed"
        return "verification_failed", out
    if gap:
        out["reason"] = "observation_gap"
        return "verification_failed", out
    try:
        base_man = load_base_manifest(root, task)
    except Exception as e:
        out["reason"] = "base_manifest_unavailable"
        out["detail"] = str(e)[:200]
        return "verification_failed", out
    # executable pins
    env0 = runner.scrubbed_env("/nonexistent")
    for a0, pin in task.get("exec_hashes", {}).items():
        try:
            p = runner.resolve_executable(a0, env0)
            if runner.executable_hash(p) != pin["sha256"]:
                out["reason"] = "executable_changed"
                out["detail"] = a0
                return "verification_failed", out
        except runner.RunnerError as e:
            out["reason"] = "executable_missing"
            out["detail"] = str(e)[:200]
            return "verification_failed", out
    # run checks on a scratch copy
    try:
        scratch = runner.scratch_copy(root, "verify", required=contract_mod.required_paths(c))
    except runner.RunnerError as e:
        out["reason"] = _copy_reason(e)
        out["detail"] = str(e)[:300]
        return "verification_failed", out
    try:
        skipped = runner.scratch_skipped(scratch)
        if skipped:
            out["scratch_skipped"] = skipped[:50]  # entries the checks could not see (unreadable, special files)
        tree = os.path.join(scratch, "tree")
        env = runner.scrubbed_env(os.path.join(scratch, "home"))
        out["env_digest"] = runner.env_digest(env)
        results = _run_checks(c, tree, env)
    finally:
        runner.remove_scratch(scratch)
    try:
        _canary(root, c, results)
    except runner.RunnerError as e:
        out["reason"] = _copy_reason(e)
        out["detail"] = str(e)[:300]
        return "verification_failed", out
    # identity after
    man_after = snapshot.manifest(root)
    if snapshot.digest(man_after) != td:
        out["reason"] = "identity_changed"
        return "verification_failed", out
    changed = snapshot.changed_paths(base_man, man_after)
    outside = [p for p in changed if not contract_mod.in_scope(p, c["allowed_paths"])]
    # a link the work created that leads out of the workspace makes the result depend on files outside it
    links_out = [p for p in changed if p not in outside and _leaves_workspace(root, p, man_after.get(p))]
    if links_out:
        out["links_out"] = links_out[:100]
        outside = outside + links_out
    out["changed"] = changed[:500]
    out["changed_count"] = len(changed)
    out["scope_ok"] = not outside
    out["outside_scope"] = outside[:100]
    vector = state_mod.vector_of(c, results)
    out["vector"] = vector
    out["results"] = results
    out["evidence"] = write_evidence(root, attempt, "results.json", {"attempt": attempt, "results": results, "changed": changed})
    out["verify_ms"] = int((time.monotonic() - t_start) * 1000)
    if outside:
        out["reason"] = "scope_violation"
        return "verification_failed", out
    if not state_mod.summarize_results(results):
        out["reason"] = "checks_failed"
        out["failing"] = state_mod.failing_ids(c, vector)
        return "verification_failed", out
    return "verification_succeeded", out
