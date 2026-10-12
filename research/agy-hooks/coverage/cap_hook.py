#!/usr/bin/env python3
"""Capability probe hook. Behavior is read from mode.json next to this file. Records every event."""
import json, pathlib, sys, time
here = pathlib.Path(__file__).resolve().parent
mode = json.loads((here / "mode.json").read_text())
event = sys.argv[1]
raw = sys.stdin.read()
try:
    p = json.loads(raw) if raw.strip() else {}
except Exception:
    p = {}
tc = p.get("toolCall") or {}
rec = {"event": event, "t": time.time(), "cid": (p.get("conversationId") or "")[:8], "stepIdx": p.get("stepIdx"),
       "inv": p.get("invocationNum"), "tool": tc.get("name"), "args": json.dumps(tc.get("args"), ensure_ascii=False)[:300] if tc else None,
       "fullyIdle": p.get("fullyIdle"), "reason": p.get("terminationReason")}
with open(here / "events.jsonl", "a") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
m = mode.get("case")
def out(o):
    print(json.dumps(o)); sys.stdout.flush()
if event == "PreInvocation" and m == "inject_toolcall" and p.get("invocationNum") == 0:
    out({"injectSteps": [{"toolCall": {"name": "view_file", "args": {"AbsolutePath": mode["state_path"]}}}]})
elif event == "PreInvocation" and m == "inject_ephemeral" and p.get("invocationNum") == 0:
    out({"injectSteps": [{"ephemeralMessage": "G1 state: " + mode["nonce_line"]}]})
elif event == "PreToolUse":
    if m == "ask" and tc.get("name") in ("write_to_file", "replace_file_content", "run_command"):
        out({"decision": "ask", "reason": "G1 probe: this write needs confirmation."})
    # else: no opinion (empty stdout)
elif event == "PostInvocation" and m == "force_continue":
    c = here / "fc_count"
    n = (int(c.read_text()) if c.exists() else 0)
    if n < int(mode.get("limit", 12)):
        c.write_text(str(n + 1))
        out({"terminationBehavior": "force_continue"})
    else:
        out({})
elif event == "Stop":
    out({"decision": "stop"})
elif event != "PreToolUse":
    out({})
