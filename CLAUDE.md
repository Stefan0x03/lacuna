# CLAUDE.md — Lacuna Vulnerability Scanner

This file guides LLM assistants (Claude Code) working on this codebase.
Read it fully before making any changes.

---

## Project Overview

**Lacuna** is an agentic C/C++ vulnerability scanner. A single Claude agent
(via the Anthropic Python SDK) uses a rich tool set to autonomously scan
C/C++ libraries for security vulnerabilities. The agent decides its own
strategy — code review, commit history analysis, fuzzing — and runs inside
a sandboxed Docker container that has **no network access at any point**.

The name "Lacuna" (a gap or missing portion) reflects the project's goal:
finding what's missing in a library's security posture.

---

## Architecture in One Paragraph

`lacuna/cli.py` is the entry point. It loads a target YAML spec, builds a
`ScanConfig`, stages the target source on the HOST (git clone, tarball, or
local copy), starts a `DockerSandbox` with the workspace bind-mounted, then
hands control to `VulnerabilityAgent` in `lacuna/agent.py`. The agent runs
an Anthropic tool-use loop: it calls the API, dispatches tool calls to
implementations in `lacuna/tools/`, appends results to the conversation
(with context window trimming via `trim_messages()`), and repeats until
`stop_reason == "end_turn"`. Findings are accumulated by `ReportAccumulator`
and rendered to Markdown by `lacuna/report.py`. A full conversation JSON is
always saved alongside the report.

---

## Directory Structure

```
lacuna/
├── CLAUDE.md                          # This file
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── lacuna/                            # Main Python package
│   ├── __init__.py
│   ├── cli.py                         # Entry point: `lacuna scan <target.yaml>`
│   ├── config.py                      # ScanConfig dataclass, env loading
│   ├── agent.py                       # Core agent loop + tool dispatch
│   ├── context.py                     # trim_messages(): context window management
│   ├── prompts.py                     # System prompt construction (dynamic)
│   ├── report.py                      # Markdown report + messages JSON writer
│   │
│   ├── tools/                         # Agent tool implementations
│   │   ├── __init__.py                # Tool registry + tool_definitions()
│   │   ├── base.py                    # BaseTool ABC, ToolResult dataclass
│   │   ├── think.py                   # Internal reasoning scratchpad
│   │   ├── shell.py                   # bash execution in sandbox
│   │   ├── filesystem.py              # read_file, write_file, list_directory
│   │   ├── git_tools.py               # git_log, git_show, git_blame
│   │   ├── search.py                  # search_code (ripgrep wrapper)
│   │   ├── fuzzing.py                 # compile, run_fuzzer, read_crash
│   │   └── report_tool.py             # emit_finding (structured findings)
│   │
│   └── sandbox/                       # Sandbox lifecycle management
│       ├── __init__.py
│       ├── manager.py                 # DockerSandbox: start/stop/exec/copy
│       └── staging.py                 # Stage target source on HOST before scan
│
├── docker/
│   ├── sandbox/
│   │   ├── Dockerfile                 # Sandbox image: build tools + AFL++ + clang
│   │   └── entrypoint.sh
│   └── runner/
│       ├── Dockerfile                 # Optional: containerize the lacuna agent
│       └── entrypoint.sh
│
├── docker-compose.yml
│
├── targets/                           # Declarative target definitions (YAML)
│   ├── example_libpng.yaml
│   ├── example_openssl.yaml
│   └── test_tiny.yaml                 # Smoke-test target (local C source)
│
├── workspace_src/                     # Committed source trees for local targets
│   └── tiny/                          # Tiny C library with intentional vulnerabilities
│       ├── tiny.h
│       ├── tiny.c
│       └── main.c
│
├── workspace/                         # Bind-mounted into sandbox at /workspace/
│   └── .gitkeep                       # Contents are gitignored
│
├── reports/                           # Generated reports (gitignored content)
│   └── .gitkeep
│
├── tests/
│   ├── conftest.py                        # Shared pytest fixtures
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_context.py
│   │   ├── test_report.py
│   │   └── test_tools.py
│   └── integration/
│       └── test_agent_sandbox.py          # Requires Docker
│
├── PROGRESS.md                            # Session handoff tracker (not gitignored)
│
└── scripts/
    ├── build_sandbox.sh
    └── run_scan.sh
```

---

## Staging Model (critical — read this first)

**All source staging happens on the HOST before the sandbox starts.**
The sandbox container starts with `network_mode: none` from the very beginning —
there is no "disconnect after clone" step. This eliminates a race condition and
simplifies the security model.

```
Staging flow (lacuna/sandbox/staging.py):

  git source  → git clone on HOST → workspace/<target>/
  tarball     → download on HOST → extract → workspace/<target>/
  local       → copy on HOST     → workspace/<target>/

Then:

  docker-compose up sandbox        (network_mode: none from start)
  workspace/ is bind-mounted at /workspace/ in container

Agent can read/write /workspace/<target>/ freely.
Network is never available inside the sandbox.
```

