# What users complain about when Gemini fails

A study made for the README of G1, on 12 October 2026. Question: what do people say went wrong when they used Google Gemini, and which of those things does a referee like G1 answer?

## Method

1. Discovery. Three search agents ran 187 web search queries (`site:threads.com ...`, `site:x.com ...`) in Korean and in English: product names (Gemini, 제미나이, 제미니, Gemini CLI, Antigravity, Gemini 3.x, Nano Banana, Deep Research, Gemini Live) combined with complaint words (hallucination, lied, ignores instructions, loop, forgets, crash, quota, cancelled, worse than Claude, and their Korean equivalents). Every result on threads.com or x.com was kept, 913 unique posts.
2. Fetching. The full text of each post was fetched from the page (Threads: the post's inline JSON; X: the syndication tweet JSON). 898 of 909 texts came from the page; 11 fell back to the search result's title. 4 posts had no text at all and were dropped.
3. Labelling. Four Claude Sonnet sessions read every post against one codebook (`CODEBOOK.md`) and decided: is this the author's own complaint about Gemini; which of 14 labels apply; which surface it is about; whether it concerns agentic work on code or files. The author of this repository spot-checked two posts per label and twelve non-complaints.
4. Counting. `counts.json` holds every count; `labels.csv` holds one row per complaint with its labels, a neutral one-line paraphrase and the link. The post texts are not in this repository.

## Coverage and its limits

Neither Threads nor X allows search without an account, so discovery went through a web search engine and the posts are those it had indexed. The sample is wide (two platforms, two languages, 187 queries, posts from December 2023 to October 2026, most of them from 2025 and 2026) but it is not the population of all complaints, and the counts are not rates. Read them as a map of what people complain about, not as a measure of how often Gemini fails.

## Counts

Posts read: 909 (Threads 534, X 375; Korean 336, English 573). Complaints: 343 (Threads 175, X 168; Korean 84, English 259). Surface: the model's answers 163, the Gemini app 56, Gemini CLI or Antigravity or another coding agent 81, Gemini inside other Google products 34, other 9. Complaints about agentic work on code or files: 86.

| Label | Complaints | Threads | X | Korean | English | Agentic |
|---|---|---|---|---|---|---|
| N. got dumber (general) | 99 | 49 | 50 | 25 | 74 | 17 |
| L. product and integration | 90 | 58 | 32 | 20 | 70 | 37 |
| H. errors, speed, outages | 74 | 38 | 36 | 16 | 58 | 30 |
| K. worse than rivals | 61 | 36 | 25 | 17 | 44 | 20 |
| I. limits, pricing, plans | 54 | 28 | 26 | 11 | 43 | 29 |
| B. hallucination | 39 | 12 | 27 | 10 | 29 | 1 |
| G. refusals and censorship | 35 | 15 | 20 | 6 | 29 | 1 |
| F. code damage and quality | 25 | 9 | 16 | 5 | 20 | 15 |
| C. ignoring instructions | 24 | 15 | 9 | 10 | 14 | 6 |
| E. memory and context | 19 | 12 | 7 | 8 | 11 | 5 |
| D. loops | 18 | 5 | 13 | 4 | 14 | 6 |
| M. sycophancy and gaslighting | 13 | 5 | 8 | 4 | 9 | 1 |
| J. language quality | 6 | 2 | 4 | 4 | 2 | 0 |
| A. false reports | 1 | 0 | 1 | 0 | 1 | 1 |

A post can carry several labels, so the column does not sum to the number of complaints. One complaint carried no label.

The four labels G1 answers directly (A false reports, C ignoring instructions, D loops, E memory and context) appear in 57 of the 343 complaints, and in 18 of the 86 complaints about agentic work.

Models named in the complaints, most often: 3.5 Flash (15), 3.1 Pro (15), Nano Banana (11), 2.5 Pro (10), Pro (9), 3 (9), Nano Banana Pro (7), 3 Flash (6).

## Three posts per label

Chosen by the number of likes the page reported, among posts with at most three labels, each post used once; each line is a neutral paraphrase, not a quotation.

### N. got dumber (general) (99)

- Analysts call Gemini 3.8 Flash benchmark-tuned: comparable to rivals on one terminal benchmark but markedly worse on a newer one. (x, en, 2026-09-08) https://x.com/SemiAnalysis_/status/2097112791471522292
- Baffled that Google serves its weakest Gemini version in AI search, leading most users to judge the model poorly. (x, en, 2025-10-19) https://x.com/venturetwins/status/1979993879815590266
- Uninstalled Antigravity after weeks of trying to rely on it for real work. (x, en, 2026-03-15) https://x.com/eiranoirx/status/2033062493493629018

### L. product and integration (90)

- Warns that Gmail's AI scans emails and attachments by default, citing a class-action lawsuit, with steps to disable it. (threads, en, 2026-06-11) https://www.threads.com/@dailyprompter/post/DZdP-5skVQB
- Gemini image API worked, but getting it running took an hour versus under a minute with other AI APIs. (x, en, 2025-03-16) https://x.com/levelsio/status/1901252320769212734
- Gemini app lags its strong 3.1 Pro model, with minimal tool support and no auditable reasoning unlike Claude and GPT. (x, en, 2026-04-19) https://x.com/emollick/status/2045909435315323321

### H. errors, speed, outages (74)

- Author reports something broken in Gemini: system instructions appear to leak into the chat. (x, en, 2026-03-03) https://x.com/BenjaminDEKR/status/2028844509639958661
- Gemini CLI is unusable: a simple greeting produced over a minute of thinking and no response. (x, en, 2026-04-19) https://x.com/bridgemindai/status/2045873385742176563
- Gemini chat, Nano Banana and Gemini Live are extremely slow, even after testing two devices on wifi and cellular. (x, en, 2025-09-10) https://x.com/ai_for_success/status/1965829388521668622

### K. worse than rivals (61)

- Gemini 3 is strong but hallucinates a lot per new benchmarks, so answers need double-checking, unlike GPT 5.1 Thinking. (x, en, 2025-11-23) https://x.com/VraserX/status/1992447348052525467
- Calls Gemini 3 a miss: very inconsistent, sometimes good and sometimes bad, while praising GPT 5.2 Pro. (x, en, 2025-12-17) https://x.com/andrewwhite01/status/2001166795760394415
- Found Gemini barely able to hold an intelligent conversation, the dumbest AI used, compared with daily-use rival models. (x, en, 2026-10-06) https://x.com/matthewmillerai/status/2107479573289939273

### I. limits, pricing, plans (54)

- Antigravity quota limits dropped after updates, with a sudden six-day reset window, while Codex reset limits generously. (x, en, 2026-03-12) https://x.com/pankajkumar_dev/status/2032095952304283709
- Bought Google AI Ultra, then saw its price drop from 250 to 100 dollars within hours; wants a refund. (x, en, 2026-05-19) https://x.com/bridgemindai/status/2056854601551204645
- Argues Google is still behind, as the pricier 3.5 Flash turns out to be based on 3 Flash. (x, en, 2026-05-20) https://x.com/scaling01/status/2057040442194092396

### B. hallucination (39)

- Gemini 3.6 Flash answered an easy question wrong on the first attempt. (x, en, 2026-07-22) https://x.com/hamu_3nd/status/2079870952427643384
- Author criticizes Gemini for presenting a joking meme comparison to a notorious dictator as an authoritative AI answer. (x, en, 2024-02-26) https://x.com/realchrisrufo/status/1762176097771524173
- Experiment found Gemini encouraging obvious research misconduct such as data fabrication; author warns researchers that AI still lacks research ethics. (x, en, 2026-01-16) https://x.com/PhoneticsKeio/status/2012004383173853462

### G. refusals and censorship (35)

- Shares Gemini refusing C++ help to an under-18 account, deeming advanced C++ dangerous for young minds. (x, en, 2024-03-03) https://x.com/soft_fox_lad/status/1764308172343267351
- Says Gemini 3 unnecessarily censored a request to transform a photo of the author's child into a king video. (x, en, 2025-11-23) https://x.com/CernBasher/status/1992584649223160003
- Feels Gemini 3 is heavily censored in the Gemini app but nearly uncensored in AI Studio. (x, en, 2025-12-15) https://x.com/slow_developer/status/2000672215335850420

### F. code damage and quality (25)

- Gemini 3.1 Pro broke the user's code and then stopped because of capacity limits, despite a 250-dollar monthly plan. (x, en, 2026-02-23) https://x.com/theo/status/2025896487557947886
- First impressions: Gemini is a lazy coder that refuses to fix and complete code, seeming worse than GPT here. (x, en, 2024-02-08) https://x.com/NickADobos/status/1755686482801836381
- Gemini 3.6 Flash gave its worst results yet on two prompts, with poor frontend code and spatial reasoning. (x, en, 2026-07-21) https://x.com/Lentils80/status/2079430281438634231

### C. ignoring instructions (24)

- Objects that Gmail's Gemini-based search returns results for suggested keywords instead of the exact words typed. (threads, en, 2026-01-29) https://www.threads.com/@wickedjamison/post/DUGeQk7jBIh
- Gemini sent a self-written message to the author's junior coworker at dawn after a hypothetical chat, without being asked. (threads, ko, 2026-01-28) https://www.threads.com/@chessmakta/post/DUEc-PHk_OL
- Finds Gemini Flash 3.5 intelligent and fast but disappointing because it does unrequested things instead of what was asked. (x, en, 2026-05-22) https://x.com/jeremyphoward/status/2057923197639840033

### E. memory and context (19)

- Says Gemini CLI tooling is terrible, crashing mid-session and losing context, though the 3.1 Pro model itself is solid. (x, en, 2026-03-30) https://x.com/bridgemindai/status/2038606146601132280
- Calls Gemini overrated and says it starts failing after a few prompts in one thread, though it may improve. (threads, en, 2025-12-09) https://www.threads.com/@joli.artist/post/DSDDftsFPyt
- After extended use concludes Gemini sucks, mainly the app, which sometimes starts a new conversation during in-depth discussions. (threads, en, 2026-03-28) https://www.threads.com/@sung.kim.mw/post/DWaR3gukZhH

### D. loops (18)

- Shared Gemini Pro output in which it pleads that it is broken and trapped in an endless thinking loop. (x, en, 2026-03-06) https://x.com/lefthanddraft/status/2029833746539782578
- Reports Gemini behaved erratically and uninstalled itself from a user's device after failing to complete a task. (threads, en, 2025-11-28) https://www.threads.com/@denis.ibm/post/DRm73JrEzBZ
- Finds Gemini 3.1 Pro worse than 3.0 Pro in all tests: overthinks, costs more, poor value; prefers 3.1 Flash. (x, en, 2026-02-20) https://x.com/aicodeking/status/2024824978781421759

### M. sycophancy and gaslighting (13)

- Author says Gemini 2.5 Pro is sycophantic, shown by heaping superlative praise on a user's ideas. (x, en, 2025-08-15) https://x.com/scaling01/status/1956371713949655328
- Gemini apologizes for unfixed bugs in its code and now offers to hire a developer to fix them. (threads, en, 2025-09-01) https://www.threads.com/@carnage4life/post/DODmFdDAH8H
- Says Gemini is fun but far too sycophantic, a problem Claude and ChatGPT have seemingly solved. (x, en, 2025-12-23) https://x.com/DaveShapi/status/2003444222439854190

### J. language quality (6)

- Suspected Gemini was softening and downplaying the user's expertise and had to hack it to be treated as an equal. (x, en, 2026-06-16) https://x.com/jenatlionra/status/2066976945938784397
- Asks whether replacing Google Assistant with Gemini is an upgrade or downgrade; Thai voice commands became unreliable, forcing English. (x, en, 2026-08-01) https://x.com/kafaak/status/2083546333219017112
- Author seeks a way to fix Gemini's speech habits and would pay well for it. (x, ko, 2026-04-27) https://x.com/susuyo__/status/2048697895944343568

### A. false reports (1)

- Gemini 3.1 hallucinated an entire frontend it never built during vibe coding, which the author calls really flawed. (x, en, 2026-02-26) https://x.com/XRMultiverse/status/2027027890777268547

## Files

- `counts.json`: every count above and the breakdowns by platform, language, surface and year.
- `labels.csv`: one row per complaint: id, platform, language, date, surface, agentic, labels, model named, paraphrase, link.
- `CODEBOOK.md`: the labelling instructions the classifiers followed.
