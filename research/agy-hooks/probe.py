#!/usr/bin/env python3
"""Run one agy probe in a fresh workspace and print a JSON result."""
import json, os, pathlib, shutil, subprocess, sys, time

P = pathlib.Path(__file__).resolve().parent
name, prompt = sys.argv[1], sys.argv[2]
mode = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
pre_timeout = int(mode.pop("pre_timeout", 30))
timeouts = mode.pop("timeouts", {})
model = mode.pop("model", "gemini-3.8-flash-low")
run = P / "runs" / name
if run.exists():
    shutil.rmtree(run)
ws = run / "ws"
(ws / ".agents" / "g1probe").mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(ws)], check=True)
(ws / "README.md").write_text("probe workspace\n")
shutil.copy(P / "hook.py", ws / ".agents" / "g1probe" / "hook.py")
log = run / "events.jsonl"
mode["log"] = str(log)
(ws / ".agents" / "g1probe" / "mode.json").write_text(json.dumps(mode))
cmd = lambda ev: f"python3 g1probe/hook.py {ev}"
hooks = {"g1-probe": {
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PreToolUse"), "timeout": pre_timeout}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PostToolUse")}]}],
    "PreInvocation": [{"type": "command", "command": cmd("PreInvocation")}],
    "PostInvocation": [{"type": "command", "command": cmd("PostInvocation")}],
    "Stop": [{"type": "command", "command": cmd("Stop"), "timeout": int(timeouts.get("Stop", 30))}],
    "SessionStart": [{"type": "command", "command": cmd("SessionStart")}],
}}
(ws / ".agents" / "hooks.json").write_text(json.dumps(hooks, indent=2))
argv = ["agy", "-p", prompt, "--model", model, "--output-format", "stream-json",
        "--dangerously-skip-permissions", "--log-file", str(run / "agy.log")]
t0 = time.time()
with open(run / "stdout.ndjson", "w") as so, open(run / "stderr.txt", "w") as se:
    rc = subprocess.run(argv, cwd=ws, stdout=so, stderr=se, stdin=subprocess.DEVNULL, timeout=420).returncode
dt = round(time.time() - t0, 1)
events = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
counts = {}
for e in events:
    counts[e["event"]] = counts.get(e["event"], 0) + 1
files = sorted(str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts and ".agents" not in p.parts)
print(json.dumps({"name": name, "rc": rc, "seconds": dt, "hook_counts": counts, "workspace_files": files}, ensure_ascii=False))
