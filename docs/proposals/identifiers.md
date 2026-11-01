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

# Proposal: fewer identifiers, one name per thing

**Status:** Superseded by [the ITF model](model.md), which gives each capability a member name owned by its contract instead of addressing it by contract path.

## Problem

A user of ITF meets about a dozen kinds of identifier, several of them for the same thing:

| Identifier | Example | Where a user meets it |
|---|---|---|
| contract token | `itf.capabilities.exec.command@1` | `@itf.requires`, recipe `contract:` |
| state token | `itf.states.platform.up` | recipe goals, relations |
| provider name | `docker.exec` | recipe `using:` |
| action name | `docker.start_platform` | pinning a producer: `states: - token, using` |
| node name | `command` | `target.command` |
| node reference | `.command`, `gw.shell` | aliases, bindings, diagnostics |
| state reference | `:itf.states.platform.up`, `gw:...` | plans, diagnostics |
| pack entrypoint | `score.itf.packs.dlt.multicast.plugin` | `pytest_plugins`, `--packs` |
| Bazel label and variant | `//score/itf/packs/dlt:multicast` | `py_itf_test(plugins = ...)` |
| pack name | `dlt` | catalog, `pack.yaml` |
| namespace | `itf`, `com.acme` | inside tokens |
| slot | `endpoint` | `bind:` |

Three costs follow.

1. **A test names the same capability twice, differently.** It gates on a token and then reaches the object
   through a node name: `@itf.requires("itf.capabilities.exec.command")`, then `target.command.exec(...)`.
   Nothing links the two. A suite works across recipes only because every recipe happens to call its command
   node `command`; a recipe that calls it `cmd` passes gating and fails with an `AttributeError`.
2. **A recipe repeats itself.** A node carries a name, often a contract, and a provider name whose prefix is the
   pack and whose suffix restates the contract (`docker.exec` for `exec.command`).
3. **One pack has several entrypoints.** `dlt` has five Bazel labels and five modules, so choosing a variant
   (multicast, receive, sim) means loading a different entrypoint rather than choosing a provider.

## Principles

- **One name per thing, and the same name everywhere** it is used: in requirements, recipes, code, plans and
  diagnostics.
- **The contract is the address.** What a test asks for is what it gets.
- **Names exist only where a choice exists.** No name is required when there is only one candidate.
- **Implementation identifiers stay internal.** `module:qualname`, probe references and origins never appear
  in what a user writes.

## The model: five identifiers

| Identifier | Form | Example | Says |
|---|---|---|---|
| **Contract** | `[namespace/]area.name[@major]` | `exec.command@1`, `platform.up`, `acme/power.relay@1` | what it is (capability or state comes from its definition) |
| **Pack** | a single word | `docker`, `ssh`, `dlt` | who implements it: the distribution, the entry point and the Bazel target |
| **Variant** | `pack:variant` | `docker:sim`, `dlt:multicast` | which of a pack's implementations, only when a pack has several |
| **Instance** | a word, optional | `sftp`, `debug` | a second instance of a contract in one scope, or a local name for one |
| **Scope** | `scope:` prefix | `gw:exec.command`, `gw:platform.up` | which device; the root has no prefix |

Separators each mean one thing: `/` namespace, `.` area and name, `@` version, `:` scope or variant (a scope
prefixes a contract, a variant suffixes a pack, so they never meet).

### Contracts

- The `capabilities`/`states` segment goes: the definition already says which it is, and area names are
  unique within a namespace across both kinds.
- `itf` is the default namespace, so the community vocabulary is short: `exec.command`, `platform.up`.
- Other namespaces get a prefix declared once in the namespace registry: `com.acme` registers the prefix
  `acme`, so `acme/power.relay` is unambiguous. `local/bench.door` is a project's own contract. This replaces
  per-token aliases: the namespace registry is the only place short names come from.
- The long form stays valid input forever and maps one to one:
  `itf.capabilities.exec.command` is `exec.command`; `com.acme.capabilities.power.relay` is
  `acme/power.relay`.

### Providers and actions: a pack plus a contract

