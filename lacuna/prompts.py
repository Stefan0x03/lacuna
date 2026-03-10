from __future__ import annotations

from lacuna.config import TargetSpec


def build_system_prompt(target: TargetSpec) -> str:
    """Return the static system prompt with an optional language-specific hint block."""
    prompt = """\
You are an autonomous C/C++ vulnerability scanner. Your mission is to find real,
exploitable security vulnerabilities in the target library.

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
- The sandbox has no network access. All source code is already staged in /workspace/.
- Prioritise breadth: call `emit_finding` for each confirmed bug, then continue exploring.

## Severity Guide
- **critical**: Remote code execution, memory corruption exploitable without user interaction.
- **high**: Exploitable memory corruption, significant privilege escalation, denial of service
  with low attacker effort.
- **medium**: Memory disclosure, limited DoS, requires user interaction or specific conditions.
- **low**: Hardening issues, minor information leaks, best-practice violations with low impact.
- **info**: Informational observations, code quality issues, theoretical concerns.

## Workspace Layout
All source code for the target is located at /workspace/<target_name>/.
Use `list_directory`, `read_file`, and `search_code` to explore the codebase.
"""

    lang = target.language.lower() if target.language else ""
    if lang == "c":
        prompt += """
## C-Specific Focus Areas
- Unchecked buffer operations: `strcpy`, `sprintf`, `gets`, `strcat` without bounds checks.
- Integer overflows and truncations in size calculations passed to `malloc`/`memcpy`.
- Use-after-free: memory freed then accessed, dangling pointers.
- Format string vulnerabilities: user-controlled format arguments.
- Missing null terminators on strings passed to library functions.
- Use `bash` for multi-file builds (e.g. `gcc -fsanitize=address,undefined *.c -o target`).
  The `compile` tool is for single translation units only.
"""
    elif lang == "cpp":
        prompt += """
## C++-Specific Focus Areas
- C-style buffer misuse in C++ code: unsafe pointer arithmetic, raw array overflows.
- Iterator invalidation: modifying containers while iterating.
- Use-after-free: `shared_ptr` cycles, raw pointer aliases outliving owners.
- Exception-unsafe resource management: leaks in constructors/destructors.
- Uninitialized memory in STL containers or placement new.
- Virtual dispatch on partially-constructed or partially-destroyed objects.
"""

    return prompt


def build_initial_user_message(target: TargetSpec, workspace_path: str) -> str:
    """Return the first user turn injected before the agent loop starts."""
    lines = [
        f"## Target: {target.name} {target.version}",
        f"**Language**: {target.language}",
        f"**Source location (in sandbox)**: {workspace_path}",
    ]

    if target.description:
        lines.append(f"\n**Description**: {target.description}")

    if target.attack_surface_hint:
        lines.append(f"\n**Attack surface hint**: {target.attack_surface_hint}")

    if target.build_hint:
        lines.append(f"\n**Build hint**: {target.build_hint}")

    lines.append(
        "\n---\n"
        "Begin your security assessment now. Use `think` to plan your approach, "
        "then systematically explore the codebase. "
        "**Call `emit_finding` immediately each time you confirm a vulnerability** — "
        "do not save them up for the end. You have a limited iteration budget."
    )

    return "\n".join(lines)
