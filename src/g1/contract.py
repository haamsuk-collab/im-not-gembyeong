"""Contracts: strict decoding, coverage matrix, scope, oracle pinning, red baseline (design 5).

Proposal shape (every key required unless marked optional):
{
  "task": "short-id",
  "objective": "one sentence",
  "criteria": [{"id": "C1", "text": "..."}],
  "checks": [{"id": "K1", "argv": ["python3", "-m", "pytest", "tests/test_x.py", "-q"],
              "kind": "must_flip" | "guard", "covers": ["C1"],
              "targets": ["src/x.py"] (required for must_flip), "timeout_s": 120 (optional)}],
  "allowed_paths": ["src/", "tests/"],
  "oracle_files": ["tests/test_x.py"],
  "depends_on": [] (optional)
}

Targets are the files the work changes and the check depends on: inside allowed_paths, never oracle files.
The canary corrupts them and the check must fail; a must_flip check without targets, or with a test file as
its target, could pass for a reason unrelated to the work (an external file, a stub), so it is rejected.
"""

import os
import re
import shutil
import unicodedata

from . import canon, paths, runner, snapshot

ID_RE = canon.ID_RE
TOP_KEYS = {"task", "objective", "criteria", "checks", "allowed_paths", "oracle_files", "depends_on"}
CRIT_KEYS = {"id", "text"}
CHECK_KEYS = {"id", "argv", "kind", "covers", "targets", "timeout_s"}
CONTRACT_DOMAIN = "g1-contract-v1"
MAX_CHECKS = 64
MAX_CRITERIA = 64
MAX_TEXT = 600        # objective, criterion text
MAX_PATH = 300
MAX_PATHS = 256
MAX_ARGV = 64
MAX_ARG = 2000
MAX_TARGETS = 32


class ContractError(Exception):
    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


def _rel_ok(p):
    """A workspace-relative path: no absolute path, no '..', not '.', no control characters, not inside an
    excluded directory (those are neither snapshotted nor copied into the scratch tree)."""
    if not isinstance(p, str) or not p or p == "." or p.startswith("/") or len(p) > MAX_PATH:
        return False
    if any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in p):
        return False
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts):
        return False
    return not any(x in paths.DEFAULT_EXCLUDES for x in parts)


def _norm(p):
    return os.path.normpath(p) + ("/" if p.endswith("/") else "")


