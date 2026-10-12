#!/usr/bin/env python3
"""Build CATALOG.md and catalog.json from the T1 atom files and the external atom files.

Usage: python3 build_catalog.py   (run inside research/atoms/)

The T1 files (A-E) use: id, name, statement, mechanism, threat, refs, tests, coupling, loc, g1_hint.
The external files (ext/*.json) use the analyst schema: verdict, hook_mapping, proof_purpose, g1_design, ...
Both are normalized to one record shape. The component is a keyword heuristic for navigation only.
"""
import collections
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent

COMPONENT_RULES = [
    ("measurement", r"bootstrap|confidence interval|wilson|mcnemar|statistic|ensemble|\ba/b\b|sample size|benchmark|calibrat|eval set|false[- ]done rate"),
    ("ledger", r"^led-|ledger|journal|head anchor|hash[- ]chain|append-only|canonical (json|form|encoding)|record hash|genesis|\block\b"),
    ("contract", r"contract|criteria|acceptance|coverage matrix|proposal|plan\.md|allowed path|red baseline|fail before|must flip|pinned (check|test)"),
    ("verify", r"verif|receipt|snapshot|evidence|digest|redact|scrubbed|artifact|output cap|deadline|process group|manifest"),
    ("completion", r"complet|done claim|false done|stale|binding|terminal state"),
    ("hooks", r"\bhook|pretooluse|posttooluse|preinvocation|postinvocation|sessionstart|inject|matcher|hooks\.json|stop hook"),
    ("integrity", r"tamper|anchor|mirror|self-heal|pinned|bootstrap|root of trust|code hash|immutable|integrity"),
    ("control", r"continue|stagnation|oscillation|budget|\bloop\b|retry|hamming|progress vector|revisit"),
    ("runners", r"^run-|runner|subprocess|launch|worker|fresh-turn|fresh turn"),
    ("projection", r"projection|state file|reconstruct|session[- ]start summary|512"),
    ("governance", r"^gov-|^thr-|governance|threat|policy|principle|minimality"),
]

VERDICT_FROM_HINT = {"keep": "adopt", "modify": "adapt", "drop": "reject", "experiment": "research"}


def component_of(text):
    t = text.lower()
    for name, pat in COMPONENT_RULES:
        if re.search(pat, t):
            return name
    return "other"


def t1_verdict(hint):
    h = (hint or "").strip().lower()
    first = re.split(r"[:,;( ]", h, maxsplit=1)[0].rstrip(".")
    return VERDICT_FROM_HINT.get(first, "adapt" if h else "unknown")


def load_t1():
    out = []
    for f in sorted(HERE.glob("*.json")):
        if f.name == "catalog.json":
            continue
        d = json.load(open(f))
        for a in d["atoms"]:
            out.append({
                "id": a["id"], "source": "t1:" + f.stem, "name": a.get("name", ""),
                "statement": a.get("statement", ""), "verdict": t1_verdict(a.get("g1_hint")),
                "hook_mapping": "", "proof_purpose": "", "note": a.get("g1_hint", ""),
                "threat": a.get("threat", ""), "coupling": a.get("coupling", ""),
                "refs": len(a.get("refs", [])), "tests": len(a.get("tests", [])),
            })
    return out


def load_ext():
    out = []
    for f in sorted((HERE / "ext").glob("*.json")):
        d = json.load(open(f))
        for a in d["atoms"]:
            out.append({
                "id": a["id"], "source": "ext:" + f.stem, "name": a.get("name", ""),
                "statement": a.get("statement", ""), "verdict": a.get("verdict", "unknown"),
                "hook_mapping": a.get("hook_mapping", ""), "proof_purpose": a.get("proof_purpose", ""),
                "note": a.get("g1_design", ""), "threat": "", "coupling": "",
                "evidence_quality": a.get("evidence_quality", ""), "novelty": a.get("novelty", ""),
                "cost": a.get("cost", ""), "refs": len(a.get("refs", [])), "tests": 0,
            })
    return out


def main():
    atoms = load_t1() + load_ext()
    for a in atoms:
        a["component"] = component_of(" ".join([a["id"], a["name"], a["statement"], a.get("note", "")]))
    (HERE / "catalog.json").write_text(json.dumps(atoms, ensure_ascii=False, indent=1))

    by_source = collections.OrderedDict()
    for a in atoms:
        by_source.setdefault(a["source"], collections.Counter())[a["verdict"]] += 1
    verdict_order = ["adopt", "adapt", "research", "reject", "unknown"]

    lines = ["# G1 atom catalog", "",
             "An atom is one small design idea with a verdict. Before G1 was built, its predecessor (T1), five other",
             "projects and one post series were taken apart into atoms. Each atom says what the idea is, how the source implements it, and",
             f"whether G1 adopts it, adapts it, rejects it, or leaves it for research. This file lists all {len(atoms)} of them;",
             "`build_catalog.py` generates it from the JSON files in this directory.", "",
             "How to read a verdict: adopt = used as is; adapt = used with a change; research = interesting but unproven;",
             "reject = does not fit the principles. T1 verdicts come from the `g1_hint` field (keep = adopt, modify = adapt,",
             "drop = reject, experiment = research). The component column is a keyword guess for navigation only.", "",
             "## By source", "", "| Source | " + " | ".join(verdict_order) + " | Total |", "|---|" + "---|" * (len(verdict_order) + 1)]
    for s, c in by_source.items():
        lines.append(f"| {s} | " + " | ".join(str(c.get(v, 0)) for v in verdict_order) + f" | {sum(c.values())} |")
    tot = collections.Counter(a["verdict"] for a in atoms)
    lines.append("| **all** | " + " | ".join(str(tot.get(v, 0)) for v in verdict_order) + f" | {len(atoms)} |")

    comps = collections.OrderedDict()
    for name, _ in COMPONENT_RULES + [("other", "")]:
        comps[name] = [a for a in atoms if a["component"] == name]
    lines += ["", "## By component", "", "| Component | adopt | adapt | research | reject | total |", "|---|---|---|---|---|---|"]
    for name, items in comps.items():
        c = collections.Counter(a["verdict"] for a in items)
        lines.append(f"| {name} | {c.get('adopt', 0)} | {c.get('adapt', 0)} | {c.get('research', 0)} | {c.get('reject', 0)} | {len(items)} |")

    for name, items in comps.items():
        lines += ["", f"## Component: {name} ({len(items)})", ""]
        for v in verdict_order:
            group = [a for a in items if a["verdict"] == v]
            if not group:
                continue
            lines.append(f"### {v} ({len(group)})")
            lines.append("")
            for a in group:
                st = a["statement"].strip().replace("\n", " ")
                if len(st) > 180:
                    st = st[:177] + "..."
                hm = f" [{a['hook_mapping']}]" if a.get("hook_mapping") and a["hook_mapping"] != "n/a" else ""
                lines.append(f"- `{a['id']}` ({a['source']}){hm} {a['name']}: {st}")
            lines.append("")
    (HERE / "CATALOG.md").write_text("\n".join(lines) + "\n")
    print(f"atoms={len(atoms)} sources={len(by_source)}")
    for name, items in comps.items():
        print(f"  {name:12s} {len(items)}")


if __name__ == "__main__":
    main()
