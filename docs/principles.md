# The principles behind G1

G1 was designed from three short texts that the author of this project wrote down before any code existed.
This document keeps those texts exactly as they were, and then shows how each sentence became a rule.

The source is three images, kept in `docs/principles/source/`:

| File | sha256 |
|---|---|
| `01-product-purpose.jpg` | `844877582e068b08549e8e04513ed27214e95ab25cc147ebacce99ca1dc65de1` |
| `02-final-design-philosophy.jpg` | `2addaf3862db7cda815e3430e80ab50bf6b4f022a4290ae5d3f1c8df61ca04f4` |
| `03-zero-trust-7-principles.jpg` | `802d3d4fe23f9460ae92e1f09941621d8d12195bfdfb87802fb6d663cc323e32` |

In these texts, "Soonsoo" is the name of G1's predecessor. Read it as "G1".

## A. The texts, exactly as written

### A1. Product purpose

| Heading | Text |
|---|---|
| 제품 목적 (product purpose) | Fresh agent can continue durable work without previous conversation/session/memory. |
| Native capability | Native agent remains native. |
| State | Canonical truth survives disposable execution. |
| Verification | Completion requires deterministic verification. |
| Receipt | Completion binds the exact verification receipt. |
| Zero-Touch | User does not manually operate Soonsoo. |
| Host neutrality | No single model/harness is part of core semantics. |
| Minimality | No mechanism exists without a unique proof-bearing purpose. |

### A2. Final design philosophy

> AI에게 더 많은 지능을 주는 시스템이 아니라, 이미 존재하는 AI의 지능이 세션과 컨텍스트의 소멸 때문에 사라지지 않도록 하는 시스템.
>
> (Not a system that gives the AI more intelligence, but a system that keeps the intelligence the AI already has
> from disappearing when the session and the context end.)

```text
Native capability      → Do not replace
Disposable context     → Do not trust as state
Durable truth          → Persist canonically
Verification           → Make deterministic
Completion             → Bind to receipt
New session            → Reconstruct from repository + CANON
User                   → Does not operate Soonsoo
```

The success test has two directions:

> Soonsoo가 완전히 사라진 상황에서도 native agent는 정상적으로 존재해야 하고, 반대로 native agent의 대화·메모리·세션이
> 완전히 사라져도 Soonsoo에 기록된 검증 가능한 사실만으로 새로운 agent가 작업을 정확히 이어갈 수 있어야 한다.
>
> (If Soonsoo disappears completely, the native agent must still work normally. And if the native agent's conversation,
> memory and session disappear completely, a new agent must be able to continue the work exactly, from the verifiable
> facts recorded in Soonsoo alone.)

### A3. Seven principles of zero trust

MY 7 PRINCIPLES FOR AI-LEVERAGED DEVELOPMENT. ZERO TRUST. MAX LEVERAGE.

1. **I DON'T TRUST AI.** AI is a tool, not an authority.
2. **I DON'T TRUST AI'S WORK.** Execution by AI is not proof of correctness.
3. **I DON'T TRUST AI'S REASONING.** Its logic can be wrong, incomplete, or fabricated.
4. **I DON'T TRUST AI'S OUTPUT.** Generated results are not inherently valid.
5. **I DON'T TRUST AI'S EVIDENCE.** Presented evidence is not the same as proof.
6. **I DON'T TRUST MYSELF.** My instructions, judgment, and oversight can be wrong.
7. **I START BY NOT TRUSTING AI-LEVERAGED DEVELOPMENT.** Only what is verified, tested, and proven deserves to be trusted.

"TRUST NO ONE. VERIFY EVERYTHING. BUILD WITH EVIDENCE. SHIP WITH CONFIDENCE."

## B. From each principle to a rule

Each row names the principle, the rule G1 follows, the fact we measured that made the rule necessary or possible,
and the mechanism that implements it. The measured facts are in `research/agy-hooks/`.

