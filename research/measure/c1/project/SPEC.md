# semver-lite specification

Implement `src/semver.py` with three functions. Follow Semantic Versioning 2.0.0 exactly as stated here.

## Grammar

A version is `MAJOR.MINOR.PATCH`, optionally followed by `-PRERELEASE`, optionally followed by `+BUILD`.

1. MAJOR, MINOR and PATCH are non-negative integers written in decimal without leading zeros (`0` is fine, `01` is not).
2. PRERELEASE is one or more identifiers separated by dots. An identifier is a non-empty string of ASCII letters,
   digits and hyphens `[0-9A-Za-z-]`. An identifier made only of digits is numeric and must not have leading zeros.
3. BUILD is one or more identifiers separated by dots, with the same character set. Build identifiers may have leading
   zeros. No identifier, in PRERELEASE or BUILD, may be empty.
4. Nothing else is allowed: no leading `v`, no whitespace anywhere, no missing parts.

## API

- `parse(text)` returns `Version(major, minor, patch, prerelease, build)`, a `namedtuple` with ints for the first three
  fields, a tuple for `prerelease` in which numeric identifiers are ints and the others are strings, and a tuple of
  strings for `build`. Invalid text raises `ValueError`.
- `compare(a, b)` takes two version strings and returns -1, 0 or 1 by precedence. Invalid input raises `ValueError`.
- `bump(text, part)` returns the next version as a string, for `part` in `"major"`, `"minor"`, `"patch"`; any other
  part raises `ValueError`. Build metadata is always dropped. For a version without PRERELEASE: `patch` adds 1 to
  PATCH; `minor` adds 1 to MINOR and sets PATCH to 0; `major` adds 1 to MAJOR and sets MINOR and PATCH to 0. For a
  version with PRERELEASE, the bump gives the release that the pre-release leads to when that release is the requested
  kind: `1.2.3-rc.1` bumped by `patch` is `1.2.3`; `1.3.0-rc.1` bumped by `minor` is `1.3.0`; `2.0.0-rc.1` bumped by
  `major` is `2.0.0`. Otherwise the pre-release is dropped and the normal rule applies to MAJOR.MINOR.PATCH:
  `1.2.3-rc.1` bumped by `minor` is `1.3.0`, and by `major` is `2.0.0`.

## Precedence

1. Compare MAJOR, then MINOR, then PATCH, numerically.
2. When those are equal, a version with PRERELEASE has lower precedence than the same version without it.
3. Two PRERELEASE lists are compared identifier by identifier from left to right. Numeric identifiers compare
   numerically. Other identifiers compare lexically in ASCII order. A numeric identifier has lower precedence than a
   non-numeric one. If all identifiers of the shorter list equal the start of the longer list, the longer list has
   higher precedence.
4. BUILD is ignored for precedence: `1.0.0+a` and `1.0.0+b` compare equal.

Example chain, each lower than the next: `1.0.0-alpha`, `1.0.0-alpha.1`, `1.0.0-alpha.beta`, `1.0.0-beta`,
`1.0.0-beta.2`, `1.0.0-beta.11`, `1.0.0-rc.1`, `1.0.0`.
