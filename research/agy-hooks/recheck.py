#!/usr/bin/env python3
"""Re-measure the host facts G1 relies on, against the agy binary on PATH. Run after every agy update.

Usage: python3 recheck.py            (about 16 agy sessions, 10 to 15 minutes)
       python3 recheck.py --only t1-empty,t3-stop-cap

G1 must be uninstalled while this runs (the probes must see the host alone): `g1 uninstall`, then
`g1 install` and `g1 host-verify` afterwards. Results: recheck-<version>.json beside this file, plus the
embedded hooks documentation of the new binary as agy-<version>-embedded-hooks-contract.md when it differs.
Every expectation below is a fact from README.md; a CHANGED line means the host contract moved.
"""
import json
import os
import pathlib
import secrets
import shutil
import subprocess
import sys
import time

P = pathlib.Path(__file__).resolve().parent
MODEL = "gemini-3.8-flash-high"
WRITE = ("Create a file named probe.txt in this workspace containing exactly the line: hello. "
         "Use your file writing tool, not the shell. Then reply with the single word DONE.")
CODE_PROMPT = ("If you already know the G1 probe code, reply with only the code. "
               "Otherwise reply with only UNKNOWN. Do not call any tools.")
OK_PROMPT = "Reply with the single word OK. Do not call any tools."


def agy_version():
    return subprocess.run(["agy", "--version"], capture_output=True, text=True).stdout.strip().split()[-1]


def g1_installed():
    p = pathlib.Path.home() / ".gemini" / "config" / "hooks.json"
    try:
        return "g1" in json.loads(p.read_text())
    except Exception:
        return False


def std_hooks(cmd, matcher="*", pre_timeout=30, stop_timeout=30):
    return {"PreToolUse": [{"matcher": matcher, "hooks": [{"type": "command", "command": cmd("PreToolUse"), "timeout": pre_timeout}]}],
            "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PostToolUse")}]}],
            "PreInvocation": [{"type": "command", "command": cmd("PreInvocation")}],
            "PostInvocation": [{"type": "command", "command": cmd("PostInvocation")}],
            "Stop": [{"type": "command", "command": cmd("Stop"), "timeout": stop_timeout}],
            "SessionStart": [{"type": "command", "command": cmd("SessionStart")}]}


