from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from lacuna.config import TargetSpec


def stage_target(spec: TargetSpec, workspace_dir: Path) -> Path:
    """
    Stage the target source on the HOST into workspace_dir/<spec.name>/.
    Returns the path to the staged directory.

    Raises RuntimeError with a descriptive message on any failure.
    Raises ValueError for unsupported source types.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    dst = workspace_dir / spec.name

    source_type = spec.source.type

    if source_type == "local":
        _stage_local(spec, dst)
    elif source_type == "git":
        _stage_git(spec, dst)
    elif source_type == "tarball":
        _stage_tarball(spec, dst)
    else:
        raise ValueError(f"unsupported source type: {source_type!r}")

    return dst


def _stage_local(spec: TargetSpec, dst: Path) -> None:
    src = Path(spec.source.path)
    if not src.exists():
        raise RuntimeError(f"local source path does not exist: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _stage_git(spec: TargetSpec, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    cmd = ["git", "clone", "--depth", "1"]
    if spec.source.ref:
        cmd += ["--branch", spec.source.ref]
    cmd += [spec.source.url, str(dst)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        raise RuntimeError(f"git clone failed: {stderr}") from e


def _stage_tarball(spec: TargetSpec, dst: Path) -> None:
    url = spec.source.url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError(f"tarball URL must use http/https, got: {parsed.scheme!r}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        filename = url.split("/")[-1].split("?")[0] or "archive"
        archive_path = tmp_path / filename

        try:
            urllib.request.urlretrieve(url, str(archive_path))
        except Exception as e:
            raise RuntimeError(f"failed to download tarball from {url}: {e}") from e

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        lower = filename.lower()
        try:
            if lower.endswith(".zip"):
                with zipfile.ZipFile(archive_path) as zf:
                    zf.extractall(extract_dir)
            elif any(
                lower.endswith(ext) for ext in (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")
            ):
                with tarfile.open(archive_path) as tf:
                    tf.extractall(extract_dir)
            else:
                raise RuntimeError(f"unrecognised archive extension: {filename}")
        except (tarfile.TarError, zipfile.BadZipFile) as e:
            raise RuntimeError(f"failed to extract archive: {e}") from e

        # Find the extracted root (usually a single top-level directory)
        entries = list(extract_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            extracted_root = entries[0]
        else:
            extracted_root = extract_dir

        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(extracted_root, dst)