Use a **bind mount** (`./workspace/` on host → `/workspace/` in container),
not a named Docker volume. Bind mounts are:
- Trivially inspectable from the host during/after a scan
- Easy to pre-populate (staging writes here before container starts)
- Naturally cleaned up by `lacuna clean`

---

## Key Conventions

### Tool Implementation Contract
- Every tool MUST inherit `BaseTool` from `lacuna/tools/base.py`.
- Tools MUST implement: `name: str`, `description: str`, `input_schema: dict`,
  and `run(input: dict) -> ToolResult`.
- Tools that execute in the sandbox receive a `DockerSandbox` instance at
  construction. They MUST NOT import `docker` SDK directly — only use
  `DockerSandbox.exec()`.
- Tool errors MUST be caught and returned as `ToolResult(is_error=True, content=...)`
  — never raised as exceptions that crash the agent loop.
- **`run_fuzzer` returns a structured summary** (run duration, crash count,
  unique crash paths, coverage delta) — not raw AFL++ output. Raw output is too
  noisy. The agent can use `bash` or `list_directory` to dig deeper.

### Agent Loop (`lacuna/agent.py`)
- The loop lives in `VulnerabilityAgent.scan()`. Keep it simple and linear.
- Do NOT add special-case logic for specific tool names inside the loop.
  All dispatch goes through `TOOL_REGISTRY[name].run(input)`.
- After each API call, pass the full `messages` list through `trim_messages()`
  before appending the new turn. This prevents context window overflow on long scans.
- Accumulate `response.usage` after every API call for cost tracking.
- The loop exits on: `stop_reason == "end_turn"`, max iterations exceeded,
  or an unrecoverable API error (after logging).
- Do NOT use streaming by default — use `client.messages.create` (blocking).

### Context Window Management (`lacuna/context.py`)
- `trim_messages(messages, max_input_tokens, keep_last_n_turns=6)` is called before
  every API request.
- Strategy: truncate the `content` of **old tool results** to `TOOL_RESULT_KEEP_CHARS`
  (named constant, 2000 chars) once total estimated token count exceeds a threshold.
  "Old" means all turns except the last `keep_last_n_turns` assistant+user pairs.
- Never truncate `assistant` messages (thinking/planning) or the initial
  system context — only tool result content from older turns.
- This is critical for correctness on scans of large codebases. Do not remove it.

### Sandbox (`lacuna/sandbox/manager.py`)
- The sandbox starts with `network_mode: none`. There is no `disconnect_network()`
  call — it is never needed.
- All sandbox interactions go through `DockerSandbox.exec()`. Never call
  `subprocess.run(["docker", ...])` outside of `manager.py`.
- `ExecResult.timed_out == True` MUST be returned to the agent as a tool error
  — never silently ignored.

### Reports
- `emit_finding` is the ONLY way findings enter the report.
  Do not parse agent text to extract findings.
- `Finding.severity` must be one of: `critical | high | medium | low | info`.
- Reports are written to `reports/<target>_<YYYYMMDD_HHMMSS>.md`.
  Never overwrite an existing report file.
- **The full conversation is always saved** as `reports/<target>_<YYYYMMDD_HHMMSS>_messages.json`
  alongside the Markdown report. This is not opt-in — it happens every scan.

### Configuration
- All runtime config lives in `ScanConfig` (dataclass in `config.py`).
- Secrets (API key) come from `.env` via `python-dotenv`. Never hardcode.
- CLI flags override `.env` values. `.env` values override code defaults.
- Key `ScanConfig` defaults: `model="claude-sonnet-4-6"`, `max_iterations=50`,
  `max_tokens=8192`, `timeout_per_tool=30` (seconds), `sandbox_name="lacuna-sandbox"`.

---

## Tool Inventory (13 tools)

| Tool Name | Description |
|---|---|
| `think` | Internal reasoning scratchpad. Never executes anything. |
| `bash` | Shell command execution inside the sandbox. |
| `read_file` | Read a file from the sandbox filesystem. |
| `write_file` | Write content to a file in the sandbox. |
| `list_directory` | List a directory tree in the sandbox. |
| `search_code` | Ripgrep-based code search in the sandbox. |
| `git_log` | Git commit history (formatted, filterable by path/date). |
| `git_show` | Show a specific commit diff or file at a ref. |
| `git_blame` | Attribute lines to commits. |
| `compile` | Compile C/C++ with specified flags and sanitizers. |
| `run_fuzzer` | Launch AFL++ or libFuzzer; returns structured summary. |
| `read_crash` | Read a crash input from fuzzer output directory. |
| `emit_finding` | Record a structured vulnerability finding. |

Note: `get_target_info` is NOT a tool. Target metadata is injected into the
initial user message and system prompt. The agent does not need a tool call
to retrieve it.

---

## CLI Commands

```
lacuna scan <target.yaml>   Run a vulnerability scan
lacuna clean                Stop sandbox, remove container, clear workspace/
lacuna report <scan-id>     Re-render a report from a saved messages JSON
```

### `lacuna scan` flags

```
--model TEXT          Model to use (default: claude-sonnet-4-6)
--max-iterations INT  Max agent iterations (default: 50)
--full-run            Use claude-opus-4-6 (expensive, thorough)
--verbose             Stream every tool call/result to terminal
```

