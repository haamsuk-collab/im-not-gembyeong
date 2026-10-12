"""Canonical encoding and hashing.

Rules (design 4.3): UTF-8, sorted keys, compact separators, no floats,
integers within +/-(2**53 - 1), duplicate keys rejected, no trailing data, no lone surrogates
(a string must be encodable as UTF-8). Strings are hashed as the exact code points they hold;
there is no Unicode normalization, because two file names that differ only in normalization
are two different files.
"""

import hashlib
import json
import re

INT_LIMIT = 2 ** 53 - 1


class CanonError(ValueError):
    pass


def _text(s, path):
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        raise CanonError(f"{path}: string is not valid Unicode (lone surrogate)") from None


def _check(obj, path="$"):
    if obj is None or isinstance(obj, bool):
        return
    if isinstance(obj, str):
        _text(obj, path)
        return
    if isinstance(obj, int):
        if abs(obj) > INT_LIMIT:
            raise CanonError(f"{path}: integer outside +/-2^53-1")
        return
    if isinstance(obj, float):
        raise CanonError(f"{path}: floats are not allowed")
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check(v, f"{path}[{i}]")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonError(f"{path}: non-string key")
            _text(k, f"{path} key {k!r}")
            _check(v, f"{path}.{k!r}")
        return
    raise CanonError(f"{path}: unsupported type {type(obj).__name__}")


def dumps(obj):
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise CanonError(f"duplicate key: {k!r}")
        out[k] = v
    return out


def _no_float(s):
    raise CanonError(f"float literal not allowed: {s}")


def loads(text):
    """Strict decode: duplicate keys, floats and trailing data are errors."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    dec = json.JSONDecoder(object_pairs_hook=_pairs, parse_float=_no_float, parse_constant=_no_float)
    obj, end = dec.raw_decode(text)
    if text[end:].strip():
        raise CanonError("trailing data after JSON value")
    _check(obj)
    return obj


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")  # task, check, criterion and challenge ids


def sha256_text(text):
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def domain_hash(domain, obj):
    """Domain-separated hash of a canonical object."""
    h = hashlib.sha256()
    h.update(domain.encode("utf-8"))
    h.update(b"\x00")
    h.update(dumps(obj).encode("utf-8"))
    return h.hexdigest()
