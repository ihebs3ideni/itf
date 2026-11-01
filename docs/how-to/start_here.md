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

# Start here

ITF composes a test target from self-describing parts: a composition file says what the target is made of, ITF
plans it from the parts' own metadata, and your tests ask for what they need. Three questions lead you to a
starter.

## 1. Where does your software run?

| It runs in | Platform factory | Starter |
|---|---|---|
| a Docker container | `docker.platform` | `examples/examples/starter/container` |
| a machine you reach over SSH (a container with sshd, a QEMU machine, a board) | `docker.platform`, `qemu.platform`, or none for a machine nobody here starts | `examples/examples/starter/ssh` |
| a device with a serial console | `serial.console` (hardware) or `serial.pty_console` (no hardware) | `examples/examples/starter/serial` |
| the test host itself | `local.platform` | `examples/examples/plain_python` |

## 2. How does ITF reach it?

You choose a factory per role. The common ones:

| Role | What a test does with it | Factories |
|---|---|---|
| `command` | run a command, get the exit code and output | `docker.exec`, `ssh.exec`, `serial.exec`, `local.exec` |
| `process` | start a program and wrap it | `docker.process`, `ssh.process`, `local.process` |
| `files` | copy files in and out | `docker.files`, `ssh.files`, `local.files` |
| `shell` | an interactive session | `ssh.shell` |
| `console` | read and write a console, with recorded lines | `serial.console`, `serial.pty_console`, `qemu.console` |
| `logs` | DLT messages | `dlt.stream`, `dlt.receive`, `dlt.multicast` |

Swapping how commands run is changing one word, `command: docker.exec` to `command: ssh.exec`; the test does not
change. Every pack's README lists its labels; the [pack catalog](../reference/plugins.rst) lists all of them.

## 3. What do your tests need?

A test asks for roles: `@itf.requires("command")` and `target.command`. It can narrow the ask with
`contract=` and `shape=`. A test whose role the target lacks is deselected with the reason, so one test file can
run on several compositions and each runs what it supports (`examples/examples/exec_everywhere`).

## What to run, in order

```
cp -r examples/examples/starter/container my_target      # 1. copy a starter
cd my_target                                              #    change what is marked "# CHANGE:"
itf validate target.itf.yaml                              # 2. every metadata rule, no hardware
itf graph target.itf.yaml                                 # 3. roles, wiring and bring-up sequence
itf up --detach target.itf.yaml                           # 4. bring it up, poke at it
itf down target.itf.yaml                                  #    and tear it down
itf test target.itf.yaml                                  # 5. run the tests
```

With Bazel, `itf` is `bazel run @score_itf//score/itf/cli:itf --` and `bazel test :test` runs the same tests.
The commands that do not touch hardware (`validate`, `plan`, `graph`) are safe anywhere, including CI.

## Next

- [Tutorial](tutorial.md): copy a starter, validate, graph, bring up, test, swap a factory, override for a bench.
- [Get started](get_started.md): the smallest real files, from `MODULE.bazel` to a test.
- [The model](../concepts/model.md): the vocabulary and where each fact lives.
- [Use, define and enforce contracts](contracts.md): contracts are your project's own.
