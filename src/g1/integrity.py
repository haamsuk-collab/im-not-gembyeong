"""Root of trust: manifest of code and hook entries, head anchors, ledger mirror, self-heal (design 7.4-7.6)."""

import json
import os
import shlex

from . import VERSION, canon, ledger as ledger_mod, paths

GROUP = "g1"
# Only events with a proof-bearing purpose are installed. PostToolUse and PostInvocation were observation only.
TIMEOUTS = {"SessionStart": 30, "PreInvocation": 900, "PreToolUse": 20, "Stop": 1800}
EVENTS = ["SessionStart", "PreInvocation", "PreToolUse", "Stop"]


class HostFileError(Exception):
    """A host configuration file that G1 must not rewrite (unreadable or not a JSON object)."""


def bootstrap_command(pyz, pin, event):
    src = (
        "import hashlib,sys\n"
        f"p={pyz!r}\n"
        "try:\n"
        "    h=hashlib.sha256(open(p,\"rb\").read()).hexdigest()\n"
        "except Exception:\n"
        "    h=\"\"\n"
        f"if h!={pin!r}:\n"
        "    sys.exit(3)\n"
        "sys.path.insert(0,p)\n"
        "from g1.__main__ import main\n"
        f"sys.exit(main([\"hook\",{event!r}]))\n"
    )
    # shlex.quote keeps the program intact for `sh -c` whatever characters the path contains
    return f"python3 -I -S -c {shlex.quote(src)}"


def hook_group(pyz, pin, tool_matcher="*"):
    """tool_matcher comes from the host adapter (the core does not know tool names)."""
    g = {}
    for ev in EVENTS:
        handler = {"type": "command", "command": bootstrap_command(pyz, pin, ev), "timeout": TIMEOUTS[ev]}
        if ev in ("PreToolUse", "PostToolUse"):
            g[ev] = [{"matcher": tool_matcher, "hooks": [handler]}]
        else:
            g[ev] = [handler]
    return g


def group_hash(group):
    return canon.sha256_text(canon.dumps(group))


def read_json(path):
    """A G1-owned JSON file (manifest, registry, anchor): strict canonical decoding."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return canon.loads(text) if text.strip() else {}


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    ledger_mod._write_atomic(path, canon.dumps(obj) + "\n", mode=0o600)


def read_host_json(path):
    """A host hooks file, which other tools also write: ordinary JSON (floats and any key order allowed),
    and it must be an object. Raises HostFileError instead of guessing."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        doc = json.loads(text) if text.strip() else {}
    except (OSError, ValueError) as e:
        raise HostFileError(f"{path} is not readable JSON ({e.__class__.__name__}); G1 left it unchanged") from None
    if not isinstance(doc, dict):
        raise HostFileError(f"{path} is not a JSON object; G1 left it unchanged")
    return doc


