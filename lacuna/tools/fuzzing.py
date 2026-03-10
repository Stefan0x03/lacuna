from __future__ import annotations

import shlex
import textwrap

from lacuna.sandbox.manager import DockerSandbox
from lacuna.tools.base import BaseTool, ToolResult

SANITIZER_MAP: dict[str, str] = {
    "asan": "address",
    "ubsan": "undefined",
    "msan": "memory",
    "tsan": "thread",
}


class CompileTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "compile"

    @property
    def description(self) -> str:
        return "Compile a C/C++ source file inside the sandbox."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "Path to the source file."},
                "output_path": {"type": "string", "description": "Path for the compiled binary."},
                "compiler": {
                    "type": "string",
                    "description": "Compiler to use (default: clang).",
                },
                "flags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra compiler flags.",
                },
                "sanitizers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sanitizers to enable: asan, ubsan, msan, tsan.",
                },
            },
            "required": ["source_path", "output_path"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            source_path = input["source_path"]
            output_path = input["output_path"]
            compiler = input.get("compiler", "clang")

            san_flags: list[str] = []
            for s in input.get("sanitizers", []):
                if s not in SANITIZER_MAP:
                    return ToolResult(is_error=True, content=f"Unknown sanitizer: {s!r}")
                san_flags.append(f"-fsanitize={SANITIZER_MAP[s]}")

            # compiler and extra flags are trusted agent input — not shell-escaped.
            # The sandbox is air-gapped (network_mode=none, cap_drop=ALL).
            cmd_parts = (
                [compiler]
                + input.get("flags", [])
                + san_flags
                + [shlex.quote(source_path), "-o", shlex.quote(output_path)]
            )
            cmd = " ".join(cmd_parts)
            result = self._sandbox.exec(cmd, timeout=120)
            combined = (result.stdout + "\n" + result.stderr).strip()
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=combined)
            return ToolResult(content=combined or "Compilation successful.")
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))


class RunFuzzerTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "run_fuzzer"

    @property
    def description(self) -> str:
        return "Launch AFL++ or libFuzzer and return a structured summary."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "fuzzer": {
                    "type": "string",
                    "enum": ["afl", "libfuzzer"],
                    "description": "Fuzzer to use.",
                },
                "target_binary": {"type": "string", "description": "Path to the fuzz target."},
                "corpus_dir": {"type": "string", "description": "Directory with seed corpus."},
                "output_dir": {"type": "string", "description": "Directory for fuzzer output."},
                "duration": {"type": "integer", "description": "Run duration in seconds."},
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra arguments passed to the fuzzer.",
                },
            },
            "required": ["fuzzer", "target_binary", "corpus_dir", "output_dir", "duration"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            fuzzer = input["fuzzer"]
            target_binary = input["target_binary"]
            corpus_dir = input["corpus_dir"]
            output_dir = input["output_dir"]
            duration = input["duration"]
            exec_timeout = duration + 120

            if fuzzer == "afl":
                return self._run_afl(target_binary, corpus_dir, output_dir, duration, exec_timeout)
            elif fuzzer == "libfuzzer":
                return self._run_libfuzzer(
                    target_binary, corpus_dir, output_dir, duration, exec_timeout
                )
            else:
                return ToolResult(
                    is_error=True, content=f"Unknown fuzzer: {fuzzer!r}. Use 'afl' or 'libfuzzer'."
                )
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))

    def _run_afl(
        self,
        target_binary: str,
        corpus_dir: str,
        output_dir: str,
        duration: int,
        exec_timeout: int,
    ) -> ToolResult:
        cmd = (
            f"mkdir -p {shlex.quote(output_dir)} && "
            f"timeout {duration} afl-fuzz -i {shlex.quote(corpus_dir)} "
            f"-o {shlex.quote(output_dir)} -t 1000 -- "
            f"{shlex.quote(target_binary)} @@ ; true"
        )
        self._sandbox.exec(cmd, timeout=exec_timeout)

        stats_result = self._sandbox.exec(
            f"cat {shlex.quote(output_dir)}/default/fuzzer_stats 2>/dev/null"
        )
        stats = _parse_kv(stats_result.stdout)

        crashes_result = self._sandbox.exec(
            f"find {shlex.quote(output_dir)}/default/crashes/ "
            f"-maxdepth 1 -type f ! -name README 2>/dev/null | wc -l || echo 0"
        )
        crash_count = crashes_result.stdout.strip()

        return ToolResult(
            content=(
                f"fuzzer: afl++\n"
                f"duration_s: {duration}\n"
                f"crashes: {crash_count}\n"
                f"execs_per_sec: {stats.get('execs_per_sec', 'unknown')}\n"
                f"paths_total: {stats.get('paths_total', 'unknown')}\n"
                f"output_dir: {output_dir}\n"
            )
        )

    def _run_libfuzzer(
        self,
        target_binary: str,
        corpus_dir: str,
        output_dir: str,
        duration: int,
        exec_timeout: int,
    ) -> ToolResult:
        cmd = (
            f"mkdir -p {shlex.quote(output_dir)} && "
            f"{shlex.quote(target_binary)} -max_total_time={duration} "
            f"-artifact_prefix={shlex.quote(output_dir)}/ "
            f"{shlex.quote(corpus_dir)} 2>&1 || true"
        )
        result = self._sandbox.exec(cmd, timeout=exec_timeout)

        stats: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if line.startswith("stat::"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    stats[parts[1].strip()] = parts[2].strip()

        crashes_result = self._sandbox.exec(
            f"find {shlex.quote(output_dir)} -maxdepth 1 -type f "
            r"\( -name 'crash-*' -o -name 'timeout-*' -o -name 'leak-*' \) "
            f"2>/dev/null | wc -l || echo 0"
        )
        crash_count = crashes_result.stdout.strip()

        return ToolResult(
            content=(
                f"fuzzer: libfuzzer\n"
                f"duration_s: {duration}\n"
                f"crashes: {crash_count}\n"
                f"execs_per_sec: {stats.get('execs_per_sec', 'unknown')}\n"
                f"paths_total: {stats.get('number_of_executed_units', 'unknown')}\n"
                f"output_dir: {output_dir}\n"
            )
        )


class ReadCrashTool(BaseTool):
    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "read_crash"

    @property
    def description(self) -> str:
        return "Read and hex-dump a crash input file from the fuzzer output directory."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "crash_path": {
                    "type": "string",
                    "description": "Absolute path to the crash file.",
                },
            },
            "required": ["crash_path"],
        }

    def run(self, input: dict) -> ToolResult:
        try:
            crash_path = input["crash_path"]
            py_script = textwrap.dedent("""
                import os, sys
                path = sys.argv[1]
                data = open(path, 'rb').read(4096)
                size = os.path.getsize(path)
                print(f'File: {path}')
                print(f'Size: {size} bytes (showing first {len(data)})')
                for i in range(0, len(data), 16):
                    c = data[i:i+16]
                    h = ' '.join(f'{b:02x}' for b in c)
                    a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in c)
                    print(f'{i:04x}: {h:<48}  |{a}|')
            """).strip()

            cmd = f"python3 -c {shlex.quote(py_script)} {shlex.quote(crash_path)}"
            result = self._sandbox.exec(cmd)
            if result.exit_code != 0:
                return ToolResult(is_error=True, content=result.stderr or result.stdout)
            return ToolResult(content=result.stdout)
        except Exception as e:
            return ToolResult(is_error=True, content=str(e))


def _parse_kv(text: str) -> dict[str, str]:
    """Parse AFL++ fuzzer_stats 'key : value' lines."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out
