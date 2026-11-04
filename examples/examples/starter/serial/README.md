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

A serial console and commands over it. The demo is a shell on a pseudo-terminal; hardware uses `serial.console` with `device` (override fragment below). Evidence: `console.txt`, the transcript.

## The target file

`targets/target.itf.yaml`:

```yaml
# A serial console. For the local demo it is a shell on a pseudo-terminal (no hardware); for a real device
# use serial.console and give `device`.
# Copy this folder and change what is marked `# CHANGE:`.
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

`targets/override.itf.yaml`, an override file merged by role:

```yaml
# An override file: merged by role over target.itf.yaml; it holds only what differs in this setup.
capabilities:
  console:
    with:
      # CHANGE: this setup's banner. A setup with hardware replaces the factory instead (see below).
      banner: OVERRIDE CONSOLE READY
```

For hardware, an override file replaces the factory (a fragment of an override file, not a whole target file):

```yaml
capabilities:
  console:
    factory: serial.console
    with:
      device: /dev/ttyUSB0
      baudrate: 115200
```

Target file or override? Put in the target file what makes the target this kind of target (the roles, their
factories, the goals). Put in an override file what changes from one setup to another (an image, a login, a retry
count). Running with the override file is `:test_override`; without it, `:test`.

## Commands

From `examples/`, with Bazel (`itf` is `bazel run @score_itf//score/itf/cli:itf --`; with a pip install it is
just `itf`; run it in this folder so the policy beside the target file is found):

```
itf validate targets/target.itf.yaml                         # every metadata rule, no hardware
itf graph targets/target.itf.yaml                            # roles, wiring and the bring-up sequence (Mermaid)
itf up --detach targets/target.itf.yaml                      # bring it up and leave it running
itf down targets/target.itf.yaml                             # unwind from what the probes observe
itf test targets/target.itf.yaml                             # bring up, run the tests, tear down
itf validate targets/target.itf.yaml --override targets/override.itf.yaml
```

```
bazel build //examples/starter/serial:target         # compile the target file: target.plan.json
bazel test //examples/starter/serial:test            # bring the target up, run test_hello.py, tear down
bazel test //examples/starter/serial:test_override   # the same with targets/override.itf.yaml merged over it
```

Without Bazel, say which target file a run uses in `pytest.ini` (`itf_target = targets/target.itf.yaml`,
`itf_override = targets/override.itf.yaml`), in `pyproject.toml` (`[tool.itf]` with `target` and `override`), with
`ITF_TARGET` and `ITF_OVERRIDE`, or per run with `pytest --itf-target ... --itf-override ...`.