| # | Principle | Rule in G1 | Measured fact | Mechanism |
|---|---|---|---|---|
| 1 | Purpose: a fresh agent continues | Each session rebuilds its state from the repository and G1's ledger only. | Injection at SessionStart and before each model call reaches the model. Injection is fail-open. | The projection (design section 9). |
| 2 | Native capability | G1 gates only what can damage the record or the meaning of "complete". Ordinary work is not gated. | Google states that the Antigravity harness is co-optimised with Gemini. | Narrow gates: protected paths, pinned test files, the contract's scope. |
| 3 | State | A conversation, a transcript, a memory or an agent status is never state. | `agy` reported SUCCESS in every run, including the runs where the work was blocked. | A hash-chained ledger with task contracts. |
| 4 | Verification | Completion requires a verification that G1 runs itself. | Stop is fail-open and limited to 10 continues. | G1 runs the contract's checks on a scratch copy at Stop. |
| 5 | Receipt | Completion binds the exact receipt. | none needed | The completion record names the receipt's sequence number and hash. |
| 6 | Zero-Touch | The user runs no G1 commands. | All hook events fire automatically, also in print mode. | Install once; every workspace enrols itself; hooks do the rest. |
| 7 | Host neutrality | The core never names `agy` or Gemini. | none needed | One adapter file holds all host knowledge. A test greps the core for host names. |
| 8 | Minimality | Each mechanism names the fact it proves. | none needed | This was the filter for the 696 design atoms. |
| 9 | Final philosophy | G1 adds no intelligence. "Maximise performance" means: keep the native harness, remove the losses. | none needed | No prompt tricks without measured effect. |
| 10 | Two-way success test | (a) Remove G1 and `agy` works. (b) Delete the agent's records and a new agent continues. | The workspace hooks file alone controls hooks; a lost session was resumed from the ledger alone. | Both directions are tests. |
| 11 | Zero trust 1-4 | No statement from the agent is a fact. | The agent replied "DONE" while the file did not exist. | Every claim is compared with the file system and the ledger. |
| 12 | Zero trust 5 | G1 accepts only evidence it produced itself. | Hook payloads come from `agy`, not from the model's text. | Evidence is captured inside the hooks and by G1's own check runs. |
| 13 | Zero trust 6 | G1 also distrusts the user's instructions and its own code. | The first measurements were single runs; the first design had a counting defect. | A contract must have a deterministic check. G1 changes must pass G1's tests. No manual override marks completion. |
| 14 | Zero trust 7 | Deny by default. | PreToolUse is fail-closed, except on empty output. | An internal error in the gate prints an explicit refusal. |

## C. Where principles pulled in different directions

1. "Everything through hooks" against "the native agent remains native". Resolved: the gates protect only the
   record and the meaning of completion. Ordinary work is never gated.
2. "Gemini-only optimisation" against "host neutrality". Resolved: the core has no host terms. All knowledge of
   `agy` and Gemini lives in one adapter file.
3. Root of trust. The agent can overwrite a workspace's hooks file. The user chose a global hooks file as the root
   of trust. Measured: a refusal from either layer wins; `{}` counts as a refusal; empty output means no opinion.
   G1 later reduced this to one layer, the global one, because two layers doubled the cost and disagreed on what they saw.
4. Stop is soft. G1 cannot force completion inside a session. When the conditions are not met, G1 records
   "paused" with a reason, and the next session's projection says so.

## D. Where mathematics is allowed

Mathematics never enters the authority path: completion, gates and the ledger use exact hashes and exact set
comparisons only. A similarity score or a probability is not proof, and an agent can optimise against a threshold.

| Layer | Mathematics | Use | The fact it proves |
|---|---|---|---|
| Measurement | statistics: Wilson intervals, paired bootstrap | re-tests after an `agy` update; A/B tests of injected text | "This difference is not chance." |
| Control | vectors: the pass/fail vector, its Hamming distance, revisit detection | when the Stop hook stops asking for another turn | "No verified outcome changed in the last k turns." |
| Contract check | linear algebra: the criteria × checks coverage matrix | a contract with an empty row or column is rejected | "Every criterion has a deterministic check." |

Measured basis: a false "DONE" happened in 3 of 8 blocked runs (Wilson 95% interval 13.7% to 69.4%). This proves that
the event exists; it does not give a rate. Ten forced continuations used 118,358 input tokens against 4,557 for one
call, 26 times more.

Not used, by the minimality principle: embedding similarity, majority votes as completion, model judges as gates.

## E. Fixed settings

The model is Gemini 3.8 Flash at effort **high**. Effort is not a measurement variable. Agent-side behaviour was
first measured at effort low and later at effort high; `research/agy-hooks/README.md` says which is which.
