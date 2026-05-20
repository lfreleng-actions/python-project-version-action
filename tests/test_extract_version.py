#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Comprehensive fixture-based tests for ``extract_version.py``.

Each test materialises a small fixture project in a temp directory, runs
the extractor, and asserts on the captured ``GITHUB_OUTPUT`` lines. The
fixtures are inlined here rather than living on disk so the test surface
is fully self-contained and obvious at review time.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "extract_version.py"


def _run(tmp_path: Path, files: dict[str, str]) -> tuple[int, dict[str, str], str, str]:
    """Materialise ``files`` under ``tmp_path`` and run the extractor.

    Returns ``(returncode, outputs, stdout, stderr)``. ``outputs`` is the
    parsed ``GITHUB_OUTPUT`` content (``key=value`` lines).
    """
    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    github_output = tmp_path / ".github_output"
    github_output.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["GITHUB_OUTPUT"] = str(github_output)
    env["INPUT_PATH_PREFIX"] = str(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    outputs: dict[str, str] = {}
    for line in github_output.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            outputs[key] = value

    return proc.returncode, outputs, proc.stdout, proc.stderr


# -- pyproject.toml -----------------------------------------------------


def test_pyproject_static_version(tmp_path: Path) -> None:
    """A modern PEP 621 pyproject.toml with a literal version."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "pyproject.toml": ('[project]\nname = "modern-pkg"\nversion = "1.2.3"\n'),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "1.2.3"
    assert out["dynamic_version"] == "false"
    assert out["dynamic_provider"] == ""
    assert out["source"].endswith("pyproject.toml")


def test_pyproject_dynamic_version_with_setuptools_scm(tmp_path: Path) -> None:
    """pyproject.toml declaring dynamic=['version'] with setuptools-scm."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "pyproject.toml": (
                "[build-system]\n"
                'requires = ["setuptools>=61", "setuptools_scm>=6.0"]\n'
                "\n"
                "[project]\n"
                'name = "scm-pkg"\n'
                'dynamic = ["version"]\n'
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_version"] == "true"
    assert out["dynamic_provider"] == "setuptools-scm"


def test_pyproject_dynamic_version_with_hatch_vcs(tmp_path: Path) -> None:
    """pyproject.toml declaring dynamic=['version'] with hatch-vcs."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "pyproject.toml": (
                "[build-system]\n"
                'requires = ["hatchling", "hatch-vcs"]\n'
                "\n"
                "[project]\n"
                'name = "hatch-pkg"\n'
                'dynamic = ["version"]\n'
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "hatch-vcs"


def test_pyproject_poetry(tmp_path: Path) -> None:
    """Poetry-style pyproject.toml without a [project] table."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "pyproject.toml": (
                '[tool.poetry]\nname = "poetry-pkg"\nversion = "0.5.0"\n'
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "0.5.0"
    assert out["dynamic_version"] == "false"


# -- setup.cfg ----------------------------------------------------------


def test_setup_cfg_static(tmp_path: Path) -> None:
    """Declarative setuptools setup.cfg with literal version."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.cfg": ("[metadata]\nname = cfg-pkg\nversion = 0.9.0\n"),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "0.9.0"
    assert out["source"].endswith("setup.cfg")
    assert out["dynamic_version"] == "false"


def test_setup_cfg_attr_indirection_is_dynamic(tmp_path: Path) -> None:
    """``attr:`` version indirection must report dynamic."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.cfg": (
                "[metadata]\nname = attr-pkg\nversion = attr: attr_pkg.__version__\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "setuptools-dynamic"


def test_setup_cfg_file_indirection_is_dynamic(tmp_path: Path) -> None:
    """``file:`` version indirection must report dynamic."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.cfg": ("[metadata]\nname = file-pkg\nversion = file: VERSION\n"),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "setuptools-dynamic"


def test_pbr_setup_cfg_plus_setup_py_shim(tmp_path: Path) -> None:
    """Canonical OpenStack/PBR layout: declarative setup.cfg + minimal
    setup.py shim carrying the pbr=True marker. setup.cfg alone provides
    no version, so the action must read setup.py to detect PBR and emit
    ``dynamic``.
    """
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.cfg": (
                "[metadata]\n"
                "name = pbr-pkg\n"
                "author = Test\n"
                "author-email = test@example.org\n"
            ),
            "setup.py": (
                "from setuptools import setup\n"
                "setup(setup_requires=['pbr'], pbr=True)\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "pbr"


def test_setup_cfg_with_setup_requires_scm(tmp_path: Path) -> None:
    """setup.cfg declaring setuptools_scm in [options].setup_requires."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.cfg": (
                "[metadata]\n"
                "name = scm-cfg-pkg\n"
                "\n"
                "[options]\n"
                "setup_requires =\n"
                "    setuptools_scm\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "setuptools-scm"


def test_setup_cfg_hyphenated_keys(tmp_path: Path) -> None:
    """Older setup.cfg with hyphenated keys must still extract version."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.cfg": (
                "[metadata]\nname = hyphen-pkg\nauthor-email = a@b\nversion = 3.4.5\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "3.4.5"


# -- setup.py -----------------------------------------------------------


def test_setup_py_double_quoted(tmp_path: Path) -> None:
    """Plain setup.py with double-quoted version string."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.py": (
                "from setuptools import setup\n"
                'setup(name="quoted-pkg", version="2.0.0")\n'
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "2.0.0"
    assert out["source"].endswith("setup.py")


def test_setup_py_single_quoted(tmp_path: Path) -> None:
    """Plain setup.py with single-quoted version string."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.py": (
                "from setuptools import setup\n"
                "setup(name='single-pkg', version='1.0.0')\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "1.0.0"


def test_setup_py_pbr_only(tmp_path: Path) -> None:
    """setup.py-only PBR project (no setup.cfg)."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.py": (
                "from setuptools import setup\n"
                "setup(name='pbr-only', setup_requires=['pbr>=2.0'], pbr=True)\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "pbr"


def test_setup_py_use_scm_version(tmp_path: Path) -> None:
    """setup.py-only project using setuptools-scm."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.py": (
                "from setuptools import setup\n"
                "setup(name='scm-only', use_scm_version=True)\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "setuptools-scm"


def test_setup_py_versioneer(tmp_path: Path) -> None:
    """setup.py-only project using versioneer."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.py": (
                "from setuptools import setup\n"
                "import versioneer\n"
                "setup(name='vsn-pkg',\n"
                "      version=versioneer.get_version(),\n"
                "      cmdclass=versioneer.get_cmdclass())\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "versioneer"


def test_setup_py_runtime_attr(tmp_path: Path) -> None:
    """setup.py-only project referencing __version__ at runtime."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "setup.py": (
                "from pkg import __version__\n"
                "from setuptools import setup\n"
                "setup(name='rtattr-pkg', version=__version__)\n"
            ),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "dynamic"
    assert out["dynamic_provider"] == "runtime-attr"


# -- precedence ---------------------------------------------------------


def test_pyproject_takes_precedence_over_setup_cfg(tmp_path: Path) -> None:
    """pyproject.toml wins when both files declare a static version."""
    rc, out, _, _ = _run(
        tmp_path,
        {
            "pyproject.toml": ('[project]\nname = "p"\nversion = "9.9.9"\n'),
            "setup.cfg": ("[metadata]\nname = p\nversion = 0.0.0\n"),
        },
    )
    assert rc == 0
    assert out["python_project_version"] == "9.9.9"
    assert out["source"].endswith("pyproject.toml")


# -- error paths --------------------------------------------------------


def test_missing_metadata_files(tmp_path: Path) -> None:
    """No pyproject.toml/setup.cfg/setup.py => error."""
    rc, _, _, stderr = _run(tmp_path, {})
    assert rc != 0
    assert "no Python project metadata" in stderr


def test_metadata_present_but_no_version(tmp_path: Path) -> None:
    """A file exists but contains no version field nor dynamic markers."""
    rc, _, _, stderr = _run(
        tmp_path,
        {
            "setup.cfg": ("[metadata]\nname = no-version\n"),
        },
    )
    assert rc != 0
    assert "version extraction failed" in stderr


def test_invalid_path_prefix(tmp_path: Path) -> None:
    """A non-existent path_prefix must fail cleanly."""
    env = os.environ.copy()
    env["INPUT_PATH_PREFIX"] = str(tmp_path / "does-not-exist")
    env["GITHUB_OUTPUT"] = str(tmp_path / "out")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode != 0
    assert "invalid path/prefix" in proc.stderr


# -- helper-level coverage ---------------------------------------------


def test_helper_detect_dynamic_provider_setup_py() -> None:
    """Direct unit-test of the setup.py provider detector."""
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        from extract_version import detect_dynamic_provider_setup_py as detect
    finally:
        sys.path.pop(0)

    assert detect("setup(pbr=True)") == "pbr"
    assert detect("setup_requires=['pbr']") == "pbr"
    assert detect("setup_requires=['setuptools_scm>=6.0']") == "setuptools-scm"
    assert detect("setup_requires = [ 'setuptools-scm' ]") == "setuptools-scm"
    assert detect("setup(use_scm_version=True)") == "setuptools-scm"
    assert detect("versioneer.get_version()") == "versioneer"
    assert detect("setup(version='1.0')") == ""
    assert detect("setup(version=__version__)") == "runtime-attr"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
