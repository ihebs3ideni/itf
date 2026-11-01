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

ITF is a platform to **compose test targets from self-describing parts**, for testing ECUs and the software on
them, with [`pytest`](https://docs.pytest.org) and Bazel. A composition file says what a target is made of;
**OCTO** (Open Contract Topology Orchestration) plans it from the parts' own metadata, before anything exists;
your tests ask for what they need. Write a test once and run it in a Docker container, on a QEMU virtual machine or
on real hardware: moving it is changing one word in the composition, not the test.

Nothing is trusted on its name. Every part brings its rules (what it needs, what it offers, what it makes true,
how to check it), and the parties that depend on a claim check it.

## Start here

1. Read [Start here](docs/how-to/start_here.md): three questions (where does your software run, how does ITF reach
   it, what do your tests need) lead you to a starter.
2. Copy a starter from [`examples/examples/starter`](examples/examples/starter): `container`, `ssh` or `serial`.
   Each has a composition with `# CHANGE:` marks, an override file for a bench, a conftest and a test.
3. Follow the [tutorial](docs/how-to/tutorial.md): copy a starter, validate, graph, bring it up, test, swap a
   factory, override a value for a bench.

```
itf validate target.itf.yaml           # every metadata rule, no hardware
itf graph target.itf.yaml              # roles, wiring and the bring-up sequence
itf up --detach target.itf.yaml        # bring it up and leave it running
itf down target.itf.yaml               # unwind from what the probes observe
itf test target.itf.yaml               # bring up, run the tests, tear down
```

## A composition, a test

```yaml
# target.itf.yaml
capabilities:
  platform:
    factory: docker.platform
    with:
      image: ubuntu:24.04
  command: docker.exec
goals:
  - platform.up
```

```python
# test_hello.py
import score.itf as itf

@itf.requires("command")
def test_hello(target):
    assert target.command.exec("echo -n hello") == (0, "hello")
```

```starlark
# BUILD
load("@score_itf//:defs.bzl", "itf_target", "py_itf_test")

itf_target(name = "target", src = "target.itf.yaml", packs = ["@score_itf//score/itf/packs/docker"])
py_itf_test(name = "test_hello", srcs = ["test_hello.py"], target = ":target")
```

`bazel build :target` compiles the composition and writes its plan (a wrong composition fails the build, before
any image is built); `bazel test :test_hello` runs the test. If the composition has no `command`, the test is
deselected with the reason. **Swapping is changing one word:** `command: docker.exec` becomes `command: ssh.exec`
and the test does not change.

## The vocabulary

| Word | What it is | Example |
|---|---|---|
| **capability contract** | a name for what a test uses, fulfilled by a capability factory | `exec.command` |
| **state contract** | a name for a condition, fulfilled by an action with a probe | `platform.up`, `shell.open` |
| **factory** | code that builds a capability: `@capability("exec.command")`; label `<pack>.<name>` | `docker.exec`, `ssh.shell` |
| **action** | code that makes a state true: `@state("platform.up", after=..., breaks=...)` | `docker.start` |
| **composition** | what a target is made of: roles, settings, goals; a `*.itf.yaml` file | `target.itf.yaml` |
| **role** | the name a factory answers to on the target | `command` in `target.command` |
| **scope** | one device of a multi-device target | `gw` |

An **override file** is a composition with only what changes (the values of one bench), merged by role. A part
outside any pack is `project.<name>`. See [the model](docs/concepts/model.md).

## Where each thing is defined

| Thing | Defined in |
|---|---|
| a factory's or action's label, contract, needs, shape, settings, probes | the pack's code: decorators, slots, annotations, dataclasses |
| a contract's meaning, version, members, conformance | an optional definition file, the project's own |
| what a target is made of | its composition |
| the values of one bench | its override file |
| what a test needs | `@itf.requires("<role>", contract=..., shape=[...])` |
| which composition a run uses | configuration: `--itf-target`, `ITF_TARGET`, `itf_target` in `pytest.ini`, `[tool.itf] target`, Bazel `target =` |

## No trust

| Rule | Brought by | Checked against | When |
|---|---|---|---|
| "I need a shell with `run` and `exec`" | the part that needs it | the shape the offering part publishes | composition |
| "I make `shell.open` true; I need `platform.up`; I break `network.reachable`" | the action | every other action's claims | composition |
| "My settings are `port: int`" | the part's config schema | the composition and override values | composition |
| "I need tcpdump on PATH" | the pack | the host (`itf doctor`) | before bring-up |
| "I need a `command` with `exec`" | the test | the composed target | collection (gating) |
| "I did make `shell.open` true" | the action | its own probe | bring-up, every run |
| "A fulfiller of `exec.command` behaves like this" | the contract's conformance checks | each part claiming it | CI |

## Contracts are your project's own

ITF knows no contracts: a contract is whatever name two parts agree on. ITF lets a project **discover** them
(`itf contracts map`: who offers and who needs each name, with which shape, and every disagreement), **define**
them (an optional definition: meaning, members, version, stability, conformance; `itf contracts new --from-usage`
writes a skeleton) and **enforce** its rules (`itf contracts check --policy policy.yaml`, exit 1 on violations).
The ITF team maintains the contracts its own packs use, with conformance checks, as a supported set, not a
standard. See [Use, define and enforce contracts](docs/how-to/contracts.md) and
[`examples/examples/vendor_contract`](examples/examples/vendor_contract).

## The lifecycle

| Command | Does | Touches hardware |
|---|---|---|
| `itf validate` | every metadata rule | no |
| `itf plan` | the plan, readable; `--json` for tools | no |
| `itf graph` | roles, wiring and the bring-up sequence, as Mermaid | no |
| `itf up [--detach]` | bring up, verify, print the target | yes |
| `itf down` | unwind from what the probes observe | yes |
| `itf test` | run the tests against the composition | yes |
| `itf contracts map`, `new`, `check` | discover, scaffold and enforce contracts | no |

With Bazel, `itf` is `bazel run @score_itf//score/itf/cli:itf --`.

## pytest, facades, plain Python

- **pytest:** the composition comes from configuration, never from the conftest. The conftest holds code only:
  `itf_verify`, `itf_teardown`, fixtures, and the project's own factories and actions.
- **A facade** keeps an old API: a thin layer in the project maps the composed roles onto the old classes
  (`target.command` behind the old `target.execute()`); see [Migrate](docs/how-to/migrate.md) and
  `examples/examples/legacy`.
- **Plain Python** composes and runs a target without a test runner: `Session(target="target.itf.yaml")`; see
  `examples/examples/plain_python`.

## Bazel

`itf_target(name, src, overrides, packs, data, srcs, contracts, env, files)` validates the composition during the
build and writes `<name>.plan.json`; it also supplies every `${NAME}` the composition uses (`files` for built files,
`env` for other values). `py_itf_test(target = ":name")` runs tests against it and inherits those values. See the
[Bazel macros](docs/reference/bazel_macros.rst).

## Packs

| Pack | Labels |
|---|---|
| `docker` | `docker.platform`, `.exec`, `.process`, `.files`, `.endpoint` |
| `qemu` | `qemu.platform`, `.console`, `.endpoint`, `.credentials` |
| `ssh` | `ssh.shell`, `.exec`, `.process`, `.files` (SFTP) |
| `net` | `net.endpoint`, `net.key`, `net.password` |
| `ping` | `ping.pinger` |
| `dlt` | `dlt.stream`, `dlt.multicast`, `dlt.receive`, `dlt.receive_tcp` |
| `pcap` | packet capture |
| `serial` | `serial.console`, `serial.pty_console`, `serial.exec` |
| `local` | the test host: `local.platform`, `.exec`, `.process`, `.files` |
| `core_dump` | core files copied off the target at teardown |
| `sim` | in-memory stand-ins for offline runs |

Each pack's README has its label table, host prerequisites and a composition excerpt.

## Guides

- [Start here](docs/how-to/start_here.md), [tutorial](docs/how-to/tutorial.md) and
  [get started](docs/how-to/get_started.md).
- [Write tests](docs/how-to/write_tests.md): compositions, overrides, scopes, gating, `reach` and `renew`.
- [Write a pack](docs/how-to/plugins.md): factories, actions, `pack.yaml`, conformance.
- [The model](docs/concepts/model.md) and [the platform](docs/concepts/platform.md).
- [Contracts](docs/how-to/contracts.md) and [DR-006](docs/decisions/DR-006-target-composition.md).
- [Migrate](docs/how-to/migrate.md): from the original plugin API.
- [OCTO](score/itf/core/octo/README.md): the planner on its own.
- [Agent skill](.github/skills/itf/SKILL.md): a guide for coding agents.

## Original API

ITF does not ship the original plugins or `Target` class. Projects keep tests written for them running with a
facade of their own over the packs; `examples/examples/legacy` is one, running ITF's original integration tests
(see docs/how-to/migrate.md).

## Requirements

Bazel builds every dependency, including a hermetic C/C++ toolchain, DLT and tcpdump. Host prerequisites, checked
when used: a Docker-compatible daemon (Docker or Podman) for the docker pack, `qemu-system-*`, `qemu-img` and
`/dev/kvm` for the qemu pack, and `CAP_NET_RAW` for packet capture.

Tests reach the engine through `DOCKER_HOST`, which Bazel does not pass to tests on its own. With rootless Podman,
start the socket, name the variable, and run tests unsandboxed so that image loading can write to `/run`:

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
