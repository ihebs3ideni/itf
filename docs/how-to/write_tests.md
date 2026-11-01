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

# Write tests

A test target has three halves, each in its own place: a **composition** (what the target is made of), a
**conftest** (code: readiness, evidence, fixtures, the project's own parts) and the **tests** (what they need).
Which composition a run uses is configuration, never conftest code.

## The composition

```yaml
# ecu.itf.yaml
capabilities:
  platform:
    factory: docker.platform
    with:
      image: my-ecu:latest
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
  files: ssh.files
goals:
  - platform.up
  - shell.open
```

- A key of `capabilities:` is a **role**: the name tests use (`target.command`). The value is the factory label,
  or a mapping with `factory`, `with` (the factory's settings, checked against its schema) and `bind`.
- Wiring comes from what each factory needs: `ssh.shell` needs an `endpoint` and `credentials`; the composition
  has exactly one of each, so they are wired.
- **Goals are listed**, nothing is inferred. A state some action makes true comes with the factories listed.
- `${NAME}` and `${NAME:-default}` in a `with:` value read the environment.
- Block style everywhere: no `{...}` or `[...]` in YAML.

### Swapping a factory

Replace one label. `command: ssh.exec` becomes `command: docker.exec` and the test does not change. A swap that
changes the contract is a plan error.

### Several roles of one kind

Two roles of one kind are two keys: `console` and `debug`, each `serial.console` with its own `device`. When a
factory's slot has two candidates, say which with `bind:`:

```yaml
capabilities:
  shell:
    factory: ssh.shell
    bind:
      endpoint: lab_endpoint     # the slot `endpoint` uses the role `lab_endpoint`
```

When two actions could make one state true, say which with `by:` (the compiler names both if you forget):

```yaml
goals:
  - state: console.open
    by: serial.open
```

### Several devices

```yaml
scopes:
  gw:
    capabilities:
      command: ssh.exec
    share:
      - platform               # gw uses the root's platform role
```

Tests use `target.gw.command`; `@itf.requires("command", scope="gw")`.

### Assumptions

A state that holds without ITF is declared, with an owner and a reason, and shows in the plan:

```yaml
assume:
  - state: power.on
    owner: lab
    reason: the rack keeps it on
```

## Override files: one bench

```yaml
# lab2.itf.yaml: only what differs on this bench
capabilities:
  endpoint:
    with:
      port: 22022
  credentials:
    with:
      user: lab
```

Merged by role over the composition, in the order given: `with:` and `bind:` keys are merged, other keys
replace; `remove: true` takes a role out. `--itf-override` (repeatable), `ITF_OVERRIDE`, `itf_override` in `pytest.ini`,
`[tool.itf] override`, or `itf_target(overrides = [...])`.

## Code: the conftest

The root `conftest.py` holds code only:

```python
from score.itf.core import hookimpl

@hookimpl
def itf_verify(session):
    """After bring-up, before the first test. `session.check(name, ok, detail=...)`."""

@hookimpl
def itf_teardown(session):
    """After the last test, targets still live, before unwind: save evidence."""
```

and the project's own parts: a factory or action written in the conftest belongs to the pack `project` and
is named `project.<function>` in a composition (see the `exec_everywhere` and `itf` examples, where a project
action waits for a fake ECU, or starts `dlt-daemon` and subscribes to its logs).

```python
class Console(Protocol):
    __contract__ = "exec.console"
    def open(self) -> None: ...
    def is_open(self) -> bool: ...

@state("console.open", after=("platform.up",), label="open_when_ecu_answers")
def open_when_ecu_answers(endpoint: Endpoint, console: Console) -> None:
    wait_until_it_greets(endpoint)
    console.open()

@open_when_ecu_answers.probe
def console_is_open(endpoint: Endpoint, console: Console) -> bool:
    return console.is_open()
```

A probe takes the same slots as its action.

## The tests

```python
import score.itf as itf

@itf.requires("command")
def test_kernel(target):
    code, output = target.command.exec("uname -s")
    assert code == 0 and output.strip() == "Linux"
```

- `@itf.requires(role, contract=..., shape=[...], scope=...)` selects a test only when the target has the role (and
  contract, and members); otherwise it is **deselected with a reason** before anything starts.
  `contract="exec.command@1"` pins the major.
- `target.<role>` and `target.<scope>.<role>` return the objects; call only the members the contract's shape lists.
- The same test runs on every target that has the role: a suite does not depend on anybody's composition.
- Change state through the planner: `session.reach("shell.open")` re-establishes what an action invalidated;
  `session.renew("platform")` rebuilds a role and everything bound to it, then reaches the goals again.
- Per-test isolation is a fixture you own, at the scope you choose:

  ```python
  @pytest.fixture(autouse=True)
  def fresh_container(session):
      session.renew("platform")
  ```

- Asynchronous processes: `WrappedProcess(target.process, "/usr/bin/app", wait_on_exit=True)` from
  `score.itf.core.process`, for any `process` role.

## The Bazel targets

```starlark
load("@score_itf//:defs.bzl", "itf_target", "py_itf_test")

itf_target(
    name = "ecu",
    src = "ecu.itf.yaml",
    overrides = [],                       # override files, merged in this order
    packs = ["@score_itf//score/itf/packs/docker"],   # the packs the factory labels name
    srcs = ["conftest.py"],               # so the project's own parts take part in the plan
    files = {"ITF_IMAGE_LOAD": ":image_load"},  # built files the composition names as ${ITF_IMAGE_LOAD}
    env = {},                             # other ${NAME} values
)

py_itf_test(
    name = "smoke",
    srcs = ["conftest.py", "test_smoke.py"],
    target = ":ecu",                      # inherits the files and values: no data, no $(location)
)
```

The composition stays plain YAML: `bootstrap: ${ITF_IMAGE_LOAD}`. Without Bazel the same file works when the
variable comes from the environment; with Bazel the `itf_target` is the one place that names the built file.

Building the test builds the target, whose plan fails the build when the composition does not compile. See the
[Bazel macros](../reference/bazel_macros.rst).

## Without pytest

```python
from score.itf import Session

session = Session(target="ecu.itf.yaml")
session.resolve()
session.bring_up()
session.target.command.exec("echo hello")
session.close()
```

See `examples/examples/plain_python`.
