import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from semver import bump, compare, parse  # noqa: E402


def test_parse_basic():
    v = parse("1.2.3")
    assert (v.major, v.minor, v.patch, v.prerelease, v.build) == (1, 2, 3, (), ())


def test_compare_major():
    assert compare("1.0.0", "2.0.0") == -1


def test_prerelease_is_lower():
    assert compare("1.0.0-alpha", "1.0.0") == -1


def test_bump_minor():
    assert bump("1.2.3", "minor") == "1.3.0"


def test_leading_zero_rejected():
    try:
        parse("01.2.3")
    except ValueError:
        return
    raise AssertionError("01.2.3 must be rejected")


def test_build_ignored():
    assert compare("1.0.0+build", "1.0.0") == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
