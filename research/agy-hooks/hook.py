#!/usr/bin/env python3
"""G1 probe hook: log every agy hook call, then act per mode.json."""
import json, pathlib, sys, time

here = pathlib.Path(__file__).resolve().parent
mode = json.loads((here / "mode.json").read_text())
event = sys.argv[1]
raw = sys.stdin.read()
with open(mode["log"], "a") as f:
    f.write(json.dumps({"layer": "workspace", "event": event, "t": time.time(), "stdin": raw}) + "\n")
behavior = mode.get(event, "default")


def out(obj):
    print(json.dumps(obj))
    sys.stdout.flush()


if event == "PreToolUse":
    if behavior in ("default", "allow"):
        out({"decision": "allow"})
    elif behavior == "deny":
        out({"decision": "deny", "reason": "G1 probe: this tool call is denied"})
    elif behavior == "exit2":
        sys.stderr.write("g1 probe failure\n")
        sys.exit(2)
    elif behavior == "timeout":
        time.sleep(float(mode.get("sleep", 20)))
        with open(mode["log"], "a") as f:
            f.write(json.dumps({"event": "PreToolUse-late-finish", "t": time.time()}) + "\n")
        out({"decision": "deny", "reason": "late deny"})
    elif behavior == "badjson":
        print("this is not json")
    elif behavior == "empty":
        pass
    elif behavior == "braces":
        out({})
    elif behavior == "ask":
        out({"decision": "ask", "reason": "G1 probe: asks for confirmation"})
    elif behavior == "overwrite":
        out({"decision": "allow", "overwrite": mode["overwrite"]})
elif event == "PreInvocation" and behavior == "exit2":
    sys.stderr.write("g1 probe preinvocation failure\n")
    sys.exit(2)
elif event == "Stop" and behavior == "timeout":
    time.sleep(float(mode.get("sleep", 10)))
    out({"decision": "continue", "reason": "late continue"})
elif event == "PreInvocation":
    if behavior == "inject":
        out({"injectSteps": [{"ephemeralMessage": mode["inject"]}]})
    else:
        out({})
elif event == "PostInvocation" and behavior.startswith("terminate_after:"):
    args = json.loads(raw)
    if int(args.get("invocationNum", 0)) >= int(behavior.split(":")[1]):
        out({"terminationBehavior": "terminate"})
    else:
        out({})
elif event == "SessionStart":
    if behavior == "inject":
        out({"injectSteps": [{"ephemeralMessage": mode["session_inject"]}]})
    else:
        out({})
elif event == "Stop":
    counter = here / "stop_count"
    n = (int(counter.read_text()) if counter.exists() else 0) + 1
    counter.write_text(str(n))
    if n <= int(mode.get("stop_continue_limit", 0)):
        out({"decision": "continue", "reason": mode.get("stop_reason", "Continue.")})
    else:
        out({"decision": "stop"})
else:
    out({})
