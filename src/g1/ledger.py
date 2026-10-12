"""Hash-chained, append-only ledger with a head anchor, a write-ahead journal and a lock.

Files under the workspace's state directory (paths.ws_dir): ledger.jsonl, ledger.head.json,
ledger.pending.json, ledger.lock. Outside it, under G1's home: anchors/<ledger_id>.head (the head
G1 last committed) and mirror/<ledger_id>.jsonl (a copy of every record).
Every record: {"schema", "seq", "prev", "ts", "event", "data", "hash"} where
hash = domain_hash("g1-record-v1", record without "hash").

Commit order, all under the lock: journal the record, append it, move the head, move the anchor,
append it to the mirror, clear the journal. Recovery finishes an interrupted commit from the journal,
so whenever no journal is pending the head, the anchor and the mirror's last record are the same record.
A ledger whose head differs from its anchor was changed outside G1 (integrity.check_anchor).
"""

import fcntl
import os
import time

from . import RECORD_SCHEMA, canon

RECORD_DOMAIN = "g1-record-v1"
EVENTS = {
    "genesis", "contract_registered", "contract_superseded", "contract_invalidated",
    "verification_started", "verification_succeeded", "verification_failed",
    "continuation_issued", "task_status_changed", "host_contract_observed",
    "integrity_alert", "checkpoint", "challenge_recorded", "challenge_decided",
}
LOCK_TIMEOUT_S = 10.0


class LedgerError(Exception):
    pass


class ConflictError(LedgerError):
    pass


def now_iso():
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int((t % 1) * 1_000_000):06d}Z"


def token_hex(n):
    return os.urandom(n).hex()


def record_hash(rec):
    body = {k: v for k, v in rec.items() if k != "hash"}
    return canon.domain_hash(RECORD_DOMAIN, body)


