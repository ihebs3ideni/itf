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

# The ITF model: what things are called, where each fact lives, who decides

ITF is a platform to **compose test targets from self-describing parts**. A part says what it offers, what it
needs, what it makes true, what it breaks and how to check that it did its job. OCTO (Open Contract Topology
Orchestration) reads those descriptions, and only those, checks that every part's rules are met by the others,
and produces a plan before anything exists. The plan can be validated, drawn, brought up and torn down. Tests
are one consumer of the composed target; a person at a terminal is another; an old framework behind a facade is
a third.

Nothing is trusted on its name. Every claim is checked by the party that depends on it (see
[No trust](#no-trust-every-part-brings-its-rules-and-they-check-each-other)).

## The vocabulary

| Word | What it is | Named by | Defined by |
|---|---|---|---|
| **Contract** | the protocol two parts meet on: a name, and optionally a version, a shape, a meaning, a conformance suite | `exec.command`, `platform.up`, `acme/power.relay@1` | whoever the parts agree with; a definition is optional |
| **Capability contract** | a contract fulfilled by a capability factory: something a test uses | `exec.command` | the consumer's Protocol and the factory's return type |
| **State contract** | a contract fulfilled by an action function: a condition that can be made true and checked | `platform.up`, `shell.open` | the actions that make it true, with probes |
| **Capability factory** | code that builds a capability: `@capability("exec.command")` | label `<pack>.<function>`: `docker.exec`, `ssh.shell` | the pack author, in code |
| **Action** | code that makes a state true, with a probe that checks it: `@state("platform.up", after=..., breaks=...)` | label `<pack>.<function>`: `docker.start`, `ssh.open` | the pack author, in code |
| **Composition** | a target: the factories it is made of, their settings, its goals | a file, `*.itf.yaml` | the person describing the target |
| **Role** | the name a placed factory answers to on the target: `target.command` | a key of the composition's `capabilities:` | the composition |
| **Scope** | one device of a multi-device target | `gw` | the composition |

Words that are not on the list are not ITF's. A part outside any pack belongs to the pack `project`:
`project.activate_logs`. An **override file** is a composition holding only what changes; it holds the values of
one bench and is merged by role.

## A part, declared

```python
class Shell(Protocol):                  # the consumer's own Protocol, never shared code
    __contract__ = "exec.shell"         # which contract this shape describes

    def run(self, command: str) -> str: ...

@capability("exec.command")             # label: <pack>.exec, from the function name
def exec(shell: Shell) -> SshExec:      # the parameter is a slot: contract and shape from its annotation
    return SshExec(shell)

@state("shell.open", after=("platform.up",))
def open_session(shell: Shell) -> None:
    shell.connect()

@open_session.probe
def session_open(shell: Shell) -> bool:
    return shell.connected()
```

- `@capability` wraps a capability factory, `@state` an action function. `after=` and `breaks=` are an action's
  state relations; `also=` lists further states one action makes true.
- A **slot** is a parameter. Its annotation's `__contract__` names the contract; its members are the shape the
  part expects. No other parameter is allowed, except `config`.
- `config: <dataclass>` is the settings schema: what a composition gives under `with:`.
- The label is `<pack>.<function name>`, or `label=`. Contract names accept `@major`; when both sides give one,
  they must agree.

## A composition

```yaml
include:
  - base.itf.yaml                 # merged first; this file wins
capabilities:
  platform:
    factory: docker.platform      # <pack>.<name>
    with:                         # the factory's settings, checked against its schema
      image: my-ecu:latest
  command: docker.exec            # short form: just the factory
  shell:
    factory: ssh.shell
    bind:                         # only when a slot has more than one candidate
      endpoint: lab_endpoint
goals:
  - platform.up                   # explicit
  - state: console.open
    by: serial.open               # only when two actions could make it true
assume:
  - state: power.on
    owner: lab
    reason: the rack keeps it on
scopes:
  gw:
    capabilities:
      command: ssh.exec
    share:
      - platform                  # gw uses the root's platform role
```

**Everything is explicit, and nothing is required.** Goals are listed, not inferred. No part enters a target
unless the composition lists it. An empty composition is valid. Wiring comes from what each part needs: a slot
with one candidate is bound to it, a slot with several needs `bind:`, a state two listed packs could make true
needs `by:`. The actions considered are those of the packs of the listed factories plus the project's own.

Roles are keyed by name because a role is the stable key for everything else: duplicates (two consoles on one
board are two roles), overrides, includes, scopes and tests all use it. It is also what Docker Compose does.

## Override files: the values of one bench

```yaml
# bench.itf.yaml: only what differs on this bench
capabilities:
  platform:
    with:
      image: my-ecu:debug
```

An override file is merged by role over the composition: `with:` and `bind:` keys are merged, any other key
replaces. It has the composition's own shape and nothing else; it cannot remove a role. `${NAME}` and
`${NAME:-default}` in a `with:` value read the environment (a value that is exactly one reference is read as a
YAML scalar, so `port: ${SSH_PORT:-22}` is an integer).

## Tests ask for roles

`@itf.requires("command")` means the target has a role `command`. `contract=` and `shape=` narrow it when a test
wants to check more: `@itf.requires("command", contract="exec.command", shape=["exec"])`. The test then uses
`target.command`. A test whose requirement is not met is deselected before anything is built, with the reason.
Which role names a project uses is the project's convention; `itf contracts check` can enforce it (the role
`command` is always an `exec.command`).

## ITF knows no contracts

A contract is whatever name two parts agree on, with whatever shape they publish and expect. ITF does not ship a
vocabulary everyone must follow: it is the platform that lets a project discover, map, define and enforce its own.
Plans and gates are the compiler: they tell you, from metadata, whether a composition would work. The ITF team
maintains the contracts its own packs use, with conformance checks, as a **supported set**, not a standard.

| Tool | Does |
|---|---|
| `itf contracts map` | every contract name in use, from the loaded parts and tests: who offers it (with which shape), who needs it (expecting which members), which tests ask for it, whether a definition exists, and every disagreement; as text, JSON or a browsable page |
| `itf contracts new <name> --from-usage` | a definition skeleton built from the shapes observed in the map |
| `itf contracts check --policy policy.yaml` | the project's rules: which namespaces need definitions, a role-to-contract convention, forbidden stabilities; exit 1 on violations, for pipelines |
| contract definitions | optional files, in a pack, a project, a distribution or `ITF_CONTRACTS_PATH`: meaning, members, version, stability, a suggested role, conformance |

Without any definition a composition still compiles: wiring and gating use names, and the no-trust checks use the
shapes the parts publish and expect. Definitions add meaning, versions and conformance where a project wants them.
See [Use, define and enforce contracts](../how-to/contracts.md) and the `vendor_contract` example.

## No trust: every part brings its rules, and they check each other

Nothing is accepted because a name matches. Each rule comes from the party that cares about it.

| Rule | Brought by | Checked against | When |
|---|---|---|---|
| "I need a shell with `run` and `exec`" | the part that needs it (its slot's annotation) | the shape the offering part publishes | composition, from metadata |
| "I fulfil `exec.command@1`" | the offering factory | the contract definition, when there is one (it exists, the major exists, every required member is offered) | composition |
| "I make `shell.open` true; I need `platform.up`; I break `network.reachable`" | the action | every other action's claims; OCTO orders or refuses | composition |
| "My settings are `port: int`, `password` is secret" | the part's config schema | the composition and override values | composition |
| "I need tcpdump on PATH" | the pack | the host (`itf doctor`) | before bring-up |
| "I need a `command`, version 1, with `exec`" | the test (`@itf.requires`) | the composed target | collection (gating) |
| "I did make `shell.open` true" | the action | its own probe, run right after | bring-up |
| "It is still true" | the probe | the target, again, before reuse and at teardown | every run |
| "A fulfiller of `exec.command` behaves like this" | the contract's conformance checks | each part claiming it | CI, certification |

The engine's only job is to hold every party to its own word and to the words of its neighbours.

## Who decides what

| Question | Decided by |
|---|---|
| what a target is made of | the composition |
| which factory fills a role | the composition (`bind` and `by` only where a choice is real) |
| what must exist, and in which order | OCTO gate 1 (what must exist) from the parts' needs |
| what must happen, and in which order | OCTO gate 2 (what must happen) from the goals, `after` and `breaks` |
| whether a state holds | its probe, never the plan |
| which tests run | gating, against the composed target |

## Where each fact lives

| Fact | Lives in | Only there |
|---|---|---|
| a contract's meaning, version, members, role, conformance | its definition, if the project wants one | yes |
| a part's label, contract, needs, shape, settings, probes | the pack's code: decorators, slots, annotations, dataclasses | yes |
| a pack's prerequisites and version | its `pack.yaml` | yes |
| what a target is made of | its composition | yes |
| the values of one bench | its override file | yes |
| what a test needs | `@itf.requires` | yes |
| which composition a run uses | configuration: `--itf-target`, `ITF_TARGET`, `itf_target` in `pytest.ini`, `[tool.itf] target`, Bazel `target =` | yes |
| code: readiness, evidence, fixtures, project parts | the root `conftest.py` | yes |

## What successful platforms got right, and what ITF takes

| Platform | What works | ITF |
|---|---|---|
| Terraform | declarative desired state; `validate`, `plan`, `apply`, `destroy`; variables files per environment; `graph`; drift shown by `plan` | a composition file; `itf validate`, `plan`, `up`, `down`; override files per bench; `itf graph`; drift shown by probes |
| Docker Compose | one file says what runs; `up`, `down`; an override file per environment | one file says what the target is made of; `itf up`, `down`; an override file per bench |
| Bazel | labels say where a thing comes from; analysis before execution; providers carry typed information between rules | factory labels say which pack a part comes from; the plan before bring-up; contracts carry names and shapes between parts |

ITF adds what none of them needs: probes, because test targets are physical and their state changes outside
the tool.
