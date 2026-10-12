#!/usr/bin/env python3
"""Run one observation case in a fresh workspace: python3 cover.py <name> "<prompt>" [model]"""
import json, pathlib, shutil, subprocess, sys, time

P = pathlib.Path(__file__).resolve().parent
name, prompt = sys.argv[1], sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else "gemini-3.8-flash-high"
run = P / "runs" / name
if run.exists():
    shutil.rmtree(run)
ws = run / "ws"
hd = ws / ".agents" / "g1cover"
hd.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(ws)], check=True)
(ws / "README.md").write_text("observation workspace\n")
shutil.copy(P / "hook.py", hd / "hook.py")
cmd = lambda ev: f"python3 g1cover/hook.py {ev}"
hooks = {"g1-cover": {
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PreToolUse")}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PostToolUse")}]}],
    "PreInvocation": [{"type": "command", "command": cmd("PreInvocation")}],
    "PostInvocation": [{"type": "command", "command": cmd("PostInvocation")}],
    "Stop": [{"type": "command", "command": cmd("Stop")}],
    "SessionStart": [{"type": "command", "command": cmd("SessionStart")}],
}}
(ws / ".agents" / "hooks.json").write_text(json.dumps(hooks, indent=2))
argv = ["agy", "-p", prompt, "--model", model, "--output-format", "stream-json",
        "--dangerously-skip-permissions", "--log-file", str(run / "agy.log")]
t0 = time.time()
with open(run / "stdout.ndjson", "w") as so, open(run / "stderr.txt", "w") as se:
    try:
        rc = subprocess.run(argv, cwd=ws, stdout=so, stderr=se, stdin=subprocess.DEVNULL, timeout=600).returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
dt = round(time.time() - t0, 1)
log = hd / "events.jsonl"
events = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
summary = {"name": name, "model": model, "rc": rc, "seconds": dt, "events": [], "conversationIds": sorted({e.get("conversationId") for e in events if e.get("conversationId")})}
for e in events:
    item = {"event": e["event"], "cid": (e.get("conversationId") or "")[:8], "step": e.get("stepIdx")}
    if e.get("tool"):
        item["tool"] = e["tool"]; item["argKeys"] = e.get("argKeys")
    summary["events"].append(item)
summary["files"] = sorted(str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts and ".agents" not in p.parts)
resp = ""
try:
    for line in (run / "stdout.ndjson").read_text().splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("type") == "result":
            resp = (j.get("result") or j.get("response") or "")[:400]
            summary["agy_status"] = j.get("status") or j.get("subtype")
            summary["usage"] = j.get("usage")
except Exception:
    pass
summary["response"] = resp
(run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
print(json.dumps(summary, ensure_ascii=False))
