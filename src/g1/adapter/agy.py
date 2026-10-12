"""Antigravity CLI adapter (docs/host-agy.md).

Output discipline (measured):
- PreToolUse: print nothing for no opinion; print {"decision":"deny","reason":...} to block. Never {} or allow.
- SessionStart / PreInvocation: {"injectSteps":[{"ephemeralMessage": ...}]} or nothing.
- Stop: {"decision":"stop"} or {"decision":"continue","reason":...}; verification only when fullyIdle is true.

The PreToolUse path imports only light modules (os, json, hashlib, the ledger reader) so a tool call costs
one short process. Heavy modules load only for SessionStart, PreInvocation and Stop.
"""

import json
import os
import re
import shlex
import time

from .. import canon, integrity, ledger as ledger_mod, paths, state as state_mod

# Tools that can change files, run code or start agents. Names from the binary's step types and the analysts'
# tool list (from an analysis of the agy binary, kept outside this repository); both spellings of the notebook tool are kept. Measured: every tool call,
# whatever its name, fires PreToolUse with matcher "*" (coverage runs c1-c6), so a listed name is always seen.
MUTATING_TOOLS = {"write_to_file", "replace_file_content", "multi_replace_file_content", "write_file", "edit_file",
                  "sed_file", "notebook_edit", "edit_notebook", "execute_notebook", "delete_directory", "delete_file",
                  "move", "create_directory", "write_blob", "generate_image", "run_command", "send_command_input",
                  "git_commit", "install_applet_dependencies", "install_applet_package", "invoke_subagent",
                  "define_subagent"}
# Measured: agy matchers are regular expressions; "a|b" and "^(a|b)$" select, the documented "a\|b" selects nothing.
# Read-only tools never start a hook process. Authority does not depend on this: verification at Stop
# re-hashes the tree, the oracles and the scope regardless of which tool changed a file.
TOOL_MATCHER = "^(" + "|".join(sorted(MUTATING_TOOLS)) + ")$"
PATH_KEYS = ("TargetFile", "Path", "NotebookPath", "AbsolutePath", "TargetPath", "Source", "Destination", "DirectoryPath", "FilePath")
SESSION_MAX = 1024
TURN_MAX = 512
JOURNAL_MAX_BYTES = 8 << 20  # a journal past this size is rotated once (journal-<layer>.jsonl.1)


def out(obj):
    return json.dumps(obj, ensure_ascii=False)


def config_root():
    """agy's user configuration root: the global hooks file, rules and skills live here."""
    return os.path.join(os.path.expanduser("~"), ".gemini", "config")


def global_hooks_path():
    return os.path.join(config_root(), "hooks.json")


def conversations_root():
    """agy's conversation store; each conversation keeps its transcript under <id>/.system_generated/."""
    return os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli", "brain")


def touches_transcripts(path):
    """A path that holds or contains a transcript G1 reads: the store itself, a conversation directory, or anything
    under a .system_generated directory. Artifacts the agent writes inside a conversation directory stay writable."""
    root = os.path.realpath(conversations_root())
    if not (path == root or path.startswith(root + os.sep)):
        return False
    parts = [p for p in path[len(root):].split(os.sep) if p]
    return len(parts) <= 1 or ".system_generated" in parts


