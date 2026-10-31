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

# The ITF model: what things are called, where each fact lives, and who decides

**Status:** Proposed. Supersedes [identifiers](identifiers.md). Being applied on the platform branch.

## Why a model, not more features

ITF already does the hard parts: OCTO plans what must exist and what must happen; packs implement; probes give
evidence; contracts let a test run on any bench that offers what it needs. What is still hard is *talking about*
it: a newcomer meets a dozen kinds of identifier, the same fact is written in two places, and a test reaches a
capability by a name that only convention keeps stable. This document fixes the vocabulary once: what each
thing is called, which file is the single source of truth (SSOT) for each fact, how a bench is configured, how a
capability is swapped, what a project may do locally, and who governs what. OCTO does not change: to the planner
every name is still an opaque string; everything below is how the engine, the recipe format and the tools
present those strings to people.

## The six things a user deals with

| Thing | What it is | Identified by | Example |
|---|---|---|---|
| **Capability** | something a test can use on a target | its **member name**, defined by its contract | `command`, `shell`, `files`, `platform`, `logs` |
| **State** | a condition that can be made true and checked | `area.name` | `platform.up`, `shell.open` |
| **Pack** | an implementation of capabilities and states | one word, plus `:variant` when it offers several | `docker`, `ssh`, `serial:pty`, `docker:sim` |
| **Recipe** | what a bench is made of | a file | `recipe.yaml`, a Starlark target |
| **Bench values** | the facts of one physical setup | a file | `benches/lab2.yaml` |
| **Scope** | one device of a multi-device bench | a word | `gw` |

A **contract** is the definition behind a capability or a state: its meaning, members, guarantees and version.
Users rarely need its full identifier; it appears in definitions, the catalog and governance.

## Identifiers

### Capabilities have a member name, owned by their contract

Each capability contract declares the member name a target exposes it under:

```yaml
- contract: exec.command
  member: command
  version: 1
  summary: Run one shell command and get its exit code and output.
```

That name is part of the contract's public API, as stable as its methods. So on **every** bench that offers it,
the capability is `target.command`, and a test both requires and uses it by that one word:

```python
@itf.requires("command")
def test_hello(target):
    assert target.command.exec("echo hi")[0] == 0
```

No recipe chooses the name, so no suite depends on a recipe's naming. This removes today's hidden coupling,
where a test gates on a token and then reaches `target.command` only because every recipe happens to name the
node that way.

### Contract identifiers

`[namespace/]area.name[@major]`: `exec.command`, `platform.up`, `com.acme/power.relay@1`, `local/bench.door`.

- `itf` is the default namespace and is never written.
- The kind (capability or state) comes from the definition, so it is not part of the identifier.
- A registered namespace may declare a short prefix (`com.acme` declares `acme`), so `acme/power.relay` is
  accepted wherever an identifier is.
- Today's long form (`itf.capabilities.exec.command`) stays accepted and maps one to one. Inside the engine and
  OCTO the canonical string is unchanged, so plans, probes and gating keep working; only what users write and
  read changes.

### Requirements accept either form

`@itf.requires("command")`, `@itf.requires("command@1")` and `@itf.requires("exec.command@1")` are the same
requirement. States are named by their identifier: `target.reach("platform.up")`.

### Packs and variants instead of provider names

A provider is identified by what it provides and who provides it: *(contract, pack, variant)*. A recipe never
names a provider; it says which pack provides a capability:

```yaml
capabilities:
  command: docker
```

A pack with several implementations of one contract names them as variants: `serial:pty` beside `serial`,
`net:password` beside `net:key`, `docker:sim`, `dlt:multicast`. *(contract, pack, variant)* is unique, which a
gate checks. Today's provider names (`docker.exec`) stay accepted in old recipes.

### Instances

In a scope, a capability's instance is named by its member name. A second instance of the same contract gets a
local name with `as`:

```yaml
capabilities:
  files: docker
  sftp:
    contract: files
    pack: ssh
```

`target.files` and `target.sftp` are then both file transfers. A requirement for `files` is met by either.

### Scopes

A device scope is a member of the target and holds the same kind of members: `target.gw.command`. As today, a
scope never falls back to the root; sharing is declared (`share: [platform]`), after which
`target.gw.platform is target.platform`.

### Name clashes are plan errors

On a target, member names, instance names, scope names and the handle's own members (`reach`, `renew`, `probe`,
`plan`, `states`, `get`, `has`, `tokens`, `names`, `scope`, `scopes`) share one name space. A clash is rejected
when the plan is made. Two loaded contracts with the same member name (two vendors both calling theirs
`relay`) are also a plan error, resolved locally by giving one an `as` name.

### What users no longer write

Provider names, action names, `module:qualname` references, `.name` and `:token` reference syntax, the
`__itf_root__` scope and the `capabilities`/`states` segment of identifiers. Plans and diagnostics print
`platform.up`, `command (docker)`, `gw.command`.

## Single source of truth

