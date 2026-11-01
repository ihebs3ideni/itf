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

# The ITF platform: lifecycle, fronts and packs

One engine, many fronts:

```text
                 parts (packs)          contracts (definitions, optional)
                        \                    /
                         composition (file)
                                 |
                       OCTO plan (validated, drawable)
                 /          |            |            \
          itf CLI     pytest adapter   facade      plain Python
```

## The lifecycle

Every command takes a composition (an argument, or the configured one) and `--override` files. Nothing before
`up` touches hardware.

| Command | Does | Touches hardware |
|---|---|---|
| `itf validate` | every metadata rule: wiring, shapes, majors, settings, action order | no |
| `itf plan` | the plan, readable; `--json` for tools | no |
| `itf graph` | the topology (roles and wiring) and the bring-up sequence, as Mermaid | no |
| `itf doctor` | host prerequisites of the composition's packs | reads the host |
| `itf up` | bring up, verify, print the target; `--detach` leaves it running | yes |
| `itf down` | unwind from what the probes observe | yes |
| `itf test` | run the tests against the composition (pytest underneath) | yes |
| `itf contracts map`, `new`, `check` | discover, scaffold and enforce the project's contracts | no |

`itf down` after `itf up --detach` needs no state file: ITF unwinds from observed state, never by replaying the
plan, so a part that can observe what it created (a container found by its labels) can be torn down by a later
process. A part that cannot observe says so, and `--detach` is refused for it.

With Bazel, `itf` is `bazel run @score_itf//score/itf/cli:itf --`; run it in the folder holding the
composition and the conftest, so the project's own parts take part in the plan.

## Plans are build artifacts

`itf_target(name = "ecu", src = "ecu.itf.yaml")` compiles the composition during the build, exactly as a test
run does (both gates, strict shapes, nothing constructed), writes `ecu.plan.json`, and fails the build with ITF's
diagnostics when the composition does not compile or when a factory label names a pack that is not in `packs`.
`py_itf_test(target = ":ecu")` runs tests against it; its pack dependencies are the `packs` listed there.

```starlark
itf_target(
    name = "ecu",
    src = "ecu.itf.yaml",
    overrides = ["lab2.itf.yaml"],
    packs = ["@score_itf//score/itf/packs/docker", "@score_itf//score/itf/packs/ssh"],
    srcs = ["conftest.py"],
)

py_itf_test(name = "smoke", srcs = ["conftest.py", "test_smoke.py"], target = ":ecu")
```

The plan has three keys: `target` (roles, the factory chosen for each, redacted settings), `action` (ordered
steps, each naming the action that runs it) and `assumptions`. It is deterministic, so two plans compare as text.

## Which composition a run uses

Said once, in configuration, never in the conftest: `--itf-target` (and `--itf-override`, repeatable), the
`itf_target` and `itf_override` ini options in `pytest.ini`, `ITF_TARGET` and `ITF_OVERRIDE`, `[tool.itf]` with
`target` and `override` in `pyproject.toml`, or `py_itf_test(target = ...)`. The root `conftest.py` holds code
only: `itf_verify(session)`, `itf_teardown(session)`, fixtures, and the project's own factories and actions.

## The pytest adapter

`pytest` builds the target from the composition, gates each test on its requirements, gives tests the `target`
fixture, and unwinds at the end. Packs load from the factory labels (`docker.exec` loads `docker`); a label
whose pack cannot be found fails with the packs it knows. `itf test` is the same, started from the command
line. `--itf-plan` prints the plan and the gating and runs nothing; `--itf-fresh` runs every planned action
ignoring what probes observe; `--itf-keep` skips unwind; `--itf-strict-gating` turns a deselection into a failure.

Tests change state through the planner: `session.reach("shell.open")` re-establishes what an action invalidated,
and `session.renew("platform")` rebuilds a role and everything bound to it, then reaches the goals again.
Per-test isolation is a fixture you own that calls `renew`; pytest's scopes decide when, the planner what.

## Facades: keep an old API

A project with tests written against an old framework keeps them: a facade in the project maps the composed
target's roles onto the old classes (`target.command` behind the old `target.execute()`). The composition does
not change. `examples/examples/legacy` is such a facade, ready to copy; see [Migrate](../how-to/migrate.md).

## Plain Python

`Session(target="ecu.itf.yaml")` is the same session without a test runner: `resolve()` plans, `bring_up()`
runs the actions, `session.target` is the target, `close()` unwinds. See `examples/examples/plain_python`.

## Pack kinds

A **pack** is a directory with a `pack.yaml` (`name`, `version`, `prerequisites`) holding capability factories
and actions. Core reads one thing from `pack.yaml`: the name. Packs load from a label, `<pack>.<name>`, as the
module `score.itf.packs.<pack>.plugin` or, for a pack outside the ITF repository, the entry point
`score_itf.packs:<pack>`. Packs never import each other; they meet only through contract names.

| Pack | Offers (labels) |
|---|---|
| `local` | `local.platform`, `local.exec`, `local.process`, `local.files`, action `local.start` |
| `docker` | `docker.platform`, `.exec`, `.process`, `.files`, `.endpoint`, action `docker.start` |
| `ssh` | `ssh.shell`, `.exec`, `.process`, `.files`, action `ssh.open` |
| `serial` | `serial.console`, `.pty_console`, `.exec`, action `serial.open` |
| `net` | `net.endpoint`, `.key`, `.password` |
| `qemu` | `qemu.platform`, `.endpoint`, `.credentials`, `.console`, actions `qemu.start`, `.open_console` |
| `ping` | `ping.pinger`, action `ping.await_boot` |
| `dlt` | `dlt.stream`, `.multicast`, `.receive`, `.receive_tcp`, an action per way of receiving |
| `pcap`, `core_dump` | capture and core-dump extraction |
| `sim` | in-memory stand-ins for offline runs |

Each pack's README carries its label table, host prerequisites and a composition excerpt.

## Evidence

Run artifacts go to `$TEST_UNDECLARED_OUTPUTS_DIR/itf-run` (else `itf-run/`): the plan, the probe record, the
failure report when something fails and a summary page (`itf evidence <run-dir>`). A conftest's `itf_teardown`
saves what a person needs to follow the run (console transcript, container output) while the target still runs.
