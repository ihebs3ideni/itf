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

# Rationale: how the proposal compares with today's ITF and with itf-core

The proposal has two ancestors. **Today's ITF** (`main`) is what projects use: a `Target` class and one pytest
plugin per environment. **itf-core** is a prototype that introduced the OCTO planner, contracts and probes,
recorded in its decisions D-1 to D-36. This paper compares the proposal with both, topic by topic, and says why
each choice was made. The words are those of the [glossary](glossary.md).

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
test runs on a host (`command: local.exec`), over SSH (`command: ssh.exec`) or on QEMU, with no change to the test
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

## itf-core and the proposal

### Kept unchanged

| itf-core decision | Says | In the proposal |
|---|---|---|
| D-5 two graphs; D-15 the core constructs nothing | plan what exists and what happens, from metadata only | OCTO's two gates |
| D-1 identity is (scope, name) | a thing is named by its scope and name, not by its contract | roles: `target.command`, `target.gw.command` |
| D-7, D-8 binding order; ambiguity is a question | explicit, then the sole candidate, then an error | the same, minus derivation (below) |
| D-10, D-11 shapes as data; the consumer sets fidelity | shapes are member lists; the consumer decides how much it checks | a slot's Protocol is its expected shape |
| D-28 contributors meet only through names | parts never import each other | packs never import each other |
| D-20, D-21 state contracts and probes | a state is named by what it delivers; a probe checks it | `@state` and `@<action>.probe` |
| D-6 third-party temporal relations | anyone may order states | the target file's `relations:` |
| D-14, D-35 aliases; devices never fall back | sharing is explicit | `share:` in a scope |
| D-16 unwind from observed state | teardown starts from what probes see | also enables `itf down` |
| D-24, D-25 startup checks and teardown hooks | `itf_verify`, `itf_teardown` | the only hooks left |
| D-30 `assume` | a skipped producer is a visible, owned decision | `assume:` with owner and reason |
| D-36 kinds plug into OCTO | the planner knows no kind | unchanged |

### Changed

| Topic | itf-core | Proposed | Why |
|---|---|---|---|
| Describing a target | code: the root conftest implements `itf_setup` and `itf_init` and calls `ctx` methods (D-23, D-29); a YAML frontend translated to the same calls (D-31) | a target file, keyed by role | One declarative file can be validated, drawn, diffed and run by every front. The hooks mixed description and code |
| Where code lives | the conftest held both the description and code | the conftest holds code only: `itf_verify`, `itf_teardown`, fixtures, project parts | Structure in the file, behaviour in Python |
| Declaring a part | `@provides(token, name=, needs={slot: token})`, shapes through `expect()` (D-34) | `@capability`, `@state`; slots are parameters; `config` dataclass; the return type is the shape | The signature says everything. In the packs, about 50 uses of `needs=` and `expect()` became none |
| Naming a part | a free provider name | a label `<pack>.<name>` | One rule, and packs load from labels |
| Finding packs | `pytest_plugins` lists them (D-26, D-29) | the labels in the target file name them; `packs:` locates uninstalled ones | No second list to keep in sync |
| Derived nodes | binding step 3 derives a node when exactly one provider fits (D-7) | removed | Nothing enters a target unless listed |
| Goals | declared in `itf_init` | listed in the target file; `by:` when two actions could make a state true | Explicit and reviewable |
| Precedence | origins ranked as data (D-3): plugin < policy | packs < target file < project code | Same idea, with the target file as its own level |
| Contracts | tokens chosen by contributors; no definition files | any name; optional definitions; tools to map, define and enforce them | Projects own their contracts; ITF provides the tooling |
| Tests | gated on tokens, then used a node by name | gated on roles, and use the same role | The test asks for the name it uses |

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
