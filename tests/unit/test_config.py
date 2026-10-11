from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lacuna.config import ScanConfig, SourceSpec, TargetSpec, load_config, load_target_spec


@pytest.fixture
def libpng_yaml() -> Path:
    return Path(__file__).parent.parent.parent / "targets" / "example_libpng.yaml"


@pytest.fixture
def openssl_yaml() -> Path:
    return Path(__file__).parent.parent.parent / "targets" / "example_openssl.yaml"


def test_source_spec_defaults():
    s = SourceSpec(type="git")
    assert s.url == ""
    assert s.ref == ""
    assert s.path == ""


def test_target_spec_defaults():
    spec = TargetSpec(
        name="foo",
        version="1.0",
        source=SourceSpec(type="local", path="/tmp/foo"),
        language="c",
    )
    assert spec.description == ""
    assert spec.attack_surface_hint == ""
    assert spec.build_hint == ""


def test_scan_config_defaults(minimal_target_spec: TargetSpec):
    cfg = ScanConfig(target_spec=minimal_target_spec)
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.max_iterations == 50
    assert cfg.max_tokens == 8192
    assert cfg.sandbox_name == "lacuna-sandbox"
    assert cfg.timeout_per_tool == 30
    assert cfg.verbose is False


def test_load_target_spec_libpng(libpng_yaml: Path):
    spec = load_target_spec(libpng_yaml)
    assert spec.name == "libpng"
    assert spec.version == "1.6.40"
    assert spec.source.type == "git"
    assert "libpng" in spec.source.url
    assert spec.language == "c"
    assert spec.attack_surface_hint != ""
    assert spec.build_hint != ""


def test_load_target_spec_openssl(openssl_yaml: Path):
    spec = load_target_spec(openssl_yaml)
    assert spec.name == "openssl"
    assert spec.source.type == "git"
    assert spec.language == "c"


def test_load_config_defaults(libpng_yaml: Path, tmp_path: Path):
    cfg = load_config(libpng_yaml, reports_dir=tmp_path)
    assert cfg.target_spec.name == "libpng"
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.max_iterations == 50
    assert cfg.reports_dir == tmp_path


def test_load_config_overrides(libpng_yaml: Path, tmp_path: Path):
    cfg = load_config(
        libpng_yaml,
        model="claude-haiku-4-5-20251001",
        max_iterations=10,
        verbose=True,
        reports_dir=tmp_path,
    )
    assert cfg.model == "claude-haiku-4-5-20251001"
    assert cfg.max_iterations == 10
    assert cfg.verbose is True


def test_load_target_spec_local(tmp_path: Path):
    yaml_data = {
        "name": "mylib",
        "version": "2.0.0",
        "source": {"type": "local", "path": "/tmp/mylib"},
        "language": "cpp",
        "description": "A test library",
    }
    yaml_file = tmp_path / "mylib.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    spec = load_target_spec(yaml_file)
    assert spec.name == "mylib"
    assert spec.source.type == "local"
    assert spec.source.path == "/tmp/mylib"
    assert spec.language == "cpp"


def test_load_target_spec_rejects_absolute_path(tmp_path: Path):
    """Test that absolute paths in target name are rejected."""
    yaml_data = {
        "name": "/etc/passwd",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot be an absolute path"):
        load_target_spec(yaml_file)


def test_load_target_spec_rejects_parent_traversal(tmp_path: Path):
    """Test that parent directory traversal in target name is rejected."""
    yaml_data = {
        "name": "../../etc/passwd",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot contain path separators"):
        load_target_spec(yaml_file)


def test_load_target_spec_rejects_dotdot(tmp_path: Path):
    """Test that '..' as target name is rejected."""
    yaml_data = {
        "name": "..",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot be '.' or '..'"):
        load_target_spec(yaml_file)


def test_load_target_spec_rejects_dot(tmp_path: Path):
    """Test that '.' as target name is rejected."""
    yaml_data = {
        "name": ".",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot be '.' or '..'"):
        load_target_spec(yaml_file)


def test_load_target_spec_rejects_path_with_slash(tmp_path: Path):
    """Test that target names with slashes are rejected."""
    yaml_data = {
        "name": "foo/bar",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot contain path separators"):
        load_target_spec(yaml_file)


def test_load_target_spec_rejects_path_with_backslash(tmp_path: Path):
    """Test that target names with backslashes are rejected."""
    yaml_data = {
        "name": "foo\\bar",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot contain path separators"):
        load_target_spec(yaml_file)


def test_load_target_spec_rejects_empty_name(tmp_path: Path):
    """Test that empty target name is rejected."""
    yaml_data = {
        "name": "",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot be empty"):
        load_target_spec(yaml_file)


def test_load_target_spec_rejects_null_byte(tmp_path: Path):
    """Test that target names with null bytes are rejected."""
    yaml_data = {
        "name": "foo\x00bar",
        "version": "1.0.0",
        "source": {"type": "local", "path": "/tmp/test"},
        "language": "c",
    }
    yaml_file = tmp_path / "malicious.yaml"
    yaml_file.write_text(yaml.dump(yaml_data))

    with pytest.raises(ValueError, match="cannot contain null bytes"):
        load_target_spec(yaml_file)