def _write_atomic(path, text, mode=0o600, sync=True):
    """Write text to a new file and rename it into place: a reader sees the old or the new content, never a mix,
    and a link planted at the name is replaced, never followed. sync=False skips the fsync, for derived files
    (views, the witness) whose loss to a crash costs nothing: the next write recreates them."""
    tmp = f"{path}.tmp.{os.getpid()}.{token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            if sync:
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    dfd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _append_bytes(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def last_line(path):
    """(last complete line, unterminated tail) of a file, read from the end. (None, b"") for an empty file."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return None, b""
    try:
        pos = os.fstat(fd).st_size
        buf, block = b"", 65536
        while pos > 0 and buf.count(b"\n") < 2:
            step = min(block, pos)
            pos -= step
            os.lseek(fd, pos, os.SEEK_SET)
            chunk = b""
            while len(chunk) < step:
                part = os.read(fd, step - len(chunk))
                if not part:
                    break
                chunk += part
            buf = chunk + buf
            block *= 2
    finally:
        os.close(fd)
    nl = buf.rfind(b"\n")
    if nl < 0:
        return None, buf
    prev = buf.rfind(b"\n", 0, nl)
    return buf[prev + 1:nl], buf[nl + 1:]


def check_chain_step(rec, seq, prev):
    """Raise LedgerError unless rec is record number `seq` of a chain whose previous hash is `prev`."""
    if rec.get("schema") != RECORD_SCHEMA:
        raise LedgerError(f"unknown record schema at seq {rec.get('seq')}")
    if rec.get("seq") != seq or rec.get("prev") != prev:
        raise LedgerError(f"chain break at seq {rec.get('seq')}")
    if rec.get("hash") != record_hash(rec):
        raise LedgerError(f"hash mismatch at seq {rec.get('seq')}")
    if rec.get("event") not in EVENTS:
        raise LedgerError(f"unknown event at seq {rec.get('seq')}: {rec.get('event')}")
    if not isinstance(rec.get("data"), dict):
        raise LedgerError(f"record data is not an object at seq {rec.get('seq')}")


class Ledger:
    def __init__(self, root):
        from . import paths
        self.root = os.path.realpath(root)
        self.dir = paths.ws_dir(self.root)
        self.path = os.path.join(self.dir, "ledger.jsonl")
        self.head_path = os.path.join(self.dir, "ledger.head.json")
        self.pending_path = os.path.join(self.dir, "ledger.pending.json")
        self.lock_path = os.path.join(self.dir, "ledger.lock")

    # ----- locking -----
    class _Lock:
        def __init__(self, ledger):
            self.ledger = ledger
            self.fd = None

        def __enter__(self):
            deadline = time.monotonic() + LOCK_TIMEOUT_S
            while True:
                fd = os.open(self.ledger.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(fd)
                    if time.monotonic() > deadline:
                        raise LedgerError("ledger lock timeout")
                    time.sleep(0.05)
                    continue
                # inode re-check: the lock file must still be the one on disk
                try:
                    st_fd = os.fstat(fd)
                    st_path = os.stat(self.ledger.lock_path)
                except FileNotFoundError:
                    os.close(fd)
                    continue
                if (st_fd.st_ino, st_fd.st_dev) != (st_path.st_ino, st_path.st_dev):
                    os.close(fd)
                    continue
                self.fd = fd
                return self

        def __exit__(self, *exc):
            if self.fd is not None:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
                self.fd = None

    def lock(self):
        return Ledger._Lock(self)

    # ----- creation -----
    def exists(self):
        return os.path.exists(self.path) and os.path.exists(self.head_path)

    def create(self, extra=None):
        from . import paths
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        if self.exists():
            raise LedgerError("ledger already exists")
        if os.path.exists(paths.witness_path(self.root)):
            raise LedgerError("this workspace already had a ledger (its witness remains); restore or forget it with g1 repair")
        with self.lock():
            self._recover()
            if self.exists():
                raise LedgerError("ledger already exists")
            data = {"ledger_id": token_hex(16), "version": RECORD_SCHEMA}
            if extra:
                data.update(extra)
            rec = self._make(0, "0" * 64, "genesis", data)
            self._commit(rec)
            return rec

    # ----- reading -----
    def read_head(self):
        with open(self.head_path, "r", encoding="utf-8") as f:
            return canon.loads(f.read())

    def records(self, stop_seq=None):
        """Yield records while verifying the chain. Raises on any mismatch, including a line that is not
        one complete record. With stop_seq, reading ends at that record, so a commit in progress after
        it (an append whose head has not moved yet) is not read."""
        prev = "0" * 64
        seq = 0
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):
                    raise LedgerError(f"unterminated record after seq {seq - 1}")
                line = line.rstrip("\n")
                if not line:
                    raise LedgerError(f"empty line after seq {seq - 1}")
                try:
                    rec = canon.loads(line)
                except ValueError as e:
                    raise LedgerError(f"unreadable record after seq {seq - 1}: {e}") from None
                if not isinstance(rec, dict):
                    raise LedgerError(f"record after seq {seq - 1} is not an object")
                check_chain_step(rec, seq, prev)
                yield rec
                if stop_seq is not None and seq == stop_seq:
                    return
                prev = rec["hash"]
                seq += 1

    def read_all(self):
        """Every record in the file (strict). Use under the lock after _recover; readers use verify()."""
        return list(self.records())

    def verify(self):
        """The committed records: the chain from genesis up to the head, which must match the record at
        its sequence number. Lines after the head belong to a commit in progress and are not read."""
        head = self.read_head()
        if not isinstance(head.get("seq"), int) or head["seq"] < 0:
            raise LedgerError("head is malformed")
        recs = list(self.records(stop_seq=head["seq"]))
        if not recs:
            raise LedgerError("empty ledger")
        last = recs[-1]
        if head["seq"] != last["seq"] or head["hash"] != last["hash"]:
            raise LedgerError("head anchor does not match the last record")
        if head["ledger_id"] != recs[0]["data"].get("ledger_id"):
            raise LedgerError("head ledger_id mismatch")
        return recs

    # ----- writing -----
    def _make(self, seq, prev, event, data):
        if event not in EVENTS:
            raise LedgerError(f"event not allowed: {event}")
        rec = {"schema": RECORD_SCHEMA, "seq": seq, "prev": prev, "ts": now_iso(), "event": event, "data": data}
        rec["hash"] = record_hash(rec)
        return rec

    def _commit(self, rec):
        # 1. journal the intent
        _write_atomic(self.pending_path, canon.dumps(rec))
        # 2. append durably
        _append_bytes(self.path, (canon.dumps(rec) + "\n").encode("utf-8"))
        # 3-5. head, anchor, mirror
        self._finish(rec)
        # 6. clear the journal
        os.unlink(self.pending_path)

    def _finish(self, rec):
        """Move the head and the anchor to rec and mirror it. Idempotent, so recovery can repeat it."""
        from . import paths
        ledger_id = rec["data"]["ledger_id"] if rec["seq"] == 0 else self.read_head()["ledger_id"]
        head = canon.dumps({"ledger_id": ledger_id, "seq": rec["seq"], "hash": rec["hash"]})
        _write_atomic(self.head_path, head)
        os.makedirs(paths.anchors_dir(), mode=0o700, exist_ok=True)
        os.makedirs(paths.mirror_dir(), mode=0o700, exist_ok=True)
        _write_atomic(paths.anchor_path(ledger_id), head + "\n")
        if rec["seq"] <= 1:
            # the workspace witness says which ledger lives here and whether it ever had a record after genesis;
            # it needs no update after that (the anchor follows the head), so an ordinary commit does not pay for it
            os.makedirs(os.path.dirname(paths.witness_path(self.root)), mode=0o700, exist_ok=True)
            _write_atomic(paths.witness_path(self.root), canon.dumps({"ledger_id": ledger_id, "seq": rec["seq"], "hash": rec["hash"],
                                                                      "root": self.root}) + "\n", sync=False)
        mp = paths.mirror_path(ledger_id)
        line, tail = last_line(mp)
        if tail:
            # an interrupted mirror append; the mirror is a copy, the ledger and the journal are the source
            with open(mp, "r+b") as f:
                f.truncate(os.fstat(f.fileno()).st_size - len(tail))
        if line is not None:
            try:
                if canon.loads(line).get("hash") == rec["hash"]:
                    return
            except ValueError:
                pass
        _append_bytes(mp, (canon.dumps(rec) + "\n").encode("utf-8"))

    def _recover(self):
        """Finish or discard an interrupted commit (call with the lock held).

        The journal holds the record being committed. If its line is in the ledger, the commit is finished
        (head, anchor, mirror). If the ledger ends in an unterminated tail that is a prefix of the journaled
        line, the crash hit the append itself and the line is completed; no committed byte is removed. Any
        other unterminated or unreadable tail is corruption and raises LedgerError."""
        line, tail = last_line(self.path)
        if not os.path.exists(self.pending_path):
            if tail:
                raise LedgerError("the ledger ends in an unterminated record and no commit is journaled")
            if line is not None and os.path.exists(self.head_path):
                try:
                    last_hash = canon.loads(line).get("hash")
                except ValueError as e:
                    raise LedgerError(f"the last ledger line is unreadable: {e}") from None
                if last_hash != self.read_head().get("hash"):
                    raise LedgerError("the ledger has records after its head and no commit is journaled")
            return
        with open(self.pending_path, "r", encoding="utf-8") as f:
            pending = canon.loads(f.read())
        full = (canon.dumps(pending) + "\n").encode("utf-8")
        if tail:
            if not full.startswith(tail):
                raise LedgerError("the ledger ends in an unterminated record that is not the journaled one")
            _append_bytes(self.path, full[len(tail):])
            line = full[:-1]
        last = None
        if line is not None:
            try:
                last = canon.loads(line)
            except ValueError as e:
                raise LedgerError(f"the last ledger line is unreadable: {e}") from None
        if last is not None and last.get("hash") == pending["hash"]:
            self._finish(pending)
        # otherwise the append never landed: the intent is dropped
        os.unlink(self.pending_path)

    def append(self, event, data, expect_head=None):
        """Append one record. With expect_head, refuse if the head hash moved (compare-and-swap)."""
        with self.lock():
            return self.append_held(event, data, expect_head)

    def append_held(self, event, data, expect_head=None):
        """append() for a caller that already holds the lock, so a check and the record it justifies happen
        under one lock hold (the completion in workspace._turn_end)."""
        self._recover()
        head = self.read_head()
        if expect_head is not None and head["hash"] != expect_head:
            raise ConflictError("ledger head moved")
        rec = self._make(head["seq"] + 1, head["hash"], event, data)
        self._commit(rec)
        return rec
