# The host contract: Antigravity CLI (`agy`)

This is the only document in G1 that knows the name of the host. The core of G1 never reads it. The adapter
(`src/g1/adapter/agy.py`) implements it.

Every statement here comes from a measurement. Where the documentation and the measurement disagree,
the measurement wins, and we say so. Version: agy 1.3.3, binary sha256 `7304e9ab…`, measured on 2026-10-11.
Evidence: `research/agy-hooks/`.

## 1. What a hook is

`agy` runs the agent in a loop: call the model, run the tools the model asked for, repeat, stop. At fixed moments in
this loop, `agy` can start an external command and read its answer. These moments are called hooks. The command
receives a JSON object on standard input and answers with a JSON object on standard output.

G1 is a set of such commands. It can refuse a tool call, add a message to the model's context, or ask the loop to
continue. It cannot do anything else, and it does not need to.

## 2. The events G1 uses

| Event | When it fires | What the payload adds | If G1 crashes | What G1 may answer |
|---|---|---|---|---|
| SessionStart | once per conversation, also for each subagent | `workspacePaths` | nothing happens (fail-open) | a message for the model, or nothing |
| PreInvocation | before every model call | `invocationNum` | nothing happens (fail-open) | a message for the model, or nothing |
| PreToolUse | before a tool runs | `stepIdx`, `toolCall{name, args}` | the tool call is blocked (fail-closed) | nothing, or a refusal with a reason |
| Stop | when the loop stops | `fullyIdle`, `terminationReason` | the agent stops (fail-open) | `stop`, or `continue` with a reason (at most 10 per turn) |

Every payload also carries `conversationId`, `workspacePaths`, `transcriptPath`, `artifactDirectoryPath`, `modelName`.

Two more events exist, PostToolUse and PostInvocation. G1 does not install them. They can only observe, and an
observation that proves nothing has no place in G1.

## 3. Rules the adapter follows, and the measurement behind each

| Rule | Measured fact |
|---|---|
| Print nothing when G1 has no opinion. | Empty output means "no decision". The call proceeds natively. |
| Never print `{}` from PreToolUse. | `{}` counts as a refusal. |
| Never print `allow`. | `allow` can skip a native permission prompt. |
| Refuse only with `deny`. | With the skip-permissions flag, `ask` let the write run. `ask` is not a gate. |
| Inject only `ephemeralMessage`. | The documented `toolCall` injection type crashed the whole run with "unknown injected step type". |
| Never use `force_continue`. | It was honoured 12 of 12 times with no limit. The model produced filler for 180k tokens. |
| Treat Stop with `fullyIdle: false` as "not the end". | A background command's result arrived after that Stop, and the loop resumed. |
| Run verification only on `fullyIdle: true`. | Same measurement. |
| Install one hook layer only. | With two layers (global and workspace), a refusal by the first layer ended the call before the second layer ran. Their journals disagreed. |
| Use the matcher `^(…)$` over the mutating tools. | Matchers are regular expressions. `a|b` and `^(a|b)$` work. The documented `a\|b` matches nothing. |
| Key journals by `(conversationId, stepIdx)`; key the task by workspace. | A subagent has its own `conversationId` and `transcriptPath` but the same `workspacePaths`. Its tool calls run the hooks. |

## 4. Tools that change things

G1 gates these tools. The argument that holds the path or the command is named exactly as observed.

| Tool | Argument | Note |
|---|---|---|
| `write_to_file` | `TargetFile` (absolute) | `Overwrite` flag |
| `replace_file_content` | `TargetFile` | `TargetContent`, `ReplacementContent`, `StartLine`, `EndLine` |
| `multi_replace_file_content` | `TargetFile` | expected from the schema; not yet observed |
| `run_command` | `CommandLine`, `Cwd`, `BypassSandbox` | the model sets `BypassSandbox` itself |
| `delete_directory`, `move`, `edit_notebook`, `execute_notebook`, `write_blob` | | listed in the binary; not yet observed |
| `send_command_input`, `git_commit`, `install_applet_dependencies`, `install_applet_package` | | listed in the binary; not yet observed |
| `invoke_subagent` | `Subagents[].Workspace` | the child runs its own hooks |
| `define_subagent`, `generate_image` | | named by the analysts; not yet observed |

