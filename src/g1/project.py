"""Projection text derived from the ledger only (design 9). Byte-safe truncation with an explicit marker.

Text that an agent wrote (an objective, a blocked item, a reason that quotes proposal content) is printed as a
JSON string: quoted, with newlines and control characters escaped, so it can never look like a G1 line (KEV-22).
"""

import json
import unicodedata

PROPOSAL_HINT = ("No active contract. For durable work, write a proposal to {proposals}/<id>.json "
                 "(format: {views}/PROPOSAL_FORMAT.md). G1 validates it before your next step.")


def _visible(text):
    """Escape every character that can end a line or act unseen: control (Cc, which includes U+0085), format
    (Cf: bidirectional overrides, zero-width characters), line separator (U+2028) and paragraph separator (U+2029).
    str.splitlines() and many renderers break lines at more characters than newline."""
    out = []
    for c in text:
        if c != "\t" and unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp"):
            o = ord(c)
            out.append("\\u%04x" % o if o <= 0xFFFF else "\\U%08x" % o)
        else:
            out.append(c)
    return "".join(out)


def quote(text, limit, max_bytes=None):
    """Agent-written text as one quoted, escaped line: at most limit characters, and with max_bytes at most that
    many bytes after escaping (a Korean objective or 160 escaped characters would otherwise take the whole block)."""
    q = _visible(json.dumps(str(text)[:limit], ensure_ascii=False))
    if max_bytes is not None and len(q.encode("utf-8")) > max_bytes:
        cut = q.encode("utf-8")[:max(0, max_bytes - 4)].decode("utf-8", "ignore").rstrip("\\")
        q = cut + '…"'
    return q


def oneline(text):
    """G1's own message that may embed agent text: escaped as above, so it stays one line."""
    return _visible(str(text))


def short_ids(ids, max_bytes):
    """A list of G1 ids (validated ASCII) printed as Python does, cut to about max_bytes with a count of the ids
    left out: a contract may hold 64 checks of 64 characters, and the block must not (R4-09)."""
    out, size = [], 2
    for i, x in enumerate(ids):
        s = repr(str(x))
        if out and size + len(s) + 2 > max_bytes:
            return "[" + ", ".join(out) + f", +{len(ids) - i} more]"
        out.append(s)
        size += len(s) + 2
    return "[" + ", ".join(out) + "]"


def short_json(items, max_bytes, item_chars=100):
    """A JSON list of agent-written strings (paths), each cut to item_chars, the list cut to about max_bytes with a
    count of the items left out (R4-09). ASCII only, so every character is one byte and nothing acts unseen."""
    out, size = [], 2
    for i, it in enumerate(items):
        it = str(it)
        s = json.dumps(it if len(it) <= item_chars else it[:item_chars] + "...")
        if out and size + len(s) + 2 > max_bytes:
            return "[" + ", ".join(out) + f", +{len(items) - i} more]"
        out.append(s)
        size += len(s) + 2
    return "[" + ", ".join(out) + "]"


def _assemble(lines, max_bytes, path=None):
    """lines are (text, priority). Priority 0 lines are always kept, whole: when they alone exceed max_bytes the
    block is them and nothing else, over the budget (each of them is bounded where it is built, R4-09). The others
    are added, lowest priority number first, while the block stays within max_bytes, and printed in their original
    order. So a long objective or a long blocked item never pushes out the scope, the open check, the liveness or
    the resume line (R3-12), and no line of priority 0 is ever cut."""
    chosen = {i for i, (t, p) in enumerate(lines) if p == 0}
    size = sum(len(lines[i][0].encode("utf-8")) + 1 for i in chosen)
    for i, (t, p) in sorted(((i, lp) for i, lp in enumerate(lines) if lp[1] > 0), key=lambda x: (x[1][1], x[0])):
        extra = len(t.encode("utf-8")) + 1
        if size + extra <= max_bytes + 1:
            chosen.add(i)
            size += extra
    return "\n".join(t for i, (t, p) in enumerate(lines) if i in chosen)


