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

# Rationale: how the proposal compares with today's ITF

Today's ITF (`main`) is a `Target` class and one pytest plugin per environment. This paper compares the proposal
with it, topic by topic, then lists the main design choices with the alternative each one was weighed against.
The words are those of the [glossary](glossary.md).

## Today's ITF and the proposal

### The same test

Today, `test_exec.py` and its `BUILD`:

```python
def test_exec(target):
    exit_code, output = target.execute("uname -a")
    assert exit_code == 0
    assert b"Linux" in output
```

```starlark
py_itf_test(
    name = "test_exec",
    srcs = ["test_exec.py"],
    args = ["--docker-image=ubuntu:24.04"],
    plugins = ["@score_itf//score/itf/plugins:docker_plugin"],
)
```

Proposed:

```python
@itf.requires("command")
def test_exec(target):
    exit_code, output = target.command.exec("uname -a")
    assert exit_code == 0
    assert "Linux" in output
```

```starlark
itf_target(
    name = "docker",
    src = "docker.itf.yaml",
    packs = ["@score_itf//score/itf/packs/docker"],
)

py_itf_test(
    name = "test_exec",
    srcs = ["test_exec.py"],
    target = ":docker",
)
```

```yaml
capabilities:
  platform:
    factory: docker.platform
    with:
      image: ubuntu:24.04
  command: docker.exec
goals:
  - platform.up
```

The proposed form is longer for one test on one container. It pays off from the second target onwards: the same
test runs on a host (`command: localhost.exec`), over SSH (`command: ssh.exec`) or on QEMU, with no change to the test
or its `BUILD` except the target file it names.

### Topic by topic

| Topic | Today | Proposed | Why |
|---|---|---|---|
| What a target is | an instance of a `Target` subclass | the roles a target file lists, built by factories | A device with an unusual set of capabilities needs no new class |
| Where a target is described | plugin options (`--docker-image`), `docker_configuration` fixtures, plugin lists in `BUILD` | one target file; override files per setup | One place that can be validated, drawn, compared and shared |
| Bring-up order | code inside each plugin | planned by OCTO from each action's `after`/`breaks` and the target file's `relations:` | New steps slot in without editing a plugin |
| Which tests run where | every test runs, and fails at run time when the target lacks a method | `@itf.requires("<role>")`; tests that do not fit are deselected before bring-up, with the reason | One suite for many targets |
| When mistakes appear | after a container or a VM started | at `itf validate`, and at `bazel build` under Bazel | Faster feedback, no wasted bring-up |
| Did a step work | the plugin's own waits | every action has a probe, run after it, before reuse and at teardown | Evidence rather than timeouts |
| Teardown | each plugin's fixture finaliser | unwind from what probes observe; every host process reaped | Correct after a crash and from a later process |
| Extending | write a plugin and a `Target` subclass | write a pack: decorated functions | Smaller surface, no inheritance |
| Running without tests | not possible | `itf up`, `itf down` | Debugging and demos |
| Old tests | | a facade of the project's own; ITF ships an example | ITF does not carry two APIs |

## Design choices

| Topic | Chosen | Alternative weighed | Why |
|---|---|---|---|
| Describing a target | a target file, keyed by role | code in a conftest calling setup functions | One declarative file can be validated, drawn, diffed and run by every front; code mixed description with behaviour |
| Where project code lives | the policy, `policy.py` beside the target file; conftests stay pytest's | the conftest | Structure in the file, ITF code in one known file, pytest fixtures where pytest expects them |
| Declaring a part | `@capability`, `@state`; slots are parameters; a `config` dataclass; the return type is the shape | a decorator listing needs and shapes by hand | The signature says everything once |
| Naming a part | a label `<pack>.<name>`; `local.<name>` in the policy | free names | One rule, and packs load from labels |
| Finding packs | the labels in the target file name them; `packs:` locates uninstalled ones | a plugin list kept beside the target | No second list to keep in sync |
| Filling a missing part | never: nothing enters a target unless listed | derive one when exactly one candidate fits | No hidden parts in a plan |
| Goals | listed in the target file; `by:` when two actions could make a state true | inferred from what tests need | Explicit and reviewable |
| Precedence | packs < target file < policy | one level | The project can always override, visibly |
| Contracts | any name; optional definitions; tools to map, define and enforce them | a fixed vocabulary owned by ITF | Projects own their contracts |
| Tests | gated on roles, and use the same role | gated on contract names | The test asks for the name it uses |
| Planning | from declarations only, in two gates (what exists, then what happens) | building as you go | Mistakes are found before anything starts |
| Teardown | from what probes observe | replaying the plan backwards | Correct after a crash and from a later process |

### Added

| Addition | Why |
|---|---|
| The `itf` command line | A target file can be driven from a terminal or a pipeline, not only from tests |
| Contract tools (`map`, `new`, `check`, `reference`) | Discovery and enforcement belong to the tooling, not to a registry |
| `itf_target` and `py_itf_test(target=)` | A target file that does not compile fails the build |
| Override files and `remove: true` | One structure for every setup |
| `evidence.json`, `evidence.html`, failure reports | A failed run must be readable |
| `ProcessWrapper` with owner-scoped reaping | Nothing outlives a run |
| `score.itf.Session` | Runners other than pytest |

## Tried and dropped on the way

The implementation went through drafts. These were built, measured and removed:

| Tried | Dropped because |
|---|---|
| Starlark recipes compiled to a JSON document read by the hooks | A second format and an indirection; target files must work without Bazel |
| Role names owned by contracts (member names), packs with variants, `capabilities: <member>: <pack>` | Target file became filling fixed slots, and OCTO's building from parts was lost |
| Contracts addressed by path (`target.exec.command`) | Less readable than one role per capability |
| A fixed contract vocabulary with a namespace registry | ITF should not claim to know every project's contracts |
| Bench values as a separate concept | Override files do the same with one structure |
| `composition.itf.yaml` and `itf_composition` | Named the mechanism, not what tests get; the file describes a target and tests use `target` |
| Orderings in packs (`ssh.open` after `platform.up`) | Forced every target file for a running machine to assume `platform.up` |