A provider is identified by what it provides and who provides it: `(contract, pack[:variant])`. A recipe never
writes a provider name; it writes the contract and the pack. The same goes for the action that makes a state
true: `(state, pack[:variant])`.

### Instances: the contract is the default name

In a scope, a contract with one instance needs no name: its contract is its name. A name is given only to tell
several instances of one contract apart (`files.transfer` from the container and `files.transfer` as `sftp`), or
when a project wants a local name for one.

### One entrypoint per pack

A pack has exactly one entrypoint and one Bazel target. Today's extra entrypoints become variants inside it
(`dlt:multicast`, `dlt:receive`, `dlt:sim`, `docker:sim`, `pcap:sim`, `ping:boot`), chosen per contract in the
recipe. Loading a pack makes all its variants available; each variant's heavy imports stay lazy, inside its
provider, so loading `dlt` does not require the native receive tools unless `dlt:receive` is used.

## Before and after

### A recipe

Before:

```yaml
setup:
  nodes:
    - name: platform
      contract: itf.capabilities.platform.instance
      using: docker.instance
      config:
        image: my-ecu:latest
    - name: command
      using: docker.exec
    - name: files
      using: docker.files
    - name: sftp
      contract: itf.capabilities.files.transfer
      using: ssh.files
init:
  goals:
    - itf.states.platform.up
```

After:

```yaml
provide:
  - platform.instance: docker
    config:
      image: my-ecu:latest
  - exec.command: docker
  - files.transfer: docker
  - files.transfer: ssh
    as: sftp
goals:
  - platform.up
```

### A test

Before:

```python
@itf.requires("itf.capabilities.exec.command@1")
def test_hello(target):
    assert target.command.exec("echo hi")[0] == 0     # node name: a convention
```

After:

```python
@itf.requires("exec.command@1")
def test_hello(target):
    assert target.exec.command.exec("echo hi")[0] == 0     # the requirement's own path
```

The attribute path is the contract written with dots: what a test requires is literally what it types.
`target["exec.command"]` is the same lookup for code that holds the contract in a variable.

### Plans and diagnostics

Before: `:itf.states.platform.up`, `.command`, `__itf_root__.platform`, `docker.instance`.
After: `platform.up`, `exec.command`, `platform.instance from docker`, `gw:exec.command`.

## Reaching things on the target

The target handle is a tree that mirrors the identifiers. Every level answers `dir()`, so a console (`itf up`)
or an editor completes it.

```
target                          the root scope
├── exec                        an area of the default namespace (itf)
│   ├── command                 the exec.command instance
│   └── shell                   the exec.shell instance
├── platform
│   ├── instance                the platform.instance instance
│   └── up                      the platform.up state
├── files
│   └── transfer                the unnamed files.transfer instance
├── sftp                        a named instance (files.transfer as sftp)
├── acme                        a namespace prefix
│   └── power
│       └── relay               acme/power.relay
└── gw                          a device scope: the same tree again
    └── exec
        └── command             gw:exec.command
```

### Capabilities

`target.exec.command` is the instance of `exec.command` in the root scope; `target.gw.exec.command` the one in
device scope `gw`. An area (`target.exec`) is a small view listing the contracts it holds; it has no other
members, so it never hides a contract.

### States

A state is reachable the same way and returns a state view, not an object:

```python
target.platform.up.holds()      # the last probe's answer
target.platform.up.probe()      # probe now
target.platform.up.reach()      # plan and run what makes it true, through the planner
target.gw.platform.up.reach()   # the same, in device scope gw
```

`target.reach("platform.up")` stays, for code holding the state in a variable.

### Named instances

A name given with `as:` becomes a top-level entry of its scope: `target.sftp`, `target.gw.sftp`. When a
contract has an unnamed instance, `target.files.transfer` is that one. When every instance of a contract is
named, `target.files.transfer` is an error that lists the names, so a test never silently gets the wrong one.

### Vendor namespaces

A registered prefix is a level of its own: `acme/power.relay` is `target.acme.power.relay`. `local/bench.door`
is `target.local.bench.door`.

### Scopes

A device scope is an entry of the root, as today: `target.gw`. It holds the same kinds of entry as the root,
and, as today, never falls back to the root. Sharing an instance is declared in the recipe:

