"""Deterministic check execution (design 6.1).

A check is one argv. It runs on a scratch copy of the tree, with an allowlisted environment,
a deadline, an output cap, in its own process group. Nothing from the workspace is on PATH.
"""

import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

from . import canon, paths

OUTPUT_CAP = 1 << 20
DEFAULT_TIMEOUT_S = 120
MAX_TIMEOUT_S = 1800
SYSTEM_PATH = ["/usr/local/bin", "/usr/bin", "/bin"]
MIN_FREE_BYTES = 50 * 1024 * 1024

REDACTIONS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "[REDACTED:gkey]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED:pem]"),
    (re.compile(r"eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}"), "[REDACTED:jwt]"),
    (re.compile(r"xox[abprs]-[0-9A-Za-z\-]{10,}"), "[REDACTED:slack]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED:aws]"),
    (re.compile(r"\b(?:gh[pousr]_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,})"), "[REDACTED:github]"),
    (re.compile(r"\bglpat-[0-9A-Za-z_\-]{20,}"), "[REDACTED:gitlab]"),
    (re.compile(r"\bsk-(?:ant-|proj-)?[0-9A-Za-z_\-]{20,}"), "[REDACTED:sk]"),
    (re.compile(r"\bhf_[0-9A-Za-z]{30,}"), "[REDACTED:hf]"),
    (re.compile(r"(?i)(bearer|basic)\s+[0-9A-Za-z+/=_\-\.]{16,}"), r"\1 [REDACTED]"),
    (re.compile(r'(?i)"([a-z0-9_\-]*(key|token|secret|password|passwd)[a-z0-9_\-]*)"\s*:\s*"[^"]*"'), r'"\1":"[REDACTED]"'),
    (re.compile(r"(?i)'([a-z0-9_\-]*(key|token|secret|password|passwd)[a-z0-9_\-]*)'\s*:\s*'[^']*'"), r"'\1':'[REDACTED]'"),
    (re.compile(r"(?i)\b([a-z0-9_\-]*(?:api[_\-]?key|token|secret|password|passwd|access[_\-]?key))\b(\s*[:=]\s*)(['\"]?)[^\s'\"&,;]{6,}\3"),
     r"\1\2\3[REDACTED]\3"),
]


class RunnerError(Exception):
    pass


def redact(text):
    for pat, rep in REDACTIONS:
        text = pat.sub(rep, text)
    return text