def write_host_json(path, doc):
    """Foreign entries keep their keys, values and order; the file is re-indented."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    ledger_mod._write_atomic(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n", mode=0o600)


def install_group(hooks_path, group):
    """Add or replace only the G1 group; every other entry keeps its keys, values and order.
    Returns the sha256 of the previous file (None when there was none)."""
    doc = read_host_json(hooks_path)
    backup = None
    if os.path.exists(hooks_path):
        with open(hooks_path, "rb") as f:
            backup = canon.sha256_bytes(f.read())
    doc[GROUP] = group
    write_host_json(hooks_path, doc)
    return backup


def remove_group(hooks_path):
    if not os.path.exists(hooks_path):
        return False
    doc = read_host_json(hooks_path)
    if GROUP not in doc:
        return False
    del doc[GROUP]
    if doc:
        write_host_json(hooks_path, doc)
    else:
        os.unlink(hooks_path)
    return True


def installed_group(hooks_path):
    if not os.path.exists(hooks_path):
        return None
    return read_host_json(hooks_path).get(GROUP)


def load_manifest():
    p = paths.manifest_path()
    if not os.path.exists(p):
        return None
    return read_json(p)


def save_manifest(m):
    write_json(paths.manifest_path(), m)


def make_manifest(pyz_sha, global_hooks_path, global_installed, tool_matcher="*"):
    group = hook_group(paths.pyz_path(), pyz_sha, tool_matcher)
    return {"version": VERSION, "pyz_sha256": pyz_sha, "group": group, "group_sha256": group_hash(group),
            "global_hooks_path": global_hooks_path, "global_installed": bool(global_installed),
            "installed_at": ledger_mod.now_iso()}


def policy_digest(manifest):
    return canon.sha256_text(canon.dumps({"version": manifest["version"], "pyz": manifest["pyz_sha256"], "group": manifest["group_sha256"]}))


def check_group_file(hooks_path, manifest):
    """Return 'ok', 'missing', 'modified' or 'unreadable' for the G1 group in a hooks file."""
    try:
        g = installed_group(hooks_path)
    except HostFileError:
        return "unreadable"
    if g is None:
        return "missing"
    try:
        return "ok" if group_hash(g) == manifest["group_sha256"] else "modified"
    except ValueError:
        return "modified"


def heal_workspace_hooks(root, manifest):
    """With a global root of trust the workspace layer is not used (one layer, half the hook processes).
    A stale workspace G1 group is removed; without a global layer it is kept current. An unreadable
    workspace hooks file is reported and left alone."""
    hp = os.path.join(root, ".agents", "hooks.json")
    status = check_group_file(hp, manifest)
    if status == "unreadable":
        return status
    if manifest.get("global_installed"):
        if status != "missing":
            remove_group(hp)
            return "removed"
        return "ok"
    if status != "ok":
        install_group(hp, manifest["group"])
    return status


# ----- host files (rules, skill) -----
# The host's configuration root comes from the adapter; the core does not name the host.

def host_file_index():
    """Relative paths of the files G1 installs into the host configuration root (g1.host.FILES): rules under
    rules/ and skills under skills/<name>/SKILL.md."""
    from .host import FILES
    return list(FILES)


def host_file_paths(config_root):
    """{relative path: absolute path under the host configuration root}. Keys are the manifest keys."""
    return {rel: os.path.join(config_root, *rel.split("/")) for rel in host_file_index()}


def host_file_texts():
    import pkgutil
    return {rel: pkgutil.get_data("g1.host", rel).decode("utf-8") for rel in host_file_index()}


def install_host_files(config_root):
    """Write every host file; returns {relative path: sha256}."""
    out = {}
    texts = host_file_texts()
    for rel, path in host_file_paths(config_root).items():
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        ledger_mod._write_atomic(path, texts[rel], mode=0o600)
        out[rel] = canon.sha256_text(texts[rel])
    return out


def remove_host_files(config_root):
    removed = []
    for rel, path in host_file_paths(config_root).items():
        if os.path.exists(path):
            os.unlink(path)
            removed.append(path)
        if rel.startswith("skills/"):
            try:
                os.rmdir(os.path.dirname(path))  # the skill's own directory, only when empty
            except OSError:
                pass
    return removed


def heal_host_files(manifest, config_root):
    """Restore any installed host file whose content differs from the manifest. Returns the names restored."""
    want = manifest.get("host_files") or {}
    restored = []
    for name, path in host_file_paths(config_root).items():
        if name not in want:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                cur = canon.sha256_text(f.read())
        except OSError:
            cur = None
        if cur != want[name]:
            text = host_file_texts()[name]
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            ledger_mod._write_atomic(path, text, mode=0o600)
            restored.append(name)
    return restored


# ----- anchors and mirror (design 7.6) -----
# The ledger moves its anchor and mirror inside every commit (ledger.Ledger._commit). The anchor is the head G1
# last wrote; through the hash chain it commits to every earlier record. The mirror is a copy used to restore
# records the workspace lost.

def _read_mirror(path, ledger_id):
    """The mirror's verified prefix and a note: '' when the whole file is a valid chain, otherwise why it stops."""
    out, note = [], ""
    if not os.path.exists(path):
        return out, note
    with open(path, "rb") as f:
        data = f.read()
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    elif lines:
        note = "unterminated last line"
        lines.pop()
    prev = "0" * 64
    for i, raw in enumerate(lines):
        try:
            rec = canon.loads(raw.decode("utf-8"))
            if not isinstance(rec, dict):
                raise ValueError("not an object")
            ledger_mod.check_chain_step(rec, i, prev)
            if i == 0 and rec["data"].get("ledger_id") != ledger_id:
                raise ValueError("genesis of another ledger")
        except (ValueError, ledger_mod.LedgerError) as e:
            return out, f"record {i}: {e}"
        out.append(rec)
        prev = rec["hash"]
    return out, note


