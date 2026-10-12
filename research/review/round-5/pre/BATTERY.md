# Pre-audit before round 5: the regression battery

Run on the round-4 code (`7a12dc3` plus the one fix below) before the fifth agy review, so that review sees code
that already survived every earlier reviewer's script and two fresh reviewers (Claude Opus 5.5 and Claude Fable 5.1,
`PROMPT.md`, reports in `opus/` and `fable/`).

## Earlier reviewers' scripts, rerun unchanged

| Round | Scripts | Result on the current code |
|---|---|---|
| 2 (`/tmp/g1-review2/`) | `test_section_a.py`, `test_section_b.py`, `test_section_c.py`, `test_section_def.py` | every verdict as in round 2: F-01 to F-16 hold (symlink target, anchor repair, forged record `diverged`, crash recovery at every journal point, concurrent readers and writers, 1,077 reads with no error, truncation and tamper cases). Two lines differ from round 2 for known reasons: `CLI_refused` is `false` only because the refusal text changed in round 3 ("decision command refused" became "G1 command line refused"); all seven decision commands are still refused. `g1\ repair` and `G1 repair` are listed as "PASSED (BYPASS)" by the script, as in round 2: a program named `g1 repair` (with a space) or `G1` is not G1. |
| 3 (`/tmp/g1-review3/`, rerun by the round-4 reviewer and again now as `/tmp/g1-review4/test_all_round3.py`) | 24 checks with variations | all `fixed`; the R3-04 line's "(bypass!)" label is printed unconditionally and now shows `exec -a x=True, env -i=True` (both refused). |
| 4 (`/tmp/g1-review4/`) | `test_unverifiable_deadlock.py`, `test_corrupt_restore.py`, `test_commit_kill.py`, `test_f_chmod.py`, `test_section_c.py`, `test_section_d.py`, `test_wrappers.py`, `test_section_e.py`, `test_section_h.py` | as in `research/review/round-4/RESPONSE.md`: every finding fixed. |

## Found by the author while probing the round-4 diff

- A corrupt head file (`ledger.head.json` that is not JSON, or empty) or a corrupt commit journal made
  `g1 repair --restore` crash with a traceback: `restore_ledger` caught only `LedgerError` around `_recover()`, and
  `read_head()` raises `ValueError`. The status was `unverifiable` and `--forget` was the only way out. Fix:
  `restore_ledger` treats `LedgerError`, `ValueError` and `OSError` from recovery alike (the mirror is the source;
  head, anchor and witness are rewritten) and removes a journal it could not apply. Test:
  `test_r4_01_c_restore_survives_a_corrupt_head_file_or_journal`.
- Checked and found as designed: `--restore` on a workspace whose witness is unreadable (falls back to the head's
  ledger id, then rewrites the witness); a ledger corrupted at its last line (restored); a foreign ledger copied in
  while the witnessed mirror is gone (`diverged`; `--restore` refuses with "holds no usable record"; `--accept-ledger`
  is the user's explicit decision and then the witness follows); `--forget` twice (the second is a no-op); a corrupt
  ledger at SessionStart (lockdown), then `--forget`, then the next SessionStart (a fresh ledger, status `ok`);
  `_python_code_runs_g1` on 100 KB input, an unterminated 50 KB string, null bytes, 5,000 nested parentheses, form
  feeds and a lone surrogate (at most 1.4 ms, no exception); gate spellings `sudo -E`, `env FOO=bar g1`,
  `xargs -0 -I{} g1`, `timeout --preserve-status 10 g1`, `sudo -- g1`, `env -- g1`, `timeout -k 5 10 g1`,
  `nice --adjustment=10 g1`, `command -v g1`, `{ g1 repair; }`, `(cd /tmp && exec python3 -m g1 repair)`,
  `x=$(g1 status)` (all refused) and `python3 - < code.py`, `import g1x.y`, `ls .agents/hooks.json.bak`,
  `cat foo.agents/hooks.json`, `git grep 'g1 repair'`, a `-c` comment or triple-quoted string mentioning `import g1`
  (all allowed).
