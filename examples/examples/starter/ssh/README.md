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

# Starter: a machine over SSH

A machine reached over SSH. The demo is a container running sshd; a real machine drops `platform` and makes `endpoint` a `net.endpoint`. Evidence: `machine.txt` (`uname -a; id`) and, for the demo, `container.log`.

## The composition

`target.itf.yaml`:

```yaml
# A machine reached over SSH. For the local demo it is a container running sshd; for a real machine delete
# `platform` and `endpoint`, make `endpoint` a net.endpoint with `host` and `port`, and set the login.
# Copy this folder and change what is marked `# CHANGE:`.
capabilities:
  # CHANGE: delete this role for a real machine (and the docker pack in BUILD).
  platform:
    factory: docker.platform
    with:
      image: linuxserver/openssh-server:version-10.2_p1-r0
      command: null
      init: false
      environment: PASSWORD_ACCESS=true,USER_NAME=score,USER_PASSWORD=score
      ports: 2222/tcp  # the port sshd listens on, published by the container
  endpoint:
    # CHANGE: net.endpoint for a real machine, with `host` and `port` under `with`.
    factory: docker.endpoint
    with:
      port: 2222
  credentials:
    # CHANGE: net.key for key authentication (`key_path` replaces `password`).
    factory: net.password
    with:
      user: score
      password: score
  shell:
    factory: ssh.shell
    with:
      n_retries: 20  # how many times to retry the connection while the machine boots
  command: ssh.exec
goals:
  - platform.up
  - shell.open
```

`bench.itf.yaml`, an override file merged by role:

```yaml
# An override file: the facts of one bench, merged by role over target.itf.yaml.
capabilities:
  shell:
    with:
      # CHANGE: a slow bench boots slowly: give it more attempts.
      n_retries: 60
  credentials:
    with:
      # CHANGE: this bench's login.
      user: score
      password: score
```

Composition or override? Put in the composition what makes the target this kind of target (the roles, their
factories, the goals). Put in an override file what changes from bench to bench (an image, a login, a retry
count). Running with the override file is `:test_bench`; without it, `:test`.

`net.password` and `net.key` are two factories of one pack: `credentials: net.key` switches to key
authentication (`key_path` replaces `password`). For a real machine, an override takes the demo container out
and points the endpoint at the machine:

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
bazel build //examples/starter/ssh:target         # compile the composition: target.plan.json
bazel test //examples/starter/ssh:test            # bring the target up, run test_hello.py, tear down
bazel test //examples/starter/ssh:test_bench      # the same with bench.itf.yaml merged over it
```

Without Bazel, say which composition a run uses in `pytest.ini` (`itf_target = target.itf.yaml`,
`itf_override = bench.itf.yaml`), in `pyproject.toml` (`[tool.itf]` with `target` and `override`), with
`ITF_TARGET` and `ITF_OVERRIDE`, or per run with `pytest --itf-target ... --itf-override ...`.
