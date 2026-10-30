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
# Integration Test Framework (ITF)

ITF is a [`pytest`](https://docs.pytest.org)-based framework for testing ECUs and the software on
them: in Docker containers, QEMU virtual machines and on real hardware, with Bazel.

A test target is **composed from packs**, not coded as a class. Each pack publishes *contracts*:
capabilities a test can hold (`itf.capabilities.exec.command`, `...files.transfer`, ...) and states
an action makes true (`itf.states.platform.up`, `itf.states.shell.open`, ...). A **recipe** (the
test's root `conftest.py`, in Python or YAML) picks providers and states goals; the **OCTO**
planner derives what to construct and in which order to run actions, before any test starts.
Tests ask for contracts by token, so the same test runs on a container, a VM or a bench.

```
tests ──(contract tokens)──► target ◄── recipe (conftest.py / YAML): nodes, goals, relations
                               ▲
           ITF core: session, gating, bring-up, probes, unwind ── OCTO: the two-gate planner
                               ▲
   packs: docker · qemu · ssh · net · ping · dlt · pcap · serial · core_dump   (+ sim variants)
```

## Quick start

`MODULE.bazel`:

```starlark
bazel_dep(name = "score_itf", version = "...")
```

`BUILD`:

```starlark
load("@score_itf//:defs.bzl", "py_itf_test")

py_itf_test(
    name = "test_container",
    srcs = ["conftest.py", "test_container.py"],
    data = ["recipe.yaml"],
    plugins = ["@score_itf//score/itf/packs/docker"],
)
```

`recipe.yaml`:

```yaml
setup:
  nodes:
    - name: platform
      contract: itf.capabilities.platform.instance
      using: docker.instance
      config:
        image: ubuntu:24.04
    - name: command
      contract: itf.capabilities.exec.command
      using: docker.exec
    - name: files
      contract: itf.capabilities.files.transfer
      using: docker.files
init:
  goals:
    - itf.states.platform.up
```

`conftest.py` (the recipe):

```python
from pathlib import Path
from score.itf.core import hookimpl, load_init, load_setup

RECIPE = Path(__file__).with_name("recipe.yaml")

@hookimpl
def itf_setup(ctx):
    load_setup(ctx, RECIPE)

@hookimpl
def itf_init(ctx):
    load_init(ctx, RECIPE)
```

`test_container.py`:

```python
import score.itf as itf

@itf.requires("itf.capabilities.exec.command")
def test_hello(target):
    assert target.command.exec("echo -n hello") == (0, "hello")
```

```bash
bazel test //:test_container                                   # bring up, run, tear down
bazel test //:test_container --test_arg=--itf-plan --test_output=all   # plan only, nothing runs
```

Artifacts land in `bazel-testlogs/<target>/test.outputs/itf-run/`: `plan.json`, `target.html`
(an interactive view of the composed target), `test.log` and `events.jsonl`.

## Packs

| Pack (Bazel label) | Provides | Delivers |
|---|---|---|
| `//score/itf/packs/docker` (`:sim`) | `platform.instance`, `exec.command`, `exec.process`, `files.transfer`, `descriptor.endpoint` | `platform.up` |
| `//score/itf/packs/qemu` | `platform.instance`, `exec.console`, `descriptor.endpoint`, `descriptor.credentials` | `platform.up`, `console.open` |
| `//score/itf/packs/ssh` (`:sim`) | `exec.shell`, `exec.command`, `exec.process`, `files.transfer` (SFTP) | `shell.open` + `network.reachable` |
| `//score/itf/packs/net` | `descriptor.endpoint`, `descriptor.credentials` (key or password) | — |
| `//score/itf/packs/ping` (`:boot`) | `net.ping` (ICMP without a ping binary) | `platform.up` for hardware (`:boot`) |
| `//score/itf/packs/dlt` (`:multicast`, `:receive`, `:on_target`, `:sim`) | `observe.logs` | `logs.active` |
| `//score/itf/packs/pcap` (`:host`, `:sim`) | `observe.capture` (tcpdump built from source) | `capture.running` |
| `//score/itf/packs/serial` | `exec.console`, `exec.command` | `console.open` |
| `//score/itf/packs/core_dump` | core files copied off the target at teardown | — |

Everything a pack offers (members, signatures, config keys, prerequisites) is in the catalog,
built from the packs' own code:

```bash
bazel run //tools/catalog:query -- schema
bazel run //tools/catalog:query -- search "serial console boot log"
bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider = 'docker.instance'"
bazel run //tools/catalog:query -- serve
```

Docker and QEMU are two providers of the same platform contract: switching a test between them is
a recipe change, not a test change. `test/integration` runs one capability-gated suite against
recipes for the host, containers, DLT benches and QEMU machines; each runs exactly the tests its
platform supports (the matrix is in its README).

## Concepts in one table

| Word | Is | Example |
|---|---|---|
| capability | an object a test uses, named by a contract token | `itf.capabilities.exec.shell` |
| provider | one implementation of a capability, chosen with `using:` | `ssh.shell` |
| state | a condition with a probe that checks it | `itf.states.shell.open` |
| action | what makes a state true; may `require`/`invalidate` others | `ssh.open_session` |
| node | one named instance in a scope; tests reach it as `target.<name>` | `target.shell` |
| scope | the root, plus one per device: `target.gw.shell` | `gw` |
| recipe | the root conftest: nodes (`itf_setup`) and goals (`itf_init`) | `recipe.yaml` |

A test changes bench state only through the planner: `target.reach(state)` (e.g. after
`target.platform.restart()`), or `target.renew(node)` for fresh objects. Called from a pytest
fixture, `renew` gives per-test isolation at whatever scope the fixture has.

## Writing packs and recipes

- [docs/how-to/write_tests.md](docs/how-to/write_tests.md): recipes, YAML, scopes, gating, reach/renew.
- [docs/how-to/plugins.md](docs/how-to/plugins.md): writing a pack.
- [docs/how-to/migrate.md](docs/how-to/migrate.md): from the original plugin API, and a legacy layer for old tests.
- [score/itf/core/octo/README.md](score/itf/core/octo/README.md): the planner on its own.
- [.github/skills/itf/SKILL.md](.github/skills/itf/SKILL.md): a guide for coding agents (see below).
- [docs/decisions/DR-003-infra-starlark-recipes.md](docs/decisions/DR-003-infra-starlark-recipes.md): proposed Starlark recipes.

## Agent skill

`.github/skills/itf` is a skill for coding agents (Claude Code, Copilot and similar tools that load
`SKILL.md` skills from `.github/skills`). It lets an agent work with ITF without prior knowledge:

| The agent can | How |
|---|---|
| Answer "what can ITF do on this target?" | queries the pack catalog (`bazel run //tools/catalog:query`): capabilities, providers, members and signatures, states, actions, config keys, prerequisites |
| Find the provider for a requirement | full-text `search` over the catalog; "no matches" is reported as a gap |
| Turn a requirement or an old test into a recipe and tests | decomposes it into scopes, capabilities, states and relations, maps each to a catalog row, writes the recipe (Python, YAML or Starlark) and gated tests |
| Validate without hardware | `--itf-plan` resolves both gates and selects the tests; never touches a device |
| Explain and write recipes | YAML schema, `extends`, `${ENV}` in config, scopes and aliases, `reach` and `renew` |
| Drive ITF from plain Python | `Session` / `describe` without pytest |
| Write a new pack | layout, providers, actions with probes, BUILD, catalog conformance test |
| Migrate old tests | points to the legacy-layer pattern and the migration table |

It enforces the rules reviewers care about: use only tokens and members the catalog holds, never
import a pack from a test or another pack, no secrets in YAML, no hardware access to "check".

## Original API

ITF no longer ships the original plugins or `Target` class. Projects keep tests written for them
running with a legacy layer of their own over the packs; `examples/examples/legacy` is one, running
ITF's original integration tests (see docs/how-to/migrate.md).

## Requirements

Bazel builds every dependency, including a hermetic C/C++ toolchain, DLT and tcpdump. Host
prerequisites, checked when used: a Docker-compatible daemon (Docker or Podman) for the docker pack,
`qemu-system-*`, `qemu-img` and `/dev/kvm` for the qemu pack, and `CAP_NET_RAW` for packet capture.

Tests reach the engine through `DOCKER_HOST`, which Bazel does not pass to tests on its own. With
rootless Podman, start the socket, name the variable, and run tests unsandboxed so that image loading can
write to `/run`:

```bash
systemctl --user enable --now podman.socket
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
bazel test //examples/exec_everywhere/... \
  --test_env=DOCKER_HOST --test_env=XDG_RUNTIME_DIR --strategy=TestRunner=local   # from examples/
```

## Development

```bash
bazel test //...                      # unit, framework, pack and container tests
bazel run //:format.fix               # ruff + buildifier
bazel run //:requirements_3_12.update # after editing requirements.in
```

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.
