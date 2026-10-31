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

**Status:** Draft for discussion. Not implemented.

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
    assert target["exec.command"].exec("echo hi")[0] == 0     # the same identifier as the requirement
```

`target.get("exec.command")` is the same call, `target["exec.command", "sftp"]` reaches a named instance, and
`target["gw:exec.command"]` a device's. A requirement and an access use one identifier, so a suite works on any
recipe that passes its gating, whatever the recipe calls things.

### Plans and diagnostics

Before: `:itf.states.platform.up`, `.command`, `__itf_root__.platform`, `docker.instance`.
After: `platform.up`, `exec.command`, `platform.instance from docker`, `gw:exec.command`.

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
- **`target["exec.command"]` is less pleasant to type than `target.command`.** Attribute access by contract
  (`target.exec.command`) reads well but collides with scope names and handle members unless scope names are
  forbidden from being area names; this proposal keeps item access as the one canonical form and leaves
  attribute sugar as an open question.
- **One entrypoint per pack** makes every variant importable whenever the pack is loaded. Providers must keep
  heavy imports inside their factories, which a gate can check.
- **Prefixes for namespaces** need the registry to stay authoritative; a project-local prefix for an
  unregistered namespace is not allowed.

## Open questions

1. Attribute sugar (`target.exec.command`) or item access only?
2. Should `provide:` list contracts the recipe does not need, so they are available to tests (lazily
   realised), or only what goals, bindings and requirements pull in?
3. Do actions ever need a name of their own, or is `(state, pack[:variant])` always enough?
4. How long do the old forms stay accepted?
