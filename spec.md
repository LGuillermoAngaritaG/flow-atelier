# Spec: `atelier ask --json` — NDJSON interactive stream for agent callers

## Objective

Make `atelier ask` callable by another agent (Claude Code, ZCode, or any
subprocess orchestrator) as a **structured**, bidirectional conversation:
the command emits one JSON object per line on stdout (the agent's reply,
its questions, tool activity, and the terminal flow result), and reads one
reply per line on stdin. Today the interactive surface is rich-console-only,
so a programmatic caller cannot reliably tell "Claude asked a question"
from "Claude is narrating." This adds a machine-readable mode without
touching the default human experience.

The WS path already solves this for the web UI (`WsPromptSink` +
`agent_input_request`/`agent_input_answer`). This spec ports the same
model to the CLI via a new `PromptSink`, reusing the existing engine,
harness loop, and `[ATELIER_DONE]` sentinel. No new infrastructure.

## Success Criteria

A test (and a real caller) can drive an interactive session over stdio:

1. `atelier ask "Q" --path ./dir --json` prints **only** NDJSON on stdout.
   Every line parses as a JSON object with a `type` field. No rich-console
   panels, rules, or raw unframed chunks leak to stdout in `--json` mode.
2. As Claude replies, `{"type":"agent_message","text":...}` chunks appear
   incrementally.
3. When Claude ends a turn without `[ATELIER_DONE]`, exactly one
   `{"type":"agent_input_request","request_id":...,"prompt":...}` line
   is emitted. The caller writes one line to stdin; that text becomes
   Claude's next prompt turn.
4. The terminal events are emitted exactly once:
   - `{"type":"flow_complete","flow_id":...}` on success, OR
   - `{"type":"flow_failed","flow_id":...,"error":...}` on failure.
5. Closed stdin (EOF) at a prompt produces a `flow_failed` with a clear
   `"interactive input unavailable"` error — not a hang or traceback.
6. Default behavior (no `--json`) is byte-identical to today.
7. `atelier ask --json --help` documents the protocol; a short example
   lives in the command help or README.

## Protocol

Reuses the WS vocabulary from `schemas/ws.py` so a caller has one mental
model. One JSON object per line, UTF-8, on stdout.

**Server → caller (stdout), each line:**
| `type` | fields | when |
|---|---|---|
| `agent_message` | `task`, `text` | each streamed agent chunk |
| `agent_input_request` | `task`, `request_id`, `prompt` | Claude awaits a reply |
| `step` | `task`, `step` (IntermediateStep) | thinking/tool call/result (only if `--show-steps`) |
| `flow_complete` | `flow_id` | run succeeded |
| `flow_failed` | `flow_id`, `error` | run failed |

Notes:
- `flow_id` is omitted from the live `agent_message`/`agent_input_request`/
  `step` events (the CLI caller has one flow; it is named in the terminal
  event). This keeps line noise down. The terminal event always carries it.
- `request_id` is a monotonic int as a string (`"1"`, `"2"`, …) — simpler
  than the WS `secrets.token_hex(8)` since the channel is a single flow
  with strictly ordered prompt/answer turns (the harness awaits each
  `request_input` before issuing the next).

**Caller → server (stdin), one line per request:**
The raw line (stripped of its trailing newline) is the answer. No JSON
wrapping needed — a reply is one turn of free text, and the harness
correlates by ordering, not id. EOF closes the run.

## Boundaries

- **Always:**
  - Reuse `Atelier(prompt_sink=...)` (`core/atelier.py:77,99`) — do not
    add a parallel injection path.
  - Mirror event field names from `schemas/ws.py` exactly.
  - Keep `--json` output strictly NDJSON; route any diagnostics/errors
    that aren't part of the conversation to **stderr** (including the
    "cannot run: tool not ready" preflight), or as `flow_failed`.
  - Add tests in `tests/cli/test_ask_cmd.py` alongside the existing ones.
- **Ask first:**
  - Any change to the `PromptSink` protocol signature.
  - Porting `--json` to `atelier run` (out of scope for this spec; flag it).
- **Never:**
  - Break the default (non-`--json`) CLI output.
  - Add a new dependency.
  - Print non-JSON to stdout in `--json` mode.
  - Introduce a REST answer endpoint (the per-connection WS broker makes
    this a bigger lift with no payoff over the sink).

## Open Questions

1. **Should `agent_message` chunk at the same granularity as the WS path?**
   The WS sink forwards each token-sized chunk. For a subprocess caller
   that's fine (and lets it stream), but it produces many small lines.
   *Working assumption:* mirror the WS behavior exactly — chunk-per-emit.
   Reconsider if tests show pathological line counts.
2. **Stdin framing:** one raw line per turn is unambiguous for ordered
   single-flow runs. If we ever support multiple concurrent interactive
   tasks in one CLI flow, we'd need `{request_id, answer}` JSON on stdin.
   *Working assumption:* raw lines now; document the constraint.
3. **Exit codes:** keep the existing scheme (`0` complete, `1` failed,
   `2` usage)? *Working assumption:* yes — a caller can rely on both the
   exit code and the terminal event.
