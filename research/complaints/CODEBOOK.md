# Codebook for classifying collected posts about Google Gemini

Each post is one JSON object with `id`, `platform` (threads | x), `lang` (ko | en), `url`, `author`, `text`.
Read the whole `text`. Decide the fields below and write ONE JSON object per post (same `id`) to the output file.

## Fields

`is_negative` (true | false): true only when the post is a user's own negative experience with, complaint about, or
negative judgment of Google Gemini (the model, the Gemini app, Gemini CLI, Antigravity, Gemini Live, Deep Research,
Nano Banana, Gemini inside Gmail/Docs/Android/Chrome, AI Overviews/AI Mode). false for: news or announcements,
tips and tutorials, promotions, memes without a complaint, positive or neutral reviews, posts about other products,
posts that only quote someone else's complaint without agreeing, satire not grounded in use. A post that praises
Gemini but mentions one drawback counts as true only if the drawback is a real complaint (then tag it).

`categories` (list, zero or more of the codes below; choose every one that the post itself states, not what you infer):

- A  false reports: says it finished, fixed, tested or checked something when it had not; fake test results; claims work it did not do.
- B  hallucination: invented facts, sources, links, functions, people, events; confidently wrong factual answers; "it lied to me" about facts.
- C  ignoring instructions: does not follow the prompt, guidelines or constraints; does unrelated or unasked changes; over-engineers; rewrites everything; drifts off task.
- D  loops: repeats the same answer, action or mistake; endless thinking; stuck in a loop; "I am a disgrace" style breakdowns.
- E  memory and context: forgets earlier parts of the conversation; resets; loses chat history; context window complaints; no memory across sessions.
- F  code damage and quality: breaks or deletes files or code; buggy or wrong code; bad at programming specifically.
- G  refusals and censorship: refuses reasonable requests; over-restrictive safety; partial or lazy answers; "I can't help with that".
- H  errors, speed, outages: crashes, error codes, "something went wrong", 429/503/overloaded, hangs, slowness, timeouts, lost connection.
- I  limits, pricing, plans: quota or usage limits hit; limits reduced; too expensive; not worth the price; cancellation or refund trouble; surprise charges.
- J  language quality: poor Korean (or other non-English) output; tone or register problems; bad translation.
- K  worse than rivals: explicitly worse than Claude, ChatGPT/GPT, Codex, Grok, DeepSeek, Copilot, Cursor, or Google Assistant; switched away to one of them.
- L  product and integration: app or CLI or Antigravity UX bugs and annoyances; forced into Android/Gmail/Docs/Chrome; replaced Google Assistant for the worse; hard to turn off; lost features; privacy or data concerns about the product.
- M  sycophancy and gaslighting: agrees with everything; endless apologies; insists it is right when wrong; overconfident tone; blames the user.
- N  got dumber (general): "got worse", "nerfed", "lobotomized", "downgrade", "dumb", "stupid", "sucks", "garbage", general disappointment with no more specific complaint than quality decline.

`about` (one of): model | app | cli_or_antigravity | integration | other. Which surface the complaint is mainly about: the model's answers/behaviour (model), the Gemini chat app or web app (app), Gemini CLI or Antigravity or another agentic coding use (cli_or_antigravity), Gemini embedded in Android/Gmail/Docs/Chrome/Assistant/AI Overviews (integration), none of these (other).

`agentic` (true | false): true when the complaint concerns Gemini doing multi-step work on code or files (coding agent use: Gemini CLI, Antigravity, Cursor/Copilot with Gemini, "it edited my repo", "it said it ran the tests"). false otherwise.

`summary` (string, at most 20 words, in English): a neutral paraphrase of the complaint. Never copy the post's sentences; do not include the author's name.

`model_mentioned` (string or null): the model or version the post names, verbatim and short (for example "3.1 Pro", "3.5 Flash", "3.8 Flash", "4 Argon", "2.5 Pro"), or null.

## Rules

- Judge only from the text. Do not open URLs. Do not guess hidden meaning; if the text is too short or ambiguous to tell, set `is_negative` to false and `categories` to [].
- A post can carry several categories; use N only when nothing more specific applies, or in addition when the post also makes the general claim.
- Keep `summary` neutral: no insults, no names of people, no quotes.
- Output exactly one JSON line per input post, same `id`, all fields present, nothing else in the file.
