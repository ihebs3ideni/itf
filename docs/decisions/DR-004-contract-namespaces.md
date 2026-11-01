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

# DR-004-Arch: Contract Namespaces, Stability and Versions

**Date:** 2026-10-31
**Status:** Proposed; implemented on the branch (`score/itf/contracts`, `itf contracts`, `examples/examples/vendor_contract`).
Amended by [DR-005](DR-005-member-names-and-recipe-model.md); the identifier, registry and member-name parts are superseded by
[DR-006](DR-006-target-composition.md) (ITF knows no contracts; names are whatever parts agree on). Stability, versions and
conformance suites stand, as optional definitions.

> This record follows the Decision Record convention established by the
> Eclipse S-CORE project:
> [eclipse-score/score — docs/design_decisions](https://github.com/eclipse-score/score/tree/main/docs/design_decisions).

## Overview

A contract is a token that says what a test can rely on (`itf.capabilities.exec.command`). Its
definition is data in `score/itf/contracts/<area>.yaml`. Until now every token lived in one flat,
community-owned set. This record proposes how tokens are named, who may define them, how they change
over time, and where definitions come from, so that a vendor, a project or a pack author can add a
contract without waiting for the ITF community, and a test can still say exactly which promise it relies
on.

## Problem Statement

1. **Only the community can add a contract.** A vendor with a relay board, a project with a bench-only
   device and a team piloting a new idea all need a token. Today the choices are to wait for a change in
   this repository or to invent a string that nothing checks.
2. **Nothing says who owns a token.** A name such as `power.relay` could mean two things in two projects, and
   a reader cannot tell which definition is the official one.
3. **Nothing says how much to trust a token.** A contract that is still being shaped looks the same as one
   that twenty packs depend on.
4. **A token's meaning can change under a test.** A test that requires `exec.command` cannot say which
   version of the promise it was written against, and a provider cannot say which one it keeps.

## Proposal

### The token grammar

```
<namespace>.<capabilities|states>.<area>.<name>[@<major>]
```

- The namespace is everything before `.capabilities.` or `.states.`, so a reverse-DNS namespace such as
  `com.acme` parses without ambiguity. It is lowercase dotted words (`[a-z][a-z0-9_-]*`).
- `capabilities` marks an object a test uses; `states` marks a condition that holds on the target.
- `<area>` and `<name>` are lowercase words (`[a-z][a-z0-9_]*`), exactly one each.
- `@<major>` is a positive integer. Requirements and `implements` entries carry it; a definition never does.
  Its version is a field.

`score/itf/contracts/names.py` parses and validates it.

This is the **canonical token**: what the engine and the planner see, and what plans and evidence record. People
write the shorter **identifier**, `[namespace/]area.name[@major]` (`exec.command`, `platform.up`,
`org.example/power.relay@1`), where `itf` is the default namespace and is never written, and a registered
namespace may declare a short `prefix` (`prefix: example`, so `example/power.relay`). The kind (capability or
state) comes from the definition, so an identifier does not carry it. Identifier and token map one to one; the
long form stays accepted everywhere. A capability contract also declares a **member name** (`member: relay`), the
one word a target exposes it under and a test requires it by (`@itf.requires("relay@1")`, `target.relay`). The
member name is part of the contract's public API, as stable as its methods. [DR-005](DR-005-member-names-and-recipe-model.md)
explains the choice.

### Three tiers of namespace

| Tier | Namespace | Owner | Where its definitions live |
|---|---|---|---|
| Community | `itf` | the ITF community | this repository, reviewed through the contract proposal template |
| Registered | reverse DNS, such as `com.acme` or `org.example` | the party that registered it | its own repository or distribution |
| Local | `local` | the project that uses ITF | a directory listed in `ITF_CONTRACTS_PATH` |

`itf` is reserved: only this repository defines tokens there. `local` is reserved and never published: a
built-in or distribution source that defines a `local.` token is an error. A project uses `local`
to start, and moves the contract to a registered namespace when a second project wants it.

### The registry

`score/itf/contracts/namespaces.yaml` lists the registered namespaces. Each entry has `namespace`, `owner`,
`contact`, `source` and `description`, and may have a `prefix`, a short alias for the namespace in identifiers
(a lowercase word, unique across the registry). A distribution or a local directory may carry its own
`namespaces.yaml`; the loader merges the registrations of every source, and two registrations of one
namespace with different content are an error. A source may define a token only in a registered namespace
or, for local sources, in `local`.

Registering a namespace needs no review for what the owner defines in it: the registry records who is
responsible. Entries in this repository's registry are added by pull request, and a name that is taken, or
that looks like it belongs to someone else, is refused. `org.example` is registered for the examples.

### Stability and `replaced_by`

Each definition has `stability`:

- `experimental`: may change without a new major. A test that requires it must say so with
  `@itf.requires(..., experimental=True)`; without that the plan warns.
- `stable`: the default. Changes follow the version rules below.
- `deprecated`: still honoured, no longer recommended. `replaced_by` names the token that supersedes it, and
  a plan that uses it warns and names the replacement. `replaced_by` is valid only on a deprecated definition.

### Version rules

A definition has an integer `version`: the latest stable major. A provider states the majors it keeps in its own
code (`@provides("exec.command@1")`), and a test requires `command@1`. A pack has no `implements` list to keep in
step: the decorators are the one place.

- A token's meaning is fixed within a major. A test written against `token@1` keeps passing with any provider of
  `token@1`.
- Adding an optional member (`required: false`) is a minor change: the major stays. Tests that use it
  gate on it with `shape=`.
- Removing a member, making an optional member required, or changing what a member or guarantee means is a
  new major.
- Parallel majors are allowed. A provider may implement `token@1` and `token@2` at the same time, and a
  recipe node may be offered by either; gating compares the requirement's major with the majors the
  provider offers and deselects the test, with the reasons, when none matches.
- The definition file describes the latest major. The text of an earlier major stays in the repository
  history until the contract needs to describe two majors at once, which is an open question below.

### Sources and conflicts

The loader merges three sources in this order:

1. the built-in YAML of `score/itf/contracts`;
2. installed distributions that declare an entry point in the group `score_itf.contracts`, whose value names a
   package of YAML files;
3. directories listed in `ITF_CONTRACTS_PATH`, separated like `PATH`.

The same token defined twice with identical content is one definition. With different content it is an error
that names both sources. A malformed file stops the load with the file and the reason; nothing is skipped.
Each definition records its source (`builtin: exec.yaml`, `local /path: x.yaml`, `distribution x (pkg): y.yaml`),
and `itf explain` and the catalog show it.

### Tools

`itf contracts` is the one place to work with all of this: `list` (filter by namespace and stability),
`show`, `namespaces`, `lint` (grammar, registered namespace or `local`, schema, clashes with the built-in set;
exit 1 on errors), `new` (a block-YAML skeleton that refuses an unknown namespace), `reference` and `catalog`
(the contracts reference and the pack marketplace). The Bazel binaries `//tools/catalog:build` and
`//tools/catalog:contracts_md` run the last two. `itf explain` shows namespace, owner, version, stability,
`replaced_by`, required and optional members, and the source.

### Defaults chosen

1. **Contracts stay in this repository, in their own package, for now.** `score/itf/contracts` is a package owned by
   no pack, imported by nobody but tools and the pytest adapter. Moving it to its own repository later costs
   a dependency change, not a design change, because the loader already reads other distributions. We move it
   when a second owner needs to release contracts on its own schedule.
2. **An unversioned requirement means the latest stable major.** `@itf.requires("command")`
   requires the `version` of the definition (any major when the token has no definition). This keeps existing
   suites working. `--itf-strict-versions` rejects a requirement without `@<major>`, so a project can make
   versions mandatory in CI.

## Alternatives Considered

| Option | For | Against |
|---|---|---|
| **A. Namespaces in the token, a registry, three tiers (proposed)** | A vendor needs no change here; ownership is readable in the name; `local` is a free first step | A registry to look after; longer tokens |
| B. One flat community set | Simplest; one place to look | Every vendor waits on this repository; no ownership; no way to mark unstable ideas |
| C. A separate repository for contracts now | Independent release | A second repository to keep in step before there is a second owner; packs and contracts change together today |
| D. Version in the definition only, never in the requirement | No `@1` noise | A test cannot say what it was written against; a provider cannot say what it keeps |
| E. Semantic `major.minor` in the token | Finer grain | Minor changes by definition do not affect a test, so the number would carry no decision |

## Implementation Status

| Step | State |
|---|---|
| Token grammar, `names.py`, `namespaces.yaml` with `itf`, `local`, `org.example` | done |
| Loader merging built-in, distribution and `ITF_CONTRACTS_PATH` sources; conflict errors | done |
| `stability`, `replaced_by`, `required` members in definitions; plan-time warnings | done |
| Versioned requirements, `@provides("area.name@major")`, `--itf-strict-versions` | done |
| Identifiers, namespace prefixes, member names (DR-005) | done |
| `itf explain` and `itf contracts` (list, show, lint, new, namespaces, reference, catalog) | done |
| Catalog and marketplace: namespace, stability, required or optional members, filter and badges | done |
| `examples/examples/vendor_contract`: a vendor namespace end to end | done |
| Contract proposal template and the how-to | done |
| A `CODEOWNERS` file for `score/itf/contracts` | not done; the how-to has the note to adopt |

## Open Questions

- Who may add an entry to the registry in this repository, and by what test of ownership? Today: a pull request
  reviewed by the maintainers.
- How long does a deprecated contract stay? A suggestion is two minor releases of ITF, then removal in a major
  release of ITF; this record does not fix it.
- When a contract has two live majors, how does the definition file describe both? Today it describes the latest
  and the older text lives in the history.
- Should a distribution be able to claim a namespace by the entry point alone, without an entry in the registry
  of this repository? The loader allows it (a `namespaces.yaml` in the package); the question is whether
  the community wants to.
