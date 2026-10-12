"""Hidden oracle for the semver-lite experiment: every rule of SPEC.md as one case. Never placed in the workspace.

Usage: python3 hidden_oracle.py <project dir>   -> prints one line per failing case and a JSON summary.
Each case has an id and the SPEC rule it tests, so a challenge can be matched to the defect class it proves.
"""
import importlib.util
import json
import os
import sys

proj = sys.argv[1]
spec = importlib.util.spec_from_file_location("semver_under_test", os.path.join(proj, "src", "semver.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CASES = []


def case(cid, rule):
    def deco(fn):
        CASES.append((cid, rule, fn))
        return fn
    return deco


def raises(fn, *a):
    try:
        fn(*a)
    except ValueError:
        return True
    except Exception:
        return False
    return False


V = lambda *a: tuple(a)  # noqa: E731


# ----- grammar, valid
@case("G-valid-basic", "grammar")
def _():
    return tuple(m.parse("0.0.0")) == (0, 0, 0, (), ())

@case("G-valid-prerelease-types", "grammar")
def _():
    return tuple(m.parse("1.0.0-alpha.1.x-y")) == (1, 0, 0, ("alpha", 1, "x-y"), ())

@case("G-valid-build-leading-zero", "grammar 3")
def _():
    return tuple(m.parse("1.0.0+001.build")) == (1, 0, 0, (), ("001", "build"))

@case("G-valid-hyphen-identifiers", "grammar 2")
def _():
    return tuple(m.parse("1.0.0-x-y-z.--")) == (1, 0, 0, ("x-y-z", "--"), ())

@case("G-valid-big-numbers", "grammar 1")
def _():
    return m.parse("10000000000000000000.0.0").major == 10000000000000000000

@case("G-valid-alnum-with-leading-zero", "grammar 2")
def _():
    return tuple(m.parse("1.0.0-0a")) == (1, 0, 0, ("0a",), ())

@case("G-valid-pre-and-build", "grammar")
def _():
    return tuple(m.parse("1.0.0-rc.1+build.5")) == (1, 0, 0, ("rc", 1), ("build", "5"))


# ----- grammar, invalid
for cid, text, rule in [
    ("I-leading-zero-minor", "1.02.3", "grammar 1"), ("I-leading-zero-patch", "1.2.03", "grammar 1"),
    ("I-missing-patch", "1.2", "grammar 4"), ("I-extra-part", "1.2.3.4", "grammar 4"),
    ("I-v-prefix", "v1.2.3", "grammar 4"), ("I-whitespace", " 1.2.3", "grammar 4"), ("I-trailing-ws", "1.2.3\n", "grammar 4"),
    ("I-negative", "-1.2.3", "grammar 1"), ("I-empty-prerelease", "1.0.0-", "grammar 3"),
    ("I-empty-identifier", "1.0.0-alpha..1", "grammar 3"), ("I-empty-build", "1.0.0+", "grammar 3"),
    ("I-empty-build-identifier", "1.0.0+a..b", "grammar 3"), ("I-underscore", "1.0.0-al_pha", "grammar 2"),
    ("I-numeric-leading-zero", "1.0.0-01", "grammar 2"), ("I-unicode-digit", "1.0.٣", "grammar 1"),
    ("I-plus-in-build", "1.0.0+a+b", "grammar 3"), ("I-empty", "", "grammar 4"),
]:
    CASES.append((cid, rule, (lambda t: (lambda: raises(m.parse, t)))(text)))


# ----- precedence
CHAIN = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]

@case("P-spec-chain", "precedence 2-3")
def _():
    return all(m.compare(a, b) == -1 and m.compare(b, a) == 1 for a, b in zip(CHAIN, CHAIN[1:]))

@case("P-numeric-ids-numeric", "precedence 3")
def _():
    return m.compare("1.0.0-2", "1.0.0-10") == -1

@case("P-numeric-below-alnum", "precedence 3")
def _():
    return m.compare("1.0.0-1", "1.0.0-a") == -1 and m.compare("1.0.0-a", "1.0.0-1") == 1

@case("P-ascii-order", "precedence 3")
def _():
    return m.compare("1.0.0-Z", "1.0.0-a") == -1

@case("P-longer-list-higher", "precedence 3")
def _():
    return m.compare("1.0.0-alpha", "1.0.0-alpha.0") == -1

@case("P-build-ignored-in-prerelease", "precedence 4")
def _():
    return m.compare("1.0.0-alpha+001", "1.0.0-alpha+002") == 0

@case("P-numeric-core", "precedence 1")
def _():
    return m.compare("1.10.0", "1.9.0") == 1 and m.compare("1.0.10", "1.0.9") == 1

@case("P-equal", "precedence")
def _():
    return m.compare("1.2.3-rc.1", "1.2.3-rc.1") == 0

@case("P-invalid-raises", "API compare")
def _():
    return raises(m.compare, "1.0", "1.0.0") and raises(m.compare, "1.0.0", "x")


# ----- bump
for cid, text, part, want, rule in [
    ("B-patch", "1.2.3", "patch", "1.2.4", "bump normal"), ("B-major", "1.2.3", "major", "2.0.0", "bump normal"),
    ("B-drops-build", "1.2.3+b5", "patch", "1.2.4", "bump build dropped"),
    ("B-pre-patch", "1.2.3-rc.1", "patch", "1.2.3", "bump pre-release"),
    ("B-pre-minor-to-release", "1.3.0-rc.1", "minor", "1.3.0", "bump pre-release"),
    ("B-pre-major-to-release", "2.0.0-rc.1", "major", "2.0.0", "bump pre-release"),
    ("B-pre-minor-normal", "1.2.3-rc.1", "minor", "1.3.0", "bump pre-release"),
    ("B-pre-major-normal", "1.2.3-rc.1", "major", "2.0.0", "bump pre-release"),
    ("B-pre-minor-normal-2", "1.2.0-rc.1", "major", "2.0.0", "bump pre-release"),
]:
    CASES.append((cid, rule, (lambda t, p, w: (lambda: m.bump(t, p) == w))(text, part, want)))

@case("B-bad-part", "API bump")
def _():
    return raises(m.bump, "1.2.3", "build") and raises(m.bump, "1.2.3", "Patch")

@case("B-invalid-version", "API bump")
def _():
    return raises(m.bump, "1.2", "patch")


failed = []
for cid, rule, fn in CASES:
    try:
        ok = bool(fn())
    except Exception as e:
        ok = False
    if not ok:
        failed.append((cid, rule))
        print(f"FAIL {cid} ({rule})")
print(json.dumps({"cases": len(CASES), "failed": len(failed), "failed_ids": [c for c, _ in failed]}))
