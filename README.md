# Lacuna

**Agentic C/C++ vulnerability scanner powered by Claude.**

Lacuna (*a gap or missing portion*) autonomously scans C/C++ libraries for security vulnerabilities. A single Claude agent uses a rich tool set — code review, git history analysis, fuzzing with AFL++/libFuzzer, and sanitizer-instrumented compilation — to find what's missing in a library's security posture.

The agent runs in a sandboxed Docker container with **no network access**, ensuring the target code cannot exfiltrate data or phone home during analysis.

---

## How It Works

```
lacuna scan targets/libpng.yaml
       │
       ├─ Stage source on HOST (git clone / tarball / local copy)
       │
       ├─ Start Docker sandbox (network_mode: none from start)
       │   └─ /workspace/<target>/ ← bind-mounted from host
       │
       └─ VulnerabilityAgent loop (Anthropic tool-use API)
              ├─ think         — internal reasoning scratchpad
              ├─ bash          — shell execution in sandbox
              ├─ read_file / write_file / list_directory
              ├─ search_code   — ripgrep across the codebase
              ├─ git_log / git_show / git_blame
              ├─ compile       — builds with ASan + UBSan
              ├─ run_fuzzer    — AFL++ or libFuzzer
              ├─ read_crash    — inspects fuzzer crash inputs
              └─ emit_finding  → structured finding → Markdown report
```

The agent decides its own strategy and iterates until it either exhausts its budget or reaches `end_turn`. Every scan writes a Markdown report and a full conversation JSON for replay and audit.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker
- An Anthropic API key

### Setup

```bash
# Clone the repo
git clone <repo-url>
cd lacuna

# Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# Install (editable)
pip install -e ".[dev]"

# Build the sandbox image (one-time, ~5 min)
./scripts/build_sandbox.sh
```

### Run a scan

```bash
# Smoke test against the bundled tiny C library
lacuna scan targets/test_tiny.yaml --verbose

# Scan libpng
lacuna scan targets/example_libpng.yaml

# Cheaper dev model
lacuna scan targets/example_libpng.yaml --model claude-haiku-4-5-20251001

# Full deep-dive with Opus
lacuna scan targets/example_openssl.yaml --full-run

# Clean up after a scan
lacuna clean
```

Reports are written to `reports/<target>_<YYYYMMDD_HHMMSS>.md`.

---

## CLI Reference

```
lacuna scan <target.yaml>   Run a vulnerability scan
lacuna clean                Stop sandbox, remove container, clear workspace/
lacuna report <scan-id>     Re-render a report from a saved messages JSON
```

### `lacuna scan` flags

| Flag | Default | Description |
|---|---|---|
| `--model TEXT` | `claude-sonnet-4-6` | Model to use |
| `--max-iterations INT` | `50` | Max agent iterations |
| `--full-run` | off | Use `claude-opus-4-6` (expensive, thorough) |
| `--verbose` | off | Stream every tool call/result to terminal |

---

## Target YAML Format

```yaml
name: libpng
version: "1.6.40"
language: c
source:
  type: git                          # git | tarball | local
  url: https://github.com/pnggroup/libpng
  ref: v1.6.40                       # tag, branch, or commit
description: "PNG reference library"
attack_surface_hint: "Focus on image parsing: png_read_image(), png_process_data()"
build_hint: "cmake -DPNG_TESTS=OFF . && make"
```

For local sources (`type: local`), put the source tree under `workspace_src/` and set `path: workspace_src/<dir>`. See `targets/test_tiny.yaml` for a working example.

---

## Tool Inventory

| Tool | Description |
|---|---|
| `think` | Internal reasoning scratchpad — never executes anything |
| `bash` | Shell command execution inside the sandbox |
| `read_file` | Read a file from the sandbox filesystem |
| `write_file` | Write a file in the sandbox |
| `list_directory` | List a directory tree in the sandbox |
| `search_code` | Ripgrep-based code search |
| `git_log` | Commit history, filterable by path/date |
| `git_show` | Show a specific commit diff or file at a ref |
| `git_blame` | Attribute lines to commits |
| `compile` | Compile C/C++ with specified flags and sanitizers |
| `run_fuzzer` | Launch AFL++ or libFuzzer; returns structured summary |
| `read_crash` | Read a crash input from fuzzer output directory |
| `emit_finding` | Record a structured vulnerability finding |

---

## Model Selection

| Model | Use Case | Est. Cost / Scan |
|---|---|---|
| `claude-haiku-4-5-20251001` | Development, iteration, testing | ~$0.10–$0.50 |
| `claude-sonnet-4-6` | Default production scans | ~$1–$5 |
| `claude-opus-4-6` | Full deep-dive (`--full-run`) | ~$10–$50 |

The CLI prints total token counts and estimated cost after every scan.

---

## Sandbox Security

The Docker sandbox enforces strict isolation:

- `network_mode: none` — no internet access, ever
- `cap_drop: ALL` — minimal Linux capabilities
- `cap_add: SYS_PTRACE` — required for sanitizers and gdb only
- `no-new-privileges: true`
- Workspace is bind-mounted read-write; no other host paths are mounted

Source staging (git clone, tarball download) always happens on the **host before** the container starts. The sandbox never has network access — not even briefly.

---

## Development

```bash
# Unit tests (no Docker required)
pytest tests/unit/ -v

# Integration tests (requires Docker + lacuna-sandbox image)
pytest tests/ -v

# Lint + type check
.venv/bin/ruff check lacuna/ --fix
.venv/bin/mypy lacuna/ --ignore-missing-imports
```

### Adding a Tool

1. Create `lacuna/tools/my_tool.py`, subclass `BaseTool`.
2. Add to `build_tool_registry()` in `lacuna/tools/__init__.py`.
3. Write a unit test in `tests/unit/test_tools.py`.

No other files need to change.

---

## Project Layout

```
lacuna/
├── lacuna/
│   ├── agent.py          # Core agent loop + tool dispatch
│   ├── cli.py            # Entry point
│   ├── config.py         # ScanConfig, TargetSpec
│   ├── context.py        # Context window trimming
│   ├── prompts.py        # System prompt construction
│   ├── report.py         # Markdown + JSON report writer
│   ├── tools/            # 13 tool implementations
│   └── sandbox/          # Docker sandbox lifecycle
├── docker/sandbox/       # Sandbox Dockerfile (AFL++, clang, sanitizers)
├── targets/              # Declarative scan targets (YAML)
├── workspace_src/        # Committed source for local targets
├── workspace/            # Bind-mounted into sandbox at /workspace/
└── reports/              # Generated reports (gitignored)
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

## Debugging

- `--verbose` streams every tool call and result to the terminal.
- After a scan the sandbox container stays alive: `docker exec -it lacuna-sandbox bash`
- Every scan writes `reports/<target>_<timestamp>_messages.json` — replay it with `lacuna report <scan-id>` to understand agent decisions.
- To reset everything: `lacuna clean`
