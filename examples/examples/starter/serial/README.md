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

# Starter: a serial console

A serial console and commands over it. The demo is a shell on a pseudo-terminal; hardware uses `serial.console` with `device`. Evidence: `console.txt`, the transcript.

## The composition

`target.itf.yaml`:

```yaml
# A serial console. For the local demo it is a shell on a pseudo-terminal (no hardware); for a real device
# use serial.console and give `device`. Copy this folder and change what is marked `# CHANGE:`.
capabilities:
  console:
    # CHANGE: serial.console for hardware, with `device` and `baudrate` under `with`.
    factory: serial.pty_console
    with:
      shell: /bin/sh
      banner: ITF PTY CONSOLE READY
  command: serial.exec
goals:
  - console.open
```

`bench.itf.yaml`, an override file merged by role:

```yaml
# An override file: the facts of one bench, merged by role over target.itf.yaml.
capabilities:
  console:
    with:
      # CHANGE: this bench's banner. A bench with hardware replaces the factory instead:
      #   factory: serial.console
      #   with: {device: /dev/ttyUSB0, baudrate: 115200} (in block style, as everywhere)
      banner: BENCH CONSOLE READY
```

Composition or override? Put in the composition what makes the target this kind of target (the roles, their
factories, the goals). Put in an override file what changes from bench to bench (an image, a login, a retry
count). Running with the override file is `:test_bench`; without it, `:test`.

## Commands

From `examples/`, with Bazel (`itf` is `bazel run @score_itf//score/itf/cli:itf --`; with a pip install it is
just `itf`; run it in this folder so the conftest beside the composition is found):

```
itf validate target.itf.yaml                         # every metadata rule, no hardware
itf graph target.itf.yaml                            # roles, wiring and the bring-up sequence (Mermaid)
itf up --detach target.itf.yaml                      # bring it up and leave it running
itf down target.itf.yaml                             # unwind from what the probes observe
itf test target.itf.yaml                             # bring up, run the tests, tear down
itf validate target.itf.yaml --override bench.itf.yaml
```

```
bazel build //examples/starter/serial:target         # compile the composition: target.plan.json
bazel test //examples/starter/serial:test            # bring the target up, run test_hello.py, tear down
bazel test //examples/starter/serial:test_bench      # the same with bench.itf.yaml merged over it
```

Without Bazel, say which composition a run uses in `pytest.ini` (`itf_target = target.itf.yaml`,
`itf_override = bench.itf.yaml`), in `pyproject.toml` (`[tool.itf]` with `target` and `override`), with
`ITF_TARGET` and `ITF_OVERRIDE`, or per run with `pytest --itf-target ... --itf-override ...`.
