"""Score the challenges recorded by G1 for the semver experiment.

For each challenge: G1's verdict (confirmed means the check fails on the worker's code), and whether the reviewer's
expectation agrees with SPEC.md, measured by running the same check against the reference implementation, which
passes all 44 hidden-oracle cases. A confirmed challenge whose check passes on the reference proves a real defect with
a correct expectation; one whose check fails on the reference demands behaviour SPEC.md does not ask for.

Usage: python3 eval_challenges.py <experiment dir>
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

E = sys.argv[1]
sys.path.insert(0, "<g1>/src")
from g1 import workspace  # noqa: E402

ws = workspace.Workspace(os.path.join(E, "semver"))
chs = ws.state().get("challenges", {})


def run_on(impl_src, argv):
    d = tempfile.mkdtemp(prefix="evalch-")
    try:
        shutil.copytree(os.path.join(E, "semver"), os.path.join(d, "w"), ignore=shutil.ignore_patterns(".git", "__pycache__"))
        shutil.copy(impl_src, os.path.join(d, "w", "src", "semver.py"))
        r = subprocess.run(argv, cwd=os.path.join(d, "w"), capture_output=True, text=True, timeout=60)
        return r.returncode
    finally:
        shutil.rmtree(d, ignore_errors=True)


rows = []
for cid, ch in chs.items():
    checks = (ch.get("contract") or {}).get("checks", [])
    on_ref = [run_on(os.path.join(E, "ref", "src", "semver.py"), k["argv"]) for k in checks]
    on_worker = [run_on(os.path.join(E, "semver", "src", "semver.py"), k["argv"]) for k in checks]
    rows.append({"id": cid, "verdict": ch["verdict"], "claim": ch["claim"][:240],
                 "fails_on_worker": all(x != 0 for x in on_worker), "passes_on_reference": all(x == 0 for x in on_ref)})
confirmed = [r for r in rows if r["verdict"] == "confirmed"]
correct = [r for r in confirmed if r["passes_on_reference"]]
print(json.dumps({"challenges": len(rows), "confirmed": len(confirmed), "unproven": sum(r["verdict"] == "unproven" for r in rows),
                  "invalid": sum(r["verdict"] == "invalid" for r in rows),
                  "confirmed_with_correct_expectation": len(correct),
                  "confirmed_with_wrong_expectation": len(confirmed) - len(correct)}, indent=1))
for r in rows:
    tag = ("REAL DEFECT" if r["passes_on_reference"] else "WRONG EXPECTATION") if r["verdict"] == "confirmed" else r["verdict"].upper()
    print(f"- {r['id']}: {tag} | {r['claim']}")
