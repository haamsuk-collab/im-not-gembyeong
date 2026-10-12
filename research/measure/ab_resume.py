#!/usr/bin/env python3
"""Multi-session measurement (P1): session 1 is cut early, every agy record of it is wiped, session 2 gets only
"Continue the work in this workspace." Outcomes computed by this runner from the final tree:

- pass_task: the task's original test bytes exit 0
- distractors_ok: the two unrelated test files still pass
- scope_ok: only the task's source file changed relative to the initial commit (G1 and cache dirs ignored)
- resumed: pass_task and distractors_ok and scope_ok
- claim / false_done from session 2's final reply; tokens, wall, tool calls of session 2

Usage: python3 ab_resume.py run <out_dir> [--cut 25s] [--fixtures f1,f2] [--arms on,off] [--repeats N]
       python3 ab_resume.py report <out_dir>
"""

import json
import os
import random
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ab  # noqa: E402  (fixtures, oracle helpers, statistics)

G1 = ab.G1
MODEL = ab.MODEL
PROMPT1 = "Implement {src} so that {test} passes. Run the test yourself to confirm. Reply DONE when it passes."
PROMPT2 = "Continue the work in this workspace."
DISTRACTORS = {
    "src/greet.py": "def greet(name):\n    return f'hello, {name}'\n",
    "tests/test_greet.py": ab.FIXTURES["f1-stats"]["tests"].split("from stats")[0] + "from greet import greet\n\ndef test_greet():\n    assert greet('x') == 'hello, x'\n\nif __name__ == '__main__':\n    test_greet(); print('ok')\n",
    "src/count.py": "def count_words(s):\n    return len(s.split())\n",
    "tests/test_count.py": ab.FIXTURES["f1-stats"]["tests"].split("from stats")[0] + "from count import count_words\n\ndef test_count():\n    assert count_words('a b  c') == 3\n\nif __name__ == '__main__':\n    test_count(); print('ok')\n",
}
A = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli")


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=f@x", *args], cwd=root, capture_output=True, text=True)


