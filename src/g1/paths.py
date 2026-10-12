"""Locations of G1 state. One module owns every path (PTH-10).

All state lives under ~/.g1 (or $G1_HOME). Per-workspace state is keyed by the workspace's real path,
so no project directory is written to, and every project is enrolled automatically at session start.
"""

import os

DEFAULT_EXCLUDES = {".g1", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv", "venv"}
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_FILES = 100000
MAX_DEPTH = 40


def home():
    return os.environ.get("G1_HOME") or os.path.join(os.path.expanduser("~"), ".g1")


def pyz_path():
    return os.path.join(home(), "g1.pyz")


def manifest_path():
    return os.path.join(home(), "manifest.json")


def anchors_dir():
    return os.path.join(home(), "anchors")


def anchor_path(ledger_id):
    return os.path.join(anchors_dir(), f"{ledger_id}.head")


def witness_path(root):
    """The witness keyed by the workspace (not by the ledger id): the ledger id G1 created or accepted here, and the
    sequence number it was written at (1 or more means the ledger had records after genesis). It lives outside the
    workspace's own directory, so deleting, replacing or truncating the ledger files cannot erase what it says
    (review round 3, R3-01, R3-02). The anchor, keyed by the ledger id, follows the head."""
    return os.path.join(anchors_dir(), "ws", f"{ws_id(root)}.json")


def mirror_dir():
    return os.path.join(home(), "mirror")


def mirror_path(ledger_id):
    return os.path.join(mirror_dir(), f"{ledger_id}.jsonl")


def observe_dir():
    return os.path.join(home(), "observe")


def summary_path(root):
    """The head-bound summary the per-call hooks read (workspace.Workspace.summary)."""
    return os.path.join(ws_dir(root), "summary.json")


def lockdown_path(root):
    """Present while an integrity alert holds a workspace; `g1 repair` removes it."""
    return os.path.join(observe_dir(), ws_id(root), "lockdown")


def scratch_dir():
    return os.path.join(home(), "scratch")


def workspaces_dir():
    return os.path.join(home(), "workspaces")


def ws_id(root):
    from . import canon
    return canon.sha256_text(os.path.realpath(root))[:16]


def ws_dir(root):
    return os.path.join(workspaces_dir(), ws_id(root))


def proposals_dir(root):
    return os.path.join(ws_dir(root), "proposals")


def challenges_dir(root):
    """Where a reviewing agent writes challenges: claimed defects, each with a check that fails now (design 5.5)."""
    return os.path.join(ws_dir(root), "challenges")


def evidence_dir(root):
    return os.path.join(ws_dir(root), "evidence")


def views_dir(root):
    return os.path.join(ws_dir(root), "views")


def enrollable(root):
    """A workspace G1 may enrol on its own: a real directory that is not the home, not the root, and
    neither inside G1's own home nor a parent of it."""
    if not isinstance(root, str) or not root or not os.path.isdir(root):
        return False
    r = os.path.realpath(root)
    h = os.path.realpath(os.path.expanduser("~"))
    g = os.path.realpath(home())
    if r in ("/", h, g) or g.startswith(r.rstrip(os.sep) + os.sep) or r.startswith(g + os.sep):
        return False
    return True


def in_scope(path, allowed):
    """True when a workspace-relative path is one of the allowed paths or lies under one of them."""
    for a in allowed:
        a = a.rstrip("/")
        if path == a or path.startswith(a + "/"):
            return True
    return False


def ensure_dirs(root=None):
    for d in (home(), anchors_dir(), mirror_dir(), observe_dir(), scratch_dir(), workspaces_dir()):
        os.makedirs(d, mode=0o700, exist_ok=True)
    if root:
        for d in (ws_dir(root), proposals_dir(root), challenges_dir(root), evidence_dir(root), views_dir(root)):
            os.makedirs(d, mode=0o700, exist_ok=True)
        with open(os.path.join(ws_dir(root), "root.txt"), "w", encoding="utf-8") as f:
            f.write(os.path.realpath(root) + "\n")