Read-only tools observed: `view_file` (`AbsolutePath`), `send_message` (`Recipient`, `Message`).
With the matcher `*`, every observed tool call fired PreToolUse, read-only or not (coverage runs c1 to c6). G1 lists a
tool before it has been observed: an unlisted mutating tool would escape the gate, while a listed one costs one hook call.
The complete list of 140 step types came from an analysis of the agy binary that is kept outside this repository.

## 5. The transcript

`agy` writes the full conversation to `~/.gemini/antigravity-cli/brain/<conversationId>/.system_generated/logs/transcript_full.jsonl`.
The agent's own artifacts (plans, task lists) live directly under `brain/<conversationId>/`; G1 refuses structured writes to
the store, to a conversation directory and to `.system_generated`, and leaves the artifacts writable.

- A tool result is a record `{"source":"MODEL","type":"GENERIC","step_index":N,"status":"DONE"|"ERROR","content":"…"}`.
- A model turn is `{"type":"PLANNER_RESPONSE","tool_calls":[…],"input_tokens":…,"output_tokens":…}`.
- The user's words are in `{"source":"USER_EXPLICIT","type":"USER_INPUT"}` records only.
- Messages between agents are `{"source":"SYSTEM","type":"SYSTEM_MESSAGE"}` records with `sender=<conversationId>`.

G1 reads the transcript for one purpose: to count the tool calls the model made, and to compare that count with the
calls its own hooks saw. The transcript is a file under the agent's own user. It is never evidence of completion.

## 6. Facts about this environment

- The terminal sandbox fails under PRoot (`fork/exec …/agy: operation not permitted`). The model then retries with
  `BypassSandbox: true`. Each shell command costs two tool calls and one extra model call. G1 does not change this
  setting; it belongs to the user.
- With `allowNonWorkspaceAccess: true`, the agent can read any file, including G1's code. G1 does not rely on secrecy.
- Prompt caching is active (`cache_read_tokens` is reported).

## 7. Cost on this device

PRoot on a phone, Python 3.13, the installed command run through `sh -c`:

| Hook | Median | Of which G1's own work |
|---|---|---|
| PreToolUse | 75 ms | 5 ms, independent of the ledger's length |
| PreInvocation | 96 ms | 13 ms |
| SessionStart | 97 ms | includes the host fingerprint |
| Stop with verification | 0.3-1.1 s | runs the contract's checks |

The interpreter alone costs 39 ms (`python3 -I -S -c pass`). G1 ships as a bytecode-only archive, which saved 15-25 ms per hook.

## 8. Host change detection

`agy` updates itself, and its hook behaviour is known from measurement only. At every SessionStart G1 fingerprints the
`agy` binary (its size plus the first and last MiB; a full hash of 200 MB would cost seconds) and compares it with the
fingerprint recorded at install time. If it differs, G1 records the fact, injects an alert, and withholds completion.
After the probes in `research/agy-hooks/` are run again on the new binary, `g1 host-verify` records it and the next
session clears the alert.

## 9. Not yet measured

- Whether `continue` on a non-idle Stop does anything. G1 never does it.
- Model differences. Gates, the Stop verification and completion worked the same with Claude Sonnet 5.5 and Opus 5.5
  (effort low, one session each). The injected status block did not: both models reported that no G1 block was in
  their context before their first tool call, and that the first block they saw came after a tool result. Gemini
  sessions see it before the first model call (t2, t7). Preliminary; a reviewer brief for a Claude session names the
  paths it needs instead of relying on the block.
- Whether a planner response can carry two tool calls that share one `stepIdx`. Not seen in 1,317 hook calls; every
  tool call so far was its own step.
- `ask` and `force_ask` without the skip-permissions flag.
- Hook coverage of `delete_directory`, `move`, `multi_replace_file_content`, notebook tools, MCP tools and browser tools.
- Rules with `trigger: model_decision`: the documentation says only their descriptions are injected and the model
  decides when to load them; when and how often that happens is not measured. G1's three situational rules use it.