def validate_shape(prop):
    reasons = []
    if not isinstance(prop, dict):
        return ["proposal must be an object"]
    extra = set(prop) - TOP_KEYS
    missing = TOP_KEYS - {"depends_on"} - set(prop)
    if extra:
        reasons.append(f"unknown keys: {sorted(extra)}")
    if missing:
        reasons.append(f"missing keys: {sorted(missing)}")
    if reasons:
        return reasons
    if not isinstance(prop["task"], str) or not ID_RE.match(prop["task"]):
        reasons.append("task id must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    if not isinstance(prop["objective"], str) or not prop["objective"].strip() or len(prop["objective"]) > MAX_TEXT:
        reasons.append(f"objective must be a non-empty string of at most {MAX_TEXT} characters")
    crits, checks = prop["criteria"], prop["checks"]
    if not isinstance(crits, list) or not crits or len(crits) > MAX_CRITERIA:
        reasons.append("criteria must be a non-empty list")
        crits = []
    if not isinstance(checks, list) or not checks or len(checks) > MAX_CHECKS:
        reasons.append("checks must be a non-empty list")
        checks = []
    cids, kids = [], []
    for c in crits:
        if not isinstance(c, dict) or set(c) != CRIT_KEYS or not isinstance(c.get("id"), str) or not ID_RE.match(c["id"]) \
                or not isinstance(c.get("text"), str) or not c["text"].strip() or len(c["text"]) > MAX_TEXT:
            reasons.append(f"bad criterion: {c!r}"[:200])
            continue
        cids.append(c["id"])
    ap = prop["allowed_paths"]
    ap_ok = isinstance(ap, list) and ap and len(ap) <= MAX_PATHS and all(_rel_ok(p) for p in ap)
    of = prop["oracle_files"]
    of_ok = isinstance(of, list) and len(of) <= MAX_PATHS and all(_rel_ok(p) for p in of)
    allowed = [_norm(p) for p in ap] if ap_ok else []
    oracles = {os.path.normpath(p) for p in of} if of_ok else set()
    for k in checks:
        if not isinstance(k, dict) or not (set(k) <= CHECK_KEYS) or not {"id", "argv", "kind", "covers"} <= set(k):
            reasons.append(f"bad check shape: {k!r}"[:200])
            continue
        kid = k["id"] if isinstance(k["id"], str) and ID_RE.match(k["id"]) else None
        if kid is None:
            reasons.append(f"bad check id: {k.get('id')!r}"[:200])
        if not isinstance(k["argv"], list) or not k["argv"] or len(k["argv"]) > MAX_ARGV \
                or not all(isinstance(a, str) and a and len(a) <= MAX_ARG for a in k["argv"]):
            reasons.append(f"check {kid}: argv must be a non-empty list of at most {MAX_ARGV} non-empty strings")
        if k["kind"] not in ("must_flip", "guard"):
            reasons.append(f"check {kid}: kind must be must_flip or guard")
        if not isinstance(k["covers"], list) or not k["covers"]:
            reasons.append(f"check {kid}: covers must be a non-empty list")
        targets = k.get("targets", [])
        if not isinstance(targets, list) or len(targets) > MAX_TARGETS:
            reasons.append(f"check {kid}: targets must be a list of at most {MAX_TARGETS} paths")
            targets = []
        if k["kind"] == "must_flip" and not targets:
            reasons.append(f"check {kid}: a must_flip check needs targets, the files of the work it depends on")
        for t in targets:
            if not _rel_ok(t) or t.endswith("/"):
                reasons.append(f"check {kid}: bad target path {t!r}"[:200])
                continue
            nt = os.path.normpath(t)
            if nt in oracles:
                reasons.append(f"check {kid}: target {nt} is a pinned oracle file; targets are the files the work changes")
            elif ap_ok and not paths.in_scope(nt, allowed):
                reasons.append(f"check {kid}: target {nt} is outside allowed_paths")
        if "timeout_s" in k and (not isinstance(k["timeout_s"], int) or isinstance(k["timeout_s"], bool) or k["timeout_s"] < 1):
            reasons.append(f"check {kid}: timeout_s must be a positive integer")
        kids.append(k.get("id"))
    if len(set(cids)) != len(cids):
        reasons.append("duplicate criterion ids")
    if len(set(kids)) != len(kids):
        reasons.append("duplicate check ids")
    # coverage matrix: no zero row, no zero column
    covered = set()
    for k in checks:
        if isinstance(k, dict) and isinstance(k.get("covers"), list):
            unknown = [c for c in k["covers"] if c not in cids]
            if unknown:
                reasons.append(f"check {k.get('id')} covers unknown criteria {unknown}")
            covered |= set(k["covers"])
    zero_rows = [c for c in cids if c not in covered]
    if zero_rows:
        reasons.append(f"criteria without a check (zero rows): {zero_rows}")
    if not ap_ok:
        reasons.append("allowed_paths must be a non-empty list of relative, non-traversing paths (never '.')")
    if not of_ok:
        reasons.append("oracle_files must be a list of relative paths")
    dep = prop.get("depends_on", [])
    if not isinstance(dep, list) or not all(isinstance(d, str) and ID_RE.match(d) for d in dep):
        reasons.append("depends_on must be a list of task ids")
    if isinstance(prop.get("task"), str) and prop["task"] in dep:
        reasons.append("a contract cannot depend on itself")
    return reasons


in_scope = paths.in_scope


def contract_hash(contract):
    return canon.domain_hash(CONTRACT_DOMAIN, contract)


def normalize(prop):
    c = {
        "task": prop["task"], "objective": prop["objective"].strip(),
        "criteria": [{"id": x["id"], "text": x["text"].strip()} for x in prop["criteria"]],
        "checks": [{"id": k["id"], "argv": list(k["argv"]), "kind": k["kind"], "covers": sorted(set(k["covers"])),
                    "targets": sorted(set(os.path.normpath(t) for t in k.get("targets", []))),
                    "timeout_s": int(k.get("timeout_s", runner.DEFAULT_TIMEOUT_S))} for k in prop["checks"]],
        "allowed_paths": sorted(set(_norm(p) for p in prop["allowed_paths"])),
        "oracle_files": sorted(set(os.path.normpath(p) for p in prop["oracle_files"])),
        "depends_on": sorted(set(prop.get("depends_on", []))),
    }
    return c


def required_paths(contract):
    """The relative paths every scratch copy for this contract must contain: targets, oracles, workspace executables."""
    req = set(contract["oracle_files"])
    for k in contract["checks"]:
        req.update(k.get("targets", []))
        if "/" in k["argv"][0]:
            req.add(os.path.normpath(k["argv"][0]))
    return req


def red_baseline(root, contract, private_home_parent):
    """Run every check on a scratch copy of the pre-work tree.
    must_flip must FAIL; guard must PASS. Returns (ok, results, reasons)."""
    reasons, results = [], {}
    scratch = runner.scratch_copy(root, "baseline", required=required_paths(contract))
    try:
        tree = os.path.join(scratch, "tree")
        env = runner.scrubbed_env(os.path.join(scratch, "home"))
        for k in contract["checks"]:
            try:
                runner.resolve_executable(k["argv"][0], env, root, contract["oracle_files"])
            except runner.RunnerError as e:
                reasons.append(f"check {k['id']}: {e}")
                continue
            argv = list(k["argv"])
            if "/" in argv[0]:
                argv[0] = os.path.join(tree, argv[0])
            r = runner.run(argv, tree, env, k["timeout_s"])
            v = runner.verdict_of(r)
            results[k["id"]] = {"verdict": v, "exit": r["exit"], "timed_out": r["timed_out"], "truncated": r["truncated"],
                                "executed": r["executed"], "stdout_sha256": r["stdout_sha256"], "stderr_sha256": r["stderr_sha256"],
                                "stderr_tail": r["stderr_tail"][-600:]}
            if k["kind"] == "must_flip" and v != "fail":
                reasons.append(f"check {k['id']} must fail on the pre-work tree but gave {v} (exit {r['exit']})")
            if k["kind"] == "guard" and v != "pass":
                reasons.append(f"guard {k['id']} must pass on the pre-work tree but gave {v} (exit {r['exit']})")
    finally:
        runner.remove_scratch(scratch)
    return (not reasons), results, reasons


def exec_hashes(contract):
    env = runner.scrubbed_env("/nonexistent")
    out = {}
    for k in contract["checks"]:
        a0 = k["argv"][0]
        if "/" in a0:
            continue  # pinned through oracle_files when workspace-relative
        p = runner.resolve_executable(a0, env)
        out[a0] = {"path": p, "sha256": runner.executable_hash(p)}
    return out


def pin_oracles(root, contract):
    hashes = snapshot.file_hashes(root, contract["oracle_files"])
    missing = [k for k, v in hashes.items() if v is None]
    return hashes, missing
