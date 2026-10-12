"""G1 command line.

  g1 install [--no-global] [--src DIR]   build ~/.g1/g1.pyz and write the hook entries
  g1 uninstall [--purge]                 remove the hook entries (and all G1 data with --purge)
  g1 init [ROOT]                         enrol a workspace (ledger genesis, views, workspace hooks)
  g1 propose ROOT FILE                   validate and register a proposal from the command line
  g1 turn-end [ROOT]                     run the turn-end verification once (what the Stop hook does)
  g1 status [ROOT]                       print the task state
  g1 audit [ROOT]                        verify the full chain, receipts and completions offline
  g1 host-verify                         record the running agy binary as the measured one (after re-running the probes)
  g1 repair [ROOT] [--accept-ledger | --restore | --forget]
                                         show a workspace's integrity state; accept the current ledger, restore it
                                         from G1's mirror, or forget a lost or unreadable one (its files are moved
                                         aside, never deleted); each lifts the lockdown
  g1 challenges [ROOT] [--run [ID ...]]  list challenges (claimed defects); --run runs the checks of the pending
                                         files (all, or the named ids) and records their verdicts
  g1 challenge ROOT ID accept|reject [REASON]   decide a confirmed challenge; accepting makes it a contract
  g1 hook EVENT                          host hook entry point (reads the event payload from stdin)

Every command but `status`, `audit`, `challenges` (listing) and `hook` is a decision of the user: it refuses to run
with the host agent among its ancestor processes, and records the process context it ran from.
"""

import json
import os
import sys

from . import VERSION, canon, paths


def _root(argv, i=0):
    return os.path.realpath(argv[i]) if len(argv) > i else os.getcwd()


def _user_only(what):
    """G1's decisions are the user's. A command started by the host agent (the agent's process among its ancestors)
    is refused; what ran is returned as a short description of the process chain, recorded with the decision.
    A tripwire with a record, not an OS boundary (design 7.7)."""
    from .adapter import agy
    chain = agy.process_chain()
    if chain is None:
        # the guard fails closed: without /proc nothing tells the user's shell from the agent (R4-04)
        print(f"refused: `g1 {what}` is the user's decision, and the process ancestry cannot be read (/proc); "
              "G1 cannot tell the user's shell from the agent here", file=sys.stderr)
        return None
    if agy.agent_in_ancestry(chain):
        print(f"refused: `g1 {what}` is the user's decision and this process was started by the agent "
              f"({' < '.join(n[0] for n in chain[:6] if n)})", file=sys.stderr)
        return None
    return " < ".join((names[0] if names else "?") for names in chain[:6]) or "no parent"


