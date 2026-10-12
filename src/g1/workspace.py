"""Workspace operations: init, proposals, verification at turn end, completion, control (host-neutral)."""

import fcntl
import json
import os
import stat
import time

from . import canon, integrity, ledger as ledger_mod, paths, project, state as state_mod

GONE = ".gone"  # suffix of entries G1 moved out of every pattern it reads


class Workspace:
    def __init__(self, root, manifest=None):
        self.root = os.path.realpath(root)
        self.ledger = ledger_mod.Ledger(self.root)
        self.manifest = manifest if manifest is not None else integrity.load_manifest()
        self._memo = None  # ((seq, hash), records, state) for this process
        self._claims = {}  # running file -> descriptor holding its lock (see _claim)

    # ----- basics -----
    def enrolled(self):
        return self.ledger.exists()

    def policy_digest(self):
        return integrity.policy_digest(self.manifest) if self.manifest else "no-manifest"

    def init(self):
        paths.ensure_dirs(self.root)
        if not self.ledger.exists():
            self.ledger.create({"workspace_id": paths.ws_id(self.root), "root": self.root})
        self.write_views()
        if self.manifest:
            integrity.heal_workspace_hooks(self.root, self.manifest)

    def append(self, event, data, expect_head=None):
        return self._appended(self.ledger.append(event, data, expect_head=expect_head))

    def _appended(self, rec):
        if self._memo and self._memo[0][1] == rec["prev"]:
            recs = self._memo[1] + [rec]
            self._memo = ((rec["seq"], rec["hash"]), recs, state_mod.fold(recs))
        self.write_views()
        return rec

    def state(self):
        """The task state folded from the verified ledger (full chain check). Memoized per head in this process,
        and its summary is cached on disk for the per-call hooks (summary())."""
        head = self.ledger.read_head()
        key = (head.get("seq"), head.get("hash"))
        if self._memo is None or self._memo[0] != key:
            recs = self.ledger.verify()
            self._memo = ((recs[-1]["seq"], recs[-1]["hash"]), recs, state_mod.fold(recs))
        s = self._memo[2]
        self._write_summary(s)
        return s

    # ----- the per-call summary (design 9, F-13) -----
    def _write_summary(self, s):
        p = paths.summary_path(self.root)
        try:
            with open(p, "r", encoding="utf-8") as f:
                cur = canon.loads(f.read())
            if cur.get("seq") == s["seq"] and cur.get("hash") == s["head"]:
                return
        except (OSError, ValueError):
            pass
        try:
            ledger_mod._write_atomic(p, canon.dumps({"seq": s["seq"], "hash": s["head"], "summary": state_mod.summary(s)}), sync=False)
        except OSError:
            pass  # the summary is a cache; summary() falls back to the full fold

    def summary(self):
        """What PreToolUse and PreInvocation need (active scope, projection facts) in O(1): the cached summary
        when it is bound to the current head, otherwise the full fold. Completion never reads it; the Stop hook
        and SessionStart verify the whole chain."""
        c = state_mod.cached_summary(self.root)
        return c if c is not None else state_mod.summary(self.state())

    def write_views(self):
        """Derived files for the agent. Each is written to a new file renamed into place (ledger._write_atomic), so a
        link the agent planted at a view's name is replaced, never followed (R3-07)."""
        try:
            os.makedirs(paths.views_dir(self.root), mode=0o700, exist_ok=True)
            vd = paths.views_dir(self.root)
            ledger_mod._write_atomic(os.path.join(vd, "PROPOSAL_FORMAT.md"),
                                     project.PROPOSAL_FORMAT.replace("{proposals}", paths.proposals_dir(self.root)).replace("{root}", self.root),
                                     sync=False)
            if self.ledger.exists():
                s = self.state()
                view = {"seq": s["seq"], "head": s["head"], "active": s["active"],
                        "tasks": {k: state_mod.task_view(v) for k, v in s["tasks"].items()}}
                ledger_mod._write_atomic(os.path.join(vd, "state.json"), canon.dumps(view) + "\n", sync=False)
                # the active contract in full, for an agent that did not write it (derived; never read back)
                cp = os.path.join(vd, "contract.json")
                t = state_mod.active_task(s)
                if t is None:
                    if os.path.lexists(cp):
                        os.unlink(cp)
                else:
                    doc = {"task": t["task"], "contract_hash": t["contract_hash"], **t["contract"]}
                    ch = (s.get("challenges") or {}).get(t.get("from_challenge") or "")
                    if ch:
                        doc["from_challenge"] = {"id": ch["id"], "claim": ch["claim"], "by": ch["by"]}
                    ledger_mod._write_atomic(cp, json.dumps(doc, ensure_ascii=False, indent=1) + "\n", sync=False)
        except OSError:
            pass

    def check_anchor(self):
        """integrity.check_anchor, keeping the verified records for this process so the state fold that follows
        (Stop, SessionStart) walks the chain once, not twice."""
        status, detail, recs = integrity.check_anchor_records(self.ledger)
        if recs:
            self._memo = ((recs[-1]["seq"], recs[-1]["hash"]), recs, state_mod.fold(recs))
        return status, detail
    # ----- proposals -----
    REPORT_KINDS = ("blocked", "resume")
    RUNNING = ".running.json"
    CLAIM_GRACE_S = 5  # a claim younger than this is never judged dead (its process may not hold the lock yet)
    # a proposal that passes the cheap checks costs a tree copy and its checks (the red baseline); a model call pays
    # for at most this many, the other proposals wait for the next call (P5-03: 30 proposals on a 500-file tree
    # held one PreInvocation for 31 s)
    MAX_BASELINES_PER_CALL = 2

    MAX_DOC_BYTES = 1 << 20  # an agent-written proposal, report or challenge
    _OPEN_FLAGS = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    UNREADABLE = "unreadable: not a regular file G1 may read (a link, a special file, or a file left unreadable)"

    def _why_abandoned(self, path, default):
        """The reason an abandoned entry is answered with: unreadable when it could not even be opened (R4-03)."""
        return self.UNREADABLE if self._claims.get(path) is None else default

    def _hold(self, path):
        """Open path and take its lock without waiting. Returns the descriptor; None when another process holds the
        lock. The open never follows a link and never blocks (a FIFO opens at once and fails later, in _read_doc).
        An entry that cannot be opened (a link, a special file, a file G1 may not read) raises OSError: it is answered
        unread. G1 never changes an entry's mode: a chmod by path would follow a link planted after the check (R4-03,
        P5-02), and a file the agent left unreadable is the agent's own loss, answered and removed."""
        fd = os.open(path, self._OPEN_FLAGS)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        try:
            if os.fstat(fd).st_ino != os.lstat(path).st_ino:  # finished and replaced while we waited
                raise FileNotFoundError(path)
        except OSError:
            os.close(fd)
            raise
        self._claims[path] = fd
        return fd

    def _claim(self, path):
        """Take a pending file for processing: rename it to <name>.running.json and hold its lock until the outcome
        is written (_finish_proposal). The rename is atomic, so two processes never run the same file. The lock tells
        a live run from a dead one: when the host stops a hook at its time limit, the lock goes with the process,
        and the next call finishes the file as not completed instead of starting it again on every call.
        Returns the running path, or None if another process took the file."""
        running = path[:-len(".json")] + self.RUNNING
        try:
            os.rename(path, running)
        except OSError:
            return None
        try:
            return running if self._hold(running) is not None else None
        except OSError:
            # a link (which cannot be locked without following it) or an entry nobody can open: answered, never read
            self._claims[running] = None
            return running
    @classmethod
    def _parse_fd(cls, fd):
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular file")
        data = os.pread(fd, cls.MAX_DOC_BYTES + 1, 0)
        if len(data) > cls.MAX_DOC_BYTES:
            raise ValueError(f"larger than {cls.MAX_DOC_BYTES} bytes")
        return canon.loads(data.decode("utf-8"))

    def _read_doc(self, path):
        """Parse a claimed file through the descriptor G1 holds, never by name again (the agent may swap the name).
        Only a regular file of at most MAX_DOC_BYTES is read."""
        fd = self._claims.get(path)
        if fd is None:
            raise ValueError(self.UNREADABLE[len("unreadable: "):])
        return self._parse_fd(fd)

    @classmethod
    def read_agent_file(cls, path):
        """Parse an agent-written file by name, for a listing: opened without following links, without blocking,
        a regular file of at most MAX_DOC_BYTES. Raises ValueError or OSError."""
        fd = os.open(path, cls._OPEN_FLAGS)
        try:
            return cls._parse_fd(fd)
        finally:
            os.close(fd)
    def _recorded_outcome(self, path, kind):
        """A dead claim whose process stopped after the ledger record and before the answer: the outcome the ledger
        already holds for this file's content, as (verdict, payload), or None. kind: proposal, challenge, blocked
        or resume."""
        from . import contract as contract_mod
        try:
            doc = self._read_doc(path)
            s = self.state()
            if kind == "challenge":
                rec = s.get("challenges", {}).get(doc["id"])
                h = contract_mod.contract_hash(contract_mod.normalize(doc["contract"]))
                if rec and rec.get("contract_hash") == h:
                    return rec["verdict"], {"verdict": rec["verdict"], "seq": rec["seq"], "recovered": True}
            elif kind == "blocked":
                t = s["tasks"].get(doc["task"])
                if t and t["status"] == "paused" and t["paused"] == "blocked" and (t.get("blocked") or {}).get("item") == doc["item"].strip():
                    return "accepted", {"task": t["task"], "kind": "blocked", "recovered": True}
            elif kind == "resume":
                t = s["tasks"].get(doc["task"])
                if t and t["status"] == "active" and s.get("active") == t["task"]:
                    return "accepted", {"task": t["task"], "kind": "resume", "recovered": True}
            else:
                t = s["tasks"].get(doc["task"])
                h = contract_mod.contract_hash(contract_mod.normalize(doc))
                if t and t.get("contract_hash") == h:
                    return "accepted", {"task": t["task"], "contract_hash": h, "recovered": True}
        except Exception:
            return None
        return None
    def _abandoned(self, directory, kind=None, names=None):
        """Running files whose process is gone: older than the grace period and nobody holds their lock. kind
        selects report files (blocked, resume) or, when None, every other running file (proposals, challenges)."""
        out = []
        for name in (self._listing(directory) if names is None else names):
            if not name.endswith(self.RUNNING):
                continue
            p = os.path.join(directory, name)
            base = name[:-len(self.RUNNING)]
            is_report = any(base.endswith("." + k) for k in self.REPORT_KINDS)
            if (kind is None and is_report) or (kind is not None and not base.endswith("." + kind)):
                continue
            try:
                if time.time() - os.lstat(p).st_ctime < self.CLAIM_GRACE_S:
                    continue
            except OSError:
                continue
            try:
                held = self._hold(p)
            except OSError:
                self._claims[p] = None  # a link, or an entry nobody can open: answered, never read
                out.append(p)
                continue
            if held is not None:
                out.append(p)
        return out
    @staticmethod
    def _listing(directory):
        """One sorted listing of an agent directory; every pass over it on the model-call path shares it (a listing
        costs about a millisecond under PRoot)."""
        try:
            return sorted(os.listdir(directory))
        except OSError:
            return []

    def pending_proposals(self, names=None):
        d = paths.proposals_dir(self.root)
        out = []
        for base in (self._listing(d) if names is None else names):
            if not base.endswith(".json") or base.endswith(".accepted.json") or base.endswith(".rejected.json") or base.endswith(self.RUNNING):
                continue
            if any(base.endswith(f".{k}.json") for k in self.REPORT_KINDS):
                continue
            out.append(os.path.join(d, base))
        return out

    def pending_reports(self, names=None):
        d = paths.proposals_dir(self.root)
        names = self._listing(d) if names is None else names
        return [(k, os.path.join(d, base)) for k in self.REPORT_KINDS for base in names if base.endswith(f".{k}.json")]

    def process_reports(self, names=None):
        """Agent reports beside the proposals (design 8, the structured BLOCKED declaration).
        `<task>.blocked.json` pauses the active task with the one item the agent could not confirm, so the
        next session's projection carries the question instead of the agent guessing again.
        `<task>.resume.json` reactivates a task paused by a blocked report; the contract is unchanged."""
        notes = []
        pdir = paths.proposals_dir(self.root)
        names = self._listing(pdir) if names is None else names
        for kind in self.REPORT_KINDS:
            for p in self._abandoned(pdir, kind, names):
                name = os.path.basename(p)[:-len(self.RUNNING)] + ".json"
                done = self._recorded_outcome(p, kind)
                if done:
                    self._finish_proposal(p, *done)
                    notes.append(f"{name}: applied (recorded before G1 stopped)")
                    continue
                why = self._why_abandoned(p, "G1 stopped before the report was applied; write it again")
                self._finish_proposal(p, "rejected", {"reasons": [why]})
                notes.append(f"{name}: rejected: {why}")
        for kind, p0 in self.pending_reports(names):
            p = self._claim(p0)
            if p is None:
                continue
            name = os.path.basename(p0)
            try:
                try:
                    rep = self._read_doc(p)
                    reasons = self._validate_report(kind, rep)
                except Exception as e:
                    reasons = [f"unreadable: {e}"]
                if reasons:
                    self._finish_proposal(p, "rejected", {"reasons": reasons})
                    notes.append(f"{name}: rejected: " + "; ".join(reasons)[:300])
                    continue
                if kind == "blocked":
                    self.append("task_status_changed", {"task": rep["task"], "status": "paused", "reason": "blocked",
                                                        "item": rep["item"].strip(), "why": rep.get("why", ""),
                                                        "options": rep.get("options", [])})
                    notes.append(f"{name}: task {rep['task']} paused, blocked on: {project.quote(rep['item'].strip(), 120)}")
                else:
                    self.append("task_status_changed", {"task": rep["task"], "status": "active", "reason": "resumed"})
                    notes.append(f"{name}: task {rep['task']} is active again; the contract is unchanged")
                self._finish_proposal(p, "accepted", {"task": rep["task"], "kind": kind})
            except Exception as e:  # one bad entry never stops the others or the hook (R3-06)
                notes.append(f"{name}: not processed: {e.__class__.__name__}")
                self._release(p)
        return notes

    def _release(self, path):
        fd = self._claims.pop(path, None)
        if fd is not None:
            os.close(fd)

    def _unclaim(self, running):
        """Give a claimed file back: pending again, for the next call."""
        fd = self._claims.pop(running, None)
        try:
            os.rename(running, running[:-len(self.RUNNING)] + ".json")
        except OSError:
            pass
        if fd is not None:
            os.close(fd)

    def _costs_a_baseline(self, prop):
        """True when registering prop would copy the tree and run its checks: its shape is valid and the state admits it."""
        from . import contract as contract_mod
        try:
            return not contract_mod.validate_shape(prop) and not self._registrable(self.state(), contract_mod.normalize(prop))
        except Exception:
            return False
    def _validate_report(self, kind, rep):
        if not isinstance(rep, dict):
            return ["report must be a JSON object"]
        allowed = {"blocked": {"task", "item", "why", "options"}, "resume": {"task"}}[kind]
        unknown = sorted(set(rep) - allowed)
        if unknown:
            return [f"unknown keys: {unknown}"]
        task = rep.get("task")
        if not isinstance(task, str) or not canon.ID_RE.match(task):
            return ["task must be a task id ([A-Za-z0-9][A-Za-z0-9_-]{0,63})"]
        s = self.state()
        active = state_mod.active_task(s)
        if kind == "blocked":
            if active is None or active["task"] != task:
                return [f"no active contract for task {task}; a blocked report needs an active contract"]
            item = rep.get("item")
            if not isinstance(item, str) or not item.strip() or len(item) > 300:
                return ["item must be a string of 1-300 characters: the one thing you could not confirm"]
            why = rep.get("why", "")
            if not isinstance(why, str) or len(why) > 600:
                return ["why must be a string of at most 600 characters"]
            opts = rep.get("options", [])
            if not isinstance(opts, list) or len(opts) > 5 or any(not isinstance(o, str) or len(o) > 200 for o in opts):
                return ["options must be a list of at most 5 strings of at most 200 characters"]
            return []
        t = s["tasks"].get(task)
        if t is None:
            return [f"unknown task {task}"]
        if t["status"] != "paused" or t["paused"] != "blocked":
            return [f"task {task} is {t['status']} (paused reason: {t['paused']}); only a task paused by a blocked report can resume"]
        if active is not None:
            return [f"a contract is already active: {active['task']}"]
        return []

    # ----- challenges (design 5.5) -----
    CHALLENGE_VERDICTS = ("confirmed", "unproven", "invalid")
    CHALLENGE_CHECK_TIMEOUT_S = 60  # a reproduction is quick; a slower check counts as not showing the defect
    MAX_CHALLENGE_CHECKS = 8        # one defect, a few checks: bounds what one `g1 challenges --run` can cost (R3-22)

    def pending_challenges(self):
        d = paths.challenges_dir(self.root)
        out = []
        for base in self._listing(d):
            if not base.endswith(".json") or base.endswith(self.RUNNING) or any(base.endswith(f".{v}.json") for v in self.CHALLENGE_VERDICTS):
                continue
            out.append(os.path.join(d, base))
        return out

    def pending_challenge_docs(self):
        """Pending challenge files parsed for a listing, without running anything: [(path, doc or None, error)]."""
        out = []
        for p in self.pending_challenges():
            try:
                out.append((p, self.read_agent_file(p), None))
            except (OSError, ValueError) as e:
                out.append((p, None, f"unreadable: {e}"[:200]))
        return out

    def process_challenges(self, only=None):
        """A challenge claims a defect and carries a contract whose must_flip checks show it. G1 runs those checks
        on the current tree: every check failing makes the challenge `confirmed`; any check passing, or running
        longer than CHALLENGE_CHECK_TIMEOUT_S, makes it `unproven`; a malformed challenge is `invalid`. Nothing
        becomes a contract here: a confirmed challenge waits for the user's decision (`g1 challenge accept|reject`),
        because a check proves that a behaviour is absent, not that the reviewer's expectation is right.

        Only `g1 challenges --run` runs this, never a hook: a reviewer's checks never make a working agent wait, and
        the user sees the checks' commands before they run (R3-08). `only` names the challenges to run (file names
        without .json, or ids); None runs every pending file. The real tree is measured before and after the checks:
        a change means a check wrote outside its scratch copy, and the challenge is invalid (R3-08)."""
        from . import contract as contract_mod, snapshot
        notes = []
        for p in self._abandoned(paths.challenges_dir(self.root)):
            done = self._recorded_outcome(p, "challenge")
            if done:
                self._finish_proposal(p, *done)
                notes.append(f"challenge {os.path.basename(p)[:-len(self.RUNNING)]}: {done[0]} (recorded before G1 stopped)")
                continue
            why = self._why_abandoned(p, "G1 stopped before it recorded a verdict; write the file again to retry")
            self._finish_proposal(p, "invalid", {"verdict": "invalid", "reasons": [why]})
            notes.append(f"challenge {os.path.basename(p)[:-len(self.RUNNING)]}: invalid: {why}")
        for p0 in self.pending_challenges():
            fname = os.path.basename(p0)[:-len(".json")]
            if only is not None and fname not in only:
                try:
                    if self.read_agent_file(p0).get("id") not in only:
                        continue
                except (OSError, ValueError, AttributeError):
                    continue
            p = self._claim(p0)
            if p is None:
                continue
            name = os.path.basename(p0)
            try:
                verdict, reasons, rec_data = "invalid", [], {}
                try:
                    ch = self._read_doc(p)
                    reasons = self._validate_challenge(ch)
                except Exception as e:
                    ch, reasons = {}, [f"unreadable: {e}"]
                if not reasons:
                    c = contract_mod.normalize(ch["contract"])
                    capped = dict(c, checks=[dict(k, timeout_s=min(k["timeout_s"], self.CHALLENGE_CHECK_TIMEOUT_S)) for k in c["checks"]])
                    tree_before = snapshot.tree_digest(self.root)
                    try:
                        _, results, why = contract_mod.red_baseline(self.root, capped, paths.scratch_dir())
                    except Exception as e:
                        results, why = {}, [f"the checks could not run: {e}"]
                    tree_after = snapshot.tree_digest(self.root)
                    # every check must have run: a check that could not start proves nothing either way
                    ran = len(results) == len(capped["checks"]) and all(r.get("executed") for r in results.values())
                    if tree_after != tree_before:
                        reasons = ["the workspace changed while the checks ran: a check wrote outside its scratch copy, "
                                   "or the tree was being edited; run again"]
                    elif ran and any(r.get("timed_out") for r in results.values()):
                        verdict, reasons = "unproven", [f"check {k} did not finish within {self.CHALLENGE_CHECK_TIMEOUT_S} s" for k, r in results.items() if r.get("timed_out")]
                    elif ran and all(r.get("verdict") == "fail" for r in results.values()):
                        verdict = "confirmed"
                    elif ran:
                        verdict, reasons = "unproven", [f"check {k} passes on the current tree" for k, r in results.items() if r.get("verdict") != "fail"]
                    else:
                        reasons = why or ["the checks did not run"]
                    # what each check did, so the user can tell a defect from a check that fails for another reason (R3-09)
                    baseline = {k: {"verdict": r["verdict"], "exit": r["exit"], "timed_out": bool(r.get("timed_out")),
                                    "stderr_tail": (r.get("stderr_tail") or "")[-600:], "stdout_tail": (r.get("stdout_tail") or "")[-300:]}
                                for k, r in results.items()}
                    rec_data = {"id": ch["id"], "claim": ch["claim"].strip(), "by": ch.get("by", ""), "verdict": verdict,
                                "contract": c, "contract_hash": contract_mod.contract_hash(c), "baseline": baseline,
                                "tree_digest": tree_before, "reasons": reasons[:10]}
                    self.append("challenge_recorded", rec_data)
                self._finish_proposal(p, verdict, {"verdict": verdict, "reasons": reasons[:10], **({"seq": self.state()["seq"]} if rec_data else {})})
                label = ch.get("id", name) if isinstance(ch, dict) else name
                notes.append(f"challenge {label}: {verdict}" + (f": {'; '.join(reasons)[:200]}" if reasons else ""))
            except Exception as e:  # one bad entry never stops the others (R3-06)
                notes.append(f"challenge {name}: not processed: {e.__class__.__name__}")
                self._release(p)
        return notes
    def _validate_challenge(self, ch):
        from . import contract as contract_mod
        if not isinstance(ch, dict):
            return ["a challenge must be a JSON object"]
        unknown = sorted(set(ch) - {"id", "claim", "contract", "by"})
        if unknown:
            return [f"unknown keys: {unknown}"]
        cid = ch.get("id")
        if not isinstance(cid, str) or not contract_mod.ID_RE.match(cid):
            return ["id must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}"]
        if cid in self.state().get("challenges", {}):
            return [f"challenge {cid} was already recorded; use a new id"]
        claim = ch.get("claim")
        if not isinstance(claim, str) or not claim.strip() or len(claim) > contract_mod.MAX_TEXT:
            return [f"claim must be one statement of at most {contract_mod.MAX_TEXT} characters"]
        if not isinstance(ch.get("by", ""), str) or len(ch.get("by", "")) > 80:
            return ["by must be a short string (the reviewer's model)"]
        reasons = contract_mod.validate_shape(ch.get("contract"))
        if reasons:
            return reasons
        if any(k.get("kind") != "must_flip" for k in ch["contract"]["checks"]):
            return ["every check of a challenge is must_flip: it fails now because of the defect, and passes once fixed"]
        if len(ch["contract"]["checks"]) > self.MAX_CHALLENGE_CHECKS:
            return [f"a challenge shows one defect with at most {self.MAX_CHALLENGE_CHECKS} checks"]
        if ch["contract"]["task"] in self.state()["tasks"]:
            # a challenge never replaces a task the user already has (a paused one would be superseded with a scope
            # the user never saw, R3-10); it proposes a new one
            return [f"task {ch['contract']['task']} already exists in this workspace; a challenge names a new task id"]
        return []

    def decide_challenge(self, cid, decision, reason="", run_by=None):
        """The user's decision on a confirmed challenge. Accepting prepares the contract (the red baseline runs again
        on the tree as it is now) and then records the acceptance and the contract as one contract_registered record:
        a contract that cannot be registered leaves the decision open instead of spending it (R3-09), and no crash
        can record the one without the other (R4-02). A rejection is a challenge_decided record. run_by, when given,
        is the process context the command line measured, recorded with the decision. Returns (ok, message)."""
        s = self.state()
        ch = s.get("challenges", {}).get(cid)
        if ch is None:
            return False, f"no recorded challenge {cid}; `g1 challenges --run` runs the checks of new challenge files and records them"
        if ch["decision"] is not None:
            return False, f"challenge {cid} was already {ch['decision']}"
        extra = {"run_by": run_by} if run_by else {}
        if decision == "rejected":
            if not reason.strip():
                return False, "a rejection needs a reason"
            self.append("challenge_decided", {"id": cid, "decision": "rejected", "reason": reason.strip()[:300], **extra})
            return True, f"challenge {cid} rejected"
        if ch["verdict"] != "confirmed":
            return False, f"challenge {cid} is {ch['verdict']}; only a confirmed challenge can be accepted"
        active = state_mod.active_task(s)
        if active is not None:
            return False, f"contract {active['task']} is active; it must complete or be paused first"
        if ch["contract"]["task"] in s["tasks"]:
            return False, f"task {ch['contract']['task']} already exists; the challenge cannot replace it"
        prop = {k: ch["contract"][k] for k in ("task", "objective", "criteria", "allowed_paths", "oracle_files")}
        prop["checks"] = [{k: v for k, v in chk.items()} for chk in ch["contract"]["checks"]]
        if ch["contract"].get("depends_on"):
            prop["depends_on"] = ch["contract"]["depends_on"]
        ok, info = self._prepare_contract(prop)
        if not ok:
            return False, f"challenge {cid} stays open; its contract cannot be registered now: " + "; ".join(info["reasons"])[:400]
        decided = {"reason": reason.strip()[:300], **extra}
        ok, info = self._commit_contract(info, from_challenge=cid, decision=decided)
        if not ok:
            return False, f"challenge {cid} stays open: " + "; ".join(info["reasons"])[:400]
        return True, f"challenge {cid} accepted as contract {info['task']} (seq {info['seq']})"
    def _finish_proposal(self, path, verdict, payload):
        """Write the answer beside the file, remove the claimed entry, then release its lock. The answer goes to a
        new file renamed into place: an entry the agent left at the answer's name is replaced, never followed, and a
        directory there is moved aside first (R3-06). A claimed entry that is a directory is moved under a unique
        name, so it is never seen again (R3-21)."""
        base = path[:-len(self.RUNNING)] if path.endswith(self.RUNNING) else path[:-len(".json")]
        target = f"{base}.{verdict}.json"
        try:
            try:
                if os.path.isdir(target) and not os.path.islink(target):
                    os.replace(target, f"{target}{GONE}.{ledger_mod.token_hex(6)}")
            except OSError:
                pass
            tmp = f"{target}.{ledger_mod.token_hex(6)}.tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(canon.dumps(payload) + "\n")
                os.replace(tmp, target)
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            try:
                os.unlink(path)
            except OSError:  # a directory: move it out of every pattern G1 reads, under a name nobody can plant
                try:
                    os.replace(path, f"{base}{GONE}.{ledger_mod.token_hex(6)}")
                except OSError:
                    pass
        finally:
            fd = self._claims.pop(path, None)
            if fd is not None:
                os.close(fd)
    def process_proposals(self):
        """Apply every pending report, then validate every pending proposal. Returns one-line outcomes.
        Challenges are not processed here: only `g1 challenges` runs them (process_challenges)."""
        names = self._listing(paths.proposals_dir(self.root))
        notes = self.process_reports(names)
        for p in self._abandoned(paths.proposals_dir(self.root), None, names):
            done = self._recorded_outcome(p, "proposal")
            if done:
                self._finish_proposal(p, *done)
                notes.append(f"proposal {os.path.basename(p)[:-len(self.RUNNING)]}.json: accepted as contract {done[1]['task']} "
                             f"(recorded before G1 stopped)")
                continue
            why = self._why_abandoned(p, "G1 stopped before the validation finished (the host ends a hook at its time limit); "
                                         "write the proposal again, with faster checks if they are slow")
            self._finish_proposal(p, "rejected", {"reasons": [why]})
            notes.append(f"proposal {os.path.basename(p)[:-len(self.RUNNING)]}.json: rejected: {why}")
        baselines, deferred = 0, 0
        for p0 in self.pending_proposals(names):
            p = self._claim(p0)
            if p is None:
                continue
            name = os.path.basename(p0)
            try:
                prop = self._read_doc(p)
            except Exception as e:
                self._finish_proposal(p, "rejected", {"reasons": [f"unreadable: {e}"]})
                notes.append(f"proposal {name}: rejected: unreadable: {e}"[:300])
                continue
            costly = self._costs_a_baseline(prop)
            if costly and baselines >= self.MAX_BASELINES_PER_CALL:
                self._unclaim(p)
                deferred += 1
                continue
            baselines += costly
            ok, info = self.register(prop)
            if ok:
                self._finish_proposal(p, "accepted", info)
                notes.append(f"proposal {name}: accepted as contract {info['task']} (hash {info['contract_hash'][:12]})")
            else:
                self._finish_proposal(p, "rejected", info)
                notes.append(f"proposal {name}: rejected: " + "; ".join(info["reasons"])[:400])
        if deferred:
            notes.append(f"{deferred} proposal(s) wait for the next model call: at most {self.MAX_BASELINES_PER_CALL} red baselines run per call")
        return notes

    def register(self, prop, from_challenge=None):
        """Validate a proposal, run its red baseline and record the contract. Returns (ok, info)."""
        ok, info = self._prepare_contract(prop)
        if not ok:
            return False, info
        return self._commit_contract(info, from_challenge=from_challenge)

    def _registrable(self, s, c):
        """Why the contract cannot be registered in state s, as a list of reasons (empty when it can)."""
        active = state_mod.active_task(s)
        if active is not None:
            return [f"a contract is already active: {active['task']}; it must complete or be superseded first"]
        if c["task"] in s["tasks"] and s["tasks"][c["task"]]["status"] in ("complete",):
            return [f"task {c['task']} is already complete; use a new task id"]
        for d in c["depends_on"]:
            dep = s["tasks"].get(d)
            if dep is None:
                return [f"unknown dependency {d}"]
            if dep["status"] != "complete":
                return [f"dependency {d} has no completion receipt (status {dep['status']})"]
        return []

    def _prepare_contract(self, prop):
        """Everything that needs no lock: shape, state, oracle pins, executable pins, the red baseline and the base
        manifest. Returns (ok, info); on success info carries what _commit_contract records."""
        from . import contract as contract_mod, snapshot
        reasons = contract_mod.validate_shape(prop)
        if reasons:
            return False, {"reasons": reasons}
        c = contract_mod.normalize(prop)
        reasons = self._registrable(self.state(), c)
        if reasons:
            return False, {"reasons": reasons}
        oracles, missing = contract_mod.pin_oracles(self.root, c)
        if missing:
            return False, {"reasons": [f"oracle files missing: {missing}"]}
        try:
            exec_pins = contract_mod.exec_hashes(c)
        except Exception as e:
            return False, {"reasons": [f"executable resolution failed: {e}"]}
        try:
            ok, base_results, why = contract_mod.red_baseline(self.root, c, paths.scratch_dir())
        except Exception as e:
            return False, {"reasons": [f"baseline could not run: {e}"]}
        if not ok:
            return False, {"reasons": ["red baseline failed"] + why, "baseline": base_results}
        man = snapshot.manifest(self.root)
        return True, {"contract": c, "oracle_hashes": oracles, "exec_hashes": exec_pins, "manifest": man,
                      "tree_digest": snapshot.digest(man),
                      "baseline": {k: {"verdict": v["verdict"], "exit": v["exit"]} for k, v in base_results.items()}}

    def _commit_contract(self, prepared, from_challenge=None, decision=None):
        """Record a prepared contract under one lock hold, re-checking the state at the current head: the active
        task, dependencies, and (for a challenge) that the challenge is still open and its task id still new. An
        acceptance (decision: reason and run_by) travels inside the contract_registered record itself: one record,
        so no crash between two records can leave a challenge accepted without its contract (R3-09, R4-02); the
        state fold reads the decision from that record."""
        from . import contract as contract_mod
        c = prepared["contract"]
        with self.ledger.lock():
            self.ledger._recover()
            s = self.state()
            reasons = self._registrable(s, c)
            if from_challenge is not None:
                ch = s.get("challenges", {}).get(from_challenge)
                if ch is None or ch["decision"] is not None:
                    reasons = reasons or [f"challenge {from_challenge} is no longer open"]
                elif c["task"] in s["tasks"]:
                    reasons = reasons or [f"task {c['task']} already exists; the challenge cannot replace it"]
            if reasons:
                return False, {"reasons": reasons}
            os.makedirs(paths.evidence_dir(self.root), mode=0o700, exist_ok=True)
            ledger_mod._write_atomic(os.path.join(paths.evidence_dir(self.root), f"base-{c['task']}.json"),
                                     canon.dumps(prepared["manifest"]))
            ch_hash = contract_mod.contract_hash(c)
            # supersede a paused task with the same id
            prev = s["tasks"].get(c["task"])
            if prev is not None and prev["status"] in ("paused", "active"):
                self._appended(self.ledger.append_held("contract_superseded", {"task": c["task"], "reason": "new proposal",
                                                                               "old_hash": prev["contract_hash"]}))
            rec = self._appended(self.ledger.append_held("contract_registered", {
                "task": c["task"], "contract": c, "contract_hash": ch_hash, "tree_digest": prepared["tree_digest"],
                "oracle_hashes": prepared["oracle_hashes"], "exec_hashes": prepared["exec_hashes"],
                "policy_digest": self.policy_digest(), "baseline": prepared["baseline"],
                **({"from_challenge": from_challenge, "decision": decision or {}} if from_challenge else {}),
            }))
        return True, {"task": c["task"], "contract_hash": ch_hash, "seq": rec["seq"], "baseline": rec["data"]["baseline"]}
    # ----- turn end -----
    def turn_end(self, gap=0, budget=None, liveness_unknown=0):
        """Verify the active task, decide completion, decide continuation.
        Returns {"decision": stop|continue, "reason": str, "terminal": str, "task": id|None}."""
        try:
            return self._turn_end(gap, budget, liveness_unknown)
        finally:
            try:
                self.compact_evidence()
            except OSError:
                pass

    def _turn_end(self, gap, budget, liveness_unknown=0):
        from . import complete as complete_mod, control, snapshot, verify
        s = self.state()
        t = state_mod.active_task(s)
        if t is None:
            return {"decision": "stop", "reason": "", "terminal": "no_active_task", "task": None}
        last = state_mod.last_result(t)
        current_td = snapshot.tree_digest(self.root)
        if last is not None and last["data"].get("tree_digest") == current_td and last["event"] == "verification_failed" \
                and last["data"].get("reason") == "checks_failed":
            self.append("task_status_changed", {"task": t["task"], "status": "paused", "reason": "no_change",
                                                "last_receipt_seq": last["seq"]})
            return {"decision": "stop", "reason": "", "terminal": "no_change", "task": t["task"]}
        if s.get("host_unverified"):
            return {"decision": "stop", "reason": "", "terminal": "host_unverified", "task": t["task"]}
        ev, data = verify.run_attempt(self.root, t, self.policy_digest(), gap=gap, liveness_unknown=liveness_unknown)
        self.append("verification_started", {"task": t["task"], "attempt": data["attempt"], "tree_digest": data.get("tree_digest")})
        rec = self.append(ev, data)
        s = self.state()
        t = s["tasks"][t["task"]]
        if ev == "verification_succeeded":
            concurrent = {"decision": "stop", "reason": "", "terminal": "concurrent_change", "task": t["task"]}
            done = None
            # One lock hold: the tree is measured, approved, measured again, and the completion is written. A write to
            # the tree after the second measurement happens after the completion; nothing can freeze a filesystem.
            with self.ledger.lock():
                self.ledger._recover()
                if self.ledger.read_head()["hash"] != rec["hash"]:
                    return concurrent  # another G1 writer appended after the receipt: decide next turn
                td_now = snapshot.tree_digest(self.root)
                oracles_now = snapshot.file_hashes(self.root, t["contract"]["oracle_files"])
                ok, reasons = complete_mod.approve(t, data, td_now, oracles_now, self.policy_digest())
                if ok:
                    if snapshot.tree_digest(self.root) != data["tree_digest"]:
                        return concurrent  # the tree changed while the completion was being decided
                    done = self.ledger.append_held("task_status_changed", complete_mod.completion_data(t, rec),
                                                   expect_head=rec["hash"])
                    self._appended(done)
                    # measured once more after the record: a write in the microseconds between the second
                    # measurement and the append is not prevented, but it is recorded and shown (R3-20)
                    after = snapshot.tree_digest(self.root)
                    if after != data["tree_digest"]:
                        self._appended(self.ledger.append_held("integrity_alert", {
                            "kind": "post_completion_change", "task": t["task"], "receipt_seq": rec["seq"],
                            "detail": f"the tree changed while the completion of {t['task']} was being written; "
                                      f"its receipt binds {data['tree_digest'][:12]}, the tree is now {after[:12]}"}))
            if done is not None:
                return {"decision": "stop", "reason": "", "terminal": "complete", "task": t["task"]}
            self.append("task_status_changed", {"task": t["task"], "status": "paused", "reason": "completion_refused", "detail": reasons[:5]})
            return {"decision": "stop", "reason": "", "terminal": "completion_refused", "task": t["task"]}
        d = control.decide(t, ev, data, budget=budget if budget is not None else control.DEFAULT_BUDGET)
        if d["decision"] == "continue":
            self.append("continuation_issued", {"task": t["task"], "n": t["continuations"] + 1, "attempt": data["attempt"]})
        else:
            self.append("task_status_changed", {"task": t["task"], "status": "paused", "reason": d["terminal"],
                                                "last_receipt_seq": rec["seq"]})
        d["task"] = t["task"]
        return d

    # ----- storage (design 4.4, tier B) -----
    KEEP_ATTEMPTS = 3

    def compact_evidence(self):
        """Keep evidence bytes for completion-bound receipts and the last attempts of each task;
        every other attempt directory is removed. The ledger (tier A) keeps digests and verdicts, so
        the facts stay provable; only the bulk text goes. Returns the number of directories removed."""
        s = self.state()
        keep = set()
        for t in s["tasks"].values():
            if t["completion"]:
                for a in t["attempts"]:
                    r = a["result"]
                    if r and r["seq"] == t["completion"]["receipt_seq"]:
                        keep.add(a["attempt"])
            for a in t["attempts"][-self.KEEP_ATTEMPTS:]:
                keep.add(a["attempt"])
        removed = 0
        ed = paths.evidence_dir(self.root)
        if not os.path.isdir(ed):
            return 0
        for name in os.listdir(ed):
            p = os.path.join(ed, name)
            if os.path.isdir(p) and name not in keep:
                import shutil
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        return removed

    # ----- views -----
    def config(self):
        """Workspace configuration under G1's protected directory (written by G1 tools, not by the agent)."""
        p = os.path.join(paths.ws_dir(self.root), "config.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return canon.loads(f.read())
        except (OSError, canon.CanonError):
            return {}

    def projection(self, nonce, max_bytes, session_start=False):
        summ = self.summary()
        variant = self.config().get("projection_variant", "default")
        lockdown = None
        lp = paths.lockdown_path(self.root)
        if os.path.exists(lp):
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    lockdown = f.read().strip() or "integrity alert"
            except OSError:
                lockdown = "integrity alert"
        return project.projection(summ, nonce, max_bytes, os.path.join(paths.views_dir(self.root), "state.json"), session_start, variant,
                                  proposals_dir=paths.proposals_dir(self.root), views_dir=paths.views_dir(self.root),
                                  lockdown=lockdown)