def scrubbed_env(private_home):
    path_dirs = [d for d in SYSTEM_PATH if os.path.isdir(d)]
    exe_dir = os.path.dirname(os.path.realpath(sys.executable))
    if exe_dir not in path_dirs and os.path.isdir(exe_dir):
        path_dirs.append(exe_dir)
    return {
        "PATH": ":".join(path_dirs),
        "HOME": private_home,
        "TMPDIR": os.path.join(private_home, "tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "NO_COLOR": "1",
        "TERM": "dumb",
    }


def env_digest(env):
    return canon.sha256_text(canon.dumps(env))


def resolve_executable(argv0, env, workspace_root=None, oracle_files=()):
    """Return the absolute executable path. argv0 without '/' resolves on the scrubbed PATH;
    a workspace-relative path is allowed only if it is a pinned oracle file."""
    if "/" not in argv0:
        found = shutil.which(argv0, path=env["PATH"])
        if not found:
            raise RunnerError(f"executable not found on the scrubbed PATH: {argv0}")
        return os.path.realpath(found)
    if os.path.isabs(argv0):
        raise RunnerError(f"absolute executable paths are not allowed: {argv0}")
    norm = os.path.normpath(argv0)
    if norm.startswith("..") or norm not in set(oracle_files):
        raise RunnerError(f"workspace executable must be a pinned oracle file: {argv0}")
    return norm  # resolved relative to the scratch copy at run time


def executable_hash(path):
    return canon.sha256_file(path)


def _copy_entry(src, dst, rel, required, skipped, depth):
    """Copy one directory level by hand (no shutil.copytree, no kernel copy fast path): regular files through
    descriptors opened without following links, symbolic links as links, directories recursively. A FIFO, a socket,
    a device or an unreadable file is skipped and recorded, never opened for reading (a FIFO would block the hook,
    R3-05; one unreadable file must not stop every verification, R3-14). A required path (a target or an oracle of
    the contract) that cannot be copied raises RunnerError."""
    if depth > paths.MAX_DEPTH:
        raise RunnerError(f"scratch copy failed: directory too deep: {rel}")
    try:
        names = sorted(os.listdir(src))
    except OSError as e:
        if rel in required or any(r.startswith(rel + "/") for r in required):
            raise RunnerError(f"scratch copy failed: required directory {rel}: {e.__class__.__name__}") from None
        skipped.append((rel + "/", e.__class__.__name__))
        return
    for name in names:
        if name in paths.DEFAULT_EXCLUDES:
            continue
        s_, d_ = os.path.join(src, name), os.path.join(dst, name)
        r_ = f"{rel}/{name}" if rel else name
        try:
            st = os.lstat(s_)
        except OSError as e:
            skipped.append((r_, e.__class__.__name__))
            continue
        if stat.S_ISLNK(st.st_mode):
            try:
                os.symlink(os.readlink(s_), d_)
            except OSError as e:
                skipped.append((r_, e.__class__.__name__))
        elif stat.S_ISDIR(st.st_mode):
            os.mkdir(d_, 0o700)
            _copy_entry(s_, d_, r_, required, skipped, depth + 1)
            try:
                os.chmod(d_, st.st_mode & 0o777)
                os.utime(d_, ns=(st.st_atime_ns, st.st_mtime_ns))  # after its entries, which would move it (R4-08)
            except OSError:
                pass
        elif stat.S_ISREG(st.st_mode):
            try:
                fd = os.open(s_, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except OSError as e:
                if r_ in required:
                    raise RunnerError(f"scratch copy failed: required file {r_}: {e.__class__.__name__}") from None
                skipped.append((r_, e.__class__.__name__))
                continue
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    skipped.append((r_, "replaced"))
                    continue
                out = os.open(d_, os.O_WRONLY | os.O_CREAT | os.O_EXCL, st.st_mode & 0o777 or 0o600)
                with os.fdopen(fd, "rb", closefd=False) as fi, os.fdopen(out, "wb") as fo:
                    shutil.copyfileobj(fi, fo, 1 << 20)  # a read/write loop: no copy_file_range, no sendfile
                try:
                    os.utime(d_, ns=(st.st_atime_ns, st.st_mtime_ns))
                except OSError:
                    pass
            except OSError as e:
                if r_ in required:
                    raise RunnerError(f"scratch copy failed: required file {r_}: {e.__class__.__name__}") from None
                skipped.append((r_, e.__class__.__name__))
            finally:
                os.close(fd)
        else:
            if r_ in required:
                raise RunnerError(f"scratch copy failed: required path {r_} is not a regular file")
            skipped.append((r_, "special"))


def scratch_copy(root, label, required=()):
    """Copy the workspace (minus excluded dirs) into a private scratch directory. required names the relative paths
    the checks depend on (targets, oracles, workspace executables): one of them failing to copy is a RunnerError, so
    a verification records `scratch_copy_failed` instead of crashing the hook. Other entries that cannot be copied
    are skipped and listed in <scratch>/skipped.json (scratch_skipped)."""
    paths.ensure_dirs()
    total = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in paths.DEFAULT_EXCLUDES]
        for fn in fns:
            try:
                total += os.lstat(os.path.join(dp, fn)).st_size
            except OSError:
                pass
    free = shutil.disk_usage(paths.scratch_dir()).free
    if free < total * 2 + MIN_FREE_BYTES:
        raise RunnerError("insufficient space for a scratch copy")
    dst = tempfile.mkdtemp(prefix=f"{label}-", dir=paths.scratch_dir())
    tree = os.path.join(dst, "tree")
    skipped = []
    req = {os.path.normpath(r).replace(os.sep, "/") for r in required}
    try:
        os.mkdir(tree, 0o700)
        _copy_entry(root, tree, "", req, skipped, 0)
    except RunnerError:
        shutil.rmtree(dst, ignore_errors=True)
        raise
    except (OSError, shutil.Error) as e:
        shutil.rmtree(dst, ignore_errors=True)
        raise RunnerError(f"scratch copy failed: {e.__class__.__name__}: {str(e)[:200]}") from None
    with open(os.path.join(dst, "skipped.json"), "w", encoding="utf-8") as f:
        f.write(canon.dumps([[r, why] for r, why in skipped[:200]]))
    os.makedirs(os.path.join(dst, "home", "tmp"), mode=0o700, exist_ok=True)
    return dst


def scratch_skipped(dst):
    """The entries scratch_copy could not copy, as [[relpath, reason], ...]."""
    try:
        with open(os.path.join(dst, "skipped.json"), "r", encoding="utf-8") as f:
            return canon.loads(f.read())
    except (OSError, ValueError):
        return []


def remove_scratch(dst):
    shutil.rmtree(dst, ignore_errors=True)


EXIT_GRACE_S = 0.5


def _read_bounded(proc, deadline, cap):
    """Read stdout and stderr as they arrive, keeping at most cap+1 bytes of each, until both close, the
    deadline passes, or one stream exceeds the cap. Memory stays bounded whatever the check prints. When the
    check itself has exited but a child it left behind still holds a pipe, reading stops after a short grace:
    the check's exit status is known, and run() kills the leftover process group."""
    import selectors
    bufs = {proc.stdout.fileno(): bytearray(), proc.stderr.fileno(): bytearray()}
    sel = selectors.DefaultSelector()
    grace = None
    try:
        for fd in bufs:
            os.set_blocking(fd, False)
            sel.register(fd, selectors.EVENT_READ)
        while sel.get_map():
            now = time.monotonic()
            if now >= deadline:
                return bufs, "timeout"
            if grace is None and proc.poll() is not None:
                grace = now + EXIT_GRACE_S
            if grace is not None and now >= grace:
                return bufs, "exited"
            left = min(deadline, grace if grace is not None else deadline) - now
            for key, _ in sel.select(timeout=min(left, 0.2)):
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    sel.unregister(key.fd)
                    continue
                b = bufs[key.fd]
                room = cap + 1 - len(b)
                if room > 0:
                    b += chunk[:room]
                if len(b) > cap:
                    return bufs, "over"
        return bufs, "eof"
    finally:
        sel.close()


def run(argv, cwd, env, timeout_s=DEFAULT_TIMEOUT_S, cap=OUTPUT_CAP):
    """Run one argv. Returns a dict with exit, timed_out, truncated, output digests and tails. Output beyond
    the cap stops the check (its process group is killed) and marks it truncated, which is a fail (ASC-22)."""
    timeout_s = max(1, min(int(timeout_s), MAX_TIMEOUT_S))
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    except OSError as e:
        return {"executed": False, "exit": None, "timed_out": False, "truncated": False,
                "error": f"spawn failed: {e.__class__.__name__}", "duration_ms": 0,
                "stdout_sha256": None, "stderr_sha256": None, "stdout_tail": "", "stderr_tail": ""}
    deadline = t0 + timeout_s
    timed_out = over = False
    out = err = b""
    try:
        bufs, how = _read_bounded(proc, deadline, cap)
        out, err = bytes(bufs[proc.stdout.fileno()]), bytes(bufs[proc.stderr.fileno()])
        timed_out, over = how == "timeout", how == "over"
        if how == "exited":
            proc.wait(timeout=5)
        if how == "eof":
            try:
                proc.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        _kill_group(proc)  # the check's whole process group goes on every exit path (RUN-23)
        proc.stdout.close()
        proc.stderr.close()
    truncated = over or len(out) > cap or len(err) > cap
    out, err = out[:cap], err[:cap]
    out_t = redact(out.decode("utf-8", "replace"))
    err_t = redact(err.decode("utf-8", "replace"))
    return {
        "executed": True, "exit": proc.returncode, "timed_out": timed_out, "truncated": truncated,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "stdout_sha256": canon.sha256_text(out_t), "stderr_sha256": canon.sha256_text(err_t),
        "stdout_tail": out_t[-4000:], "stderr_tail": err_t[-4000:],
    }


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def verdict_of(r):
    """Pass requires exit 0, no timeout, untruncated output (ASC-22)."""
    if not r.get("executed"):
        return "unknown"
    if r["exit"] == 0 and not r["timed_out"] and not r["truncated"]:
        return "pass"
    return "fail"
