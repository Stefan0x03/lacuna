# Lacuna — Build Progress

## Status: Smoke test + integration tests complete ✓ (v1.0)

`pytest tests/unit/ -v` — 78 passed, 0 failed.
`pytest tests/integration/ -v` — 5 sandbox tests + 4 agent tests (9 total; agent tests skip without Docker/image/API key).

---

## Completed

- [x] `pyproject.toml` — all dependencies, build config, ruff/mypy/pytest settings
- [x] `.claude/settings.json` — PostToolUse hook: ruff + mypy on every .py write
- [x] `CLAUDE.md` — full project specification

### Session: Foundation Layer

- [x] `lacuna/__init__.py`
- [x] `lacuna/tools/__init__.py` — stubs: `build_tool_registry()` / `tool_definitions()`
- [x] `lacuna/tools/base.py` — `BaseTool` ABC, `ToolResult` dataclass
- [x] `lacuna/config.py` — `ScanConfig`, `TargetSpec`, `SourceSpec` + `load_target_spec()` / `load_config()`
- [x] `lacuna/context.py` — `trim_messages()`, `TOOL_RESULT_KEEP_CHARS = 2000`
- [x] `lacuna/sandbox/__init__.py`
- [x] `targets/example_libpng.yaml`
- [x] `targets/example_openssl.yaml`
- [x] `tests/__init__.py`
- [x] `tests/unit/__init__.py`
- [x] `tests/conftest.py` — `minimal_target_spec`, `minimal_scan_config`, `sample_messages` fixtures
- [x] `tests/unit/test_tools.py` — 7 tests (BaseTool + ToolResult)
- [x] `tests/unit/test_config.py` — 8 tests
- [x] `tests/unit/test_context.py` — 10 tests

### Session: Sandbox Layer

- [x] `lacuna/config.py` — added `workspace_dir: Path` field + `LACUNA_WORKSPACE_DIR` env var
- [x] `lacuna/sandbox/manager.py` — `ExecResult` dataclass + `DockerSandbox` (start/stop/exec/copy_to)
- [x] `lacuna/sandbox/staging.py` — `stage_target()`: git, tarball, local source types
- [x] `docker/sandbox/Dockerfile` — ubuntu:22.04, build tools, clang-15, AFL++, libFuzzer
- [x] `docker/sandbox/entrypoint.sh` — `tail -f /dev/null` keepalive
- [x] `docker-compose.yml` — sandbox service: network_mode=none, bind mount, cap_drop ALL
- [x] `tests/integration/__init__.py`
- [x] `tests/integration/test_agent_sandbox.py` — 5 tests, all passing (start/stop, exec echo, nonzero exit, timeout, network disabled)
- [x] `tests/unit/test_tools.py` — extended to 16 tests (+ ExecResult, DockerSandbox mock, stage_target)

---

### Session: Agent + CLI Layer

- [x] `lacuna/prompts.py` — `build_system_prompt()`, `build_initial_user_message()`
- [x] `lacuna/report.py` — `render_markdown`, `write_report`, `write_messages_json`, `extract_findings_from_messages`, `estimate_cost`, `make_stem`
- [x] `lacuna/agent.py` — `VulnerabilityAgent`, `ScanResult` dataclass
- [x] `lacuna/cli.py` — `scan`, `clean`, `report` commands (click)
- [x] `tests/unit/test_report.py` — 15 new tests (78 total, all passing)
- [x] `scripts/build_sandbox.sh` — executable
- [x] `scripts/run_scan.sh` — executable

---

## In Progress

_(nothing)_

---

### Session: Smoke Test + Integration

- [x] Fix A — `json.dumps(default=str)` in `write_messages_json()` to handle non-serialisable SDK types
- [x] Fix B — `lacuna report` now accepts `--reports-dir` option; respects `LACUNA_REPORTS_DIR` env var
- [x] Fix C — `lacuna clean` hardcodes `Path("workspace")` — verified acceptable, no change needed
- [x] `workspace_src/tiny/` — three C source files (~150 lines) with real stack overflow, integer overflow, and format string vulnerabilities
- [x] `targets/test_tiny.yaml` — smoke-test target spec (`source.type: local`, `path: workspace_src/tiny`)
- [x] `tests/integration/test_agent_sandbox.py` — extended with 4 agent tests using session-scoped scan fixture (`test_agent_scan_completes`, `test_agent_writes_report`, `test_agent_report_rerender`, `test_agent_clean`)
- [x] `CLAUDE.md` directory listing updated to include `workspace_src/` and `targets/test_tiny.yaml`

