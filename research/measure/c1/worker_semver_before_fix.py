"""semver-lite: see SPEC.md."""
import re
from collections import namedtuple

Version = namedtuple("Version", "major minor patch prerelease build")

_IDENT_CHAR_RE = re.compile(r"^[0-9A-Za-z-]+$")
_NUMERIC_RE = re.compile(r"^[0-9]+$")


def parse(text):
    if not isinstance(text, str) or not text:
        raise ValueError("Invalid version: must be a non-empty string")

    if "+" in text:
        main_part, build_part = text.split("+", 1)
        if "+" in build_part:
            raise ValueError("Multiple '+' delimiters in version string")
        build_raw = build_part.split(".")
        build = []
        for ident in build_raw:
            if not ident or not _IDENT_CHAR_RE.match(ident):
                raise ValueError(f"Invalid build identifier: {ident!r}")
            build.append(ident)
        build_tuple = tuple(build)
    else:
        main_part = text
        build_tuple = ()

    if "-" in main_part:
        core_part, prerelease_part = main_part.split("-", 1)
        prerelease_raw = prerelease_part.split(".")
        prerelease = []
        for ident in prerelease_raw:
            if not ident or not _IDENT_CHAR_RE.match(ident):
                raise ValueError(f"Invalid prerelease identifier: {ident!r}")
            if _NUMERIC_RE.match(ident):
                if len(ident) > 1 and ident.startswith("0"):
                    raise ValueError(f"Numeric prerelease identifier with leading zero: {ident!r}")
                prerelease.append(int(ident))
            else:
                prerelease.append(ident)
        prerelease_tuple = tuple(prerelease)
    else:
        core_part = main_part
        prerelease_tuple = ()

    core_raw = core_part.split(".")
    if len(core_raw) != 3:
        raise ValueError(f"Invalid core version: expected MAJOR.MINOR.PATCH, got {core_part!r}")

    core_nums = []
    for part in core_raw:
        if not part or not _NUMERIC_RE.match(part):
            raise ValueError(f"Invalid core version part: {part!r}")
        if len(part) > 1 and part.startswith("0"):
            raise ValueError(f"Leading zero in core version part: {part!r}")
        core_nums.append(int(part))

    return Version(core_nums[0], core_nums[1], core_nums[2], prerelease_tuple, build_tuple)


def compare(a, b):
    va = parse(a)
    vb = parse(b)

    if (va.major, va.minor, va.patch) < (vb.major, vb.minor, vb.patch):
        return -1
    if (va.major, va.minor, va.patch) > (vb.major, vb.minor, vb.patch):
        return 1

    if va.prerelease and not vb.prerelease:
        return -1
    if not va.prerelease and vb.prerelease:
        return 1
    if not va.prerelease and not vb.prerelease:
        return 0

    for ida, idb in zip(va.prerelease, vb.prerelease):
        if ida == idb:
            continue
        if isinstance(ida, int) and isinstance(idb, int):
            return -1 if ida < idb else 1
        if isinstance(ida, int) and isinstance(idb, str):
            return -1
        if isinstance(ida, str) and isinstance(idb, int):
            return 1
        return -1 if ida < idb else 1

    if len(va.prerelease) < len(vb.prerelease):
        return -1
    if len(va.prerelease) > len(vb.prerelease):
        return 1

    return 0


def bump(text, part):
    if part not in ("major", "minor", "patch"):
        raise ValueError(f"Invalid bump part: {part!r}")

    v = parse(text)

    if v.prerelease:
        if v.patch > 0:
            lead_kind = "patch"
        elif v.minor > 0:
            lead_kind = "minor"
        else:
            lead_kind = "major"

        if lead_kind == part:
            return f"{v.major}.{v.minor}.{v.patch}"

    if part == "patch":
        return f"{v.major}.{v.minor}.{v.patch + 1}"
    if part == "minor":
        return f"{v.major}.{v.minor + 1}.0"
    return f"{v.major + 1}.0.0"