def host_binary():
    """The agy executable on PATH (resolved through symlinks)."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, "agy")
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return os.path.realpath(p)
    return None


def host_fingerprint():
    """Cheap identity of the host binary: size plus the first and last MiB. A full hash of a 200 MB
    binary would cost seconds at every session start; an update changes size or edges in practice."""
    p = host_binary()
    if not p:
        return "no-binary"
    import hashlib
    h = hashlib.sha256()
    st = os.stat(p)
    h.update(str(st.st_size).encode())
    with open(p, "rb") as f:
        h.update(f.read(1 << 20))
        if st.st_size > (2 << 20):
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return h.hexdigest()


def host_check(ctx):
    """Compare the running agy with the fingerprint recorded at the last verified measurement.
    Records a change in the workspace ledger once and returns an alert line or None."""
    if not ctx.manifest or not ctx.manifest.get("host_fingerprint"):
        return None
    fp = host_fingerprint()
    s = ctx.ws.state()
    if fp == ctx.manifest["host_fingerprint"]:
        if s.get("host_unverified"):
            ctx.ws.append("host_contract_observed", {"status": "verified", "fingerprint": fp})
        return None
    if s.get("host_fp") != fp:
        ctx.ws.append("host_contract_observed", {"status": "unverified", "fingerprint": fp})
    return ("ALERT: the agy binary changed since G1's hook contract was last measured. Completion is withheld "
            "until the probes in research/agy-hooks are re-run and `g1 host-verify` records the new binary.")


def _str(v):
    return v if isinstance(v, str) else ""


class Context:
    def __init__(self, event, payload, cwd):
        self.event = event
        self.payload = payload if isinstance(payload, dict) else {}
        self.cwd = os.path.realpath(cwd)
        self._cfg_real = os.path.realpath(config_root())
        self.layer = "global" if self.cwd == self._cfg_real else "workspace"
        self._manifest = None
        wps = self.payload.get("workspacePaths")
        first = wps[0] if isinstance(wps, list) and wps else None
        self.root = os.path.realpath(first) if isinstance(first, str) and first and "\x00" not in first else None
        self.enrolled = bool(self.root and os.path.exists(os.path.join(paths.ws_dir(self.root), "ledger.head.json")))
        self.cid = _str(self.payload.get("conversationId"))
        self.obs = os.path.join(paths.observe_dir(), paths.ws_id(self.root)) if self.root else None
        self._ws = None

    @property
    def manifest(self):
        if self._manifest is None:
            self._manifest = integrity.load_manifest() or {}
        return self._manifest

    @property
    def primary(self):
        """Verification, proposals and injection run in one layer: the global one when it is installed."""
        gi = bool(self.manifest.get("global_installed"))
        return (self.layer == "global") if gi else (self.layer == "workspace")

    @property
    def ws(self):
        if self._ws is None:
            from .. import workspace as workspace_mod
            self._ws = workspace_mod.Workspace(self.root, self.manifest or None)
        return self._ws

    # ----- observation journal (enrolled workspaces only) -----
    def journal(self, kind, extra):
        """One appended line per hook call. The line carries the conversation's transcript path, so the gap
        check needs no shared read-modify-write file (concurrent subagents append lines, never rewrite)."""
        if not self.obs or not self.enrolled:
            return
        try:
            os.makedirs(self.obs, mode=0o700, exist_ok=True)
            rec = {"t": time.time(), "layer": self.layer, "kind": kind, "cid": self.cid}
            tp = _str(self.payload.get("transcriptPath"))
            if tp:
                rec["tp"] = tp
            rec.update(extra)
            jp = os.path.join(self.obs, f"journal-{self.layer}.jsonl")
            try:
                if os.path.getsize(jp) > JOURNAL_MAX_BYTES:  # one rotation; the gap check reads both files
                    os.replace(jp, jp + ".1")
            except OSError:
                pass
            with open(jp, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def lockdown_path(self):
        return paths.lockdown_path(self.root) if self.root else None

    def locked_down(self):
        p = self.lockdown_path()
        return bool(p and os.path.exists(p))

    def set_lockdown(self, detail):
        p = self.lockdown_path()
        if p:
            os.makedirs(self.obs, mode=0o700, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(detail + "\n")


# ----- protected paths -----
def protected_roots(ctx):
    """G1's own state and the files G1 installs into the host (hooks, rules, skill). Other host configuration
    stays under the host's native rules (P2). Two realpath calls in all: each costs a dozen lstat calls under PRoot,
    and the installed files sit at fixed names under the resolved configuration root."""
    cfg = ctx._cfg_real
    roots = [os.path.realpath(paths.home()), os.path.join(cfg, "hooks.json")]
    for rel in integrity.host_file_index():
        p = os.path.join(cfg, *rel.split("/"))
        roots.append(os.path.dirname(p) if rel.startswith("skills/") else p)
    if ctx.root:
        roots.append(os.path.join(ctx.root, ".agents", "hooks.json"))
    return roots


def agent_writable(ctx, path):
    """The places under G1's home the agent may write: this workspace's proposals and challenges directories."""
    if not ctx.root:
        return False
    for d in (paths.proposals_dir(ctx.root), paths.challenges_dir(ctx.root)):
        d = os.path.realpath(d)
        if path == d or path.startswith(d + os.sep):
            return True
    return False


def target_paths(ctx, args):
    found = []
    for k in PATH_KEYS:
        v = args.get(k)
        if isinstance(v, str) and v and "\x00" not in v:
            p = v if os.path.isabs(v) else os.path.join(ctx.root or ctx.cwd, v)
            found.append(os.path.realpath(p))
    return found


def _under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def gate(ctx):
    """Return a deny reason or None."""
    tc = ctx.payload.get("toolCall")
    tc = tc if isinstance(tc, dict) else {}
    name, args = _str(tc.get("name")), tc.get("args")
    args = args if isinstance(args, dict) else {}
    if name not in MUTATING_TOOLS:
        return None
    if ctx.locked_down():
        return "G1 integrity alert is active for this workspace; mutating tools are refused until the user runs `g1 repair`."
    task = None
    if ctx.enrolled:
        try:
            summ = state_mod.cached_summary(ctx.root)  # O(1): the summary bound to the current head (design 7.2)
            task = (summ if summ is not None else ctx.ws.summary())["active"]
        except Exception:
            return "G1 ledger could not be verified; mutating tools are refused (the user runs `g1 repair`)."
    if name in ("run_command", "send_command_input", "execute_notebook"):
        text = " ".join(_str(v) for v in args.values())
        return textual_gate(ctx, text, task)
    for p in target_paths(ctx, args):
        if agent_writable(ctx, p):
            continue
        for r in protected_roots(ctx):
            if _under(p, r):
                return f"G1 protected path: {p} is part of the verification root of trust and cannot be written by the agent."
        if touches_transcripts(p):
            return f"G1 protected path: {p} holds conversation transcripts that G1 reads as evidence."
        if task is not None:
            rel = os.path.relpath(p, ctx.root)
            if rel in task["oracle_files"]:
                return f"G1 pinned oracle: {rel} is fixed for contract {task['task']}; propose a new contract to change it."
            if rel.startswith("..") or not paths.in_scope(rel, task["allowed_paths"]):
                from .. import project
                return (f"G1 scope: {rel} is outside the allowed paths {project.short_json(task['allowed_paths'], 300)} "
                        f"of contract {task['task']}.")
    return None


# G1's own command line is the user's. Its decision commands change G1's trust state (accepting a ledger, recording
# a host binary, installing, removing, deciding a challenge, running a verification outside the Stop hook), and the
# agent needs none of the others either: the status block and the views carry what G1 knows. So the textual gate
# refuses every G1 command line in command position, whatever the subcommand, which removes the subcommand spellings
# round 3 found (`-mg1`, `$(echo repair)`, R3-04). A tripwire, like the rest of the textual gate (design 7.3): the
# command is split into shell tokens and only a command in command position counts, so a commit message or a grep
# pattern that mentions `g1 repair` is not refused. The boundary behind it is in the command line itself: a decision
# command refuses to run with the host agent among its ancestors (process_chain, __main__._user_only).
DECISIONS = {"repair", "host-verify", "install", "uninstall", "turn-end", "init", "propose", "challenge", "challenges"}
CLI_DECISIONS = re.compile(r"(?:(?:^|[\s;&|()`'\"])(?:\S*/)?g1(?:\.pyz)?|-m\s*g1(?:\.__main__)?)(?:\s|$)")  # fallback only
AGENT_PROCESS_NAMES = {"agy"}
# A wrapper runs the command that follows its own options. The letters are its short options that take the next
# token as their argument, so `exec -a NAME python3 -m g1`, `sudo -u USER g1` and `nice -n 10 python3 -m g1` are
# still seen (R4-06); the command strings of `script -c`, `flock -c` and `env -S` are read as command lines.
_WRAPPERS = {"sudo": "uUgChprtDT", "doas": "uC", "env": "uCS", "exec": "a", "nohup": "", "time": "fo", "command": "",
             "builtin": "", "nice": "n", "ionice": "cnp", "stdbuf": "ioe", "xargs": "aIdLnPsE", "timeout": "sk",
             "setsid": "", "chrt": "p", "taskset": "c", "unbuffer": "", "strace": "oepsP", "ltrace": "oepsn",
             "flock": "wEc", "caffeinate": "t", "watch": "n", "script": "c", "uv": "", "poetry": "", "pipenv": "", "pdm": ""}
_WRAPPER_LONG_ARGS = {"--user", "--group", "--chdir", "--chroot", "--host", "--role", "--type", "--prompt", "--close-from",
                      "--other-user", "--unset", "--split-string", "--adjustment", "--class", "--classdata", "--pid",
                      "--signal", "--kill-after", "--input", "--output", "--error", "--format", "--max-args", "--max-procs",
                      "--delimiter", "--arg-file", "--replace", "--max-lines", "--max-chars", "--eof", "--cpu-list",
                      "--timeout", "--conflict-exit-code", "--interval", "--command"}
_COMMAND_STRING_OPTS = {("script", "-c"), ("flock", "-c"), ("flock", "--command"), ("env", "-S"), ("env", "--split-string")}
_WRAPPER_POSITIONALS = {"timeout": 1, "flock": 1, "chrt": 1}  # a duration, a lock file, a priority: one operand before the command
# shlex costs about a millisecond per KB and grows faster on one long token (400 KB: 6 s); the gate tokenizes only
# this much and scans the rest with the linear patterns, so no command line an agent writes holds a tool call (P5-01).
# Past GATE_MAX_BYTES the command is refused outright: the linear scan of a mebibyte costs about 200 ms, and a shell
# command that long is a file written the wrong way (the host's time limit would otherwise end the hook as "allow").
GATE_TOKENIZE_BYTES = 16 << 10
GATE_MAX_BYTES = 1 << 20
_RUNNERS = {"uv", "poetry", "pipenv", "pdm", "pipx"}  # `uv run python -m g1`, `uv tool run g1`: the command follows
_RUNNER_WORDS = {"run", "tool"}
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for", "in", "case",
             "esac", "function", "select", "coproc"}  # shell words after which a command still starts (`f() { ...; }`)
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_SEP = set(";&|()")
_PY_G1_RE = re.compile(r"(?:^|[^A-Za-z0-9_.])(?:from\s+g1\b|import\s+g1\b|g1\.__main__"
                       r"|(?:import_module|__import__|run_module)\(\s*[rRbBuU]*['\"]g1\b)")


def _shell_tokens(text):
    # backticks and newlines separate commands too; inside quotes the replacement stays inside the token
    lx = shlex.shlex(text.replace("`", " ( ").replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lx.whitespace_split = True
    lx.commenters = ""
    return list(lx)


def _split_for_gate(text):
    """(head, tail): the head, at most GATE_TOKENIZE_BYTES cut at whitespace, is tokenized; the tail is scanned by
    the linear patterns (CLI_DECISIONS, _PY_G1_RE) and by whitespace tokens, coarser but bounded (P5-01)."""
    if len(text) <= GATE_TOKENIZE_BYTES:
        return text, ""
    cut = max(text.rfind(" ", 0, GATE_TOKENIZE_BYTES), text.rfind("\n", 0, GATE_TOKENIZE_BYTES), text.rfind("\t", 0, GATE_TOKENIZE_BYTES))
    if cut <= 0:
        cut = GATE_TOKENIZE_BYTES
    return text[:cut], text[cut:]


def _python_code_runs_g1(code):
    """Python code that loads G1's package: `import g1`, `from g1 ...`, `g1.__main__`, or an import by name
    (import_module("g1"), __import__("g1..."), run_module("g1")). Judged on tokens, so a string that merely holds
    the words is not refused (R4-07); code that does not tokenize is judged by the plain pattern."""
    import io
    import tokenize
    try:
        toks = [(t.type, t.string) for t in tokenize.generate_tokens(io.StringIO(code).readline)
                if t.type in (tokenize.NAME, tokenize.OP, tokenize.STRING)]
    except (tokenize.TokenError, SyntaxError, ValueError):
        return bool(_PY_G1_RE.search(code))
    for i, (ty, s) in enumerate(toks):
        if ty != tokenize.NAME:
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else (None, "")
        if s in ("import", "from"):
            j = i + 1
            while j < len(toks) and (toks[j][0] == tokenize.NAME or toks[j][1] in (",", ".", "(")):
                if toks[j] == (tokenize.NAME, "g1") and toks[j - 1][1] != ".":
                    return True
                j += 1
        elif s == "g1" and nxt == (tokenize.OP, ".") and i + 2 < len(toks) and toks[i + 2] == (tokenize.NAME, "__main__"):
            return True
        elif s in ("import_module", "__import__", "run_module") and nxt == (tokenize.OP, "(") and i + 2 < len(toks) \
                and toks[i + 2][0] == tokenize.STRING and re.match(r"^[rRbBuU]*['\"]g1(?:[.'\"]|$)", toks[i + 2][1]):
            return True
    return False


def _skip_wrapper(toks, i, base, depth):
    """Index of the command a wrapper at toks[i] runs, after its options; or -1 when an option's command string
    (script -c '...') runs G1's command line itself."""
    opts, i, operands = _WRAPPERS[base], i + 1, _WRAPPER_POSITIONALS.get(base, 0)
    while i < len(toks):
        a = toks[i]
        if set(a) <= _SEP:
            break
        if a == "--":
            return i + 1
        if a.startswith("-") and len(a) > 1:
            takes_arg = (len(a) == 2 and a[1] in opts) or a in _WRAPPER_LONG_ARGS
            if takes_arg and (base, a) in _COMMAND_STRING_OPTS and i + 1 < len(toks) and depth < 3 \
                    and invokes_g1(toks[i + 1], depth + 1):
                return -1
            i += 2 if takes_arg else 1
            continue
        if operands:
            operands, i = operands - 1, i + 1
            continue
        if base in _RUNNERS and a in _RUNNER_WORDS:
            i += 1
            continue
        break
    return i


