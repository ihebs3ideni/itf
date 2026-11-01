<!--
*******************************************************************************
Copyright (c) 2025 Contributors to the Eclipse Foundation
See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.
This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0
SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# ITF as target composition: OCTO first

**Status:** Accepted direction; decisions below. Being implemented on the platform branch. Replaces [the ITF
model](model.md).

## Decisions

0. **Vocabulary.** Contracts are of two kinds: **capability contracts**, fulfilled by **capability factories**
   (`@capability`), and **state contracts**, fulfilled by **action functions** (`@state`, with probes). A
   composition lists capabilities by role and states as goals. Where this document says "part", read "a
   capability factory or an action".

1. **ITF knows no contracts.** A contract is whatever name two parts agree on, with whatever shape they publish
   and expect. ITF is the platform that lets projects discover, map, define and enforce their contracts; it does
   not ship a vocabulary everyone must follow. Plans and gates are the compiler: they tell you, from metadata,
   whether a composition would work. The ITF team maintains the contracts its own packs use, with conformance
   checks, as a supported set, not as a standard.
2. **A composition is keyed by role**, chosen from the examples below.
3. **Everything is explicit, and nothing is required.** Goals are listed, not inferred; no part enters a target
   unless the composition lists it; an empty composition is valid.
4. **The first command line is** `itf validate`, `plan`, `graph`, `up`, `down` and `test`, plus the contract
   tools `itf contracts map|new|check`.

## Choosing the composition format from examples

Two candidates: keyed by part label, or keyed by role. Four cases:

**A. A plain container target.**

```yaml
# keyed by part label                    # keyed by role
parts:                                   parts:
  docker.platform:                         platform:
    image: my-ecu:latest                     part: docker.platform
  docker.exec:                               with:
                                               image: my-ecu:latest
                                           command: docker.exec
```

**B. The same part twice** (two consoles on one board).

```yaml
parts:                                   parts:
  serial.console:                          console:
    device: /dev/ttyUSB0                     part: serial.console
  serial.console:        # duplicate key     with:
    as: debug            # not valid YAML      device: /dev/ttyUSB0
    device: /dev/ttyUSB1                   debug:
                                             part: serial.console
                                             with:
                                               device: /dev/ttyUSB1
```

**C. One bench changes a value** (an override file).

```yaml
# keyed by part label: which of the two   # keyed by role: unambiguous
# serial.console entries?
                                         parts:
                                           debug:
                                             with:
                                               device: /dev/ttyUSB3
```

**D. A test reaches the part.** Keyed by part label, the test needs a second name to say which part it means;
keyed by role, the key is that name: `target.debug`.

Keyed by part label reads well in case A and breaks in B, C and D. **Keyed by role** costs one word per part in
case A and works the same in every case: duplicates, overrides, includes, scopes and tests all use the role as
their stable key. It is also what Docker Compose does (services keyed by name, `image:` as the value).

### The format

```yaml
include:
  - base.itf.yaml               # merged first; this file wins
capabilities:
  platform:
    factory: docker.platform    # pack.name
    with:                       # the part's settings, checked against its schema
      image: my-ecu:latest
  command: docker.exec          # short form: just the factory
  shell:
    factory: ssh.shell
    bind:                       # only when a slot has more than one candidate
      endpoint: lab_endpoint
goals:
  - platform.up                 # explicit; the part that makes it true comes with the parts listed
  - state: console.open
    by: serial.open             # only when two listed packs could make it true
assume:
  - state: power.on
    owner: lab
    reason: the rack keeps it on
scopes:
  gw:
    capabilities:
      command: ssh.exec
    share:
      - platform                # gw uses the root's platform role
```

An override file is a composition with only what changes; it is merged by role like an include.

### Tests ask for roles

`@itf.requires("command")` means the target has a role `command`; `contract=` and `shape=` narrow it when a
test wants to check more: `@itf.requires("command", contract="exec.command", shape=["exec"])`. The test then
uses `target.command`. Which role names a project uses is the project's convention; `itf contracts check` can
enforce it (role `command` is always an `exec.command`).

## A part, declared

```python
class Shell(Protocol):              # the consumer's own Protocol, never shared code
    __contract__ = "exec.shell"     # which contract this shape describes
    def run(self, command: str) -> str: ...

@capability("exec.command")         # label: <pack>.exec, from the function name
def exec(shell: Shell) -> SshExec:  # the parameter is a slot: contract and shape from its annotation
    return SshExec(shell)

@state("shell.open", after=("platform.up",))
def open_session(shell: Shell) -> None:
    shell.connect()

@open_session.probe
def session_open(shell: Shell) -> bool:
    return shell.connected()
```