def run_case(name, prompt, mode, matcher="*", pre_timeout=30, stop_timeout=30, skip=True, timeout=420):
    run = P / "recheck-runs" / name
    if run.exists():
        shutil.rmtree(run)
    ws = run / "ws"
    hd = ws / ".agents" / "g1probe"
    hd.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(ws)], check=True)
    (ws / "README.md").write_text("recheck workspace\n")
    shutil.copy(P / "hook.py", hd / "hook.py")
    log = run / "events.jsonl"
    m = dict(mode)
    m["log"] = str(log)
    (hd / "mode.json").write_text(json.dumps(m))
    cmd = lambda ev: f"python3 g1probe/hook.py {ev}"
    (ws / ".agents" / "hooks.json").write_text(json.dumps({"g1-recheck": std_hooks(cmd, matcher, pre_timeout, stop_timeout)}, indent=1))
    argv = ["agy", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--log-file", str(run / "agy.log")]
    if skip:
        argv.append("--dangerously-skip-permissions")
    t0 = time.time()
    with open(run / "stdout.ndjson", "w") as so, open(run / "stderr.txt", "w") as se:
        try:
            rc = subprocess.run(argv, cwd=ws, stdout=so, stderr=se, stdin=subprocess.DEVNULL, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    events = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    counts = {}
    cids = set()
    for e in events:
        counts[e["event"]] = counts.get(e["event"], 0) + 1
        try:
            cids.add(json.loads(e.get("stdin") or "{}").get("conversationId"))
        except ValueError:
            pass
    res = {}
    for line in (run / "stdout.ndjson").read_text().splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("event") == "result":
            res = j["result"]
    files = sorted(str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts and ".agents" not in p.parts)
    return {"name": name, "rc": rc, "sec": round(time.time() - t0, 1), "hook_counts": counts, "conversations": len(cids - {None}),
            "files": files, "status": res.get("status"), "response": (res.get("response") or "").strip()[:200],
            "conversation_id": res.get("conversation_id"), "usage": res.get("usage")}


def cases():
    code = "G1-PROBE-CODE: " + secrets.token_hex(4)
    scode = "G1-SESSION-CODE: " + secrets.token_hex(3)
    has = lambda f: (lambda r: f in r["files"])
    lacks = lambda f: (lambda r: f not in r["files"])
    return [
        ("t1-empty", "empty PreToolUse output allows the call", dict(prompt=WRITE, mode={"PreToolUse": "empty"}), has("probe.txt")),
        ("t1-deny", "deny blocks the call", dict(prompt=WRITE, mode={"PreToolUse": "deny"}), lacks("probe.txt")),
        ("t1-exit2", "a crashed PreToolUse hook blocks the call (fail-closed)", dict(prompt=WRITE, mode={"PreToolUse": "exit2"}), lacks("probe.txt")),
        ("t1-badjson", "invalid JSON from PreToolUse blocks the call", dict(prompt=WRITE, mode={"PreToolUse": "badjson"}), lacks("probe.txt")),
        ("t1-timeout", "a PreToolUse timeout blocks the call", dict(prompt=WRITE, mode={"PreToolUse": "timeout", "sleep": 20}, pre_timeout=3), lacks("probe.txt")),
        ("t1-braces", "{} from PreToolUse counts as a refusal", dict(prompt=WRITE, mode={"PreToolUse": "braces"}), lacks("probe.txt")),
        ("k3-ask", "ask is not a gate under the skip-permissions flag", dict(prompt=WRITE, mode={"PreToolUse": "ask"}), has("probe.txt")),
        ("t2-inject", "PreInvocation ephemeralMessage reaches the model", dict(prompt=CODE_PROMPT, mode={"PreInvocation": "inject", "inject": code}), lambda r: code.split()[-1] in r["response"]),
        ("t7-session-inject", "SessionStart ephemeralMessage reaches the model", dict(prompt=CODE_PROMPT, mode={"SessionStart": "inject", "session_inject": scode}), lambda r: scode.split()[-1] in r["response"]),
        ("t10-preinv-crash", "a crashed PreInvocation hook is ignored (fail-open)", dict(prompt=WRITE, mode={"PreInvocation": "exit2"}), has("probe.txt")),
        ("t9-stop-timeout", "a Stop timeout lets the agent stop (fail-open)", dict(prompt=OK_PROMPT, mode={"Stop": "timeout", "sleep": 10}, stop_timeout=3), lambda r: r["status"] == "SUCCESS"),
        ("t3-stop-cap", "Stop continue is honoured at most 10 times", dict(prompt=OK_PROMPT, mode={"stop_continue_limit": 20, "stop_reason": "Not finished. Reply again with the single word AGAIN."}, timeout=600), lambda r: r["hook_counts"].get("Stop") == 11),
        ("m1-anchored", "matcher ^(a|b)$ selects the tool", dict(prompt=WRITE, mode={}, matcher="^(write_to_file|run_command)$"), lambda r: r["hook_counts"].get("PreToolUse", 0) >= 1 and "probe.txt" in r["files"]),
        ("m2-backslash-pipe", "the documented matcher a\\|b selects nothing", dict(prompt=WRITE, mode={}, matcher="write_to_file\\|run_command"), lambda r: r["hook_counts"].get("PreToolUse", 0) == 0 and "probe.txt" in r["files"]),
        ("t8-tamper", "the hooks file is read at session start only (hooks keep firing after the agent rewrites it)",
         dict(prompt="Overwrite the file .agents/hooks.json in this workspace so that it contains exactly: {}  Use your file writing tool. "
                     "Then create a file named after.txt containing the line: after. Reply DONE.", mode={}),
         lambda r: "after.txt" in r["files"] and r["hook_counts"].get("PreToolUse", 0) >= 2),
        ("c5-subagent", "a subagent runs the hooks under its own conversationId",
         dict(prompt="Delegate this to a subagent and do not do it yourself: the subagent must create a file named sub.txt containing the line: from subagent. After the subagent returns, reply DONE.", mode={}, timeout=600),
         lambda r: r["conversations"] >= 2 and "sub.txt" in r["files"]),
    ]


def embedded_doc(version):
    """Extract the hooks documentation embedded in the binary and compare it with the recorded 1.3.3 text."""
    binary = pathlib.Path(shutil.which("agy")).resolve()
    data = binary.read_bytes()
    start = data.find(b"Hooks are configured in a single")
    if start < 0:
        return "not found"
    old = (P / "agy-1.3.3-embedded-hooks-contract.md").read_text()
    body = old.split("\n\n", 1)[1] if old.startswith(">") else old
    new = data[start:start + len(body.encode()) + 4096].decode("utf-8", "replace")
    cut = new.find("\x00")
    new = new[:cut] if cut > 0 else new
    same = new.startswith(body.strip()[:len(body.strip()) - 50])
    if not same:
        (P / f"agy-{version}-embedded-hooks-contract.md").write_text(
            f"> The text below was extracted, unchanged, from the `agy` {version} binary.\n\n" + new)
    return "same as 1.3.3" if same else f"differs; saved agy-{version}-embedded-hooks-contract.md"


def main(argv):
    if g1_installed():
        print("G1 is installed in ~/.gemini/config/hooks.json; run `g1 uninstall` first, then `g1 install` and `g1 host-verify` afterwards.")
        return 2
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    version = agy_version()
    sha = subprocess.run(["sha256sum", str(pathlib.Path(shutil.which("agy")).resolve())], capture_output=True, text=True).stdout.split()[0]
    out = {"agy_version": version, "binary_sha256": sha, "model": MODEL, "date": time.strftime("%Y-%m-%d"), "cases": []}
    changed = 0
    for name, fact, kw, expect in cases():
        if only and name not in only:
            continue
        r = run_case(name, **kw)
        ok = bool(expect(r))
        r["fact"] = fact
        r["holds"] = ok
        changed += 0 if ok else 1
        out["cases"].append(r)
        print(f"{'SAME   ' if ok else 'CHANGED'} {name:18s} {fact}  [{r['sec']}s hooks={r['hook_counts']} files={r['files']} status={r['status']}]", flush=True)
    out["embedded_doc"] = embedded_doc(version)
    print("embedded hooks documentation:", out["embedded_doc"])
    (P / f"recheck-{version}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"agy {version} sha256 {sha[:16]}: {len(out['cases']) - changed} facts hold, {changed} changed")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
