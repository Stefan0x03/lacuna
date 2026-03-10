from __future__ import annotations

import io
import tarfile
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


class DockerSandbox:
    def __init__(self, sandbox_name: str, workspace_dir: Path) -> None:
        import docker  # lazy import — keeps unit tests docker-free

        self._name = sandbox_name
        self._workspace_dir = workspace_dir.resolve()
        self._client = docker.from_env()

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the sandbox container. Idempotent."""
        import docker

        try:
            container = self._client.containers.get(self._name)
            if container.status == "running":
                return
            container.restart()
        except docker.errors.NotFound:
            self._client.containers.run(
                image="lacuna-sandbox",
                name=self._name,
                network_mode="none",
                volumes={str(self._workspace_dir): {"bind": "/workspace", "mode": "rw"}},
                cap_drop=["ALL"],
                cap_add=["SYS_PTRACE"],
                security_opt=["no-new-privileges:true"],
                detach=True,
                tty=True,
            )

    def stop(self) -> None:
        """Stop and remove the container. Idempotent."""
        import docker

        try:
            container = self._client.containers.get(self._name)
            container.stop(timeout=5)
            container.remove(force=True)
        except docker.errors.NotFound:
            return

    def is_running(self) -> bool:
        """Return True if the container exists and is running."""
        import docker

        try:
            container = self._client.containers.get(self._name)
            return container.status == "running"  # type: ignore[no-any-return]
        except docker.errors.NotFound:
            return False

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def exec(self, cmd: str, timeout: int = 30) -> ExecResult:
        """Run cmd inside the sandbox via docker exec."""
        import docker

        try:
            container = self._client.containers.get(self._name)
        except docker.errors.NotFound:
            raise RuntimeError("sandbox not running")

        result_holder: list[tuple[int, tuple[bytes | None, bytes | None]]] = []
        exc_holder: list[Exception] = []

        def _run() -> None:
            try:
                exit_code, output = container.exec_run(["bash", "-c", cmd], demux=True)
                result_holder.append((exit_code, output))
            except Exception as e:
                exc_holder.append(e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Thread still running — timeout exceeded
            return ExecResult(stdout="", stderr="", exit_code=1, timed_out=True)

        if exc_holder:
            raise RuntimeError(f"docker exec error: {exc_holder[0]}") from exc_holder[0]

        exit_code, (raw_stdout, raw_stderr) = result_holder[0]
        return ExecResult(
            stdout=raw_stdout.decode() if raw_stdout else "",
            stderr=raw_stderr.decode() if raw_stderr else "",
            exit_code=exit_code,
            timed_out=False,
        )

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def copy_to(self, src: Path, dst_in_container: str) -> None:
        """Copy a single file from host into the container."""
        import docker

        try:
            container = self._client.containers.get(self._name)
        except docker.errors.NotFound:
            raise RuntimeError("sandbox not running")

        dst_path = dst_in_container.rstrip("/")
        dst_dir = dst_path.rsplit("/", 1)[0] if "/" in dst_path else "/"
        arcname = dst_path.rsplit("/", 1)[-1]

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            tar.add(str(src), arcname=arcname)
        buf.seek(0)

        try:
            container.put_archive(dst_dir, buf)
        except docker.errors.APIError as e:
            raise RuntimeError(f"copy_to failed: {e}") from e
