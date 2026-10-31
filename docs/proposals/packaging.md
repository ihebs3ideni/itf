<!--
*******************************************************************************
Copyright (c) 2025 Contributors to the Eclipse Foundation
See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.
This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0
SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# Proposal: ITF with and without Bazel

**Status:** Plan only. It sets the constraints the design must respect. No implementation is proposed
yet.

## Goal

ITF must work in two kinds of projects:

- **Bazel projects**, as today: packs as Bazel targets, built native tools, Starlark recipes, plans
  checked during the build.
- **Projects without Bazel**: the core and each pack installed as Python wheels from an index, each wheel
  with its own `pyproject.toml` and dependencies, configured from the project's own files, and run with
  `pytest` and the `itf` command.

Both must use the same recipes, contracts, packs and tests. A suite should not need to change when a
project moves from one kind to the other.

## What already fits

- The core and OCTO are plain Python. OCTO uses the standard library only; the core needs `pluggy` and
  `pyyaml`, the pytest adapter needs `pytest`.
- Packs are Python modules whose dependencies come from PyPI (`docker`, `paramiko`, `pyserial`,
  `pydantic`).
- A recipe is a data document read by the YAML frontend. Starlark only produces that document.
- On the platform branch, the `itf` command does without Bazel what the Bazel rules do: `itf plan` checks a
  recipe, `itf up` opens a bench, `itf explain` describes a contract. Contracts are YAML data files.
- `pack.yaml` already lists what wheel metadata needs: name, version, kind, implemented contracts,
  entrypoints, prerequisites.

## What is tied to Bazel today

| Today | Without Bazel |
|---|---|
| A test loads packs because `py_itf_test(plugins = [...])` passes `-p module` to pytest | Packs declare entry points; the adapter loads the installed packs that the configuration enables |
| `score/itf/packs/__init__.py` makes the packs one package | `score.itf.packs` becomes a PEP 420 namespace, so each pack's wheel installs only `score/itf/packs/<name>/` |
| `dlt-receive`, `tcpdump` and `libpcap` are built from source and found in runfiles | Host prerequisites (already the fallback: `bundled()` searches `PATH`), or platform wheels that ship the binaries; `python-dlt` needs `libdlt` |
| Plans are checked by `itf_plan` and plan tests | `itf plan` in CI or a pre-commit hook |
| Benches are `bazel run //pkg:bench` | `itf up <recipe>` |
| Gates and suites run as Bazel test targets | The same tests run with `pytest`; only the BUILD wiring is Bazel's |

## Target layout

| Distribution | Contains |
|---|---|
| `score-itf` | core, OCTO, contracts (data and conformance suites), the pytest adapter, the `itf` command |
| `score-itf-pack-<name>` | one pack: its modules, its `pyproject.toml` with dependencies, entry points and version |

Each pack's `pyproject.toml` declares:

```toml
[project]
name = "score-itf-pack-docker"
version = "0.1.0"
dependencies = ["score-itf>=1.0,<2", "docker>=7"]

[project.entry-points."score_itf.packs"]
docker = "score.itf.packs.docker.plugin"
```

A pack of kind `pytest-plugin` also declares a `pytest11` entry point for its pytest module.

## Configuration without Bazel

The project's own `pyproject.toml` (or `pytest.ini`, or a runner's own flag) chooses the recipe and the
packs; the same resolution serves pytest, the `itf` command and other runners:

```toml
[tool.itf]
recipe = "recipes/board.yaml"
packs = ["docker", "ssh"]
```

- Leaving out `packs` enables every installed pack. Naming them keeps a run reproducible.
- `--itf-config` and `ITF_CONFIG`, which exist today, override `recipe` per run.
- `${NAME:-default}` in a recipe takes values from the environment, which is how a CI job passes an
  image name or an address.
- The conftest keeps the code half, as today: `itf_verify`, `itf_teardown`, fixtures and bench-local
  actions.

## Design statements to realign

These parts of the current design assume Bazel and must change before either branch is proposed for
release:

1. **YAML is a first-class authoring format.** The platform branch calls Starlark "primary" and YAML
   "interchange", and its examples dropped their YAML recipes. The rule becomes: the recipe document is the
   contract, YAML writes it everywhere, Starlark is a Bazel convenience that compiles to it (labels instead
   of paths, plans in the build). Examples keep a YAML variant of each recipe.
2. **One source for pack metadata.** A pack's version, contracts and entry points live in its
   `pyproject.toml`; `pack.yaml` is generated from it or reduced to what Python metadata cannot hold (kind,
   prerequisites), and the gate checks they agree.
3. **Discovery by entry points in both worlds.** Bazel's `py_itf_plugin` keeps passing `-p module`, but
   the adapter's selection logic is the same one that reads entry points, so a pack behaves the same
   whether Bazel or pip installed it.
4. **Native tools are prerequisites first.** A pack that uses a native tool finds it on `PATH`, states it
   in its prerequisites and checks it when used; Bazel's hermetic build is an optimisation, not a
   requirement.
5. **No runfiles outside Bazel-specific helpers.** Code that looks up runfiles keeps a `PATH` fallback and
   lives in one helper per pack.
6. **The recipe comes from configuration, for every runner.** Which recipe a run uses is said once, in
   the project's configuration: `--itf-recipe` (or a runner's own flag), `ITF_RECIPE`, `[tool.itf] recipe`
   in `pyproject.toml`, or, under Bazel, `py_itf_test(recipe = ...)`. The resolution and the step that
   turns a recipe into `itf_setup`/`itf_init` live in the runner-agnostic core
   (`resolve()`, `recipe_contributor()`, `Session(recipe=...)`), so pytest, the `itf` command and any
   other runner load a recipe the same way. A conftest holds only code (`itf_verify`, `itf_teardown`,
   fixtures, local actions) and never loads the recipe itself. Generating a conftest from the recipe was
   considered and rejected: it collides with the user's own `conftest.py` in Bazel's runfiles, merges
   Python by text, loses the document that plans and tools read, and erases which declarations came from
   the recipe and which from the project.
7. **Every user-facing tool exists as a command.** Anything a Bazel rule offers (plan, bench, catalog,
   contracts reference) is also an `itf` subcommand, and the Bazel rule calls that subcommand.

## Verification to add

- A CI job without Bazel: build the wheels, install them in a fresh virtual environment, run
  `itf plan` on the example YAML recipes, then `pytest` on the integration suite with the local and
  docker recipes.
- A check that the YAML and Starlark variants of each example compile to the same document (the
  integration suite already has one such equivalence test).

## Order of work (when it is scheduled)

1. Namespace package, per-distribution `pyproject.toml`, entry points.
2. `[tool.itf]` configuration and the adapter reading entry points.
3. Native tools as prerequisites; runfiles behind helpers.
4. YAML back as a first-class format in the examples and docs; equivalence checks.
5. The CI job without Bazel; publishing wheels.

## Open questions

- One index for all wheels, or the core on PyPI and packs where their owners publish them?
- Does `score-itf` include the pytest adapter, or is it a separate `score-itf-pytest` so other runners
  do not install pytest?
- How are contract versions expressed in wheel metadata: an extra, a dependency on a contracts
  distribution, or `pack.yaml` only?