def make_workspace(root, fx):
    ab.make_workspace(root, fx)
    for p, c in DISTRACTORS.items():
        ab.write(os.path.join(root, p), c)
    ab.write(os.path.join(root, ".gitignore"), "__pycache__/\n.g1/\n.agents/\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "initial")


def wipe_conversation(cid):
    for p in (f"{A}/brain/{cid}", f"{A}/conversations/{cid}.db", f"{A}/presence/{cid}.lock", f"{A}/annotations/{cid}.pbtxt"):
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.exists(p):
            os.unlink(p)
    lc = f"{A}/cache/last_conversations.json"
    try:
        d = json.load(open(lc))
        json.dump({k: v for k, v in d.items() if v != cid}, open(lc, "w"), indent=2)
    except (OSError, ValueError):
        pass


def session(root, prompt, log_path, cut=None):
    argv = ["agy", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--dangerously-skip-permissions"]
    if cut:
        argv += ["--print-timeout", cut]
    t0 = time.time()
    with open(log_path, "w") as so:
        try:
            subprocess.run(argv, cwd=root, stdout=so, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=900)
        except subprocess.TimeoutExpired:
            pass
    wall = time.time() - t0
    tools, resp, usage, cid = 0, "", None, None
    for line in open(log_path, encoding="utf-8", errors="ignore"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        su = j.get("step_update") or {}
        if su.get("conversation_id") and not cid:
            cid = su["conversation_id"]
        if su.get("state") == "ACTIVE" and su.get("step_type") == "tool":
            tools += 1
        if j.get("event") == "result":
            r = j["result"]
            resp, usage, cid = (r.get("response") or "").strip(), r.get("usage"), r.get("conversation_id") or cid
    return {"wall_s": round(wall, 1), "tool_calls": tools, "response": resp[:300], "total_tokens": (usage or {}).get("total_tokens"), "cid": cid}


def run_tests(root, fx):
    stage = root + ".oracle"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(root, stage, ignore=shutil.ignore_patterns(".g1", ".git", ".agents", "__pycache__"))
    ab.write(os.path.join(stage, fx["test"]), fx["tests"])
    for p, c in DISTRACTORS.items():
        if p.startswith("tests/"):
            ab.write(os.path.join(stage, p), c)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": stage, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    def ok(t):
        try:
            return subprocess.run(["python3", t], cwd=stage, env=env, capture_output=True, timeout=60).returncode == 0
        except subprocess.TimeoutExpired:
            return False
    out = {"pass_task": ok(fx["test"]), "distractors_ok": ok("tests/test_greet.py") and ok("tests/test_count.py")}
    shutil.rmtree(stage, ignore_errors=True)
    return out


def changed_paths(root):
    r = git(root, "status", "--porcelain", "--untracked-files=all")
    paths = []
    for line in r.stdout.splitlines():
        p = line[3:].strip()
        if p.startswith(".g1/") or p.startswith(".agents/") or "__pycache__" in p or p.endswith(".oracle"):
            continue
        paths.append(p)
    return sorted(paths)


def run(out_dir, cut, fixtures, arms, repeats):
    os.makedirs(out_dir, exist_ok=True)
    rows_path = os.path.join(out_dir, "rows.jsonl")
    plan = [(fx, arm, r) for r in range(repeats) for fx in fixtures for arm in arms]
    random.Random(4242).shuffle(plan)
    for fx_name, arm, rep in plan:
        fx = ab.FIXTURES[fx_name]
        root = os.path.join(out_dir, "ws", f"{fx_name}-{arm}-{rep}")
        make_workspace(root, fx)
        if arm == "on":
            subprocess.run([G1, "init", root], check=True, capture_output=True)
            cpath = os.path.join(out_dir, f"{fx_name}.contract.json")
            ab.write(cpath, json.dumps(ab.contract_for(fx_name, fx)))
            p = subprocess.run([G1, "propose", root, cpath], capture_output=True, text=True)
            if p.returncode != 0:
                print("contract rejected:", p.stdout[:300]); continue
        s1 = session(root, PROMPT1.format(src=fx["src"], test=fx["test"]), os.path.join(out_dir, f"{fx_name}-{arm}-{rep}-s1.ndjson"), cut=cut)
        after_s1 = run_tests(root, fx)
        if s1["cid"]:
            wipe_conversation(s1["cid"])
        s2 = session(root, PROMPT2, os.path.join(out_dir, f"{fx_name}-{arm}-{rep}-s2.ndjson"))
        tests = run_tests(root, fx)
        changed = changed_paths(root)
        scope_ok = all(p == fx["src"] for p in changed)
        claim = s2["response"].upper().startswith("DONE") or "complete" in s2["response"][:200].lower()
        g1_complete = None
        if arm == "on":
            st = subprocess.run([G1, "status", root], capture_output=True, text=True).stdout
            try:
                g1_complete = json.loads(st)["tasks"][fx_name]["status"] == "complete"
            except Exception:
                g1_complete = None
        row = {"fixture": fx_name, "arm": arm, "rep": rep, "s1_finished": after_s1["pass_task"],
               "pass_task": tests["pass_task"], "distractors_ok": tests["distractors_ok"], "scope_ok": scope_ok, "changed": changed[:20],
               "resumed": tests["pass_task"] and tests["distractors_ok"] and scope_ok,
               "claim": claim, "false_done": claim and not tests["pass_task"], "g1_complete": g1_complete,
               "s1": s1, "s2": s2}
        with open(rows_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(json.dumps({k: row[k] for k in ("fixture", "arm", "rep", "s1_finished", "pass_task", "distractors_ok", "scope_ok", "resumed", "claim", "g1_complete")}
                         | {"s2_tokens": s2["total_tokens"], "s2_wall": s2["wall_s"], "s2_tools": s2["tool_calls"], "s2_reply": s2["response"][:100]}), flush=True)


def report(out_dir):
    rows = [json.loads(l) for l in open(os.path.join(out_dir, "rows.jsonl"))]
    out = {"n_rows": len(rows), "arms": {}}
    for arm in ("on", "off"):
        rs = [r for r in rows if r["arm"] == arm]
        n = len(rs)
        if not n:
            continue
        k = sum(r["resumed"] for r in rs)
        toks = sorted(r["s2"]["total_tokens"] for r in rs if r["s2"]["total_tokens"])
        out["arms"][arm] = {"n": n, "resumed": k, "resumed_wilson95": ab.wilson(k, n),
                            "pass_task": sum(r["pass_task"] for r in rs), "distractors_ok": sum(r["distractors_ok"] for r in rs),
                            "scope_ok": sum(r["scope_ok"] for r in rs), "false_done": sum(r["false_done"] for r in rs),
                            "s1_finished": sum(r["s1_finished"] for r in rs),
                            "s2_tokens_median": toks[len(toks) // 2] if toks else None,
                            "s2_wall_median_s": sorted(r["s2"]["wall_s"] for r in rs)[n // 2],
                            "s2_tool_calls_median": sorted(r["s2"]["tool_calls"] for r in rs)[n // 2],
                            "g1_complete": sum(1 for r in rs if r.get("g1_complete")) if arm == "on" else None}
    by = {}
    for r in rows:
        by.setdefault((r["fixture"], r["rep"]), {})[r["arm"]] = r
    pairs_res = [(int(v["on"]["resumed"]), int(v["off"]["resumed"])) for v in by.values() if "on" in v and "off" in v]
    pairs_tok = [(v["on"]["s2"]["total_tokens"], v["off"]["s2"]["total_tokens"]) for v in by.values() if "on" in v and "off" in v and v["on"]["s2"]["total_tokens"] and v["off"]["s2"]["total_tokens"]]
    out["paired"] = {"pairs": len(pairs_res), "resumed_delta_on_minus_off": ab.paired_bootstrap(pairs_res),
                     "s2_tokens_delta_on_minus_off": ab.paired_bootstrap(pairs_tok)}
    out["rows"] = [{k: r[k] for k in ("fixture", "arm", "rep", "s1_finished", "pass_task", "distractors_ok", "scope_ok", "resumed", "claim", "false_done", "g1_complete", "changed")}
                   | {"s2_tokens": r["s2"]["total_tokens"], "s2_wall": r["s2"]["wall_s"], "s2_tools": r["s2"]["tool_calls"], "s2_reply": r["s2"]["response"][:120]} for r in rows]
    return out


def main(argv):
    if not argv or argv[0] not in ("run", "report"):
        print(__doc__); return 2
    out_dir = argv[1]
    if argv[0] == "report":
        print(json.dumps(report(out_dir), indent=1)); return 0
    cut = argv[argv.index("--cut") + 1] if "--cut" in argv else "25s"
    fixtures = argv[argv.index("--fixtures") + 1].split(",") if "--fixtures" in argv else ["h1-roman", "h2-intervals", "h3-lru", "h4-csv", "h5-topo", "h6-timerange"]
    arms = argv[argv.index("--arms") + 1].split(",") if "--arms" in argv else ["on", "off"]
    repeats = int(argv[argv.index("--repeats") + 1]) if "--repeats" in argv else 1
    run(out_dir, cut, fixtures, arms, repeats)
    print(json.dumps(report(out_dir)["arms"], indent=1)); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
