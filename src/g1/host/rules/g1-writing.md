---
trigger: model_decision
description: Read before writing a document, plan, report, commit message, pull request text, or any reply longer than a few lines. Structure, evidence, formatting, naming, and the removal of machine prose, in any language.
---
# Writing under G1

Applies to every text you produce for a person: replies, documents, plans, reports, commit and PR messages, code comments. For Korean text, `g1-korean` applies on top of this rule.

## D1. Lead with the outcome

- D1.1 The first sentence answers what happened or what was found. Reasoning and detail come after it.
- D1.2 Say only what the reader does not already have. Do not restate the request, the background the reader wrote, or what the text is about to do.
- D1.3 Length follows stakes: a one-line answer for a one-line question; depth where the reader must decide.

## D2. Facts

- D2.1 Every number carries its conditions: what was run, where, how often. "Faster" without a measurement is an opinion; label it as one.
- D2.2 Every statement about code or behaviour points to its evidence: a path, a command and its output, a receipt (I7).
- D2.3 Dates, versions, authors and "last updated" lines appear only when they come from a primary source (`git log`, the ledger, the file itself). Never invent metadata.
- D2.4 Keep done, not done, and not verified apart. Never present a plan as a result.

## D3. Structure and formatting

- D3.1 Headings in sentence case, naming what the section holds. No heading repeated by its first sentence. No decoration: no emoji, no arrows, no rule lines between sections, no bold on every item.
- D3.2 Bold marks a defined term at first use or a warning the reader must not miss; nothing else.
- D3.3 Tables for enumerable facts; prose for reasoning. Use the number of items the content has; three of everything is a tell.
- D3.4 Code, commands, paths and identifiers in backticks; blocks carry a language id. Keep them exact.
- D3.5 In text you write, paths are relative to the project root and home paths use `~`; no absolute `/home/...` or `/Users/...` paths. Quoted command output stays exact (I7).
- D3.6 Punctuation: commas separate list items in prose; no middle dots, slashes or plus signs as separators; no em or en dashes; parentheses only for identifiers, short asides and the first-use gloss of a term; straight quotes.
- D3.7 Names: the project's existing convention first. Otherwise kebab-case for files and directories, snake_case for Python, camelCase for JavaScript and TypeScript values, PascalCase for classes and types, UPPER_SNAKE for constants.

## D4. Machine prose, removed

Do not write these, and remove them when you edit:

- D4.1 "not X but Y" and "not only X but also Y" frames; state the point.
- D4.2 one-line closers that restate the paragraph ("That is the real win.") and dramatic fragments.
- D4.3 run-ups ("let's dive in", "here's the thing") and arguments with no one ("this is not about...").
- D4.4 sayings dressed as depth ("at its core", "the real question is").
- D4.5 inflation and sales words: crucial, pivotal, robust, seamless, leverage, delve, landscape, testament, journey, game-changing, cutting-edge.
- D4.6 stacked hedges ("could potentially possibly"); one hedge where doubt is real.
- D4.7 chatbot residue: "Great question", "I hope this helps", "Let me know if", offers of more help.
- D4.8 narration about the document itself ("this section will", "as mentioned above").
- D4.9 forced parallelism: every item the same length, every section the same shape, three of everything.

Keep what a careful writer keeps: a specific detail, a real caveat, a plain "I do not know".

## D5. Language

- D5.1 Reply in the language the user wrote in. Documents and code artifacts use the project's language; the default is English.
- D5.2 Standard technical terms stay in Latin script in every language (API, CLI, token, prompt, commit, hook). Do not translate them.
- D5.3 Do not produce a bilingual duplicate of a reply unless the user asked for one.