- `@capability` wraps a capability factory, `@state` an action function; `after=` and `breaks=` are an action's
  state relations.
- A slot is a parameter; its annotation's `__contract__` names the contract, its members are the expected shape.
- `config: <dataclass>` is the part's settings schema (`with:` in a composition).
- The label is `<pack>.<function name>`, or `label=`. A part outside any pack belongs to `project`.
- Contract names accept `@major`; when both sides give one, they must agree.

## Contracts are discovered, defined and enforced by projects

| Tool | Does |
|---|---|
| `itf contracts map` | every contract name in use, from the loaded parts and tests: who offers it (and with which shape), who needs it (and expecting which members), which tests ask for it, whether a definition exists, and every disagreement between them; as text, JSON or a browsable page |
| `itf contracts new <name> --from-usage` | a definition skeleton built from the shapes observed in the map |
| `itf contracts check --policy policy.yaml` | the project's rules: which namespaces need definitions, that every offering part passes its contract's conformance checks, a role-to-contract convention, forbidden stabilities; exit 1 on violations, for pipelines |
| contract definitions | optional files (in a pack, a project, a distribution, `ITF_CONTRACTS_PATH`): meaning, members, version, stability, a suggested role, conformance |

Without any definition, a composition still compiles: wiring and gating use names, and the no-trust checks use
the shapes the parts themselves publish and expect. Definitions add meaning, versions and conformance where a
project wants them.

## The idea, in one paragraph

A test target is **composed from parts**. Every part describes itself: what it offers, what it needs, what it
makes true, what it breaks, what it expects of its neighbours and how to check that it did its job. OCTO
(Open Contract Topology Orchestration) reads those descriptions and only those, checks that every part's
rules are met by the others, and produces a plan before anything exists. The plan can be validated, drawn,
queried, diffed, brought up and torn down. Tests are one consumer of a composed target; a person at a terminal
is another; an old framework wrapped in a facade is a third. Nothing in the composition is trusted on its name:
every claim is checked by the party that depends on it.

## What successful platforms got right, and what ITF takes

| Platform | What works | ITF |
|---|---|---|
| Terraform | declarative desired state; `validate`, `plan`, `apply`, `destroy`; a registry of versioned providers; variables files per environment; `terraform graph`; drift shown by `plan` | a composition file; `itf validate`, `plan`, `up`, `down`; a catalog of versioned packs; overrides per bench; `itf graph`; drift shown by probes |
| Docker Compose | one file says what runs; `compose up`, `ps`, `down`; an override file per environment | one file says what the target is made of; `itf up`, `status`, `down`; an override file per bench |
| Bazel | labels say where a thing comes from; analysis before execution; `bazel query`; providers carry typed information between rules | part labels say which pack a part comes from; the plan before bring-up; `itf query`; contracts carry names and shapes between parts |

The pattern all three share: **one declarative file**, **a lifecycle of verbs on the command line**,
**everything checked and visible before it runs**, **a registry**, and **environment values kept out of the
structure**. ITF adds what none of them needs: probes, because test targets are physical and their state
changes outside the tool.

## The vocabulary: five words

| Word | What it is | How it is named | Who defines it |
|---|---|---|---|
| **Contract** | the protocol two parts meet on: a name, a version, a shape, a meaning, a conformance suite | `exec.command`, `platform.up`, `acme/power.relay@1` | the namespace owner, in contract definitions |
| **Part** | a self-describing unit: a provider of a capability or an action that makes a state true | `pack.part`: `docker.exec`, `ssh.shell`, `serial.pty_console`, `docker.start` | the pack author, in code |
| **Composition** | a target: the parts it is made of, their settings, its goals | a file (`target.itf.yaml`) or a Starlark target | the person describing the target |
| **Role** | the name a placed part answers to on the target: `target.command` | defaults to the role its contract declares; renamed with `as` only for a second instance | the contract (default) or the composition (rename) |
| **Scope** | one device of a multi-device target | `gw` | the composition |

A **state** is a contract of kind state (`platform.up`). An **override file** holds the values of one physical
bench; it has the shape of the composition's settings and nothing else.

### What this removes

- Separate provider names, action names, variants and node names: a part has one label, and its role comes from
  its contract.
- Pack lists in test targets: the part labels name their packs (`docker.exec` loads `docker`), as Bazel labels
  name their packages.
