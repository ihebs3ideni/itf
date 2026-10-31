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

# Proposal: onboarding and contract discovery

**Status:** Draft, to be evaluated. Not part of the 8-commit series.

## Problem

Someone new to ITF who wants to test their own software has two questions: *where do I start?* and
*what can ITF do on my target?* The current docs and tools answer both poorly.

1. **Contracts have no definition of their own.** A token such as `itf.capabilities.exec.command`
   exists only because providers implement it. Nothing states what it means, which members a test may
   rely on, what it guarantees, or when to choose it over `exec.shell` or `exec.console`. The
   marketplace borrows a description from whichever provider documents it first.
2. **The docs explain the mechanism before the use.** The README opens with contracts, recipes, OCTO
   and a planner diagram. A newcomer's question is "my software runs in a container, a VM or on a
   board: how do I test it?"; the vocabulary only helps once that is answered.
3. **The tools are hard to find and expect expertise.** The marketplace is linked from one paragraph
   of the packs reference. The catalog CLI is SQL-shaped (`sql "SELECT * FROM v_recipe_node ..."`),
   which suits someone who already knows the schema.
4. **There is nothing to copy.** The getting-started page shows a single test; no template is a
   working project to copy and adapt. `examples/exec_everywhere`, which shows the core value (one
   test file, four targets, only the recipe changes), is not reachable from the start page.

## Goals

- A newcomer reaches a passing test on their own kind of target in about 15 minutes.
- Every contract has one authoritative page: meaning, members, guarantees, providers, consumers and
  copyable snippets.
- The question "which contract do I need?" can be answered without reading pack source code.

## Non-goals

- Changing how contracts, providers or the planner work.
- Moving domain vocabulary into the core: contract definitions stay outside `score/itf/core`.

## Proposal

### 1. Contract definitions as first-class data

One file per contract area (for example `contracts/exec.yaml`) gives, for every token:

- a one-paragraph description of what the contract means;
- the members a consumer may rely on, with their semantics;
- guarantees and limits (for example: `exec.command` is stateless, `exec.shell` keeps shell state,
  `exec.console` is the raw boot console and may interleave output);
- when to choose a neighbouring contract instead.

The catalog conformance test fails when a provider, action or test uses a token that has no entry.
Providers keep publishing their own shapes; the definition states the intended meaning they implement.

### 2. A contracts reference, generated

Generated from the definitions and the catalog: one page per contract with the meaning, members,
providers (with variants and configuration), consumers, a test snippet (`@itf.requires(...)` plus a
call) and a recipe snippet. This becomes the main section of the marketplace, which moves to the
front of the documentation site.

### 3. A "Start here" page

A decision path in three questions, each answer linking to a starter and to the relevant contract
pages:

| Question | Typical answers |
|---|---|
| Where does your software run? | a container, a QEMU VM, a board on the network, a board on a serial line, the host |
| How does ITF reach it? | the container API, SSH, a serial console, a local shell |
| What do your tests need? | run commands, transfer files, read logs (DLT), capture traffic, restart the target |

### 4. Starter templates

`examples/starter/{container,ssh_board,qemu,serial}`: each a recipe, a conftest with `itf_verify` and
`itf_teardown`, one test and a BUILD file, built and tested in CI so they never rot, copyable as-is.

### 5. A tutorial

About 15 minutes: run a test against a container, then point the same test at an SSH target by
changing only the recipe. It ends at the contracts reference and the how-to guides.

### 6. How-to guides by goal

Task pages: run a command; transfer files; read DLT logs; capture packets; use a serial console;
restart the target and reach the goals again; isolate tests with `renew`; write a bench-local action.

### 7. A catalog CLI that answers questions

Keep `sql` for power users and add task-shaped commands:

```bash
bazel run //tools/catalog:query -- explain itf.capabilities.exec.command
bazel run //tools/catalog:query -- providers itf.capabilities.exec.command
bazel run //tools/catalog:query -- starter container
```

### 8. Documentation landing page

Cards for Start here, Marketplace, Tutorial and Reference instead of the generic How-to, Reference
and Concepts.

## Order of work

1. Contract definitions and the conformance check (everything else depends on it).
2. Contracts reference in the marketplace; landing page cards.
3. Starter templates and the Start here page.
4. Tutorial and how-to guides.
5. Catalog CLI commands; the agent skill updated to use them.

## Open questions

- Where do contract definitions live: a top-level `contracts/` directory, a contracts package beside
  the packs, or the docs tree? They must be loadable by the catalog and not owned by any pack.
- Should a contract definition also carry a reference Protocol for consumers to copy, or would that
  invite shared code across packs?
- Who owns a contract once several packs implement it?
