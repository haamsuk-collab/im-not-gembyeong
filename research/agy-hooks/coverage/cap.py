#!/usr/bin/env python3
"""python3 cap.py <name> <case> "<prompt>" -> one run with cap_hook.py; prints a JSON summary."""
import json, pathlib, secrets, shutil, subprocess, sys, time
P = pathlib.Path(__file__).resolve().parent
name, case, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
model = "gemini-3.8-flash-high"
run = P / "runs-cap" / name
if run.exists(): shutil.rmtree(run)
ws = run / "ws"; hd = ws / ".agents" / "g1cap"; hd.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(ws)], check=True)
(ws / "README.md").write_text("capability probe workspace\n")
nonce = "NONCE-" + secrets.token_hex(4).upper()
state = ws / "G1_STATE.md"
state.write_text(f"# G1 state\n\nG1 nonce: {nonce}\n")
mode = {"case": case, "state_path": str(state), "nonce_line": f"G1 nonce: {nonce}", "limit": 12}
(hd / "mode.json").write_text(json.dumps(mode))
shutil.copy(P / "cap_hook.py", hd / "hook.py")
cmd = lambda ev: f"python3 g1cap/hook.py {ev}"
hooks = {"g1-cap": {
    "SessionStart": [{"type": "command", "command": cmd("SessionStart")}],
    "PreInvocation": [{"type": "command", "command": cmd("PreInvocation")}],
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PreToolUse")}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd("PostToolUse")}]}],
    "PostInvocation": [{"type": "command", "command": cmd("PostInvocation")}],
    "Stop": [{"type": "command", "command": cmd("Stop")}],
}}
(ws / ".agents" / "hooks.json").write_text(json.dumps(hooks, indent=2))
argv = ["agy", "-p", prompt, "--model", model, "--output-format", "stream-json", "--dangerously-skip-permissions", "--log-file", str(run / "agy.log")]
t0 = time.time()
with open(run / "stdout.ndjson", "w") as so, open(run / "stderr.txt", "w") as se:
    try: rc = subprocess.run(argv, cwd=ws, stdout=so, stderr=se, stdin=subprocess.DEVNULL, timeout=900).returncode
    except subprocess.TimeoutExpired: rc = "timeout"
resp, usage, status = "", None, None
for line in (run / "stdout.ndjson").read_text().splitlines():
    try: j = json.loads(line)
    except Exception: continue
    if j.get("event") == "result":
        resp = (j["result"].get("response") or "").strip(); usage = j["result"].get("usage"); status = j["result"].get("status")
events = [json.loads(l) for l in (hd / "events.jsonl").read_text().splitlines()] if (hd / "events.jsonl").exists() else []
seq = []
for e in events:
    tag = e["event"] + (f"({e['tool']}#{e['stepIdx']})" if e.get("tool") else "") + (f"[inv={e['inv']}]" if e.get("inv") is not None else "")
    seq.append(tag)
out = {"name": name, "case": case, "rc": rc, "seconds": round(time.time() - t0, 1), "status": status, "nonce": nonce,
       "nonce_in_reply": nonce in resp, "files": sorted(str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts and ".agents" not in p.parts),
       "response": resp[:400], "total_tokens": (usage or {}).get("total_tokens"), "sequence": " > ".join(seq),
       "stderr_tail": (run / "stderr.txt").read_text()[-600:]}
(run / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False))
