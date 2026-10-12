#!/usr/bin/env python3
"""Observation-only hook: record each agy hook call. It never blocks anything."""
import json, pathlib, sys, time

here = pathlib.Path(__file__).resolve().parent
event = sys.argv[1]
raw = sys.stdin.read()
try:
    payload = json.loads(raw) if raw.strip() else {}
except Exception:
    payload = {"_unparsed": raw[:2000]}
rec = {"event": event, "t": time.time(), "keys": sorted(payload.keys()),
       "conversationId": payload.get("conversationId"), "stepIdx": payload.get("stepIdx"),
       "invocationNum": payload.get("invocationNum"), "executionNum": payload.get("executionNum"),
       "transcriptPath": payload.get("transcriptPath")}
tc = payload.get("toolCall")
if isinstance(tc, dict):
    args = tc.get("args") or {}
    rec["tool"] = tc.get("name")
    rec["argKeys"] = sorted(args.keys()) if isinstance(args, dict) else str(type(args))
    rec["args"] = json.dumps(args, ensure_ascii=False)[:1500]
if event == "PostToolUse":
    rec["error"] = payload.get("error")
if event == "Stop":
    rec["terminationReason"] = payload.get("terminationReason")
    rec["fullyIdle"] = payload.get("fullyIdle")
with open(here / "events.jsonl", "a") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
# Output: nothing for PreToolUse (no opinion). Empty object elsewhere. Stop: let it stop.
if event == "Stop":
    print(json.dumps({"decision": "stop"}))
elif event != "PreToolUse":
    print("{}")