def _write_mirror(path, recs):
    ledger_mod._write_atomic(path, "".join(canon.dumps(r) + "\n" for r in recs))


def _write_anchor(head):
    os.makedirs(paths.anchors_dir(), mode=0o700, exist_ok=True)
    ledger_mod._write_atomic(paths.anchor_path(head["ledger_id"]), canon.dumps(head) + "\n")


def _write_witness(root, head):
    wp = paths.witness_path(root)
    os.makedirs(os.path.dirname(wp), mode=0o700, exist_ok=True)
    ledger_mod._write_atomic(wp, canon.dumps({"ledger_id": head["ledger_id"], "seq": head["seq"], "hash": head["hash"],
                                              "root": os.path.realpath(root)}) + "\n", sync=False)


def read_witness(root):
    """The workspace witness (paths.witness_path), or None. An unreadable witness is returned as {"unreadable": True}."""
    wp = paths.witness_path(root)
    if not os.path.exists(wp):
        return None
    try:
        w = read_json(wp)
    except (OSError, ValueError):
        return {"unreadable": True}
    return w if isinstance(w, dict) else {"unreadable": True}


def lost_ledger(root):
    """The witness of a workspace whose ledger files are gone, or None. SessionStart locks such a workspace down
    instead of enrolling it again silently (R3-01); the user restores the ledger from the mirror or forgets it."""
    led = ledger_mod.Ledger(root)
    if led.exists():
        return None
    return read_witness(root)


def forget_workspace(root):
    """The user's decision to start this workspace over: the witness goes, so the next session enrols a new ledger.
    Ledger files still present (a ledger that no longer verifies, R4-01) are moved aside under the workspace's state
    directory, never deleted, so the user can still read them. Returns the directory they went to, or None."""
    led = ledger_mod.Ledger(root)
    moved = None
    for name in (led.path, led.head_path, led.pending_path):
        if os.path.lexists(name):
            if moved is None:
                moved = os.path.join(led.dir, f"forgotten-{ledger_mod.token_hex(6)}")
                os.makedirs(moved, mode=0o700)
            os.replace(name, os.path.join(moved, os.path.basename(name)))
    try:
        os.unlink(paths.witness_path(root))
    except FileNotFoundError:
        pass
    return moved


def _known_ledger_id(led, wit):
    """The id of the ledger that belongs to this workspace: the witness (G1's own record of it) first, then the head
    file. A ledger copied in from another workspace brings its own head file, so the head alone would name the wrong
    mirror (R4-01)."""
    if wit and not wit.get("unreadable") and isinstance(wit.get("ledger_id"), str) and wit["ledger_id"]:
        return wit["ledger_id"]
    if led.exists():
        try:
            lid = led.read_head().get("ledger_id")
        except (OSError, ValueError):
            return None
        return lid if isinstance(lid, str) and lid else None
    return None


def _bound_mirror(mirror, lid, wit):
    """The mirror is G1's copy, written after the anchor in every commit, so it never holds a record the anchor does
    not cover, and its record at the witness's seq is the witness's. A mirror that says more was written by someone
    else: the records beyond the anchor are not restored (P5-03), and a mirror that contradicts the anchor or the
    witness is refused. Returns (mirror, notes)."""
    notes = []
    anchor = None
    ap = paths.anchor_path(lid)
    if os.path.exists(ap):
        try:
            a = read_json(ap)
            if isinstance(a, dict) and a.get("ledger_id") == lid and isinstance(a.get("seq"), int) and a["seq"] >= 0:
                anchor = a
        except (OSError, ValueError):
            pass
        if anchor is None:
            notes.append("the anchor is unreadable; it did not bound the mirror")
    else:
        notes.append("no anchor bounded the mirror")
    if anchor is not None:
        if len(mirror) > anchor["seq"] + 1:
            notes.append(f"{len(mirror) - anchor['seq'] - 1} mirror record(s) beyond the anchor (seq {anchor['seq']}) were not restored: G1 never wrote them")
            mirror = mirror[:anchor["seq"] + 1]
        if len(mirror) == anchor["seq"] + 1 and mirror[-1]["hash"] != anchor.get("hash"):
            raise ValueError(f"the mirror's record at seq {anchor['seq']} is not the one the anchor names; the mirror is not G1's copy")
        if len(mirror) < anchor["seq"] + 1:
            notes.append(f"the mirror ends at seq {len(mirror) - 1} but the anchor names seq {anchor['seq']}: the records after it are lost")
    if wit and not wit.get("unreadable") and isinstance(wit.get("seq"), int) and 0 <= wit["seq"] < len(mirror) \
            and mirror[wit["seq"]]["hash"] != wit.get("hash"):
        raise ValueError(f"the mirror's record at seq {wit['seq']} is not the one the witness names; the mirror is not G1's copy")
    return mirror, notes


