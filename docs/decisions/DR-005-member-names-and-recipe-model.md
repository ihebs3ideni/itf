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


# DR-005-Arch: Member Names and the Recipe Model

**Date:** 2026-10-31
**Status:** Superseded by [DR-006](DR-006-target-composition.md): the recipe, member names, variants and bench values
described here are replaced by compositions keyed by role and override files. Kept for the record.

> This record follows the Decision Record convention established by the
> Eclipse S-CORE project:
> [eclipse-score/score — docs/design_decisions](https://github.com/eclipse-score/score/tree/main/docs/design_decisions).

## Overview

ITF plans what must exist and what must happen (OCTO), packs implement it, probes give evidence, and contracts
let a test run on any bench that offers what it needs. What stayed hard was talking about it: a newcomer met a
dozen kinds of identifier, the same fact was written in two places, and a test reached a capability by a name that
only convention kept stable. This record fixes the vocabulary and says where each fact lives. OCTO does not
change: to the planner every name is still an opaque string. The change is in what users write and read.

## Problem Statement

1. **A test gates on one name and uses another.** `@itf.requires("itf.capabilities.exec.command")` followed by
   `target.command` works only because every recipe happens to name the node `command`.
2. **A recipe names providers.** `using: docker.exec` ties a bench to an implementation; swapping the way to run
   commands means knowing a provider's name, and the provider names are not stable API.
3. **One fact, two homes.** `pack.yaml` listed `implements` and the code said it again with `@provides`; a
   physical setup's address was written into the recipe that is shared by every setup of that kind.
4. **Long identifiers everywhere.** `itf.capabilities.files.transfer` in a recipe, a requirement and a log line.

## Proposal

### Six things a user deals with

| Thing | What it is | Identified by | Example |
|---|---|---|---|
| Capability | something a test can use on a target | its member name, defined by its contract | `command`, `files`, `platform` |
| State | a condition that can be made true and checked | `area.name` | `platform.up`, `shell.open` |
| Pack | an implementation of capabilities and states | one word, plus `:variant` when it offers several | `docker`, `serial:pty` |
| Recipe | what a bench is made of | a file | `recipe.yaml`, a Starlark target |
| Bench values | the facts of one physical setup | a file | `bench.yaml` |
| Scope | one device of a multi-device bench | a word | `gw` |

A contract is the definition behind a capability or a state: meaning, members, guarantees, version. Users rarely
need its full identifier.

### Member names

A capability contract declares the name a target exposes it under (`member: command`). The name is part of the
contract's public API: it is fixed within a major, and renaming it is a new major. A test requires and uses a
capability by that one word, on every bench that offers it:

```python
@itf.requires("command")
def test_hello(target):
    assert target.command.exec("echo hi")[0] == 0
```

No recipe chooses the name, so no suite depends on a recipe's naming. `command`, `command@1` and
`exec.command@1` are the same requirement. Two loaded contracts with one member name are a plan error, resolved
locally by an instance name; a clash between a member, instance, scope and a handle member (`reach`, `renew`,
`plan`, ...) is rejected when the plan is made.

### Identifiers and prefixes

`[namespace/]area.name[@major]`. `itf` is the default namespace and is not written. A registered namespace may
declare a `prefix`, so `acme/power.relay` is accepted wherever `com.acme/power.relay` is. The long token
(`itf.capabilities.exec.command`) stays accepted and maps one to one; plans and OCTO keep it as the canonical
string.

### Packs and variants, not provider names

A recipe says which pack provides a capability: `command: docker`. A pack with several implementations of one
contract names them as variants (`serial:pty`, `net:key`, `net:password`, `docker:sim`, `dlt:multicast`).
(contract, pack, variant) is unique, which a gate checks. A pack is a directory with a `pack.yaml`; any provider
or action outside one, such as a project's own conftest, belongs to the pack `project` (`led: project`), and
what a pack offers is what the session registered of it, never what else happened to be imported. Provider
names (`docker.exec`) stay accepted in the first recipe schema.

### One recipe schema

```yaml
capabilities:
  platform: docker
  command: ssh
  sftp:
    contract: files
    pack: ssh
goals:
  - platform.up
states:
  platform.up: docker
assume:
  - state: platform.up
    owner: lab
    reason: the rig is powered by hand
relations:
  - state: logs.active
    requires:
      - bench.dlt_daemon.running
scopes:
  gw:
    capabilities:
      command: ssh
    share:
      - platform
```

A capability value is `pack[:variant]`, or a mapping with `pack`, `contract` (only for an instance name),
`config` and `bind`. The same keys under `scopes.<name>` address a device scope, and `share` lists the members of
the root that scope uses as they are. Starlark (`capability(...)`, `scope(...)`, `itf_recipe(capabilities = ...)`)
compiles to the same document. A document without `capabilities` is the first schema (`setup`, `init`, `nodes`,
`using`): it still loads, with a warning, and the engine issues the same calls for both.

### Recipe for the structure, bench values for the facts

A recipe says what a bench is made of; every bench of that kind shares it. A bench values file says where things
are on one physical setup; it belongs to whoever runs that setup:

```yaml
endpoint:
  host: 10.0.0.7
credentials:
  key_file: ~/.ssh/lab2
console:
  device: /dev/ttyUSB0
```

Keys are member or instance names (and `scopes: <name>:`). The values are merged into each capability's `config`
after `extends`, and validated by the provider's own config schema like any recipe value. A name that is not a
capability of the recipe is an error. Precedence, lowest to highest: pack defaults, recipe, bench values, the
project's own code. A run picks them up from `--itf-bench`, `ITF_BENCH`, `[tool.itf] bench`,
`py_itf_test(bench = ...)` or `Session(bench = ...)`.

### Swapping, local flexibility, governance

Swapping is changing one word: `command: docker` becomes `command: ssh`. A swap that changes the contract is a
plan error, because the member name `command` belongs to `exec.command`. Simulations are swaps too:
`command: docker:sim`.

A project may, without asking anyone: define `local/` contracts; provide capabilities and make states true in its
conftest; name extra instances and resolve member-name clashes; override any recipe declaration from its
conftest; `assume` a state on its own word, recorded with owner and reason; keep bench values per physical setup.

| Decision | Who | Where |
|---|---|---|
| Contracts and member names in `itf` | the ITF community, by review | the contracts package |
| Contracts in a registered namespace | the namespace owner alone | the owner's contracts distribution |
| Registering a namespace and its prefix | ITF maintainers check the claim only | the namespace registry |
| Contracts in `local` | the project | the project's repository |
| Which packs and variants a bench uses | the recipe author | the recipe |
| The facts of a bench | the bench owner | bench values |

A contract's meaning and member name are fixed within a major. Stability (`experimental`, `stable`,
`deprecated` with `replaced_by`) is a field, never part of the name. Conformance suites are owned with the
contract and are the test of "implements".

