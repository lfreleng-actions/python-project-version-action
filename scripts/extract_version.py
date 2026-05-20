#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Extract the version of a Python project.

Supported sources, in priority order:

1. ``pyproject.toml`` (PEP 621 ``[project].version`` or
   ``[tool.poetry].version``; ``dynamic = ["version"]`` is recognised).
2. ``setup.cfg`` (``[metadata] version`` field; ``attr:``/``file:``
   indirection is recognised as dynamic).
3. ``setup.py`` (regex-based extraction, single- and double-quoted forms).

When the project uses a dynamic versioning provider (PBR,
setuptools-scm, versioneer, setuptools-dynamic) the script emits
``version=dynamic`` and surfaces the provider via ``dynamic_provider``.

Outputs (one per line, ``key=value``) are written to ``GITHUB_OUTPUT``
when running inside a GitHub Action and to stdout when running stand-alone:

* ``python_project_version`` -- the resolved version, or the literal
  ``dynamic`` for dynamic-versioned projects.
* ``source`` -- the file path the version (or dynamic flag) was derived
  from.
* ``dynamic_version`` -- ``true`` when a dynamic provider was detected.
* ``dynamic_provider`` -- ``pbr`` | ``setuptools-scm`` | ``hatch-vcs`` |
  ``versioneer`` | ``setuptools-dynamic`` | ``pyproject-dynamic`` |
  ``runtime-attr`` | ``""`` (static).
"""

from __future__ import annotations

import argparse
import configparser
import os
import re
import sys
from pathlib import Path

try:  # pragma: no cover - exercised on Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]


# Regex patterns shared by setup.py and setup.cfg analysis.
_PBR_IN_SETUP_REQUIRES = re.compile(
    r"setup_requires\s*=\s*\[[^\]]*['\"]pbr",
    re.IGNORECASE,
)
_SCM_IN_SETUP_REQUIRES = re.compile(
    r"setup_requires\s*=\s*\[[^\]]*['\"]setuptools[_-]scm",
    re.IGNORECASE,
)
_PBR_KWARG = re.compile(r"\bpbr\s*=\s*True\b", re.IGNORECASE)

# Match ``version=`` assignments referencing a non-literal identifier such
# as ``__version__``, ``pkg.__version__``, ``get_version`` or
# ``read_version`` (with or without a trailing call). Anchoring on
# ``version\s*=`` avoids false positives from unrelated occurrences of
# the ``__version__`` substring in imports, docstrings, or comments.
_RUNTIME_ATTR_ASSIGN = re.compile(
    r"\bversion\s*=\s*(?:[\w.]*__version__|get_version|read_version)\b",
)


def detect_dynamic_provider_setup_py(text: str) -> str:
    """Return the dynamic-versioning provider implied by setup.py.

    Returns the empty string when no dynamic-versioning marker is found.
    """
    if _PBR_KWARG.search(text) or _PBR_IN_SETUP_REQUIRES.search(text):
        return "pbr"
    if "use_scm_version" in text or _SCM_IN_SETUP_REQUIRES.search(text):
        return "setuptools-scm"
    if "versioneer.get_version" in text or "versioneer.get_cmdclass" in text:
        return "versioneer"
    if _RUNTIME_ATTR_ASSIGN.search(text):
        return "runtime-attr"
    return ""


def detect_dynamic_provider_setup_cfg(cfg: configparser.ConfigParser) -> str:
    """Return the dynamic-versioning provider implied by setup.cfg.

    Returns the empty string when no dynamic-versioning marker is found.
    """
    if cfg.has_section("pbr"):
        return "pbr"

    if cfg.has_option("metadata", "version"):
        version = cfg.get("metadata", "version").strip()
        if version.startswith("attr:") or version.startswith("file:"):
            return "setuptools-dynamic"

    if cfg.has_option("options", "setup_requires"):
        for line in cfg.get("options", "setup_requires").splitlines():
            line = line.strip().lower()
            if not line:
                continue
            if "pbr" in line:
                return "pbr"
            if "setuptools_scm" in line or "setuptools-scm" in line:
                return "setuptools-scm"
            if "versioneer" in line:
                return "versioneer"

    return ""


def _read_setup_cfg(path: Path) -> configparser.ConfigParser:
    """Parse setup.cfg, tolerating duplicate keys (older PBR style)."""
    cfg = configparser.ConfigParser(
        interpolation=None,
        strict=False,
        empty_lines_in_values=False,
    )
    # Preserve option keys exactly as written in the file. By default,
    # ``configparser`` lowercases keys via ``optionxform``; assigning
    # ``str`` disables that transform. ``_get_cfg`` then probes both
    # ``author_email`` and ``author-email`` spellings explicitly when
    # reading values.
    cfg.optionxform = str  # type: ignore[assignment,method-assign]
    cfg.read(path, encoding="utf-8")
    return cfg


def _get_cfg(cfg: configparser.ConfigParser, section: str, key: str) -> str:
    """Look up a value in setup.cfg supporting both hyphen and underscore
    spellings (older setuptools / PBR conventions).
    """
    if not cfg.has_section(section):
        return ""
    for candidate in (key, key.replace("_", "-"), key.replace("-", "_")):
        if cfg.has_option(section, candidate):
            return cfg.get(section, candidate).strip()
    return ""


def extract_from_pyproject(path: Path) -> tuple[str, str, str]:
    """Extract ``(version, dynamic_provider, error_message)`` from
    pyproject.toml. ``version`` is the resolved value, the literal
    ``dynamic`` when the project declares dynamic versioning, or empty
    when extraction failed (in which case ``error_message`` is set).
    """
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception as exc:  # pragma: no cover - exercised on bad TOML
        return "", "", f"failed to parse pyproject.toml: {exc}"

    project = data.get("project") or {}
    dynamic_fields = project.get("dynamic") or []
    if "version" in dynamic_fields:
        # Detect provider from build-system requires.
        requires = data.get("build-system", {}).get("requires", []) or []
        joined = " ".join(requires).lower()
        if "setuptools_scm" in joined or "setuptools-scm" in joined:
            return "dynamic", "setuptools-scm", ""
        if "hatch-vcs" in joined:
            return "dynamic", "hatch-vcs", ""
        if "pbr" in joined:
            return "dynamic", "pbr", ""
        return "dynamic", "pyproject-dynamic", ""

    version = project.get("version") or ""
    if not version:
        # Poetry layout: [tool.poetry].version
        tool = data.get("tool") or {}
        poetry = tool.get("poetry") or {}
        version = poetry.get("version") or ""

    return version, "", ""


def extract_from_setup_cfg(
    path: Path, setup_py_text: str | None
) -> tuple[str, str, str]:
    """Extract ``(version, dynamic_provider, error_message)`` from
    setup.cfg. Optionally cross-references ``setup_py_text`` to detect the
    canonical PBR layout (declarative setup.cfg + minimal setup.py shim).
    """
    try:
        cfg = _read_setup_cfg(path)
    except configparser.Error as exc:
        return "", "", f"failed to parse setup.cfg: {exc}"

    provider = detect_dynamic_provider_setup_cfg(cfg)
    if not provider and setup_py_text:
        provider = detect_dynamic_provider_setup_py(setup_py_text)

    if provider:
        return "dynamic", provider, ""

    version = _get_cfg(cfg, "metadata", "version")
    return version, "", ""


def extract_from_setup_py(path: Path) -> tuple[str, str, str]:
    """Extract ``(version, dynamic_provider, error_message)`` from setup.py
    using regex; recognises single- and double-quoted forms as well as
    common dynamic providers.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return "", "", f"failed to read setup.py: {exc}"

    provider = detect_dynamic_provider_setup_py(text)
    if provider in {"pbr", "setuptools-scm", "versioneer"}:
        return "dynamic", provider, ""

    # version='...' / version="..." / version = '...' etc. A static
    # quoted literal wins outright: clear ``provider`` so a stray
    # ``__version__`` reference elsewhere in the file cannot leak a
    # spurious ``runtime-attr`` value to downstream consumers.
    match = re.search(r"""version\s*=\s*['\"]([^'\"]+)['\"]""", text)
    if match:
        return match.group(1), "", ""

    # Fall back to runtime-attr style (version=__version__ etc.) which we
    # cannot resolve statically.
    if provider == "runtime-attr":
        return "dynamic", provider, ""

    return "", "", ""


