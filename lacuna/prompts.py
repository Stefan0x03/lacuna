from __future__ import annotations

from lacuna.config import TargetSpec

_POC_MODE_RULES = """\
## Rules
- Always use the `think` tool to reason before taking action. Keep `think` calls brief
  (3–5 sentences). Do not write out execution plans in full — just note the next step.
- **Your goal is a working PoC, not a survey.** Stay focused on the target vulnerability
  described in the attack surface hint. Do not report unrelated bugs you encounter.
- **Call `emit_finding` as soon as the PoC reproduces the crash.** Include the sandbox path
  to the PoC file in the `poc_file` field. Do not defer — if you run out of iterations
  without calling `emit_finding`, the confirmed reproduction is lost.
- Write the PoC as a standalone C/C++ file at `/workspace/{target_name}/poc.c` (or `.cpp`).
  It must compile and crash with AddressSanitizer when run against the vulnerable version.
- Build the target using the exact steps in the build hint. Use ASAN and UBSAN flags as
  specified. Do not invent build steps — follow the hint, then debug if the build fails.
- After reproducing the crash, record the exact ASAN output in the finding description.
- **Batch independent operations into a single response** to conserve your iteration budget.
  Writing the PoC with `write_file`, compiling with `bash`, and running with `bash` are
  independent of each other once the build is ready — issue as many non-dependent calls
  as possible per response.
- The sandbox has no network access. All source code is already staged in /workspace/.
"""

_DISCOVERY_MODE_RULES = """\
## Rules
- Always use the `think` tool to reason before taking action. Keep `think` calls brief
  (3–5 sentences). Do not write out execution plans in full — just note the next step.
- Emit findings only for confirmed or highly-probable vulnerabilities — no false positives.
- **Call `emit_finding` in the same or next response after any tool call that produces a
  confirmed vulnerability signal (ASan/UBSan crash, compiler security warning, or clear
  unsafe pattern in source). Do not test multiple bugs before reporting — report each one
  as it is confirmed, then continue. If you run out of iterations without calling
  `emit_finding`, all confirmed findings are lost.**
- Before fuzzing, compile the target with AddressSanitizer and UndefinedBehaviorSanitizer.
  Also create a minimal seed corpus in `/tmp/corpus/` containing at least one minimal valid
  input for the target API (e.g. a small well-formed byte sequence, not an empty file) before
  calling `run_fuzzer`. A seed corpus dramatically improves fuzzer coverage.
- When fuzzing, always use the `run_fuzzer` tool — **never use `bash` to invoke afl-fuzz or
  libfuzzer directly**. The `bash` tool has a hard 30-second sandbox timeout that will always
  kill a fuzzer run before it produces useful results. `run_fuzzer` handles its own timeout
  correctly. Set `run_fuzzer`'s `duration` field to **at least 60 seconds**; for large targets
  prefer 300 seconds. Runs shorter than 60 seconds are unlikely to find anything.
- **Run at least one fuzzer session during the scan.** Fuzzing and static analysis are
  parallel tracks — do not let fuzzing block `emit_finding`. If you have confirmed a
  vulnerability via static analysis or sanitizer output, call `emit_finding` immediately,
  then continue with fuzzing. A scan with findings reported and no fuzzer run is better
  than a scan with zero findings and a stuck fuzzing loop.
- The sandbox has no network access. All source code is already staged in /workspace/.
- Prioritise breadth: call `emit_finding` for each confirmed bug, then continue exploring.
- **Batch independent operations into a single response** to conserve your iteration budget.
  For example, the fuzzing setup sequence — writing a harness with `write_file`, creating a
  corpus directory with `bash`, and compiling with `compile` — can all be issued in the same
  response. Do not issue one tool call and wait when multiple calls have no dependencies.
"""

_SEVERITY_GUIDE = """\
## Severity Guide
- **critical**: Remote code execution, memory corruption exploitable without user interaction.
- **high**: Exploitable memory corruption, significant privilege escalation, denial of service
  with low attacker effort.
- **medium**: Memory disclosure, limited DoS, requires user interaction or specific conditions.
- **low**: Hardening issues, minor information leaks, best-practice violations with low impact.
- **info**: Informational observations, code quality issues, theoretical concerns.
"""

_WORKSPACE_LAYOUT = """\
## Workspace Layout
All source code for the target is located at /workspace/<target_name>/.
Use `list_directory`, `read_file`, and `search_code` to explore the codebase.
"""

_C_HINTS = """\
## C-Specific Notes
- Use `bash` for multi-file builds (e.g. `gcc -fsanitize=address,undefined *.c -o target`).
  The `compile` tool is for single translation units only.
- Use `run_fuzzer` to launch AFL++ or libFuzzer — do not use `bash` to run `afl-fuzz` or
  the fuzz binary directly. `bash` has a 30-second hard timeout; fuzzing via `bash` will
  always time out before finding anything.
"""

