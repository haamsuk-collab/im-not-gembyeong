"""Reference implementation used only to validate the hidden oracle."""
import re
from collections import namedtuple

Version = namedtuple("Version", "major minor patch prerelease build")
_NUM = re.compile(r"^(0|[1-9][0-9]*)$")
_ID = re.compile(r"^[0-9A-Za-z-]+$")


def parse(text):
    if not isinstance(text, str) or not re.fullmatch(r"[0-9A-Za-z.+-]+", text or ""):
        raise ValueError(text)
    core, plus, build = text.partition("+")
    core, dash, pre = core.partition("-")
    parts = core.split(".")
    if len(parts) != 3 or not all(_NUM.match(p) for p in parts):
        raise ValueError(text)
    pre_ids, build_ids = (), ()
    if dash:
        ids = pre.split(".")
        if not all(_ID.match(i) for i in ids):
            raise ValueError(text)
        out = []
        for i in ids:
            if i.isdigit():
                if not _NUM.match(i):
                    raise ValueError(text)
                out.append(int(i))
            else:
                out.append(i)
        pre_ids = tuple(out)
    if plus:
        ids = build.split(".")
        if not all(_ID.match(i) for i in ids):
            raise ValueError(text)
        build_ids = tuple(ids)
    return Version(int(parts[0]), int(parts[1]), int(parts[2]), pre_ids, build_ids)


def _cmp_id(a, b):
    if isinstance(a, int) and isinstance(b, int):
        return (a > b) - (a < b)
    if isinstance(a, int):
        return -1
    if isinstance(b, int):
        return 1
    return (a > b) - (a < b)


def compare(a, b):
    x, y = parse(a), parse(b)
    c = (x[:3] > y[:3]) - (x[:3] < y[:3])
    if c:
        return c
    if x.prerelease == y.prerelease:
        return 0
    if not x.prerelease:
        return 1
    if not y.prerelease:
        return -1
    for i, j in zip(x.prerelease, y.prerelease):
        r = _cmp_id(i, j)
        if r:
            return r
    return (len(x.prerelease) > len(y.prerelease)) - (len(x.prerelease) < len(y.prerelease))


def bump(text, part):
    v = parse(text)
    if part not in ("major", "minor", "patch"):
        raise ValueError(part)
    M, m, p = v.major, v.minor, v.patch
    if v.prerelease:
        if part == "patch" or (part == "minor" and p == 0) or (part == "major" and m == 0 and p == 0):
            return f"{M}.{m}.{p}"
    if part == "patch":
        return f"{M}.{m}.{p + 1}"
    if part == "minor":
        return f"{M}.{m + 1}.0"
    return f"{M + 1}.0.0"
