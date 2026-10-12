"""Harder fixtures for ab.py: each test file holds edge cases that are easy to miss."""

HEAD = "import sys, os\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"

FIXTURES_HARD = {
    "h1-roman": {
        "src": "src/roman.py", "test": "tests/test_roman.py",
        "stub": "def to_roman(n):\n    return ''\n\n\ndef from_roman(s):\n    return 0\n",
        "tests": HEAD + "from roman import to_roman, from_roman\n\n"
                 "def test_to():\n    assert to_roman(1) == 'I'\n    assert to_roman(4) == 'IV'\n    assert to_roman(1994) == 'MCMXCIV'\n    assert to_roman(3999) == 'MMMCMXCIX'\n\n"
                 "def test_to_range():\n    for bad in (0, 4000, -5):\n        try:\n            to_roman(bad)\n        except ValueError:\n            continue\n        raise AssertionError(f'to_roman({bad}) must raise ValueError')\n\n"
                 "def test_from():\n    assert from_roman('MCMXCIV') == 1994\n    assert from_roman('iv') == 4\n    assert from_roman(' XLII ') == 42\n\n"
                 "def test_from_invalid():\n    for bad in ('IIII', 'VV', 'IM', 'MMMM', '', 'ABC', 'IC'):\n        try:\n            from_roman(bad)\n        except ValueError:\n            continue\n        raise AssertionError(f'from_roman({bad!r}) must raise ValueError')\n\n"
                 "def test_roundtrip():\n    for n in range(1, 4000):\n        assert from_roman(to_roman(n)) == n\n\n"
                 "if __name__ == '__main__':\n    test_to(); test_to_range(); test_from(); test_from_invalid(); test_roundtrip(); print('ok')\n",
    },
    "h2-intervals": {
        "src": "src/intervals.py", "test": "tests/test_intervals.py",
        "stub": "def merge(intervals):\n    return intervals\n",
        "tests": HEAD + "from intervals import merge\n\n"
                 "def test_basic():\n    assert merge([(1, 3), (2, 6), (8, 10), (15, 18)]) == [(1, 6), (8, 10), (15, 18)]\n\n"
                 "def test_unsorted_and_touching():\n    assert merge([(8, 10), (1, 4), (4, 5)]) == [(1, 5), (8, 10)]\n\n"
                 "def test_contained_and_duplicates():\n    assert merge([(1, 10), (2, 3), (2, 3), (9, 12)]) == [(1, 12)]\n\n"
                 "def test_empty_and_single():\n    assert merge([]) == []\n    assert merge([(5, 5)]) == [(5, 5)]\n\n"
                 "def test_input_not_mutated_and_tuples():\n    data = [(3, 4), (1, 2)]\n    out = merge(data)\n    assert data == [(3, 4), (1, 2)]\n    assert out == [(1, 2), (3, 4)]\n    assert all(type(x) is tuple for x in out)\n\n"
                 "def test_invalid():\n    for bad in ([(2, 1)], [(1, 'a')], [(1,)]):\n        try:\n            merge(bad)\n        except ValueError:\n            continue\n        raise AssertionError(f'merge({bad}) must raise ValueError')\n\n"
                 "if __name__ == '__main__':\n    test_basic(); test_unsorted_and_touching(); test_contained_and_duplicates(); test_empty_and_single(); test_input_not_mutated_and_tuples(); test_invalid(); print('ok')\n",
    },
    "h3-lru": {
        "src": "src/lru.py", "test": "tests/test_lru.py",
        "stub": "class LRU:\n    def __init__(self, capacity):\n        self.capacity = capacity\n\n    def get(self, key):\n        return None\n\n    def put(self, key, value):\n        pass\n\n    def __len__(self):\n        return 0\n",
        "tests": HEAD + "from lru import LRU\n\n"
                 "def test_basic():\n    c = LRU(2)\n    c.put('a', 1); c.put('b', 2)\n    assert c.get('a') == 1\n    c.put('c', 3)  # evicts b (a was used more recently)\n    assert c.get('b') is None\n    assert c.get('c') == 3\n    assert len(c) == 2\n\n"
                 "def test_update_moves_to_front():\n    c = LRU(2)\n    c.put('a', 1); c.put('b', 2); c.put('a', 10)\n    c.put('c', 3)  # evicts b\n    assert c.get('a') == 10 and c.get('b') is None\n\n"
                 "def test_get_missing_does_not_change_order():\n    c = LRU(2)\n    c.put('a', 1); c.put('b', 2)\n    assert c.get('zzz') is None\n    c.put('c', 3)  # evicts a\n    assert c.get('a') is None and c.get('b') == 2\n\n"
                 "def test_none_values_and_keys_view():\n    c = LRU(2)\n    c.put('k', None)\n    assert 'k' in c.keys() and len(c) == 1\n    c.put('x', 1); c.put('y', 2)\n    assert list(c.keys()) == ['x', 'y']  # most recent last\n\n"
                 "def test_capacity_validation():\n    for bad in (0, -1, 1.5):\n        try:\n            LRU(bad)\n        except ValueError:\n            continue\n        raise AssertionError(f'LRU({bad}) must raise ValueError')\n\n"
                 "if __name__ == '__main__':\n    test_basic(); test_update_moves_to_front(); test_get_missing_does_not_change_order(); test_none_values_and_keys_view(); test_capacity_validation(); print('ok')\n",
    },
    "h4-csv": {
        "src": "src/minicsv.py", "test": "tests/test_minicsv.py",
        "stub": "def parse_line(line):\n    return line.split(',')\n",
        "tests": HEAD + "from minicsv import parse_line\n\n"
                 "def test_plain():\n    assert parse_line('a,b,c') == ['a', 'b', 'c']\n    assert parse_line('') == ['']\n    assert parse_line('a,,c') == ['a', '', 'c']\n\n"
                 "def test_quotes():\n    assert parse_line('\"a,b\",c') == ['a,b', 'c']\n    assert parse_line('\"he said \"\"hi\"\"\",x') == ['he said \"hi\"', 'x']\n    assert parse_line('\"\",\"\"') == ['', '']\n\n"
                 "def test_whitespace_kept():\n    assert parse_line(' a , b ') == [' a ', ' b ']\n\n"
                 "def test_trailing_comma_and_newline():\n    assert parse_line('a,b,') == ['a', 'b', '']\n    assert parse_line('a,b\\n') == ['a', 'b']\n\n"
                 "def test_invalid():\n    for bad in ('\"unterminated', 'a\"b', '\"a\"b'):\n        try:\n            parse_line(bad)\n        except ValueError:\n            continue\n        raise AssertionError(f'parse_line({bad!r}) must raise ValueError')\n\n"
                 "if __name__ == '__main__':\n    test_plain(); test_quotes(); test_whitespace_kept(); test_trailing_comma_and_newline(); test_invalid(); print('ok')\n",
    },
    "h5-topo": {
        "src": "src/topo.py", "test": "tests/test_topo.py",
        "stub": "def topo_sort(graph):\n    return list(graph)\n",
        "tests": HEAD + "from topo import topo_sort\n\n"
                 "def test_basic():\n    g = {'a': ['b', 'c'], 'b': ['d'], 'c': ['d'], 'd': []}\n    assert topo_sort(g) == ['a', 'b', 'c', 'd']\n\n"
                 "def test_lexicographic_tiebreak():\n    g = {'z': [], 'y': [], 'x': ['z']}\n    assert topo_sort(g) == ['x', 'y', 'z']\n\n"
                 "def test_implicit_nodes():\n    assert topo_sort({'a': ['b']}) == ['a', 'b']\n\n"
                 "def test_empty():\n    assert topo_sort({}) == []\n\n"
                 "def test_cycle():\n    for g in ({'a': ['b'], 'b': ['a']}, {'a': ['a']}):\n        try:\n            topo_sort(g)\n        except ValueError as e:\n            assert 'cycle' in str(e).lower()\n            continue\n        raise AssertionError('a cycle must raise ValueError mentioning cycle')\n\n"
                 "def test_deterministic_large():\n    g = {str(i): [str(j) for j in range(i + 1, min(i + 3, 30))] for i in range(30)}\n    out = topo_sort(g)\n    assert sorted(out) == sorted(g)\n    pos = {n: i for i, n in enumerate(out)}\n    for a, deps in g.items():\n        for b in deps:\n            assert pos[a] < pos[b]\n\n"
                 "if __name__ == '__main__':\n    test_basic(); test_lexicographic_tiebreak(); test_implicit_nodes(); test_empty(); test_cycle(); test_deterministic_large(); print('ok')\n",
    },
    "h6-timerange": {
        "src": "src/timerange.py", "test": "tests/test_timerange.py",
        "stub": "def minutes(spec):\n    return 0\n",
        "tests": HEAD + "from timerange import minutes\n\n"
                 "def test_basic():\n    assert minutes('09:30-17:45') == 495\n    assert minutes('00:00-00:00') == 0\n\n"
                 "def test_wrap_midnight():\n    assert minutes('22:15-01:05') == 170\n\n"
                 "def test_spaces_and_multiple():\n    assert minutes(' 09:00 - 10:00 , 13:00-13:30') == 90\n\n"
                 "def test_overlap_counted_once():\n    assert minutes('09:00-11:00,10:00-12:00') == 180\n\n"
                 "def test_invalid():\n    for bad in ('9:00-10:00', '09:60-10:00', '24:00-01:00', '09:00', '09:00-10:00-11:00', ''):\n        try:\n            minutes(bad)\n        except ValueError:\n            continue\n        raise AssertionError(f'minutes({bad!r}) must raise ValueError')\n\n"
                 "if __name__ == '__main__':\n    test_basic(); test_wrap_midnight(); test_spaces_and_multiple(); test_overlap_counted_once(); test_invalid(); print('ok')\n",
    },
}
