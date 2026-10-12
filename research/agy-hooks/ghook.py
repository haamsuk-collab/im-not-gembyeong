#!/usr/bin/env python3
"""G1 global probe hook: acts only for probe workspaces, otherwise prints {}."""
import json, pathlib, sys, time

RUNS = pathlib.Path(__file__).resolve().parent / "gruns"
event = sys.argv[1]
raw = sys.stdin.read()
try:
    ws = pathlib.Path((json.loads(raw).get("workspacePaths") or [""])[0]).resolve()
except Exception:
    ws = None
if ws is None or RUNS not in ws.parents:
    sys.exit(0)  # print nothing: measured as "no decision" for non-probe workspaces
run = ws.parent
mode = json.loads((run / "global-mode.json").read_text())
with open(run / "events.jsonl", "a") as f:
    f.write(json.dumps({"layer": "global", "event": event, "t": time.time(), "stdin": raw}) + "\n")
b = mode.get(event, "noop")
if event == "PreToolUse" and b == "deny":
    print(json.dumps({"decision": "deny", "reason": "G1 global probe deny"}))
elif event == "PreToolUse" and b == "allow":
    print(json.dumps({"decision": "allow"}))
elif event == "PreToolUse" and b == "empty":
    pass
else:
    print("{}")