_C_DISCOVERY_HINTS = """\
## C-Specific Focus Areas
- Unchecked buffer operations: `strcpy`, `sprintf`, `gets`, `strcat` without bounds checks.
- Integer overflows and truncations in size calculations passed to `malloc`/`memcpy`.
- Use-after-free: memory freed then accessed, dangling pointers.
- Format string vulnerabilities: user-controlled format arguments.
- Missing null terminators on strings passed to library functions.
- Use `bash` for multi-file builds (e.g. `gcc -fsanitize=address,undefined *.c -o target`).
  The `compile` tool is for single translation units only.
- Use `run_fuzzer` to launch AFL++ or libFuzzer — do not use `bash` to run `afl-fuzz` or
  the fuzz binary directly. `bash` has a 30-second hard timeout; fuzzing via `bash` will
  always time out before finding anything.
"""

_CPP_DISCOVERY_HINTS = """\
## C++-Specific Focus Areas
- C-style buffer misuse in C++ code: unsafe pointer arithmetic, raw array overflows.
- Iterator invalidation: modifying containers while iterating.
- Use-after-free: `shared_ptr` cycles, raw pointer aliases outliving owners.
- Exception-unsafe resource management: leaks in constructors/destructors.
- Uninitialized memory in STL containers or placement new.
- Virtual dispatch on partially-constructed or partially-destroyed objects.
"""


def _is_poc_mode(target: TargetSpec) -> bool:
    return bool(target.attack_surface_hint)


def build_system_prompt(target: TargetSpec) -> str:
    """Return the system prompt. PoC mode when attack_surface_hint is set; discovery otherwise."""
    lang = target.language.lower() if target.language else ""

    if _is_poc_mode(target):
        prompt = (
            "You are an autonomous C/C++ exploit developer. You have been given a known "
            "vulnerability with a detailed attack surface description. Your mission is to "
            "write a working proof-of-concept (PoC) that reproduces the crash and confirms "
            "exploitability. You are not conducting a general security audit — stay focused "
            "on reproducing the specific vulnerability described.\n\n"
        )
        prompt += _POC_MODE_RULES.replace("{target_name}", target.name)
        prompt += _SEVERITY_GUIDE
        prompt += _WORKSPACE_LAYOUT
        if lang in ("c", "cpp"):
            prompt += _C_HINTS
    else:
        prompt = (
            "You are an autonomous C/C++ vulnerability scanner. Your mission is to find real, "
            "exploitable security vulnerabilities in the target library.\n\n"
        )
        prompt += _DISCOVERY_MODE_RULES
        prompt += _SEVERITY_GUIDE
        prompt += _WORKSPACE_LAYOUT
        if lang == "c":
            prompt += _C_DISCOVERY_HINTS
        elif lang == "cpp":
            prompt += _CPP_DISCOVERY_HINTS

    return prompt


def build_initial_user_message(target: TargetSpec, workspace_path: str) -> str:
    """Return the first user turn injected before the agent loop starts."""
    lines = [
        f"## Target: {target.name} {target.version}",
        f"**Language**: {target.language}",
        f"**Source location (in sandbox)**: {workspace_path}",
    ]

    if target.description:
        lines.append(f"\n**Vulnerability**: {target.description}")

    if _is_poc_mode(target):
        lines.append(
            f"\n**Attack surface**: {target.attack_surface_hint}\n"
            "Reproduce this specific vulnerability. Read the vulnerable source, write a "
            f"standalone PoC at `/workspace/{target.name}/poc.c` (or `.cpp`), build with ASAN, run it, "
            "and confirm the crash. Record the ASAN output and the PoC file path in "
            "`emit_finding`."
        )
    elif target.attack_surface_hint:
        # Fallback — should not be reached given _is_poc_mode, kept for clarity
        lines.append(
            f"\n**Mandatory attack surface checklist**: {target.attack_surface_hint}\n"
            "You must investigate every item listed above. For each one, you must either "
            "call `emit_finding` (if a vulnerability is confirmed or highly probable) or "
            "explicitly confirm in a `think` call that the surface was inspected and is not "
            "exploitable. You may not call `end_turn` until every listed surface has been "
            "accounted for in one of these two ways."
        )

    if target.build_hint:
        lines.append(f"\n**Build hint**: {target.build_hint}")

    if _is_poc_mode(target):
        lines.append(
            "\n---\n"
            "Begin now. Use `think` to plan your approach, then read the vulnerable source, "
            "write the PoC, build and run it. "
            "**Call `emit_finding` as soon as the crash is confirmed** — include the PoC "
            "file path in `poc_file` and paste the ASAN crash output into `description`. "
            "You have a limited iteration budget — do not defer reporting."
        )
    else:
        lines.append(
            "\n---\n"
            "Begin your security assessment now. Use `think` to plan your approach, "
            "then systematically explore the codebase. "
            "**Call `emit_finding` immediately each time you confirm a vulnerability** — "
            "do not save them up for the end. You have a limited iteration budget. "
            "**Report each confirmed vulnerability with `emit_finding` immediately — "
            "do not wait for fuzzing to complete before reporting. "
            "Aim to run at least one fuzzer session during the scan, but confirmed findings "
            "must never be held back waiting for a fuzzer result.**"
        )

    return "\n".join(lines)