| Fact | Lives in, and only there | Everything else derives it |
|---|---|---|
| What a capability or state means, its members, member name, version, stability | the contract definition, in its namespace owner's package | catalog, marketplace, contracts reference, `itf explain`, stubs |
| Which contracts and majors a pack implements | the pack's code: `@provides("command@1")`, `@delivers("platform.up")` | catalog, gates, version gating (no `implements` list to keep in sync) |
| A pack's kind, variants, prerequisites, version | `pack.yaml` (later: wheel metadata) | catalog, `itf doctor`, docs |
| A provider's configuration keys, defaults, secrets, held hardware | its config schema, in code | validation, catalog, redaction, the hold check |
| What a bench is made of | the recipe | plans, gating, benches |
| The facts of one physical setup | the bench values file | merged into the recipe's configuration |
| Which recipe and bench a run uses | configuration: `--itf-recipe`/`--itf-bench`, `ITF_RECIPE`/`ITF_BENCH`, `[tool.itf]`, `py_itf_test(recipe=, bench=)` | every runner, the `itf` command |
| What a test needs | `@itf.requires` | gating, the requirement-and-use lint |
| Who owns a namespace and its prefix | the namespace registry | contract loading, prefixes, governance |

`pack.yaml` loses its `implements` list: the decorators already say it, and two copies drift.

## Configuration: recipe for the structure, bench values for the facts

A recipe says what a bench is made of; it is shared by every bench of that kind. A bench values file says where
things are on one physical setup; it belongs to whoever runs that setup.

```yaml
# recipe.yaml: the same for every board of this kind
capabilities:
  platform:
    pack: ssh
  endpoint: net
  credentials: net:key
  command: ssh
  console: serial
goals:
  - platform.up
```

```yaml
# benches/lab2.yaml: one physical setup
endpoint:
  host: 10.0.0.7
  port: 22
credentials:
  key_file: ~/.ssh/lab2
console:
  device: /dev/ttyUSB0
```

Bench values are configuration overrides keyed by member (and `scope.member`), validated by each provider's
config schema like any recipe value, applied after `extends` and before planning. `${VAR}` keeps working for
values that come from the environment (a CI job's image tag). Precedence, lowest to highest: pack defaults,
recipe, bench values, the project's own code (conftest).

## Swapping a capability

Swapping is changing one word in a recipe: `command: docker` becomes `command: ssh`. Tests keep using
`target.command`; gating still sees the same contract; providers that need a command get the new one through
the contract. A swap that changes the contract (a console where a command was expected) is a plan error,
because the member name `command` belongs to `exec.command`. Simulations are swaps too: `command: docker:sim`.

## Local flexibility

A project may, without asking anyone:

- define contracts in `local/` (never published by a pack);
- provide capabilities and make states true with code in its conftest (bench-local providers and actions);
- name extra instances (`as`) and resolve member-name clashes locally;
- override any recipe declaration from its conftest (the project outranks the recipe);
- assume a state on its own word (`assume`, recorded with owner and reason);
- keep bench values per physical setup.

## Governance

| Decision | Who | Where |
|---|---|---|
| Contracts and member names in `itf` | the ITF community, by review | the contracts package and its pull request template |
| Contracts in a registered namespace | the namespace owner alone | the owner's contracts distribution |
| Registering a namespace and its prefix | ITF maintainers check the claim only | the namespace registry |
| Contracts in `local` | the project | the project's repository |
| Which packs and variants a bench uses | the recipe author | the recipe |
| The facts of a bench | the bench owner | bench values |

Rules: a contract's meaning and member name are fixed within a major; renaming a member is a new major;
stability (`experimental`, `stable`, `deprecated` with `replaced_by`) is a field, never part of the name;
conformance suites are owned with the contract and are the test of "implements".

## What this changes on the platform branch

1. Contract definitions gain `member`; identifiers accept the short form and namespace prefixes.
2. `@provides`/`@delivers` accept short identifiers and majors; `pack.yaml` drops `implements` and names its
   variants; *(contract, pack, variant)* is unique.
3. A recipe schema keyed by member name (`capabilities`, `goals`, `states`, `scopes` with `share`, `assume`,
   `relations`), in YAML and Starlark, with today's schema still accepted.
4. Bench values (`--itf-bench`, `ITF_BENCH`, `[tool.itf] bench`, `py_itf_test(bench = ...)`, `itf ... --bench`).
5. Requirements by member name or identifier; plans and diagnostics in the short form.
6. Packs, examples, starters, the integration suite, `itf init`, the catalog, `itf explain`, docs and the skill
   moved to the new forms; `itf migrate` rewrites a recipe.

## Costs

- It changes what users write: recipes, requirements and docs. Old forms keep working with a warning, and
  `itf migrate` rewrites recipes, but the change should land before the first release on this design.
- Member names are a shared, flat vocabulary. The `itf` set must be chosen with care, and vendors must avoid
  clashes or resolve them with `as`.
