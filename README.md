<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# 🐍 Python Project Current Version

Returns the current version of a Python project, derived from any of the
supported metadata locations:

- `pyproject.toml` (PEP 621 `[project].version`, or `[tool.poetry].version`)
- `setup.cfg` (`[metadata] version`)
- `setup.py` (regex-based, single- and double-quoted forms)

The action recognises dynamic versioning providers and reports them via
the `dynamic_provider` output:

- **pbr** — OpenStack / LFIT convention (`pbr = True`, `setup_requires =
  ['pbr']`, or a `[pbr]` section in `setup.cfg`)
- **setuptools-scm** — `use_scm_version`, `setup_requires` containing
  `setuptools_scm`, or `setuptools-scm` listed in `[build-system].requires`
- **versioneer** — `versioneer.get_version` / `get_cmdclass`
- **setuptools-dynamic** — `version = attr:` / `version = file:` in
  `setup.cfg`
- **hatch-vcs** — `hatch-vcs` listed in `[build-system].requires`
- **pyproject-dynamic** — `dynamic = ["version"]` declared without a
  recognised provider
- **runtime-attr** — `version=__version__` style indirection in `setup.py`

## Usage Example

```yaml
  # Code checkout performed in earlier workflow step
  - name: 'Retrieve the current Python project version'
    id: version
    uses: lfreleng-actions/python-project-version-action@main

  - name: 'Print version info'
    run: |
      echo "version:  ${{ steps.version.outputs.python_project_version }}"
      echo "source:   ${{ steps.version.outputs.source }}"
      echo "dynamic:  ${{ steps.version.outputs.dynamic_version }}"
      echo "provider: ${{ steps.version.outputs.dynamic_provider }}"
```

## Inputs

<!-- markdownlint-disable MD013 -->

| Input         | Required | Default | Description                                    |
| ------------- | -------- | ------- | ---------------------------------------------- |
| `path_prefix` | False    | `.`     | Directory path to the repository/project files |

<!-- markdownlint-enable MD013 -->

## Outputs

<!-- markdownlint-disable MD013 -->

| Output                   | Description                                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------------------ |
| `python_project_version` | Current version of the project, or the literal `dynamic` when a dynamic versioning provider is in use. |
| `source`                 | Path to the file that supplied the version (`pyproject.toml`, `setup.cfg`, or `setup.py`).             |
| `dynamic_version`        | `true` when the project uses dynamic versioning, `false` otherwise.                                    |
| `dynamic_provider`       | Identifier of the dynamic versioning provider (see list above). Empty when `dynamic_version` is false. |

<!-- markdownlint-enable MD013 -->

## Implementation

The action delegates version detection to `scripts/extract_version.py`,
a small Python helper bundled with the action. The helper uses the
standard library's `tomllib` (Python 3.11+) / `tomli` (3.10 fallback)
for `pyproject.toml` and `configparser` for `setup.cfg`, and falls back
to regex for `setup.py`. The full unit-test suite lives under `tests/`.
