"""Workspace content digest (EVI-36/37).

G1 computes its own digest from file bytes. No version-control tool is on the authority path.
Symbolic links are recorded by their target text and never followed. Directories are recorded with
their mode, so an empty directory or a permission change is a change. Excluded directories are a fixed list
(paths.DEFAULT_EXCLUDES): they are neither recorded nor copied into the scratch tree where checks run, so no
check result can depend on them and no change inside them is a scope violation.
"""

import os
import stat

from . import canon, paths

TREE_DOMAIN = "g1-tree-v1"


class SnapshotError(Exception):
    pass


def _walk(dirfd, rel, out, depth, excludes):
    if depth > paths.MAX_DEPTH:
        raise SnapshotError(f"directory too deep: {rel}")
    try:
        names = sorted(os.listdir(dirfd))
    except OSError as e:
        out[rel.rstrip("/") + "/"] = {"kind": "unreadable", "error": e.__class__.__name__}
        return
    for name in names:
        if name in excludes:
            continue
        p = f"{rel}{name}" if rel else name
        try:
            st = os.lstat(name, dir_fd=dirfd)
        except FileNotFoundError:
            out[p] = {"kind": "vanished"}
            continue
        if stat.S_ISLNK(st.st_mode):
            out[p] = {"kind": "symlink", "target": os.readlink(name, dir_fd=dirfd)}
        elif stat.S_ISDIR(st.st_mode):
            out[p + "/"] = {"kind": "dir", "mode": st.st_mode & 0o777}  # created, removed or chmod-ed directories count
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=dirfd)
            except OSError as e:
                out[p + "/"] = {"kind": "unreadable", "error": e.__class__.__name__}
                continue
            try:
                _walk(fd, p + "/", out, depth + 1, excludes)
            finally:
                os.close(fd)
        elif stat.S_ISREG(st.st_mode):
            if len(out) >= paths.MAX_FILES:
                raise SnapshotError("too many files")
            if st.st_size > paths.MAX_FILE_BYTES:
                out[p] = {"kind": "large", "size": st.st_size}
                continue
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
            except OSError as e:
                out[p] = {"kind": "unreadable", "error": e.__class__.__name__}
                continue
            try:
                with os.fdopen(fd, "rb") as f:
                    h = canon.sha256_bytes(f.read())
            except OSError:
                out[p] = {"kind": "unreadable", "error": "read"}
                continue
            out[p] = {"kind": "file", "sha256": h, "size": st.st_size, "mode": st.st_mode & 0o777}
        else:
            out[p] = {"kind": "special"}


def manifest(root, excludes=None):
    """Map relpath -> entry for every path under root (fd-relative walk)."""
    ex = set(paths.DEFAULT_EXCLUDES) | set(excludes or ())
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        st = os.fstat(fd)
        if st.st_uid != os.getuid():
            raise SnapshotError("workspace root is owned by another user")
        out = {}
        _walk(fd, "", out, 0, ex)
        return out
    finally:
        os.close(fd)


def digest(man):
    return canon.domain_hash(TREE_DOMAIN, man)


def tree_digest(root):
    return digest(manifest(root))


def changed_paths(base, current):
    """Paths whose entry differs between two manifests (added, removed, or modified)."""
    keys = set(base) | set(current)
    return sorted(k for k in keys if base.get(k) != current.get(k))


def file_hashes(root, relpaths):
    out = {}
    for rp in relpaths:
        p = os.path.join(root, rp)
        try:
            if os.path.islink(p) or not os.path.isfile(p):
                out[rp] = None
            else:
                out[rp] = canon.sha256_file(p)
        except OSError:
            out[rp] = None
    return out