def projection(summ, nonce, max_bytes, full_path, session_start=False, variant="default", proposals_dir="", views_dir="",
               lockdown=None):
    """summ is state.summary(). variant 'default' includes the completion-directive lines; 'facts' carries facts
    only. The wording is a measured A/B variable (design section 10), never a guarantee. Lines carry a priority
    (see _assemble): 0 always, then 1, 2, 3 while they fit."""
    big = session_start  # the session-start block has room for what a fresh agent needs once (1,024 bytes)
    lines = [(f"[G1 {nonce}] ledger seq {summ['seq']} head {str(summ['head'])[:12]}", 0)]
    if lockdown:
        lines.append((f"ALERT: integrity lockdown ({oneline(lockdown)[:160]}); mutating tools are refused until the user runs `g1 repair`", 0))
    if summ.get("alert"):
        a = summ["alert"]
        lines.append((f"ALERT: {oneline(a['kind'])} (seq {a['seq']})", 0))
    if summ.get("host_unverified"):
        lines.append(("host contract unverified: completion is withheld until the probe suite passes", 0))
    if summ.get("challenges_waiting"):
        lines.append((f"{summ['challenges_waiting']} confirmed challenge(s) wait for the user's decision (`g1 challenges`); tell the user", 0))
    t = summ.get("active")
    if t is None:
        done = summ.get("last_complete")
        if done:
            lu = done.get("liveness_unknown")
            lines.append((f"last complete: {done['task']} (receipt seq {done['receipt_seq']}"
                          + (f"; liveness unverifiable for {lu} conversation(s)" if lu else "") + ")", 0))
        p = summ.get("last_paused")
        blocked = False
        if p:
            b = p.get("blocked")
            if p["reason"] == "blocked" and b:
                blocked = True
                lines.append((f"paused task: {p['task']} blocked on: {quote(b['item'], 300, 600 if big else 160)}", 0))
                if b.get("options"):
                    lines.append(("options: [" + ", ".join(quote(o, 200, 200 if big else 60) for o in b["options"]) + "]", 2))
                lines.append((f"ask the user; after the answer write {proposals_dir or '<proposals dir>'}/{p['task']}.resume.json "
                              f'{{"task":"{p["task"]}"}} to continue the same contract', 0))
            else:
                lines.append((f"paused task: {p['task']} reason={p['reason']} (new proposal supersedes it)", 0))
        # with a blocked task the resume line is the instruction; the proposal hint is kept only when it fits
        lines.append((PROPOSAL_HINT.format(proposals=proposals_dir or "<proposals dir>", views=views_dir or "<views dir>"), 3 if blocked else 0))
    else:
        v = t["last_vector"]
        lines.append((f"active contract {t['task']} hash {t['contract_hash'][:12]}", 0))
        lines.append((f"objective: {quote(t['objective'], 600 if big else 160, 700 if big else 160)}", 2))
        if v is None:
            lines.append((f"checks {short_ids(t['checks'], 200 if big else 100)}: not yet verified"
                          + ("" if variant == "facts" else "; G1 verifies at the end of the turn"), 0))
        else:
            lines.append((f"checks pass {sum(v)}/{len(v)}; failing: {short_ids(t['failing'], 200 if big else 100)}", 0))
            if t.get("last_reason"):
                lines.append((f"last attempt: {t['last_reason']} (seq {t['last_seq']})", 0))
        if t.get("open_checks") and variant != "no_check_cmd":
            k = t["open_checks"][0]
            lines.append((f"next check {k['id']} must exit 0: {quote(k['cmd'], 600 if big else 160, 700 if big else 120)}", 1))
        lines.append((f"scope: {short_json(t['allowed_paths'], 400 if big else 200)}; "
                      f"pinned oracles: {short_json(t['oracle_files'], 300 if big else 120)}", 0))
        if big and variant != "no_check_cmd":
            if t.get("challenge"):
                lines.append((f"from challenge {t['challenge']['id']}: {quote(t['challenge']['claim'], 300, 400)}", 1))
            if views_dir:
                lines.append((f"full contract: {views_dir}/contract.json", 0))
        if t.get("liveness_unknown"):
            lines.append((f"liveness unverifiable for {t['liveness_unknown']} conversation(s) whose records were deleted", 0))
        if variant != "facts":
            lines.append(("completion is granted only by G1 receipts; your own summary never completes a task", 0))
    return _assemble(lines, max_bytes, full_path)

PROPOSAL_FORMAT = """# G1 proposal format

Write ONE JSON object to `{proposals}/<id>.json`. G1 validates it at your next step and
records the result as `{proposals}/<id>.accepted.json` or `{proposals}/<id>.rejected.json`.
Paths inside the proposal are relative to the workspace root `{root}`.

```json
{
  "task": "fix-median",
  "objective": "median() returns the middle value for odd-length lists",
  "criteria": [{"id": "C1", "text": "tests in tests/test_stats.py pass"}],
  "checks": [
    {"id": "K1", "argv": ["python3", "-m", "pytest", "tests/test_stats.py", "-q"],
     "kind": "must_flip", "covers": ["C1"], "targets": ["src/stats.py"], "timeout_s": 120}
  ],
  "allowed_paths": ["src/"],
  "oracle_files": ["tests/test_stats.py"]
}
```

Rules G1 enforces mechanically:
- Every criterion needs at least one check, and every check must cover a criterion.
- `must_flip` checks must FAIL on the current tree (before your work) and PASS after it.
  `guard` checks must PASS both before and after.
- Every `must_flip` check names `targets`: files inside `allowed_paths`, never oracle files, that the check
  depends on. G1 corrupts them in a scratch copy and the check must then fail.
- `oracle_files` (tests, fixtures, configs the checks read) are pinned by hash: writes to them are refused
  during the task, and they must be unchanged at completion.
- `allowed_paths` is the write scope. Changes outside it block completion.
- A check is one argv run by G1 in a scrubbed environment on a copy of the tree; no shell.
"""
