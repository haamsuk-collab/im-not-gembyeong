#!/usr/bin/env python3
"""Run one agy probe with a global hook layer and an optional workspace layer."""
import json, pathlib, shutil, subprocess, sys, time

P = pathlib.Path(__file__).resolve().parent
name, prompt, gmode, wmode, skip = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4]), sys.argv[5] == "skip"
run = P / "gruns" / name
if run.exists():
    shutil.rmtree(run)
ws = run / "ws"
ws.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(ws)], check=True)
(ws / "README.md").write_text("probe workspace\n")
(run / "global-mode.json").write_text(json.dumps(gmode))
if wmode is not None:
    (ws / ".agents" / "g1probe").mkdir(parents=True)
    shutil.copy(P / "hook.py", ws / ".agents" / "g1probe" / "hook.py")
    wmode["log"] = str(run / "events.jsonl")
    (ws / ".agents" / "g1probe" / "mode.json").write_text(json.dumps(wmode))
    cmd = lambda ev: f"python3 g1probe/hook.py {ev}"
    (ws / ".agents" / "hooks.json").write_text(json.dumps({"g1-ws-probe": {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PreToolUse")}]}],
        "Stop": [{"type": "command", "command": cmd("Stop")}],
    }}))
argv = ["agy", "-p", prompt, "--model", "gemini-3.8-flash-low", "--output-format", "stream-json", "--log-file", str(run / "agy.log"), "--print-timeout", "90s"]
if skip:
    argv.append("--dangerously-skip-permissions")
t0 = time.time()
with open(run / "stdout.ndjson", "w") as so, open(run / "stderr.txt", "w") as se:
    try:
        rc = subprocess.run(argv, cwd=ws, stdout=so, stderr=se, stdin=subprocess.DEVNULL, timeout=240).returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
ev = [json.loads(l) for l in (run / "events.jsonl").read_text().splitlines()] if (run / "events.jsonl").exists() else []
seq = [f"{e.get('layer', 'workspace')}:{e['event']}" for e in ev]
lines = (run / "stdout.ndjson").read_text().strip().splitlines()
res = json.loads(lines[-1]).get("result", {}) if lines else {}
files = sorted(str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts and ".agents" not in p.parts)
print(json.dumps({"name": name, "rc": rc, "sec": round(time.time() - t0, 1), "hook_sequence": seq, "files": files, "status": res.get("status"), "response": (res.get("response") or "").strip()[:160], "conversation_id": res.get("conversation_id")}, ensure_ascii=False))
