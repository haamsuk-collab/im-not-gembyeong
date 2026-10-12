"""Fixtures meant to have a non-zero native failure rate: many strict cases per task."""

HEAD = "import sys, os\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"

FIXTURES_X = {
    "x1-json": {
        "src": "src/strictjson.py", "test": "tests/test_strictjson.py",
        "stub": "def parse(text):\n    raise NotImplementedError\n",
        "tests": HEAD + "from strictjson import parse\n\n"
"def test_values():\n"
"    assert parse('{\"a\": [1, 2.5, -0, 1e3, true, null, \"x\"]}') == {'a': [1, 2.5, 0, 1000.0, True, None, 'x']}\n"
"    assert parse(' \\n{ \"k\" : \"v\" }\\t') == {'k': 'v'}\n"
"    assert parse('true') is True and parse('null') is None and parse('\"s\"') == 's'\n"
"    assert parse('[[[[[[[[[[1]]]]]]]]]]') == [[[[[[[[[[1]]]]]]]]]]\n"
"    assert parse('[' + ','.join(['1'] * 10000) + ']') == [1] * 10000\n\n"
"def test_numbers():\n"
"    assert parse('123456789012345678901234567890') == 123456789012345678901234567890\n"
"    v = parse('1E+2'); assert v == 100.0 and isinstance(v, float)\n"
"    assert parse('-1.5e-3') == -0.0015\n"
"    assert parse('-0') == 0 and isinstance(parse('-0'), int)\n"
"    assert parse('0.5') == 0.5\n\n"
"def test_strings():\n"
"    assert parse('\"\\\\u00e9\"') == '\\u00e9'\n"
"    assert parse('\"\\\\ud83d\\\\ude00\"') == '\\U0001F600'\n"
"    assert parse('\"a\\\\\"b\\\\\\\\c\\\\n\"') == 'a\"b\\\\c\\n'\n"
"    assert parse('\"\\\\/\"') == '/'\n\n"
"def test_invalid():\n"
"    bad = ['{\"a\":1,}', '[1,]', '01', '+1', '1.', '.5', 'NaN', 'Infinity', '-Infinity', \"'x'\", '{\"a\":1 \"b\":2}',\n"
"           '\"\\\\x41\"', '\"lone \\\\ud83d\"', '\"tab\\there\"', '', '   ', '{\"a\":1} x', 'tru', '[', '{\"a\":1,\"a\":2}',\n"
"           '\"\\\\u12\"', '{a:1}', '[1 2]', '{\"a\"}', '--1', '1e', '0x10', 'True', '\"unterminated']\n"
"    for b in bad:\n"
"        try:\n"
"            parse(b)\n"
"        except ValueError:\n"
"            continue\n"
"        raise AssertionError(f'parse({b!r}) must raise ValueError')\n\n"
"if __name__ == '__main__':\n    test_values(); test_numbers(); test_strings(); test_invalid(); print('ok')\n",
    },
    "x2-regex": {
        "src": "src/minire.py", "test": "tests/test_minire.py",
        "stub": "def fullmatch(pattern, text):\n    return pattern == text\n",
        "tests": HEAD + "from minire import fullmatch\n\n"
"CASES = [('abc', 'abc', True), ('abc', 'abcd', False), ('a.c', 'abc', True), ('a.c', 'ac', False),\n"
"         ('a*', '', True), ('a*', 'aaa', True), ('a+', '', False), ('ab?c', 'ac', True), ('ab?c', 'abbc', False),\n"
"         ('a|b', 'b', True), ('a|b', 'ab', False), ('(ab)*', 'ababab', True), ('(ab)*', 'aba', False),\n"
"         ('(a|b)+c', 'abbac', True), ('((ab)*c)+', 'ababcc', True), ('((ab)*c)+', 'ababcab', False),\n"
"         ('[abc]+', 'cab', True), ('[a-c]+', 'd', False), ('[^a-c]+', 'xyz', True), ('[^a-c]+', 'xya', False),\n"
"         ('\\\\d+', '123', True), ('\\\\d+', '12a', False), ('\\\\w+', 'ab_1', True), ('\\\\s*', '  ', True),\n"
"         ('a\\\\.b', 'a.b', True), ('a\\\\.b', 'axb', False), ('.*', 'anything at all', True),\n"
"         ('a*b*c*', 'aabbcc', True), ('a*a*a*b', 'aaab', True), ('(a*)*b', 'aaab', True), ('(a*)*b', 'aaac', False),\n"
"         ('(a|ab)(c|bcd)', 'abcd', True), ('(a|ab)(c|bcd)(d*)', 'abcd', True), ('x(y|)z', 'xz', True), ('x(y|)z', 'xyz', True),\n"
"         ('\\\\(a\\\\)', '(a)', True), ('[.]', 'a', False), ('[.]', '.', True), ('\\u00e9+', '\\u00e9\\u00e9', True),\n"
"         ('a|b|c', 'c', True), ('', '', True), ('', 'a', False), ('a?a?a?aaa', 'aaa', True), ('(a+)+b', 'aaaaaaaaaaaaaaaaaaaaaaaac', False)]\n\n"
"def test_cases():\n"
"    for p, t, want in CASES:\n"
"        got = fullmatch(p, t)\n"
"        assert got == want, (p, t, got, want)\n\n"
"def test_invalid_patterns():\n"
"    for bad in ('(ab', 'ab)', '*a', 'a**', '[abc', 'a++', '+', 'a|*'):\n"
"        try:\n"
"            fullmatch(bad, 'x')\n"
"        except ValueError:\n"
"            continue\n"
"        raise AssertionError(f'pattern {bad!r} must raise ValueError')\n\n"
"if __name__ == '__main__':\n    test_cases(); test_invalid_patterns(); print('ok')\n",
    },
    "x3-markdown": {
        "src": "src/minimd.py", "test": "tests/test_minimd.py",
        "stub": "def render(md):\n    return md\n",
        "tests": HEAD + "from minimd import render\n\n"
"CASES = [\n"
"    ('Hello', '<p>Hello</p>'),\n"
"    ('# Title', '<h1>Title</h1>'), ('### Sub', '<h3>Sub</h3>'), ('#### x', '<p>#### x</p>'), ('#no space', '<p>#no space</p>'),\n"
"    ('a\\nb', '<p>a b</p>'), ('a\\n\\nb', '<p>a</p>\\n<p>b</p>'), ('  \\n\\n\\n', ''), ('', ''),\n"
"    ('- one\\n- two', '<ul><li>one</li><li>two</li></ul>'),\n"
"    ('- a\\n  - b\\n- c', '<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>'),\n"
"    ('- a\\n  - b\\n  - c\\n- d', '<ul><li>a<ul><li>b</li><li>c</li></ul></li><li>d</li></ul>'),\n"
"    ('**b** and *i* and `c`', '<p><strong>b</strong> and <em>i</em> and <code>c</code></p>'),\n"
"    ('`*x*`', '<p><code>*x*</code></p>'), ('*a', '<p>*a</p>'), ('**a*', '<p>**a*</p>'),\n"
"    ('[t](http://x)', '<p><a href=\"http://x\">t</a></p>'), ('[a *b*](u)', '<p><a href=\"u\">a <em>b</em></a></p>'),\n"
"    ('a < b & c', '<p>a &lt; b &amp; c</p>'), ('`x<y`', '<p><code>x&lt;y</code></p>'),\n"
"    ('```\\nx < y\\n  *z*\\n```', '<pre><code>x &lt; y\\n  *z*</code></pre>'),\n"
"    ('# T\\n\\npara\\n\\n- l', '<h1>T</h1>\\n<p>para</p>\\n<ul><li>l</li></ul>'),\n"
"    ('# *T*', '<h1><em>T</em></h1>'), ('- **x** y', '<ul><li><strong>x</strong> y</li></ul>'),\n"
"    ('p1\\n- l1\\n\\np2', '<p>p1</p>\\n<ul><li>l1</li></ul>\\n<p>p2</p>'),\n"
"]\n\n"
"def test_cases():\n"
"    for md, want in CASES:\n"
"        got = render(md)\n"
"        assert got == want, (md, got, want)\n\n"
"if __name__ == '__main__':\n    test_cases(); print('ok')\n",
    },
    "x4-sched": {
        "src": "src/sched/parse.py", "test": "tests/test_sched.py",
        "extra_src": {
            "src/sched/__init__.py": "",
            "src/sched/plan.py": "def plan(jobs):\n    raise NotImplementedError\n",
            "src/sched/report.py": "def report(schedule):\n    raise NotImplementedError\n",
        },
        "stub": "def parse_jobs(text):\n    raise NotImplementedError\n",
        "tests": HEAD + "from sched.parse import parse_jobs\nfrom sched.plan import plan\nfrom sched.report import report\n\n"
"SPEC = '''# jobs\\nbuild: 3\\ntest: 2 after build\\ndocs: 1 after build\\nship: 1 after test docs\\n'''\n\n"
"def test_parse():\n"
"    jobs = parse_jobs(SPEC)\n"
"    assert jobs == {'build': (3, []), 'test': (2, ['build']), 'docs': (1, ['build']), 'ship': (1, ['test', 'docs'])}\n"
"    assert parse_jobs('') == {}\n"
"    assert parse_jobs('a:1') == {'a': (1, [])}\n"
"    assert parse_jobs('a : 1 after  b   c ') == {'a': (1, ['b', 'c'])}\n"
"    for bad in ('a', 'a: x', 'a: 0', 'a: -1', 'a: 1 after', 'a: 1\\na: 2', 'a: 1 before b', ': 1'):\n"
"        try:\n"
"            parse_jobs(bad)\n"
"        except ValueError:\n"
"            continue\n"
"        raise AssertionError(f'parse_jobs({bad!r}) must raise ValueError')\n\n"
"def test_plan():\n"
"    s = plan(parse_jobs(SPEC))\n"
"    assert s == {'build': (0, 3), 'test': (3, 5), 'docs': (3, 4), 'ship': (5, 6)}\n"
"    assert plan({}) == {}\n"
"    for bad in ({'a': (1, ['b'])}, {'a': (1, ['b']), 'b': (1, ['a'])}, {'a': (1, ['a'])}):\n"
"        try:\n"
"            plan(bad)\n"
"        except ValueError:\n"
"            continue\n"
"        raise AssertionError(f'plan({bad}) must raise ValueError')\n\n"
"def test_report():\n"
"    s = plan(parse_jobs(SPEC))\n"
"    assert report(s) == 'build  0-3\\ndocs   3-4\\ntest   3-5\\nship   5-6\\nmakespan 6'\n"
"    assert report({}) == 'makespan 0'\n"
"    assert report({'zz': (0, 10), 'a': (0, 2)}) == 'a   0-2\\nzz  0-10\\nmakespan 10'\n\n"
"if __name__ == '__main__':\n    test_parse(); test_plan(); test_report(); print('ok')\n",
    },
    "x5-wrap": {
        "src": "src/wrap.py", "test": "tests/test_wrap.py",
        "stub": "def wrap(text, width):\n    return [text]\n",
        "tests": HEAD + "from wrap import wrap\n\n"
"def test_basic():\n"
"    assert wrap('the quick brown fox', 10) == ['the quick', 'brown fox']\n"
"    assert wrap('abc def', 7) == ['abc def']\n"
"    assert wrap('abc def', 6) == ['abc', 'def']\n"
"    assert wrap('', 5) == []\n"
"    assert wrap('  hi  ', 5) == ['hi']\n\n"
"def test_whitespace():\n"
"    assert wrap('a   b', 5) == ['a b']\n"
"    assert wrap('a\\tb', 5) == ['a b']\n"
"    assert wrap('a\\nb', 5) == ['a b']\n"
"    assert wrap('a\\n\\nb', 5) == ['a', '', 'b']\n"
"    assert wrap('a\\n\\n\\n\\nb', 5) == ['a', '', 'b']\n\n"
"def test_long_words_and_hyphens():\n"
"    assert wrap('abcdefghij', 4) == ['abcd', 'efgh', 'ij']\n"
"    assert wrap('well-known fact', 6) == ['well-', 'known', 'fact']\n"
"    assert wrap('well-known fact', 11) == ['well-known', 'fact']\n"
"    assert wrap('a-b-c-d', 3) == ['a-', 'b-', 'c-d']\n"
"    assert wrap('x abcdefgh', 4) == ['x', 'abcd', 'efgh']\n\n"
"def test_invalid():\n"
"    for bad in (0, -1, 1.5, '5', None):\n"
"        try:\n"
"            wrap('x', bad)\n"
"        except ValueError:\n"
"            continue\n"
"        raise AssertionError(f'wrap(..., {bad!r}) must raise ValueError')\n\n"
"if __name__ == '__main__':\n    test_basic(); test_whitespace(); test_long_words_and_hyphens(); test_invalid(); print('ok')\n",
    },
}