---

## Adding a New Tool

1. Create `lacuna/tools/my_tool.py`, subclass `BaseTool`.
2. Add to `build_tool_registry()` in `lacuna/tools/__init__.py`.
3. `tool_definitions()` collects from the registry automatically.
4. Write a unit test in `tests/unit/test_tools.py`.

No other files need to change.

---

## Adding Language Support

1. Add `language: <lang>` to a new target YAML file.
2. Optionally extend `prompts.language_context()` for language-specific hints
   (dangerous patterns, typical build commands, etc.).
3. If the language needs a different fuzzer, extend `FuzzerTool` with a new
   `fuzzer` option (`afl | libfuzzer | cargo-fuzz | go-fuzz`).
4. The rest of the tools (`bash`, `search_code`, `git_*`) are language-agnostic.
   No further changes required.

---

## Container Architecture

```
HOST
├── staging.py: git clone / copy → ./workspace/<target>/
│
├── lacuna Python process
│   ├── Anthropic SDK → Claude API
│   └── DockerSandbox.exec(cmd) ──────────────────┐ docker exec
│                                                  ▼
└── lacuna-sandbox container (network_mode: none, always)
    ├── /workspace/ ← bind mount of ./workspace/
    ├── gcc, g++, clang, llvm
    ├── AFL++, libFuzzer
    ├── AddressSanitizer, UBSan
    ├── valgrind, gdb
    └── cmake, make, git, ripgrep
```

### Sandbox security properties
- `network_mode: none` — no internet access, ever
- `cap_drop: ALL` — minimal Linux capabilities
- `cap_add: SYS_PTRACE` — required for sanitizers and gdb only
- `no-new-privileges: true`
- Bind mount is `rw` for the workspace only; no other host paths mounted

---

## Running Locally

```bash
# One-time setup
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY

# Install Python package (editable)
pip install -e ".[dev]"

# Build sandbox image
./scripts/build_sandbox.sh

# Run a scan (default: claude-sonnet-4-6)
lacuna scan targets/example_libpng.yaml --verbose

# Development scan (cheapest)
lacuna scan targets/example_libpng.yaml --model claude-haiku-4-5-20251001

# Full run with Opus
lacuna scan targets/example_openssl.yaml --full-run

# Clean up after a scan
lacuna clean
```

## Running Tests

```bash
# Unit tests (no Docker required)
pytest tests/unit/ -v

# All tests including integration (requires Docker + sandbox image)
pytest tests/ -v
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `LACUNA_DEFAULT_MODEL` | No | Override default model |
| `LACUNA_MAX_ITERATIONS` | No | Override default max iterations (50) |
| `LACUNA_REPORTS_DIR` | No | Override default `./reports` |

---

## Model Selection Guide

| Model | Use Case | Est. Cost / Scan |
|---|---|---|
| `claude-haiku-4-5-20251001` | Development, iteration, testing | ~$0.10–$0.50 |
| `claude-sonnet-4-6` | Default production scans | ~$1–$5 |
| `claude-opus-4-6` | Full deep-dive runs (`--full-run`) | ~$10–$50 |

The CLI prints token counts and estimated cost after every scan.

---

## What NOT to Do

- **No AI frameworks.** Do not add LangChain, CrewAI, AutoGen, or similar.
  The Anthropic SDK tool-use loop IS the framework.
- **No database by default.** Findings are in-memory during a scan, written
  to Markdown. A SQLite store can be added later.
- **No streaming by default.** Complicates the loop. Add as a `--stream` flag later.
- **No network in sandbox — ever.** Stage on host first. This is non-negotiable.
- **No secrets in code or git.** API key in `.env` only (gitignored).
- **No premature abstraction.** Three similar lines of code is better than
  a helper function called once.
- **No named Docker volumes for workspace.** Use bind mount only.

---

## Session Handoffs (PROGRESS.md)

`PROGRESS.md` at the project root tracks implementation state across sessions.
Every implementation session should:
1. Read PROGRESS.md at the start to understand what's done and what's next.
2. Update PROGRESS.md at the end: mark completed items, note blockers, list next steps.

PROGRESS.md is committed to git — it is the canonical record of build state.

---

## Debugging Tips

- `--verbose` streams every tool call and result to the terminal.
- After a scan, the sandbox container stays alive. Inspect it with:
  `docker exec -it lacuna-sandbox bash`
- Every scan writes `reports/<target>_<timestamp>_messages.json` — use this
  to replay and understand why the agent made certain decisions.
- To reset: `lacuna clean` removes the container and clears `./workspace/`.

---

## Future Work (do not implement prematurely)

- [ ] Multi-target batch scanning
- [ ] SQLite findings database
- [ ] SARIF output format
- [ ] GitHub Actions integration
- [ ] `cargo-fuzz` / `go-fuzz` support for Rust/Go targets
- [ ] Differential analysis between two library versions
- [ ] Streaming output (`--stream` flag)
- [ ] Auto-discovery of popular libraries