def restore_ledger(root):
    """The user's decision after a loss (`g1 repair --restore`): rebuild the ledger from the mirror of the ledger the
    witness names (or, without a witness, the current head), bounded by the anchor (_bound_mirror). The current
    ledger's readable records, if any, must be a prefix of the mirror: a ledger that stops reading at some record (a
    corrupt byte, R4-01) is restored from the record it stops at. Returns (head, notes), the notes being what the
    user should know (records not restored, a missing anchor). Raises ValueError when there is nothing usable to
    restore from."""
    led = ledger_mod.Ledger(root)
    wit = read_witness(root)
    lid = _known_ledger_id(led, wit)
    if lid is None:
        raise ValueError("no ledger id is known for this workspace (no readable witness and no readable head)")
    mirror, note = _read_mirror(paths.mirror_path(lid), lid)
    if not mirror:
        raise ValueError(f"the mirror of ledger {lid[:12]} holds no usable record" + (f" ({note})" if note else ""))
    mirror, notes = _bound_mirror(mirror, lid, wit)
    os.makedirs(led.dir, mode=0o700, exist_ok=True)
    with led.lock():
        if led.exists():
            try:
                led._recover()
            except (ledger_mod.LedgerError, ValueError, OSError):
                # a ledger past recovery (a corrupt record, head file or journal) is restored from its readable
                # prefix; the mirror is the source, and the head, anchor and witness are rewritten below
                pass
            try:
                os.unlink(led.pending_path)  # a journal that could not be applied belongs to the ledger being replaced
            except FileNotFoundError:
                pass
            current, cnote = _read_mirror(led.path, lid)
            if len(current) > len(mirror) or any(current[i]["hash"] != mirror[i]["hash"] for i in range(len(current))):
                raise ValueError(f"the current ledger's readable records ({len(current)}"
                                 + (f", then {cnote}" if cnote else "") + f") are not a prefix of the mirror ({len(mirror)} records); "
                                 "accept the ledger, or forget it")
        ledger_mod._write_atomic(led.path, "".join(canon.dumps(r) + "\n" for r in mirror))
        last = mirror[-1]
        head = {"ledger_id": lid, "seq": last["seq"], "hash": last["hash"]}
        ledger_mod._write_atomic(led.head_path, canon.dumps(head))
        led.verify()
        _write_anchor(head)
        _write_witness(root, head)
        if note or notes:
            _write_mirror(paths.mirror_path(lid), mirror)  # the mirror is G1's copy again: exactly the restored records
        return head, notes


def check_anchor(led):
    """check_anchor_records without the records."""
    status, detail, _ = check_anchor_records(led)
    return status, detail