```yaml
scopes:
  gw:
    provide:
      - exec.command: ssh
    share:
      - platform.instance          # gw uses the root's platform instance
```

`target.gw.platform.instance is target.platform.instance`.

### One name space per level, checked at plan time

At each level of a scope, these share one name space: the handle's own members (`reach`, `renew`, `probe`,
`plan`, `states`, `get`, `has`, `tokens`, `names`, `scope`, `scopes`), scope names, instance names, namespace
prefixes and the default namespace's area names. Clashes are plan diagnostics, the way scope names that shadow
handle members are rejected today:

- a scope or instance named like an area (`exec`), a prefix (`acme`) or a handle member: rejected, with the
  clashing entry named;
- the namespace registry refuses a prefix equal to an `itf` area name, and the contracts gate refuses an area
  named like a handle member.

So `target.<name>` is never ambiguous, and the lookup order below only matters for error messages: handle
member, scope, instance, namespace prefix, area.

### Linking requirements and use

Because a requirement and an access use the same path, ITF can check one against the other. A test that reaches
`target.exec.shell` without requiring `exec.shell` passes on a recipe that happens to provide it and fails on
one that does not. A lint (part of `itf plan` or a gate) reads each test's attribute paths and warns when one is
not covered by its `@itf.requires`.

### Types in an editor

The tree is dynamic, so an editor does not know that `target.exec.command` has `exec()`. `itf stubs` can write a
`.pyi` for a recipe from the contract definitions (one Protocol per contract, from its members), so completion
and type checking work without changing the runtime.

## What stays, feature by feature

| Feature | How it is expressed |
|---|---|
| Swapping implementations | change the pack: `exec.command: docker` becomes `exec.command: ssh` |
| Simulations and other variants | `exec.command: docker:sim` |
| Several instances of one contract | `as: name` |
| Wiring a slot to a specific instance | `bind: endpoint: sftp` (slots keep their names; a binding names an instance or a contract) |
| Sharing an instance across scopes | `gw:platform.instance: same` (or an alias entry naming the root instance) |
| Pinning which pack makes a state true | `platform.up: docker` under `goals` or `states` |
| Versions | `@major` on contracts, unchanged rules |
| Namespaces and local contracts | `acme/...`, `local/...`, the registry gives prefixes |
| Precedence (project over recipe over packs) | unchanged |
| Exclusive hardware (`holds`) | unchanged; keys stay as proposed |

## Migration

- Long tokens, provider names (`docker.exec`), node names and `.name`/`:token` references keep working as input
  during a deprecation period; `itf plan` warns once per old form with its new spelling.
- `itf migrate <recipe>` rewrites a recipe document; a codemod rewrites `@itf.requires(...)` strings and
  `target.<node>` accesses where the node's contract is known from the recipe.
- Packs keep their old extra entrypoints as thin shims that load the pack and select the variant, for one
  release.
- The legacy layer is unaffected: it maps the original API onto whatever the target offers.

## Costs and risks

- **It is a breaking change of the surface**, even with shims: documentation, examples, starters, the skill and
  every downstream recipe change. It should land before ITF's first release on this design, not after.
- **Attribute access needs naming discipline.** Scope names, instance names, prefixes, area names and handle
  members share one name space per level. The plan-time check makes clashes impossible, but it does forbid a
  scope called `exec` or an instance called `platform`.
- **Paths are one level longer than today's node names** (`target.exec.command` instead of `target.command`).
  In exchange they mean the same thing on every recipe.
- **One entrypoint per pack** makes every variant importable whenever the pack is loaded. Providers must keep
  heavy imports inside their factories, which a gate can check.
- **Prefixes for namespaces** need the registry to stay authoritative; a project-local prefix for an
  unregistered namespace is not allowed.

## Open questions

1. Should `provide:` list contracts the recipe does not need, so they are available to tests (lazily
   realised), or only what goals, bindings and requirements pull in?
2. Do actions ever need a name of their own, or is `(state, pack[:variant])` always enough?
3. How long do the old forms stay accepted?
4. Is the requirement-and-use lint a warning or, under `--itf-strict-gating`, an error?