Bugs found and fixed:
- `write_messages_json()` used `json.dumps` without `default=str` — could crash on SDK objects
- `lacuna report` hardcoded `Path("reports")` — broke `--reports-dir` and `LACUNA_REPORTS_DIR` override

### Session: Live Scan Validation + Prompt Tuning

All 5 smoke-test validation points confirmed passing (scan 4, `--max-iterations 20`):
1. CLI exited cleanly (exit code 0)
2. `reports/tiny_*.md` written, non-empty, 3 findings (1 CRITICAL stack overflow, 1 CRITICAL format string, 1 CRITICAL integer overflow)
3. `reports/tiny_*_messages.json` written, parses as valid JSON
4. `lacuna report <scan-id>` re-rendered second `.md` without error
5. `lacuna clean` stopped sandbox and cleared `workspace/`

Prompt tuning (4 runs, converged):
- Run 1 (15 iter): 0 findings — agent confirmed all 3 bugs but hit iteration limit before calling `emit_finding`
- Run 2 (15 iter): 3 findings — prompt fix ("call immediately") worked; agent batched at end but had budget
- Run 3 (15 iter): 2 findings — integer overflow missed; `atol()` silently discarded hex args
- Run 4 (20 iter): 3 findings — all bugs found and reported; stable

Changes made during this session:
- `lacuna/prompts.py` — three prompt improvements: `think` brevity, immediate `emit_finding` sequencing, multi-file build hint
- `workspace_src/tiny/main.c` — replaced `atol()` with `strtoul(..., 0)` (handles hex); added decimal/hex example in comments

Stable operating point: `--max-iterations 20` for the tiny target; default of 50 is appropriate for real codebases.

---

### Session: Tool Implementations

- [x] `lacuna/tools/think.py` — internal reasoning scratchpad
- [x] `lacuna/tools/shell.py` — `bash` tool (sandbox exec wrapper)
- [x] `lacuna/tools/filesystem.py` — `read_file`, `write_file`, `list_directory`
- [x] `lacuna/tools/search.py` — `search_code` (ripgrep wrapper)
- [x] `lacuna/tools/git_tools.py` — `git_log`, `git_show`, `git_blame`
- [x] `lacuna/tools/fuzzing.py` — `compile`, `run_fuzzer`, `read_crash`
- [x] `lacuna/tools/report_tool.py` — `Finding` dataclass + `emit_finding`
- [x] `lacuna/tools/__init__.py` — `build_tool_registry()` / `tool_definitions()` (breaking signature change: now takes sandbox + findings + timeout)
- [x] `tests/unit/test_tools.py` — extended to 63 tests (29 new tool tests)

## Up Next

_(nothing — project v1.0 complete)_

---

## Backlog (ordered)

1. ~~**Agent loop** — `lacuna/agent.py` (`VulnerabilityAgent`)~~ ✓
2. ~~**Prompts** — `lacuna/prompts.py`~~ ✓
3. ~~**Report** — `lacuna/report.py`~~ ✓
4. ~~**CLI** — `lacuna/cli.py` (`scan`, `clean`, `report` commands)~~ ✓
5. **Integration tests** — `tests/integration/test_agent_sandbox.py` ✓ (skeleton done; full run requires Docker)
6. ~~**Scripts** — `scripts/build_sandbox.sh`, `scripts/run_scan.sh`~~ ✓

---

## Known Issues / Blockers

_(none)_

---

## Notes

- `.venv/` is at project root; always use `.venv/bin/pytest`, `.venv/bin/mypy`, etc.
- ruff + mypy run automatically via PostToolUse hook on every `.py` file write/edit.
- `trim_messages()` behaviour: when fewer assistant turns exist than `keep_last_n_turns`,
  all turns are protected (nothing is trimmed). Tests must use a `keep_last_n_turns`
  value smaller than the number of assistant messages in the fixture.
- Sandbox mock pattern: use `patch.dict(sys.modules, {"docker": mock_docker})` since
  docker is imported lazily inside DockerSandbox methods. Use plain `MagicMock()` for
  the module stub (not `MagicMock(spec=ModuleType)` — that restricts attribute access).
- Integration tests skip automatically if Docker is unavailable or `lacuna-sandbox`
  image isn't built. Build with: `docker build docker/sandbox -t lacuna-sandbox`
- `_image_available()` must use `client.images.get("lacuna-sandbox")` — iterating
  `img.tags` and checking `"lacuna-sandbox" in tags` fails because Docker stores tags
  as `"lacuna-sandbox:latest"` (exact equality, not substring).
- `test_sandbox_network_disabled` uses `curl` (installed in image), not `ping`
  (not installed). With `network_mode: none`, curl exits non-zero immediately via ENETUNREACH.
