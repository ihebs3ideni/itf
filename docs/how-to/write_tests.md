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

A test setup has three halves, each in its own place: a **target file** (what the target is made of), a
**policy** (`policy.py` beside the target file: readiness, evidence, the project's own parts) and the **tests**
(what they need, with their pytest fixtures in `conftest.py` as usual).
Which target file a run uses is configuration, never policy code. The words are defined in the glossary of
[the model](../concepts/model.md#the-vocabulary).

## The target file

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
relations:
  - state: shell.open
    after:
      - platform.up
```

- A key of `capabilities:` is a **role**: the name tests use (`target.command`). The value is the label of a
  capability factory, or a mapping with `factory`, `with` (the factory's settings, checked against its schema),
  `bind` (slot to role) or `remove: true`.
- Wiring comes from what each factory needs: `ssh.shell` needs an `endpoint` and `credentials`; the target file
  has exactly one of each, so they are wired.
- **Goals are listed**, nothing is inferred. The actions considered are those of the packs of the listed
  factories plus the project's own.
- **Orderings are the target file's to state.** `docker.start` and `ssh.open` do not know about each other (a pack
  states no ordering that depends on another pack), so `relations:` says that `shell.open` comes `after`
  `platform.up`. It may also list states the action `breaks`.
- `${NAME}` and `${NAME:-default}` in a `with:` value read the environment, else a `.env` file beside the target
  file. Keep logins there (git ignores `.env`) and commit a `.env.example`, so a target file is shared without them.
- `packs:` (`acme: acme.plugin`) names the module of a pack that is not installed.
- Block style everywhere: no `{...}` or `[...]` in YAML.

### Swapping a factory

Replace one label. `command: ssh.exec` becomes `command: docker.exec` and the test does not change. A swap that
changes the contract is a plan error.

### Several roles of one kind

Two roles of one kind are two keys: `console` and `debug`, each `serial.console` with its own `device`. Whatever
has a slot with two candidates needs to be told which, and `itf validate` names the line to write:

- a **factory's** slot: `bind:` on its role (`command` below uses the role `console` for its slot `console`);
- an **action's** slot: `actions:`, keyed by the action's label, with `bind:` (slot to role). An action is a
  candidate for a state in a scope only if all of its slots can be filled;
- a **state** two actions could make true: `by:` on the goal (the compiler names both if you forget).

```yaml
capabilities:
  console:
    factory: serial.pty_console
    with:
      shell: /bin/sh
  debug:
    factory: serial.pty_console
    with:
      shell: /bin/sh
  command:
    factory: serial.exec
    bind:
      console: console           # the slot `console` of serial.exec uses the role `console`
goals:
  - console.open
actions:
  serial.open:
    bind:
      console: console           # the slot `console` of the action uses the role `console`
```

A fragment, for two actions that could make `console.open` true (say the target file lists both `serial` and
`qemu` factories):

```yaml
goals:
  - state: console.open
    by: serial.open
```

### Several devices

A scope has its own `capabilities`, `goals`, `actions` and `relations` (the roles and states are the scope's own),
and lists under `share:` the root roles it uses:

```yaml
capabilities:
  platform: localhost.platform
  command: localhost.exec
goals:
  - platform.up
scopes:
  gw:
    capabilities:
      command: localhost.exec
    share:
      - platform               # gw uses the root's platform role
```

Tests use `target.gw.command`; `@itf.requires("command", scope="gw")`.

### Assumptions

A state that holds without ITF is declared, with an owner and a reason, and shows in the plan. A fragment:

```yaml
assume:
  - state: power.on
    owner: lab
    reason: the rack keeps it on
```

## Override files: one setup

```yaml
# lab2.itf.yaml: only what differs in this setup (an override file; it is merged over ecu.itf.yaml)
capabilities:
  endpoint:
    with:
      port: 22022
  credentials:
    with:
      user: lab
```

Merged by role over the target file, in the order given: `with:` and `bind:` keys are merged, other keys
replace; `remove: true` takes a role out; `relations:` of one state are joined. Name override files with
`--itf-override` (repeatable) or `--override` (`itf`), `ITF_OVERRIDE`, `itf_override` in `pytest.ini`,
`[tool.itf] override`, or `itf_target(overrides = [...])`; several are separated by `os.pathsep`.

## Code: the policy

`policy.py`, beside the target file, holds the project's ITF code. ITF loads it; pytest never does, so pytest
fixtures stay in `conftest.py`, and ITF code found in a conftest is an error that points here.

```python
from score.itf.core import hookimpl

@hookimpl
def itf_verify(session):
    """After bring-up, before the first test. `session.check(name, ok, detail=...)`."""

@hookimpl
def itf_teardown(session):
    """After the last test, targets still live, before unwind: save evidence."""
```

and the project's own parts: a factory or action written in the policy belongs to the pack `local` and
is named `local.<function>` in a target file (see the `exec_everywhere` and `itf` examples, where a project
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
- A requirement can also sit higher up, and a test needs every requirement on it and above it:

  ```python
  # test_files.py: every test in this module needs `files`
  itf_requires = itf.requires("files", contract="files.transfer")

  @itf.requires("command")          # every test in this class, and in its subclasses, also needs `command`
  class TestUpload:
      def test_round_trip(self, target): ...
  ```

  A package does the same with `itf_requires` in its `__init__.py`; a list sets several
  (`itf_requires = [itf.requires("files"), itf.requires("command")]`). `itf contracts map` reads all of them
  without importing the tests.
- `target.<role>` and `target.<scope>.<role>` return the objects; call only the members the contract's shape lists.
- The same test runs on every target that has the role: a suite does not depend on anybody's target file.
- Change state through the planner: `session.reach("shell.open")` re-establishes what an action invalidated;
  `session.discard("platform")` dismantles a role and everything bound to it and reaches nothing, so the next
  access builds a fresh one you can adjust before `reach`; `session.renew("platform")` is `discard` followed by
  reaching the goals again.
- Per-test isolation is a fixture you own, at the scope you choose:

  ```python
  @pytest.fixture(autouse=True)
  def fresh_container(session):
      session.renew("platform")
  ```

- Asynchronous processes: `WrappedProcess(target.process, "/usr/bin/app", wait_on_exit=True)` from
  `score.itf.core.process`, for any `process` role.

## The Bazel rules

```starlark
load("@score_itf//:defs.bzl", "itf_target", "py_itf_test")

itf_target(
    name = "ecu",
    src = "ecu.itf.yaml",
    overrides = [],                       # override files, merged in this order
    packs = ["@score_itf//score/itf/packs/docker"],   # the packs the factory labels name
    srcs = ["policy.py"],               # the policy: the project's own parts take part in the plan
    files = {"ITF_IMAGE_LOAD": ":image_load"},  # built files the target file names as ${ITF_IMAGE_LOAD}
    env = {},                             # other ${NAME} values
)

py_itf_test(
    name = "smoke",
    srcs = ["test_smoke.py"],             # the policy comes from the target file
    target = ":ecu",                      # inherits the files and values: no data, no $(location)
)
```

The target file stays plain YAML: `bootstrap: ${ITF_IMAGE_LOAD}`. Without Bazel the same file works when the
variable comes from the environment; with Bazel the `itf_target` is the one place that names the built file.

Building the test builds the target file, whose plan fails the build when it does not compile. See the
[Bazel macros](../reference/bazel_macros.rst).

## Without pytest

```python
from score.itf import Session

session = Session(target="ecu.itf.yaml", overrides=["lab2.itf.yaml"])
session.resolve()      # the plan; nothing is built or probed
session.bring_up()
session.target.command.exec("echo hello")
session.close()
```

See `examples/examples/plain_python`.