def read_payload(stream):
    """The hook payload: a JSON object, or {} for anything else (empty, not UTF-8, not JSON, not an object)."""
    try:
        raw = stream.read()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        payload = json.loads(text) if text.strip() else {}
    except (ValueError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def cmd_hook(argv):
    from .adapter import agy
    event = argv[0] if argv else ""
    payload = read_payload(getattr(sys.stdin, "buffer", sys.stdin))
    try:
        text = agy.handle(event, payload, os.getcwd())
    except Exception as e:  # authority part fails closed only where the host is fail-closed
        if event == "PreToolUse":
            wps = payload.get("workspacePaths")
            root = wps[0] if isinstance(wps, list) and wps and isinstance(wps[0], str) else None
            if root and os.path.exists(os.path.join(paths.ws_dir(root), "ledger.head.json")):
                text = json.dumps({"decision": "deny", "reason": f"G1 internal error: {e.__class__.__name__}; mutating tools are refused in this G1 workspace"})
            else:
                text = ""
        elif event == "Stop":
            text = json.dumps({"decision": "stop"})
        elif event in ("PostToolUse", "PostInvocation"):
            text = "{}"
        else:
            text = ""
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()
    return 0


def cmd_install(argv):
    from . import install
    if _user_only("install") is None:
        return 3
    with_global = "--no-global" not in argv
    src = None
    if "--src" in argv:
        src = argv[argv.index("--src") + 1]
    if src is None:
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    m = install.install(src, with_global=with_global)
    print(f"G1 {m['version']} installed")
    print(f"  code:   {paths.pyz_path()} sha256 {m['pyz_sha256'][:16]}...")
    print(f"  hooks:  {m['global_hooks_path'] if with_global else '(workspace layer only)'}")
    if m.get("host_files"):
        from . import integrity
        from .adapter import agy
        for p in integrity.host_file_paths(agy.config_root()).values():
            print(f"  host:   {p}")
    print(f"  policy: {m['group_sha256'][:16]}...")
    print("Every workspace is enrolled automatically at its first agy session. Nothing else to do.")
    return 0


def cmd_uninstall(argv):
    from . import install
    if _user_only("uninstall") is None:
        return 3
    removed = install.uninstall(purge="--purge" in argv)
    for r in removed:
        print(f"removed G1 entries from {r}")
    print("G1 uninstalled" + (" and all data removed" if "--purge" in argv else ""))
    return 0


def cmd_init(argv):
    from . import install, workspace
    if _user_only("init") is None:
        return 3
    root = _root(argv)
    ws = workspace.Workspace(root)
    try:
        ws.init()
    except Exception as e:
        print(f"cannot initialise {root}: {e}", file=sys.stderr)
        return 1
    install.register_workspace(root)
    print(f"G1 workspace initialised at {root}")
    return 0


def cmd_propose(argv):
    from . import workspace
    if _user_only("propose") is None:
        return 3
    root, path = _root(argv, 0), argv[1]
    ws = workspace.Workspace(root)
    with open(path, "r", encoding="utf-8") as f:
        prop = canon.loads(f.read())
    ok, info = ws.register(prop)
    print(json.dumps({"accepted": ok, **info}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


def cmd_turn_end(argv):
    from . import workspace
    if _user_only("turn-end") is None:
        return 3
    ws = workspace.Workspace(_root(argv))
    d = ws.turn_end()
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


def cmd_status(argv):
    from . import state as state_mod, workspace
    ws = workspace.Workspace(_root(argv))
    if not ws.enrolled():
        print("not enrolled yet (G1 enrols a workspace at the first agy session; or run: g1 init)")
        return 1
    s = ws.state()
    print(json.dumps({"seq": s["seq"], "head": s["head"], "active": s["active"], "alerts": s["alerts"],
                      "tasks": {k: state_mod.task_view(v) for k, v in s["tasks"].items()}}, ensure_ascii=False, indent=1))
    return 0


def cmd_audit(argv):
    from . import audit
    report = audit.run(_root(argv))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1


def cmd_host_verify(argv):
    from . import install
    if _user_only("host-verify") is None:
        return 3
    fp = install.host_verify()
    print(f"host binary recorded as verified: {fp[:16]}...")
    return 0


def cmd_repair(argv):
    """Show a workspace's integrity state. The user's decisions: --accept-ledger takes the current ledger as truth;
    --restore rebuilds the ledger from G1's mirror (after a loss or a truncation); --forget drops the witness of a
    lost ledger so the next session enrols a new one. Each lifts the lockdown."""
    from . import integrity, workspace
    flags = {a for a in argv if a.startswith("--")}
    unknown = flags - {"--accept-ledger", "--restore", "--forget"}
    if unknown or len(flags) > 1:
        print("usage: g1 repair [ROOT] [--accept-ledger | --restore | --forget]", file=sys.stderr)
        return 2
    root = _root([a for a in argv if not a.startswith("--")])
    ws = workspace.Workspace(root)
    lp = paths.lockdown_path(root)
    held = None
    if os.path.exists(lp):
        with open(lp, encoding="utf-8") as f:
            held = f.read().strip() or "lockdown"
    if not ws.enrolled():
        wit = integrity.read_witness(root)
        if wit is None:
            print("not enrolled")
            return 1
        mirror, note = integrity._read_mirror(paths.mirror_path(str(wit.get("ledger_id"))), str(wit.get("ledger_id")))
        print(json.dumps({"lockdown": held, "ledger": "missing", "witness": wit, "mirror_records": len(mirror),
                          "mirror_note": note}, ensure_ascii=False, indent=1))
        status, detail = "missing", "the ledger files are gone"
    else:
        try:
            status, detail = integrity.check_anchor(ws.ledger)  # writes the witness of a ledger from before witnesses
        except Exception as e:
            status, detail = "unverifiable", f"{e.__class__.__name__}: {e}"
        wit = integrity.read_witness(root)
        print(json.dumps({"lockdown": held, "anchor": status, "detail": detail, "witness": wit}, ensure_ascii=False, indent=1))
    # every state has a way out (R4-01): a readable ledger is accepted or restored; one that no longer reads as a
    # chain, or one whose files are gone, is restored from the mirror or forgotten
    if not flags:
        if not ws.enrolled():
            print("The ledger files are gone. Then: g1 repair ROOT --restore (rebuild it from G1's mirror) or --forget (start over).")
        elif status == "unverifiable":
            print("The ledger does not read as a chain. Then: g1 repair ROOT --restore (rebuild it from G1's mirror, which must "
                  "extend its readable records) or --forget (move it aside and start over).")
        elif held or status == "diverged":
            print("Inspect the ledger (g1 audit). Then: g1 repair ROOT --accept-ledger (the current ledger is the truth) "
                  "or --restore (rebuild it from G1's mirror).")
        return 0 if (not held and status in ("ok", "missing", "repaired") and ws.enrolled()) else 1
    run_by = _user_only("repair")
    if run_by is None:
        return 3
    if "--forget" in flags:
        if ws.enrolled() and status != "unverifiable":
            print("the ledger is present and reads as a chain; --forget is for a lost or unreadable ledger (use --accept-ledger or --restore)")
            return 1
        moved = integrity.forget_workspace(root)
        if os.path.exists(lp):
            os.unlink(lp)
        print("forgotten: the next session enrols a new ledger for this workspace"
              + (f"; the old ledger files were moved to {moved}" if moved else ""))
        return 0
    if "--restore" in flags:
        try:
            head, notes = integrity.restore_ledger(root)
        except ValueError as e:
            print(f"cannot restore: {e}")
            return 1
        if os.path.exists(lp):
            os.unlink(lp)
        ws = workspace.Workspace(root)
        said = ("; " + "; ".join(notes)) if notes else ""
        ws.append("integrity_alert", {"kind": "restored_by_user", "run_by": run_by,
                                      "detail": (f"ledger restored from the mirror at seq {head['seq']} after: {status} {detail}" + said)[:400]})
        print(f"restored: the ledger holds seq 0..{head['seq']} from the mirror; lockdown cleared" + said)
        return 0
    if not ws.enrolled():
        print("the ledger is missing; use --restore or --forget")
        return 1
    if status == "unverifiable":
        print("the ledger itself does not read as a chain; it cannot be accepted (use --restore or --forget)")
        return 1
    head = integrity.accept_ledger(ws.ledger)
    if os.path.exists(lp):
        os.unlink(lp)
    ws.append("integrity_alert", {"kind": "accepted_by_user", "detail": f"anchor reset at seq {head['seq']} after: {status} {detail}"[:300],
                                  "run_by": run_by})
    print(f"accepted: the anchor now names seq {head['seq']}; lockdown cleared")
    return 0


def cmd_challenges(argv):
    """List the challenges of a workspace (design 5.5): the pending files, parsed but not run, and the recorded ones
    with each check's exit code and output tail. With --run, the checks of the pending files (all, or the named ids
    or file names) run first, on the user's decision and with the user's rights: they are code another model wrote
    and nothing confines them, so read their commands first."""
    from . import workspace
    run = "--run" in argv
    before, ids = (argv[:argv.index("--run")], argv[argv.index("--run") + 1:]) if run else (argv, [])
    root = _root(before)
    only = set(ids) if ids else None
    ws = workspace.Workspace(root)
    if not ws.enrolled():
        print("not enrolled")
        return 1
    if run:
        if _user_only("challenges --run") is None:
            return 3
        for note in ws.process_challenges(only=only):
            print(note, file=sys.stderr)
    tasks = ws.state()["tasks"]

    def contract_view(c):
        return {"task": c.get("task"), "task_exists": c.get("task") in tasks, "objective": c.get("objective"),
                "allowed_paths": c.get("allowed_paths"), "oracle_files": c.get("oracle_files"),
                "checks": [{"id": k.get("id"), "argv": k.get("argv"), "targets": k.get("targets", []), "timeout_s": k.get("timeout_s")}
                           for k in (c.get("checks") or []) if isinstance(k, dict)]}
    pending = []
    for p, doc, err in ws.pending_challenge_docs():
        row = {"file": os.path.basename(p)}
        if doc is None or not isinstance(doc, dict):
            row["error"] = err or "not a JSON object"
        else:
            row.update({"id": doc.get("id"), "claim": doc.get("claim"), "by": doc.get("by"),
                        "contract": contract_view(doc.get("contract") or {}) if isinstance(doc.get("contract"), dict) else None})
        pending.append(row)
    recorded = []
    for c in ws.state().get("challenges", {}).values():
        recorded.append({"id": c["id"], "verdict": c["verdict"], "reasons": c.get("reasons") or [], "decision": c["decision"],
                         "decision_reason": c.get("reason"), "run_by": c.get("run_by"), "by": c["by"], "claim": c["claim"],
                         "checks_ran": c.get("baseline") or {}, "contract": contract_view(c.get("contract") or {})})
    print(json.dumps({"pending": pending, "recorded": recorded,
                      "note": "pending files have not run; `g1 challenges ROOT --run [ID ...]` runs their checks with your rights"},
                     ensure_ascii=False, indent=1))
    return 0


def cmd_challenge(argv):
    from . import workspace
    if len(argv) < 3 or argv[2] not in ("accept", "reject"):
        print("usage: g1 challenge ROOT ID accept|reject [REASON]", file=sys.stderr)
        return 2
    run_by = _user_only("challenge")
    if run_by is None:
        return 3
    ws = workspace.Workspace(_root(argv))
    ok, msg = ws.decide_challenge(argv[1], "accepted" if argv[2] == "accept" else "rejected", " ".join(argv[3:]), run_by=run_by)
    print(msg)
    return 0 if ok else 1


COMMANDS = {"hook": cmd_hook, "install": cmd_install, "uninstall": cmd_uninstall, "init": cmd_init,
            "propose": cmd_propose, "turn-end": cmd_turn_end, "status": cmd_status, "audit": cmd_audit,
            "host-verify": cmd_host_verify, "repair": cmd_repair, "challenges": cmd_challenges, "challenge": cmd_challenge}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] == "--version":
        print(VERSION)
        return 0
    fn = COMMANDS.get(argv[0])
    if fn is None:
        print(f"unknown command: {argv[0]}", file=sys.stderr)
        return 2
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