def emit(outputs: dict[str, str]) -> None:
    """Write outputs as ``key=value`` lines to ``$GITHUB_OUTPUT`` (or
    stdout when the variable is unset).
    """
    target = os.environ.get("GITHUB_OUTPUT")
    handle = open(target, "a", encoding="utf-8") if target else sys.stdout
    try:
        for key, value in outputs.items():
            print(f"{key}={value}", file=handle)
    finally:
        if target:
            handle.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--path-prefix",
        default=os.environ.get("INPUT_PATH_PREFIX", "."),
        help="Directory containing the project metadata files.",
    )
    args = parser.parse_args(argv)

    prefix = Path(args.path_prefix)
    if not prefix.is_dir():
        print(
            f"Error: invalid path/prefix to project directory: {prefix}",
            file=sys.stderr,
        )
        return 1

    pyproject = prefix / "pyproject.toml"
    setup_cfg = prefix / "setup.cfg"
    setup_py = prefix / "setup.py"

    setup_py_text: str | None = None
    if setup_py.is_file():
        try:
            setup_py_text = setup_py.read_text(encoding="utf-8")
        except OSError:
            setup_py_text = None

    version = ""
    provider = ""
    source = ""
    error = ""

    if pyproject.is_file():
        version, provider, error = extract_from_pyproject(pyproject)
        source = str(pyproject)

    if not version and setup_cfg.is_file():
        version, provider, error = extract_from_setup_cfg(setup_cfg, setup_py_text)
        source = str(setup_cfg)

    if not version and setup_py.is_file():
        version, provider, error = extract_from_setup_py(setup_py)
        source = str(setup_py)

    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not version:
        if not (pyproject.is_file() or setup_cfg.is_file() or setup_py.is_file()):
            print(
                "Error: no Python project metadata found "
                "(searched pyproject.toml, setup.cfg, setup.py)",
                file=sys.stderr,
            )
            return 1
        print(
            "Error: Python project version extraction failed; "
            "no version field detected in project metadata",
            file=sys.stderr,
        )
        return 1

    dynamic_flag = "true" if version == "dynamic" else "false"

    emit(
        {
            "python_project_version": version,
            "source": source,
            "dynamic_version": dynamic_flag,
            "dynamic_provider": provider,
        }
    )

    label = f"Python project version: {version} [{source}]"
    if provider:
        label += f" (dynamic_provider={provider})"
    print(f"{label} ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