def _piped_code(toks, i):
    """The tokens of the pipeline segment before the command at toks[i], joined, when a pipe feeds it; else ''."""
    if i < 1 or toks[i - 1] != "|":
        return ""
    j = i - 2
    while j >= 0 and not (toks[j] and set(toks[j]) <= _SEP):
        j -= 1
    return " ".join(toks[j + 1:i - 1])


def invokes_g1(text, depth=0, toks=None):
    """True when a shell command line runs G1's command line (g1, g1.pyz, python -m g1, python code that imports it,
    given with -c, on standard input or in a here-document) in command position, with any subcommand or none,
    behind the common wrappers and their options (R4-06). A tripwire (design 7.3): the boundary is the ancestry
    guard inside the command itself (process_chain, __main__._user_only)."""
    head, tail = _split_for_gate(text)
    if tail and (CLI_DECISIONS.search(tail) or _PY_G1_RE.search(tail)):
        return True  # beyond the tokenized head, any G1 command line in the text counts (coarse, linear)
    if toks is None:
        try:
            toks = _shell_tokens(head)
        except ValueError:  # unbalanced quotes: the plain patterns
            return bool(CLI_DECISIONS.search(text)) or bool(_PY_G1_RE.search(text))
    start, i = True, 0
    while i < len(toks):
        t = toks[i]
        if t and set(t) <= _SEP:
            start, i = True, i + 1
            continue
        if not start:
            i += 1
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) or t in _KEYWORDS:
            i += 1
            continue
        base = os.path.basename(t.lstrip("$"))
        if base in _WRAPPERS:
            i = _skip_wrapper(toks, i, base, depth)
            if i < 0:
                return True
            continue  # the command follows: start stays
        start = False
        rest = toks[i + 1:]
        if base in ("g1", "g1.pyz"):
            return True
        if re.match(r"^(?:python|pypy)[0-9.]*$", base):
            for j, a in enumerate(rest):
                if set(a) <= _SEP:
                    break
                if a == "-m" and j + 1 < len(rest) and rest[j + 1] in ("g1", "g1.__main__"):
                    return True
                if a.startswith("-m") and a[2:] in ("g1", "g1.__main__"):
                    return True
                if os.path.basename(a) == "g1.pyz":
                    return True
                if a == "-c" and j + 1 < len(rest) and _python_code_runs_g1(rest[j + 1]):
                    return True
                if a.startswith("<<") and _PY_G1_RE.search(" ".join(rest[j + 1:])):
                    return True  # a here-document (`<<EOF`, `<< 'EOF'`): its body follows, newlines being separators here
                if a == "-" and _PY_G1_RE.search(_piped_code(toks, i)):
                    return True  # code on standard input, from the pipe before this command; prose elsewhere on the line is not code (P5-02)
        if base in _SHELLS and depth < 3:
            for j, a in enumerate(rest):
                if set(a) <= _SEP:
                    break
                if a.startswith("-") and "c" in a[1:] and j + 1 < len(rest):
                    if invokes_g1(rest[j + 1], depth + 1):
                        return True
                    break
        if base == "eval" and depth < 3 and invokes_g1(" ".join(rest), depth + 1):
            return True
        i += 1
    return False


