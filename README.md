<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# 🐍 Python Project Current Version

Returns the current version of a Python Project declared in the metadata
description/files. Supports both pyproject.toml and setup.py locations.

## python-project-version-action

## Usage Example

An example workflow step using this action:

```yaml
  # Code checkout performed in earlier workflow step
  - name: 'Retrieve the current Python project version'
    uses: lfreleng-actions/python-project-version-action@main
```

## Inputs

<!-- markdownlint-disable MD013 -->

| Output Variable     | Required | Description                                    |
| ------------------- | -------- | ---------------------------------------------- |
| path_prefix         | False    | Directory path to the repository/project files |

<!-- markdownlint-enable MD013 -->

## Outputs

<!-- markdownlint-disable MD013 -->

| Output Variable        | Description                                                   |
| ---------------------- | ------------------------------------------------------------- |
| python_project_version | Current version of the Python Project                         |
| source                 | Project metadata/description file [ pyproject.toml/setup.py ] |

Note: python_project_version set to 'dynamic' when dynamic project versioning enabled

<!-- markdownlint-enable MD013 -->
