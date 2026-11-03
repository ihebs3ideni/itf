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

# RFC: compose ITF test targets from self-describing parts

| | |
|---|---|
| **Status** | Proposed, open for review |
| **Decision record** | [DR-002-Arch: Target Composition](../decisions/DR-002-arch-target-composition.md) |
| **Implementation** | branch `ihsa_itf_platform`: 12 commits on `main`; every commit passes Bazel analysis, and the last passes every test |
| **Words** | defined once, in the [glossary](glossary.md) |

## Summary

Today an ITF test target is a Python class, `Target`, with one subclass per environment (Docker, QEMU). A pytest
plugin per environment creates it, and command-line options set it up. This RFC proposes to replace that with
**target composition**. ITF builds the target, meaning the system under test and everything needed to reach it,
from parts, and tests use it:

- A **target file** (`target.itf.yaml`) lists the parts of a target by role, the states that must be
  true once it is up (goals), and the orderings between them.
- **Parts** declare themselves in code. A capability factory builds something a test uses (`docker.exec`,
  `ssh.shell`). An action makes a state true (`docker.start` makes `platform.up` true) and comes with a probe
  that checks it.
- A small planner, **OCTO**, reads only those declarations. It checks that every part's needs are met and plans
  the order of bring-up before anything is started.
- Tests ask for roles (`@itf.requires("command")`) and use them (`target.command`). The same test runs on a
  host, a container, a machine over SSH or a QEMU guest, depending on the target file.

ITF ships the engine, a set of packs (docker, qemu, ssh, net, ping, dlt, pcap, serial, local, core_dump, sim),
a command line (`itf validate|plan|graph|up|down|test|...`) and Bazel rules (`itf_target`, and
`py_itf_test(target=...)`).

## Motivation

These problems come from using ITF on real projects:

1. **A new device means a new `Target` subclass.** The class has fixed methods (`execute`, `upload`, `ssh`,
   `ping`, ...). A device that has some of them, or others, forks the class or raises `NotImplementedError`.
2. **Bring-up order is code inside each plugin.** Adding a step, for example "flash, then wait for the network,
   then start DLT", means editing a plugin or writing fixtures that depend on fixture ordering.
3. **Tests are written per environment.** A test that needs `target.ssh()` cannot run on a target without SSH,
   and nothing tells the runner so before the run.
4. **Mistakes appear late.** A typo in an option or an image that has no SSH server shows up after a container
   or a virtual machine has started, often as a timeout.
5. **Nothing describes a target as data.** It cannot be validated, drawn, compared between two branches, or
   brought up by hand from a terminal for debugging.

## Goals

- A target is described as **one declarative file** that can be validated, planned, drawn, compared and brought
  up without running any test.
- A test says **what it needs**, and runs on every target that has it. It is deselected, with the reason, on
  every target that does not.
- **Mistakes are found before bring-up**: missing parts, wrong settings, parts that do not fit each other, and
  orderings that cannot be met. Under Bazel they fail `bazel build`.
- **New devices and tools plug in** as packs, without changes to ITF.
- **Nothing is trusted on its name.** A part's claims are checked against its neighbours from metadata, and its
  states by probes at run time.
- **Projects own their vocabulary.** ITF does not ship a list of contracts everyone must use.
- Works **with and without Bazel**, and with pytest, from a terminal, or from a plain Python script.

## Non-goals

- A test-case language or a replacement for pytest. pytest remains the test runner.
- Scheduling of shared hardware between pipelines. Exclusive use of a board in one plan is a separate proposal.
- A central registry of contracts or packs.
- Keeping the original plugin API inside ITF. A project that needs it keeps a thin facade of its own (see the
  [migration guide](migration.md)); ITF provides a complete example of one.
- Running QEMU or QNX in this RFC's CI changes. The existing workflows stay as they are.

## The design in one page

A test:

```python
import score.itf as itf


@itf.requires("command")
def test_run_a_command(target):
    code, out = target.command.exec("echo hello-itf")
    assert code == 0
```

A target file: a container running an SSH server, and a shell session into it (shortened; the full file is
`examples/examples/starter/ssh/target.itf.yaml` on the implementation branch).