def check_anchor_records(led):
    """Compare the workspace ledger with its anchor and its witness; restore lost records from the mirror.
    Runs under the ledger lock after crash recovery, so a G1 commit is never seen half done.
    Returns (status, detail, records), status in ok | repaired | missing | diverged, records the verified chain when
    the ledger is trusted (so the caller folds state without a second chain walk) and None otherwise. Diverged means
    the ledger is not the one G1 last wrote (records added, changed, removed or replaced outside G1); the caller locks
    the workspace down and the user decides with `g1 repair`."""
    with led.lock():
        led._recover()
        recs = led.verify()
        head = led.read_head()
        lid = head["ledger_id"]
        ap, mp = paths.anchor_path(lid), paths.mirror_path(lid)
        wit = read_witness(led.root)
        if wit is not None and wit.get("unreadable"):
            return "diverged", "the workspace witness is unreadable", None
        if wit is not None and wit.get("ledger_id") != lid:
            # the ledger files were replaced by another ledger (a fresh genesis, or a ledger of another workspace)
            return "diverged", f"the workspace's ledger was replaced: its witness names ledger {str(wit.get('ledger_id'))[:12]}", None
        try:
            anchor = read_json(ap) if os.path.exists(ap) else None
        except ValueError:
            return "diverged", "the anchor file is unreadable", None
        if isinstance(anchor, dict) and anchor.get("ledger_id") == lid and anchor.get("seq") == head["seq"] \
                and anchor.get("hash") == head["hash"]:
            # The common case: the ledger is the one G1 last wrote. Under the lock, after recovery, the file holds
            # exactly the committed records, so its copy must be the same bytes; a byte hash covers every record
            # without parsing them (a corrupt middle line of the mirror is found here too).
            if wit is None:
                _write_witness(led.root, head)  # a ledger from before the witness existed
            try:
                same = os.path.getsize(mp) == os.path.getsize(led.path) and canon.sha256_file(mp) == canon.sha256_file(led.path)
            except OSError:
                same = False
            if not same:
                _write_mirror(mp, recs)
                return "ok", "mirror rewritten from the anchored ledger", recs
            return "ok", "", recs
        if anchor is None:
            mirror, note = _read_mirror(mp, lid)
            if head["seq"] == 0 and len(mirror) <= 1 and (wit is None or wit.get("seq") == 0):
                # a ledger with only its genesis record, and no copy or witness that remembers more: anchor it now
                _write_anchor(head)
                _write_witness(led.root, head)
                _write_mirror(mp, recs)
                return "missing", "anchor and mirror created", recs
            # G1 writes the anchor inside every commit; a ledger with records and no anchor lost its witness,
            # and a ledger cut back to its genesis record is contradicted by the mirror or the witness (R3-02)
            if head["seq"] == 0:
                remembered = f"the mirror holds {len(mirror)} records" if len(mirror) > 1 else f"the witness names seq {wit.get('seq')}"
                return "diverged", f"the anchor is missing and the ledger holds only its genesis record, but {remembered}", None
            return "diverged", f"the anchor is missing for a ledger with {head['seq']} records after genesis", None
        mirror, note = _read_mirror(mp, lid)
        if not isinstance(anchor, dict) or anchor.get("ledger_id") != lid or not isinstance(anchor.get("seq"), int):
            return "diverged", "the anchor does not belong to this ledger", None
        a_seq, a_hash = anchor["seq"], anchor.get("hash")
        if head["seq"] < a_seq:
            prefix_ok = len(mirror) > a_seq and mirror[a_seq]["hash"] == a_hash and \
                all(mirror[i]["hash"] == recs[i]["hash"] for i in range(len(recs)))
            if not prefix_ok:
                why = f" (mirror: {note})" if note else ""
                return "diverged", f"the ledger lost the records after seq {head['seq']} and the mirror cannot restore them{why}", None
            restored = mirror[:a_seq + 1]
            ledger_mod._write_atomic(led.path, "".join(canon.dumps(r) + "\n" for r in restored))
            ledger_mod._write_atomic(led.head_path, canon.dumps({"ledger_id": lid, "seq": a_seq, "hash": a_hash}))
            recs = led.verify()
            if len(mirror) != len(restored):
                _write_mirror(mp, restored)
            return "repaired", f"restored {a_seq - head['seq']} records from the mirror", recs
        if a_seq < len(recs) and recs[a_seq]["hash"] == a_hash:
            return "diverged", f"the ledger has {head['seq'] - a_seq} records after seq {a_seq} that G1 did not write", None
        return "diverged", f"the ledger differs from the anchor at or before seq {min(a_seq, head['seq'])}", None


def accept_ledger(led):
    """The user's decision after a divergence (`g1 repair --accept-ledger`): the current ledger, if it is a
    valid chain, becomes the anchored truth; the anchor and the mirror are rewritten from it."""
    with led.lock():
        led._recover()
        recs = led.verify()
        head = led.read_head()
        _write_anchor(head)
        _write_witness(led.root, head)
        _write_mirror(paths.mirror_path(head["ledger_id"]), recs)
        return head