- `contract:` on nodes: a part already says what it offers.
- Mapping capabilities to packs: a composition lists parts, it does not fill slots.

## A composition

```yaml
# target.itf.yaml: an ECU image under test in a container, reached over SSH
parts:
  docker.platform:
    image: my-ecu:latest
  docker.endpoint:
    port: 2222
  net.password:
    user: score
    password: score
  ssh.shell:
  ssh.exec:
  ssh.files:
goals:
  - shell.open
```

- Six parts. Roles come from their contracts: `platform`, `endpoint`, `credentials`, `shell`, `command`,
  `files`.
- Wiring comes from what each part needs: `ssh.exec` needs a `shell`, the composition has exactly one, so it is
  wired; `ssh.shell` needs an `endpoint` and `credentials`, likewise.
- `shell.open` is a goal; the part that can make it true (`ssh`'s open action) comes with `ssh.shell`, and its own
  requirement (`platform.up`) pulls in `docker`'s start action.
- Swapping is replacing a part: `ssh.exec` becomes `docker.exec` and the test does not change.

When a choice is real, the composition says so, and only then:

```yaml
parts:
  docker.files:
  ssh.files:
    as: sftp              # a second part offering files: give it its own role
  ssh.exec:
    bind:
      shell: debug_shell  # two shells in the target: say which one this part uses
goals:
  - platform.up: docker.start   # two parts could make it true: say which one
```

### Reuse

A composition can include another (`include: base.itf.yaml`) and override its settings, like a Terraform
module. An override file for a bench is the same mechanism with nothing but settings in it.

```yaml
# benches/lab2.itf.yaml
docker.endpoint:
  port: 22022
net.password:
  user: lab
```

## No trust: every part brings its rules, and they check each other

Nothing is accepted because a name matches. Each rule comes from the party that cares about it.

| Rule | Brought by | Checked against | When |
|---|---|---|---|
| "I need a shell with `run` and `exec`" | the part that needs it (its parameter and annotation) | the shape the offering part publishes | composition, from metadata |
| "I offer `exec.command@1`" | the offering part | the contract definition (it exists, the major exists, the part offers every required member) | composition |
| "I make `shell.open` true; I need `platform.up`; I break `network.reachable`" | the action | every other action's claims; OCTO orders or refuses | composition |
| "My settings are `port: int`, `password` is secret" | the part's config schema | the composition and override values | composition |
| "I hold `serial:/dev/ttyUSB0` exclusively" | the part | every other part's holds | composition |
| "I need tcpdump on PATH" | the pack | the host (`itf doctor`) | before bring-up |
| "I need a `command`, version 1, with `exec`" | the test (`@itf.requires`) | the composed target | collection (gating) |
| "I did make `shell.open` true" | the action | its own probe, run right after | bring-up |
| "It is still true" | the probe | the target, again, before reuse and at teardown | every run |
| "A provider of `exec.command` behaves like this" | the contract's conformance suite | each part claiming it | CI, certification |

The engine's only job is to hold every party to its own word and to the words of its neighbours.

## One engine, many fronts

```
                 parts (packs)          contracts (definitions)
                        \                    /
                         composition (file)
                                 |
                       OCTO plan (validated, drawable)
                 /          |            |            \
          itf CLI     pytest adapter   facade      plain Python
```

### The command line: the lifecycle

| Command | Does | Touches hardware |
|---|---|---|
| `itf validate` | every metadata rule above | no |
| `itf plan` | the plan, readable; `--json` for tools | no |
| `itf graph` | the topology (parts and wiring) and the bring-up sequence, as Mermaid | no |
| `itf query` | `deps(command)`, `rdeps(platform.up)`, `breaks(shell.open)`, `offers(console)` | no |
| `itf doctor` | host prerequisites of the composition's packs | reads the host |
| `itf up` | bring up, verify, print the target; `--detach` leaves it running | yes |
| `itf status` | probe every state of the plan, show what holds and what drifted | reads |
| `itf down` | unwind from what the probes observe | yes |
| `itf shell` | a console with `target` on a running composition | yes |
| `itf test` | run the tests against the composition (pytest underneath) | yes |

`itf down` after `itf up --detach` needs no state file. OCTO already unwinds from observed state, never by
replaying the plan (D-16), so a part that can observe what it created (a container found by its labels) can be
torn down by a later process. A part that cannot observe says so, and `--detach` is refused for it.

### The pytest adapter: the same composition, no new concepts

```toml
[tool.itf]
target = "target.itf.yaml"
```

`pytest` then builds the target from the composition, gates each test on its requirements, gives tests the
`target` fixture and unwinds at the end. The packs load from the part labels; the conftest holds only code
(readiness checks, evidence, fixtures, project-local parts). `itf test` is the same thing started from the
command line.

### A facade: keep an old API

A project with tests written against an old framework keeps them: a facade maps the composed target's roles
onto the old classes (`target.command` behind the old `target.execute()`). The composition does not change; the
facade is a thin layer in the project, as the legacy example already shows.

### Bazel

Bazel adds checking and packaging, not a dialect: the composition reaches a test as the YAML file it is, and the
engine reads it exactly as `pytest --itf-target` would without Bazel (no generated document, no setup hooks).

```python
itf_target(
    name = "ecu",
    src = "ecu.itf.yaml",
    packs = ["@score_itf//score/itf/packs/docker"],
    files = {"ITF_IMAGE_LOAD": "//images:load"},    # the composition says ${ITF_IMAGE_LOAD}
)
py_itf_test(name = "smoke", srcs = ["test_smoke.py"], target = ":ecu")
```

- **Verifier.** `bazel build :ecu` compiles the composition with its packs and overrides (both gates, nothing
  constructed), writes `ecu.plan.json` and fails with ITF's diagnostics when it does not compile. The run compiles
  again, because its action plan depends on what the probes observe at that moment.
- **Bundle.** The target carries the composition, overrides, included files, the project's conftest and the packs'
  code to every test that uses it. `packs` is the one repetition Bazel needs (it cannot read YAML while analysing),
  and the build fails if a factory label names a pack not listed.
- **The one place for `${NAME}` values.** `files` maps a name to a built file's label: every test gets the file in
  its runfiles and `${NAME}` set to its path. `env` gives the other values. Tests inherit both, so they need no
  `data` or `$(location)`, and the composition stays plain, portable YAML. While compiling, `${NAME}` is the label
  written as a path: nothing is opened, so checking a composition never builds or downloads what it points at.

## Where each thing is defined

| Thing | Defined in | Only there |
|---|---|---|
| A contract's name, version, shape, meaning, default role, conformance | its contract definition | yes |
| A part's label, contract, needs, published shape, settings, holds, probes | the pack's code (decorators, parameters, annotations, dataclasses) | yes |
| A pack's prerequisites and version | the pack's metadata | yes |
| What a target is made of | its composition | yes |
| The values of one bench | its override file | yes |
| What a test needs | `@itf.requires` | yes |
| Which composition a run uses | configuration (`--itf-target`, `ITF_TARGET`, `[tool.itf] target`, Bazel `target =`) | yes |

## A part, declared

```python
@part("exec.command")                                   # label docker.exec: pack + function name
def exec(platform: Platform) -> DockerExec:             # needs a platform with this shape; gives this
    return DockerExec(platform)

@part("platform.up", needs_state=("image.present",), breaks=())
def start(platform: Platform) -> None:                  # an action is a part too
    platform.start()

@start.probe
def running(platform: Platform) -> bool:
    return platform.running()
```

One decorator for providers and actions. The label is the pack and the function name unless the decorator gives
one. Everything else comes from parameter names, annotations and the return type.

## What changes from the current platform branch

| Today (platform) | Proposed |
|---|---|
| recipe maps capabilities to packs (`command: ssh`) | composition lists parts (`ssh.exec:`) |
| member names, variants, provider names, node names | part labels and roles (roles default from the contract) |
| pack lists in test targets and in `pytest_plugins` | derived from part labels |
| bench values | override files with the composition's own shape |
| `@provides` and `@delivers` | `@part`, one decorator |
| CLI: `plan`, `up`, `explain`, `diff`, ... | the lifecycle: `validate`, `plan`, `graph`, `query`, `doctor`, `up`, `status`, `down`, `shell`, `test` |
| no diagrams, no query | `itf graph`, `itf query` from metadata |

Kept as they are: OCTO, contracts and their governance (namespaces, versions, stability, conformance), probes,
evidence, failure reports, the process wrapper, gating.

## Open questions

1. Composition keys are part labels (`ssh.exec:`); is a list form (`- ssh.exec`) clearer when the same part is
   used twice?
2. Should a composition name its goals, or should the goals of a target default to "every state some part's
   probe can check"?
3. How many verbs does the first release need? A minimal set is `validate`, `plan`, `graph`, `up`, `down`,
   `test`.