### Single source of truth

| Fact | Lives in, and only there |
|---|---|
| What a capability or state means, its members, member name, version, stability | the contract definition |
| Which contracts and majors a pack implements | the pack's code (`@provides`, `@delivers`) |
| A pack's kind, variants, prerequisites, version | `pack.yaml` |
| A provider's configuration keys, defaults, secrets | its config schema, in code |
| What a bench is made of | the recipe |
| The facts of one physical setup | the bench values file |
| Which recipe and bench a run uses | configuration (`--itf-recipe`, `--itf-bench`, `ITF_RECIPE`, `ITF_BENCH`, `[tool.itf]`, `py_itf_test`) |
| What a test needs | `@itf.requires` |
| Who owns a namespace and its prefix | the namespace registry |

## Alternatives Considered

| Option | For | Against |
|---|---|---|
| **A. Member names owned by the contract, recipes by pack (proposed)** | One name everywhere; swapping is one word; no suite depends on a recipe's naming | A shared, flat vocabulary of member names; vendors must avoid clashes or use an instance name |
| B. Recipes name nodes freely (the first schema) | Flexible | The hidden coupling between a test's gate and its use; every recipe repeats the convention |
| C. Names derived from the contract automatically in the engine, with no declaration | No new field | Clever inference: the derived name changes when an identifier does; no review point |
| D. Keep provider names in recipes | Nothing to migrate | Providers become public API; a swap needs their names; no variants |

## Implementation Status

| Step | State |
|---|---|
| `member` in contract definitions; identifiers, namespace prefixes, short requirements | done |
| `@provides`/`@delivers` with identifiers and majors; `variant`; (contract, pack, variant) unique | done |
| Recipe schema by member name in YAML and Starlark; the first schema still accepted | done |
| Bench values (`--itf-bench`, `ITF_BENCH`, `[tool.itf] bench`, `py_itf_test(bench = ...)`, `Session(bench = ...)`) | done |
| Plans and diagnostics in the short form | done |
| Integration suite, examples, starters, docs and the agent skill in the new forms | done |

## Open Questions

- The `itf` member names are a flat, shared vocabulary chosen once; adding one is a review in the contracts
  package. Whether a distribution may claim a member name outside its namespace is not decided (today: no).