```yaml
capabilities:
  platform:
    factory: docker.platform
    with:
      image: linuxserver/openssh-server:version-10.2_p1-r0
      ports: 2222/tcp
  endpoint:
    factory: docker.endpoint
    with:
      port: 2222
  credentials:
    factory: net.password
    with:
      user: score
      password: score
  shell: ssh.shell
  command: ssh.exec
goals:
  - platform.up
  - shell.open
relations:
  - state: shell.open
    after:
      - platform.up
```

An override file for a lab machine: the same structure with no container.

```yaml
capabilities:
  platform:
    remove: true
  endpoint:
    factory: net.endpoint
    with:
      host: 10.0.0.7
      port: 22
assume:
  - state: platform.up
    owner: lab
    reason: the machine is powered and booted by the lab
```

Under Bazel:

```starlark
itf_target(
    name = "target",
    src = "target.itf.yaml",
    packs = [
        "@score_itf//score/itf/packs/docker",
        "@score_itf//score/itf/packs/net",
        "@score_itf//score/itf/packs/ssh",
    ],
)

py_itf_test(
    name = "test",
    srcs = ["test_hello.py"],
    target = ":target",
)
```

A part, in a pack:

```python
class Shell(Protocol):
    __contract__ = "exec.shell"

    def run(self, command: str) -> str: ...


@capability("exec.command")
def exec(shell: Shell) -> SshExec:
    return SshExec(shell)
```

The [architecture](architecture.md) describes every piece. The [rationale](rationale.md) compares each choice
with today's ITF and with the itf-core design it builds on.

## What changes for whom

| Who | Today | With this RFC |
|---|---|---|
| Test author | `target.execute(...)`, `target.ssh()`; a test runs on Docker or fails on QEMU at run time | `@itf.requires("command")`, `target.command.exec(...)`; the test runs wherever a `command` exists, and is deselected with a reason elsewhere |
| Target owner | command-line options per plugin, `docker_configuration` fixtures, plugin lists in `BUILD` | one target file, override files per setup, `itf_target` in `BUILD` |
| Pack author | a pytest plugin and a `Target` subclass | decorated functions: `@capability` and `@state` with a probe |
| CI owner | runs tests | also `bazel build` fails on a target file that does not compile; `itf contracts check` enforces a project's contract rules |
| Developer at a desk | starts a container by hand | `itf up target.itf.yaml`, `itf down` |

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep `Target` and add mixins per capability | Keeps the fixed method set and per-plugin ordering; checks still happen at run time |
| Fixtures only (pytest's dependency graph) | Orders setup but cannot plan before running, cannot tell which tests a target supports, and cannot unwind from observed state |
| A target file keyed by part label, or a list | Breaks when one part is used twice, and gives tests and overrides no stable name. See [DR-002](../decisions/DR-002-arch-target-composition.md), decision 2 |
| A fixed vocabulary of contracts owned by ITF, with a registry | ITF cannot know every project's devices. Projects name their own; ITF gives the tools to map, define and enforce them |
| Infer goals and parts from what tests need | Hidden parts and surprising plans. Everything is listed instead, and an empty target file is valid |
| Starlark recipes compiled to a document read by hooks | A second format and an indirection; a target file must also work without Bazel. Tried on the implementation branch and removed |

## Adoption

- **Existing tests keep running** through a facade of the project's own. The example facade runs ITF's original
  integration tests with only their imports changed.
- **Migration is per test**: a test moves from the facade to `target.<role>` when it is touched.
- The change lands as a **series of pull requests**, in the order of the [roadmap](roadmap.md).

## Cost

- A larger repository: the change is about 40,000 added and 5,000 removed lines across 478 files, of which
  about 10,700 are tests and 3,900 documentation.
- New words to learn: target file, role, part, capability factory, action, state, probe. The
  [glossary](glossary.md) defines all of them on one page.
- A hermetic C/C++ toolchain (zig) and new third-party dependencies: tcpdump and libpcap built from source for the
  pcap pack, and pluggy, PyYAML and pyserial in the locked Python requirements.
- Review effort. The [risks and FAQ](risks-faq.md) say how the implementation was checked and what is not yet
  measured.

## Unresolved questions

Listed with options and a recommendation in [open decisions](open-decisions.md).
