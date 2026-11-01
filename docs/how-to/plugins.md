<!--
*******************************************************************************
Copyright (c) 2026 Contributors to the Eclipse Foundation

See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.

This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0

SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# Write a pack

A pack is a directory holding capability factories (`@capability`) and actions (`@state`). A composition names
them by label (`<pack>.<name>`); tests reach them only through roles. A pack is optional: code in a project's
own conftest is the pack `project` and works the same way.

## Layout

```
score/itf/packs/<pack>/
  pack.yaml        name, version, prerequisites
  __init__.py      one-line description
  <topic>.py       implementation: classes, config dataclasses, the Protocols they expect
  providers.py     @capability factories only: import from topic modules, declare
  steps.py         @state actions and their probes only
  plugin.py        pytest_plugins = ["...providers", "...steps"]   (the entry point)
  contracts/       optional contract definitions the pack ships
  README.md        the label table, host prerequisites and a composition excerpt
  BUILD            py_library(name = "lib") + py_itf_plugin
```

`pack.yaml` carries what tools read: the pack's `name` (the first segment of every label), `version` and
`prerequisites` (host requirements, read by `itf doctor`).

```yaml
name: docker
version: 0.1.0
prerequisites:
  - a Docker-compatible daemon (DOCKER_HOST for Podman)
```

A pack is loaded from a label: the module `score.itf.packs.<name>.plugin`, or, for a pack outside the ITF
repository, an entry point of the group `score_itf.packs` (`acme = acme.plugin`). A vendor's distribution adds
`score_itf.contracts` for its definitions (see `examples/examples/vendor_contract`).

## Factories

```python
@capability("exec.command")                   # the contract this factory fulfils; label <pack>.exec
def exec(platform: Platform) -> DockerExec:   # a slot: the factory's own Protocol with __contract__
    return DockerExec(platform)

@capability("platform.instance", label="platform")
def make_platform(config: PlatformConfig) -> Iterator[DockerPlatform]:   # a generator: teardown after yield
    platform = DockerPlatform(config)
    yield platform
    platform.stop()
```

- The return annotation is what the factory publishes. `gives=("host", "port")` overrides it.
- A slot is a parameter annotated with a class that sets `__contract__`; the class's members are the shape the
  factory expects. Never import another pack: write your own Protocol with only the members you use.
- `config: <dataclass>` is the settings schema (`with:` in a composition); a typo fails at plan time with the
  role named.
- Constructing starts nothing. Starting is an action's job.
- `@major` after a contract name (`"exec.command@1"`) says which major the factory fulfils, or a slot expects;
  when both sides give one they must agree.

## Actions

```python
@state("platform.up", label="start")
def start_platform(platform: Platform) -> None:
    platform.start()

@start_platform.probe
def platform_is_up(platform: Platform) -> bool:
    return platform.running()

@state("shell.open", after=("platform.up",), also=("network.reachable",), label="open")
def open_session(shell: Shell) -> None:
    shell.connect()

@open_session.probe_for("network.reachable")
def is_reachable(shell: Shell) -> bool: ...
```

- The probe takes the same slots as the action and decides whether the state holds; it must be cheap, safe to
  repeat and never change anything.
- `after=` lists states that must hold first; `breaks=` lists states the action destroys; `also=` lists further
  states the one action makes true, each with its own `probe_for`.
- Two actions that make the same state true are fine; a composition picks one with `by:`.

## Conformance and definitions

A contract a pack fulfils may have a definition (`contracts/<area>.yaml`) naming a `conformance:` module whose
`CHECKS` (keyed by contract name) hold the checks:

```python
@check()
def a_failing_command_reports_its_exit_code_without_raising(node):
    code, _ = node.exec("sh -c 'exit 3'")
    expect(code == 3, f"exit code was {code}")
```

`//score/itf/contracts:conformance` runs every check against every part of a target that claims the contract.
See [Use, define and enforce contracts](contracts.md).

## BUILD

```starlark
py_library(name = "lib", srcs = glob(["**/*.py"]) + ["//score/itf/packs:init"],
           data = ["README.md", "pack.yaml"] + glob(["contracts/*.yaml"]),
           deps = ["//score/itf/contracts", "//score/itf/core"])
py_itf_plugin(name = "<pack>", enabled_plugins = ["score.itf.packs.<pack>.plugin"], py_library = ":lib")
```

Binaries a pack runs are built by Bazel and found through runfiles (see the dlt and pcap packs). Add unit tests
under `test/packs/`, and a composition for the pack to `test/integration/targets/` so the generic suite runs on
it. The pack README is generated with the catalog; refresh it with the tools under `//tools`.