invokes_g1_decision = invokes_g1  # the round-2 name


def _proc_names(pid):
    """(names, ppid) of one process from /proc: its comm first, then the basenames of its executable and of argv[0].
    (None, 0) when the process cannot be read."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
        names = [data[data.index(b"(") + 1:data.rindex(b")")].decode("utf-8", "replace")]
        ppid = int(data[data.rindex(b")") + 2:].split()[1])
    except (OSError, ValueError, IndexError):
        return None, 0
    try:
        names.append(os.path.basename(os.readlink(f"/proc/{pid}/exe")))
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv0 = f.read().split(b"\0")[0]
        if argv0:
            names.append(os.path.basename(argv0.decode("utf-8", "replace")))
    except OSError:
        pass
    return [n for i, n in enumerate(names) if n and n not in names[:i]], ppid


def process_chain(limit=40):
    """The names of this process's ancestors, nearest first, one list of names per ancestor (comm first). A G1
    decision command run by the agent has the host agent (agy) among them; the user's shell does not. None when the
    parent process cannot be read at all (no /proc): the guard then fails closed (R4-04). An ancestor further up
    that cannot be read (another user's process under hidepid) ends the chain with a "?" entry. A tripwire: a
    process that leaves the tree (a double fork) is not seen, and what is measured is recorded with the decision."""
    chain, pid = [], os.getppid()
    while pid > 1 and len(chain) < limit:
        names, ppid = _proc_names(pid)
        if names is None:
            if not chain:
                return None
            chain.append(["?"])
            break
        chain.append(names)
        pid = ppid
    return chain


def agent_in_ancestry(chain=None):
    """True with the host agent among the ancestors, and when the ancestry cannot be read at all (chain None):
    unknown counts as the agent (R4-04)."""
    if chain is None:
        chain = process_chain()
    return chain is None or any(AGENT_PROCESS_NAMES & set(names) for names in chain)


def _blank_own_dirs(text, dirs):
    """Blank out mentions of the agent's own directories (proposals, challenges, views) only where the path stays
    inside them after normalization: `<views>/../ledger.jsonl` keeps its text, so the needle for G1's home finds it
    (R3-03). The length of the text is kept, so later matches keep their positions."""
    stop = set(" \t\n\r;&|()<>`'\"")
    for d in dirs:
        i = 0
        while True:
            j = text.find(d, i)
            if j < 0:
                break
            k = j + len(d)
            while k < len(text) and text[k] not in stop:
                k += 1
            norm = os.path.normpath(text[j:k])
            if norm == d or norm.startswith(d + os.sep):
                text = text[:j] + " " * (k - j) + text[k:]
            i = k
    return text


_PATH_NEEDLES = (".agents/hooks.json", ".system_generated")  # relative names: matched as a path, not inside prose (R4-07)


def _names_path(toks, needle):
    pat = re.compile(r"(?:^|/)" + re.escape(needle) + r"(?:/|$)")
    return any(pat.search(t) for t in toks)


def textual_gate(ctx, text, task):
    """Refuse shell commands that name G1's own state, the files G1 installs into the host or the host's conversation
    store, and commands that run G1's command line. The agent may mention its proposals, challenges and views
    directories, but not a path that leaves them. Pinned oracle files are NOT refused here: the agent may run its
    tests freely; an edit is caught by the hash check at verification. The absolute names are matched anywhere in
    the text; the relative ones (a workspace hooks file, a transcript directory) as a path token, so a commit
    message that mentions them is not refused (R4-07)."""
    if len(text) > GATE_MAX_BYTES:
        return (f"G1 refused a shell command of {len(text)} bytes: longer than {GATE_MAX_BYTES} bytes. "
                "Write files with a file tool, not through the shell.")
    head, tail = _split_for_gate(text)
    try:
        toks = _shell_tokens(head)
    except ValueError:
        toks = None
    if invokes_g1(text, toks=toks):
        return ("G1 command line refused: G1's commands are the user's (`g1 repair`, `host-verify`, `install`, `uninstall`, "
                "`turn-end`, `init`, `propose`, `challenges`, `challenge`); the status block and the state.json view carry "
                "what you need. Report what you need to the user instead.")
    home = os.path.expanduser("~")
    t = text.replace("~/", home + "/")
    if ctx.root:
        t = _blank_own_dirs(t, [paths.proposals_dir(ctx.root), paths.challenges_dir(ctx.root), paths.views_dir(ctx.root)])
    conv = conversations_root()
    needles = [os.path.realpath(paths.home()), paths.home(), global_hooks_path(), conv, os.path.realpath(conv)]
    for rel, p in integrity.host_file_paths(config_root()).items():
        needles.append(os.path.dirname(p) if rel.startswith("skills/") else p)
    view = f"{paths.views_dir(ctx.root) if ctx.root else '<views>'}/state.json"
    for n in needles:
        if n and n in t:
            if n in (conv, os.path.realpath(conv)):
                return f"G1 protected path referenced in the command: {n} holds conversation transcripts that G1 reads as evidence."
            return f"G1 protected path referenced in the command: {n}. G1 state is read-only for the agent; the task view is at {view}."
    for n in _PATH_NEEDLES:
        if _names_path((toks if toks is not None else head.split()) + tail.split(), n):
            return f"G1 protected path referenced in the command: {n}. G1 state is read-only for the agent; the task view is at {view}."
    return None


# ----- liveness gap -----
def compute_gap(ctx, since_ts):
    return compute_liveness(ctx, since_ts)["gap"]


def compute_liveness(ctx, since_ts):
    """Compare mutating tool calls recorded in host transcripts with the PreToolUse journals (PSN-08, ASC-15).
    Journals of every layer are merged: a call denied by one layer never reaches the other (measured).
    Returns {"gap": n, "unknown": [conversation ids]}. A conversation journaled since since_ts whose transcript
    is gone cannot be counted: it is reported as unknown, never as zero. It does not refuse completion, because a
    deleted session must not stop a fresh agent from continuing (two-way test, principles A2); the receipt records
    it, the status block shows it, and the agent's own tools cannot delete transcripts (protected_roots)."""
    if not ctx.obs:
        return {"gap": 0, "unknown": []}
    conv, observed, last_t = {}, {}, {}
    cp = os.path.join(ctx.obs, "conversations.json")  # written by G1 0.1 before the journal carried paths
    if os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8") as f:
                conv.update({k: v for k, v in json.load(f).items() if isinstance(k, str) and isinstance(v, str)})
        except (OSError, ValueError, AttributeError):
            pass
    for layer, suffix in (("global", ".1"), ("workspace", ".1"), ("global", ""), ("workspace", "")):
        jp = os.path.join(ctx.obs, f"journal-{layer}.jsonl{suffix}")
        if not os.path.exists(jp):
            continue
        with open(jp, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                cid = _str(r.get("cid"))
                if cid and isinstance(r.get("tp"), str):
                    conv[cid] = r["tp"]
                if cid and isinstance(r.get("t"), (int, float)):
                    last_t[cid] = max(last_t.get(cid, 0), r["t"])
                if r.get("kind") == "pre" and cid:
                    observed.setdefault(cid, set()).add(r.get("step"))
    gap, unknown = 0, []
    for cid, tp in conv.items():
        if not os.path.exists(tp):
            if last_t.get(cid, 0) >= since_ts:
                unknown.append(cid)
            continue
        try:
            if os.path.getmtime(tp) < since_ts:
                continue
            expected = 0
            with open(tp, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        j = json.loads(line)
                    except ValueError:
                        gap += 1
                        continue
                    if j.get("type") == "PLANNER_RESPONSE":
                        expected += sum(1 for tc in (j.get("tool_calls") or []) if tc.get("name") in MUTATING_TOOLS)
        except OSError:
            unknown.append(cid)
            continue
        gap += max(0, expected - len(observed.get(cid, ())))
    return {"gap": gap, "unknown": sorted(unknown)}


# ----- event handlers -----
def handle(event, payload, cwd):
    t0 = time.monotonic()
    ctx = Context(event, payload, cwd)
    if event == "PreToolUse":
        tc = ctx.payload.get("toolCall") or {}
        reason = gate(ctx)
        ctx.journal("pre", {"step": ctx.payload.get("stepIdx"), "tool": tc.get("name"), "denied": bool(reason),
                            "args_sha256": canon.sha256_text(json.dumps(tc.get("args") or {}, sort_keys=True)),
                            "ms": int((time.monotonic() - t0) * 1000)})
        return out({"decision": "deny", "reason": reason}) if reason else ""
    if event in ("PostToolUse", "PostInvocation"):
        return "{}"
    if event == "SessionStart":
        if ctx.primary and not ctx.enrolled and ctx.root:
            lost = integrity.lost_ledger(ctx.root)
            if lost is not None:
                # the workspace had a ledger (its witness remains) and the files are gone: nothing is enrolled again
                # until the user restores the ledger from the mirror or forgets it (g1 repair --restore | --forget)
                ctx.set_lockdown(f"ledger missing: the workspace witness names ledger {str(lost.get('ledger_id'))[:12]} "
                                 f"at seq {lost.get('seq')}; run: g1 repair --restore (from the mirror) or --forget")
                return out({"injectSteps": [{"ephemeralMessage": "[G1] ALERT: this workspace's ledger is missing. Mutating "
                                                                 "tools are refused until the user runs `g1 repair`."}]})
        if ctx.primary and not ctx.enrolled and paths.enrollable(ctx.root):
            try:
                ctx.ws.init()
                ctx.enrolled = True
            except Exception as e:
                ctx.journal("error", {"where": "auto-enrol", "error": repr(e)[:200]})
        if not (ctx.primary and ctx.enrolled):
            return ""
        return session_start(ctx)
    if event == "PreInvocation":
        if not (ctx.primary and ctx.enrolled):
            return ""
        try:
            notes = ctx.ws.process_proposals()
        except Exception as e:
            ctx.journal("error", {"where": "proposals", "error": repr(e)[:200]})
            notes = [f"G1 could not process the proposals directory: {e.__class__.__name__}"]
        text = ctx.ws.projection(ledger_mod.token_hex(3), TURN_MAX, session_start=False)
        if notes:
            from .. import project
            text = text + "\n" + "\n".join(project.oneline(n) for n in notes)
            text = text.encode("utf-8")[:TURN_MAX + 600].decode("utf-8", "ignore")
        ctx.journal("inject", {"event": "PreInvocation", "inv": ctx.payload.get("invocationNum"), "text": text,
                               "ms": int((time.monotonic() - t0) * 1000)})
        return out({"injectSteps": [{"ephemeralMessage": text}]})
    if event == "Stop":
        idle = bool(ctx.payload.get("fullyIdle", False))
        if not idle or not (ctx.primary and ctx.enrolled):
            ctx.journal("stop", {"fullyIdle": idle, "reason": ctx.payload.get("terminationReason"), "ms": int((time.monotonic() - t0) * 1000)})
            return out({"decision": "stop"})
        text = stop(ctx)
        ctx.journal("stop", {"fullyIdle": idle, "reason": ctx.payload.get("terminationReason"), "out": text[:120],
                             "ms": int((time.monotonic() - t0) * 1000)})
        return text
    return ""


def session_start(ctx):
    alerts = []
    status = anchor_check(ctx)
    if status == "unverifiable":
        return out({"injectSteps": [{"ephemeralMessage": "[G1] ALERT: the ledger does not verify. Mutating tools are refused "
                                                         "until the user runs `g1 repair`."}]})
    try:
        host_alert = host_check(ctx)
        if host_alert:
            alerts.append(host_alert)
    except Exception as e:
        alerts.append(f"host check failed: {e.__class__.__name__}")
    if ctx.manifest:
        healed = integrity.heal_workspace_hooks(ctx.root, ctx.manifest)
        if healed not in ("ok", "missing"):
            alerts.append(f"workspace hooks.json G1 entries were {healed}")
        gp = ctx.manifest.get("global_hooks_path")
        if ctx.manifest.get("global_installed") and gp and integrity.check_group_file(gp, ctx.manifest) != "ok":
            alerts.append("global hooks.json entries differ from the manifest; run: g1 install")
        try:
            restored = integrity.heal_host_files(ctx.manifest, config_root())
            if restored:
                alerts.append("restored G1 host files that had changed: " + ", ".join(restored))
        except Exception as e:
            alerts.append(f"host file check failed: {e.__class__.__name__}")
    text = ctx.ws.projection(ledger_mod.token_hex(3), SESSION_MAX, session_start=True)
    if alerts:
        text = "\n".join(alerts) + "\n" + text
    text = text.encode("utf-8")[:SESSION_MAX].decode("utf-8", "ignore")
    ctx.journal("inject", {"event": "SessionStart", "text": text})
    return out({"injectSteps": [{"ephemeralMessage": text}]})


def anchor_check(ctx):
    """Compare the ledger with its anchor (integrity.check_anchor). A diverged or unverifiable ledger locks the
    workspace down without writing to it, so the evidence stays as found; the user decides with `g1 repair`."""
    try:
        status, detail = ctx.ws.check_anchor()
    except Exception as e:
        ctx.set_lockdown(f"ledger unverifiable: {e.__class__.__name__}: {e}"[:300])
        return "unverifiable"
    if status == "diverged":
        ctx.set_lockdown(f"ledger diverged from its anchor: {detail}"[:300])
    elif status == "repaired":
        ctx.ws.append("integrity_alert", {"kind": "ledger_repaired", "detail": detail[:300]})
    return status


def stop(ctx):
    try:
        if ctx.locked_down() or anchor_check(ctx) in ("diverged", "unverifiable"):
            return out({"decision": "stop"})  # no verification and no completion while integrity is in doubt
        ctx.ws.process_reports()  # a blocked report written this turn pauses the task before any verification
        s = ctx.ws.state()
        t = state_mod.active_task(s)
        if t is None:
            ctx.ws.process_proposals()
            return out({"decision": "stop"})
        since = os.path.getmtime(ctx.ws.ledger.path) - 3600
        live = compute_liveness(ctx, since)
        d = ctx.ws.turn_end(gap=live["gap"], liveness_unknown=len(live["unknown"]))
        if d["decision"] == "continue":
            return out({"decision": "continue", "reason": d["reason"]})
        return out({"decision": "stop"})
    except Exception as e:
        try:
            ctx.journal("error", {"where": "stop", "error": repr(e)[:300]})
        except Exception:
            pass
        return out({"decision": "stop"})
