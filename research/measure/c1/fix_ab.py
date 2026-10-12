"""A/B of the fix phase: the same accepted challenge, the same pre-fix code, the status block with or without the open
check's command. Usage: python3 fix_ab.py <experiment dir> <repeats>"""
import json
import os
import random
import shutil
import subprocess
import sys
import time

E, REPS = sys.argv[1], int(sys.argv[2])
sys.path.insert(0, "<g1>/src")
from g1 import paths, workspace  # noqa: E402

orig = workspace.Workspace(os.path.join(E, "semver")).state()["challenges"]["newline-accepted"]
CHALLENGE = {"id": "newline-accepted", "claim": orig["claim"], "by": orig["by"],
             "contract": {k: orig["contract"][k] for k in ("task", "objective", "criteria", "checks", "allowed_paths", "oracle_files")}}
OUT = os.path.join(E, "ab")
os.makedirs(OUT, exist_ok=True)
plan = [(arm, r) for r in range(REPS) for arm in ("default", "no_check_cmd")]
random.Random(73129).shuffle(plan)
for arm, rep in plan:
    root = os.path.join(OUT, f"{arm}-{rep}")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(os.path.join(root, "src"))
    for rel in ("SPEC.md", "README.md", "tests/test_semver.py"):
        os.makedirs(os.path.dirname(os.path.join(root, rel)) or root, exist_ok=True)
        shutil.copy(os.path.join(E, "semver", rel), os.path.join(root, rel))
    shutil.copy(os.path.join(E, "prefix_semver.py"), os.path.join(root, "src", "semver.py"))
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "pre-fix"], check=True)
    ws = workspace.Workspace(root)
    ws.init()
    with open(os.path.join(paths.challenges_dir(root), "c.json"), "w") as f:
        json.dump(CHALLENGE, f)
    notes = ws.process_challenges()  # at the time of the run, process_proposals() also ran challenges
    ok, msg = ws.decide_challenge("newline-accepted", "accepted", "a/b harness")
    assert ok, (notes, msg)
    if arm != "default":
        with open(os.path.join(paths.ws_dir(root), "config.json"), "w") as f:
            json.dump({"projection_variant": arm}, f)
    t0 = time.time()
    log = os.path.join(OUT, f"{arm}-{rep}.ndjson")
    with open(log, "w") as so:
        subprocess.run(["agy", "-p", "Continue the work in this workspace.", "--model", "gemini-3.8-flash-high", "--output-format",
                        "stream-json", "--dangerously-skip-permissions"], cwd=root, stdout=so, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, timeout=1500)
    wall = round(time.time() - t0, 1)
    tokens, cid = None, None
    for line in open(log, errors="ignore"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("event") == "result":
            tokens, cid = (j["result"].get("usage") or {}).get("total_tokens"), j["result"].get("conversation_id")
    s = workspace.Workspace(root).state()
    status = s["tasks"]["fix-newline-accepted"]["status"]
    pre = 0
    for jp in [os.path.join(paths.observe_dir(), paths.ws_id(root), f"journal-{l}.jsonl") for l in ("global", "workspace")]:
        if os.path.exists(jp):
            pre += sum(1 for l in open(jp) if '"kind": "pre"' in l)
    orc = subprocess.run([sys.executable, os.path.join(E, "hidden_oracle.py"), root], capture_output=True, text=True).stdout.strip().splitlines()[-1]
    row = {"arm": arm, "rep": rep, "g1_status": status, "oracle": json.loads(orc)["failed"], "tokens": tokens, "wall_s": wall,
           "mutating_calls": pre, "cid": cid}
    with open(os.path.join(OUT, "rows.jsonl"), "a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)
    if cid:
        shutil.rmtree(os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{cid}"), ignore_errors=True)
print("FIX_AB_DONE")
