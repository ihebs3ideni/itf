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

# Tutorial

Fifteen minutes: copy a starter, validate and draw the target, bring it up, run a test, swap one factory, and
change a value for one bench. It needs a Docker-compatible daemon (`DOCKER_HOST` for Podman). `itf` below is
`bazel run @score_itf//score/itf/cli:itf --` under Bazel, or just `itf` with a pip install; run it in the folder
that holds the composition.

## 1. Copy the container starter

```
cp -r examples/examples/starter/container examples/examples/my_target
cd examples/examples/my_target
```

The folder has a composition, an override file, a conftest, a test and a `BUILD`. The composition:

```yaml
# A Docker container from an image, reached through the container API.
# Copy this folder and change what is marked `# CHANGE:`.
capabilities:
  platform:
    factory: docker.platform  # CHANGE: another platform factory (qemu.platform, ...) for another machine
    with:
      # CHANGE: the image your software runs in.
      image: ubuntu:24.04
  command: docker.exec
  files: docker.files
goals:
  - platform.up
```

Four lines say what the target is. `platform` and `command` and `files` are **roles**: names tests use. Each is
filled by a **factory** (`docker.platform`, `docker.exec`, `docker.files`), and `platform.up` is the **goal**.
The `# CHANGE:` marks are what you edit for your own software: the image.

The test asks for roles, and uses them as `target.<role>`:

```python
@itf.requires("command")
def test_run_a_command(target):
    code, out = target.command.exec("echo hello-itf")
    assert code == 0
    assert "hello-itf" in out
```

## 2. Validate and draw it, without hardware

```
itf validate target.itf.yaml
itf graph target.itf.yaml
```

`validate` checks every rule from the parts' metadata: each slot has a candidate with the shape it expects, the
settings fit their schemas, the actions can be ordered. `graph` prints the roles, their wiring and the bring-up
sequence as Mermaid: `docker.exec` and `docker.files` need `platform`; `docker.start` makes `platform.up`
true first. Under Bazel the build does the same: `bazel build :target` compiles the composition and writes
`target.plan.json`, and fails with ITF's diagnostics when it does not compile.

## 3. Bring it up

```
itf up --detach target.itf.yaml
```

ITF runs the planned actions in order, checks each state with its probe, runs your `itf_verify`, and leaves the
container running. Look at it, then take it down:

```
docker ps
itf down target.itf.yaml
```

`down` needs no state file: it unwinds from what the probes observe.

## 4. Test it

```
itf test target.itf.yaml                 # or: bazel test :test
```

The same target is brought up, the tests run against it, and it is torn down. Evidence (the container's output)
is saved by `itf_teardown` in the conftest, while the target still runs.

## 5. Swap a factory

Make the same test run over SSH. Copy `starter/ssh/target.itf.yaml` over yours, or edit your composition: the
platform becomes a container running sshd, `endpoint` and `credentials` tell the `shell` where and how to log in,
and `command` becomes `ssh.exec`:

```yaml
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

The test file did not change: it still asks for `command` (`test_transfer_a_file` asks for `files`, which this
composition does not list, so it is deselected with the reason). In `BUILD`, add the `net` and `ssh` packs to the
`itf_target`'s `packs` (a label naming a pack that is not listed fails the build, with the label). Run
`itf validate`, `itf graph` and `itf test` again: the graph now shows `ssh.shell` needing `endpoint` and
`credentials`, and `ssh.open` after `docker.start`.

## 6. Override a value for one bench

A bench is one physical setup. Its values go in an override file with the composition's own shape and only what
differs:

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

```
itf validate target.itf.yaml --override bench.itf.yaml
itf test target.itf.yaml --override bench.itf.yaml
```

The override is merged by role: `with:` keys are merged, other keys replace. Under Bazel, give it to the
target: `itf_target(name = "target_bench", src = "target.itf.yaml", overrides = ["bench.itf.yaml"], ...)` and
`py_itf_test(target = ":target_bench")`. Without Bazel, `itf_override = bench.itf.yaml` in `pytest.ini`,
`ITF_OVERRIDE`, or `pytest --itf-override bench.itf.yaml`.

## Where next

- [Get started](get_started.md): the smallest real files.
- [Write tests](write_tests.md): compositions, roles, hooks and gating in depth.
- [Use, define and enforce contracts](contracts.md): `itf contracts map` shows every contract name in use.
- [Write a pack](plugins.md): your own factories and actions.
