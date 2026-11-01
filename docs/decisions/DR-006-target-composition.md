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

# DR-006-Arch: Target Composition

**Date:** 2026-11-01
**Status:** Proposed; implemented on the branch (`score/itf/core`, `score/itf/packs`, `bazel/itf_target.bzl`,
`test/integration`)

**Supersedes:** the recipe, member-name, variant and bench-value parts of [DR-005](DR-005-member-names-and-recipe-model.md)
and the identifier and namespace-registry parts of [DR-004](DR-004-contract-namespaces.md). The recipe format of
[DR-003](DR-003-infra-starlark-recipes.md) is replaced by compositions and `itf_target`.

> This record follows the Decision Record convention established by the
> Eclipse S-CORE project:
> [eclipse-score/score — docs/design_decisions](https://github.com/eclipse-score/score/tree/main/docs/design_decisions).

## Overview

ITF is a platform to compose test targets from self-describing parts. Every part says what it offers, needs,
makes true, breaks and expects of its neighbours, and how to check that it did its job. OCTO reads those
descriptions, and only those, and plans the target before anything exists. The earlier model (DR-004, DR-005)
asked a project to learn a registry of namespaces, member names owned by contracts, packs with variants, a recipe
mapping capabilities to packs, and bench values keyed by member or instance name. This record replaces that with
one declarative file keyed by role, and moves contracts from a vocabulary ITF owns to a practice a project owns.

## Decisions

0. **Vocabulary.** Contracts are of two kinds: **capability contracts**, fulfilled by **capability factories**
   (`@capability`), and **state contracts**, fulfilled by **action functions** (`@state`, with probes). A
   composition lists capabilities by role and states as goals.
1. **ITF knows no contracts.** A contract is whatever name two parts agree on, with whatever shape they publish
   and expect. ITF is the platform that lets projects discover (`itf contracts map`), define (optional definition
   files, `itf contracts new --from-usage`) and enforce (`itf contracts check --policy`) their contracts; it does
   not ship a vocabulary everyone must follow. Plans and gates are the compiler: they say, from metadata, whether a
   composition would work. The ITF team maintains the contracts its own packs use, with conformance checks, as a
   supported set, not a standard.
2. **A composition is keyed by role.** `capabilities:` maps a role to a factory label (`command: docker.exec`) or
   to a mapping with `factory`, `with` and `bind`. Alternatives considered: keyed by part label (reads well for one
   part, breaks for the same part twice, for overrides and for tests, which need a second name); a list form.
   Keyed by role costs one word per part and uses the same stable key for duplicates, overrides, includes, scopes
   and tests (`target.debug`). It is what Docker Compose does.
3. **Everything is explicit, and nothing is required.** Goals are listed, not inferred (`state` plus `by` when two
   actions could make one state true); no part enters a target unless the composition lists it; an empty
   composition is valid.
4. **The command line is the lifecycle:** `itf validate`, `plan`, `graph`, `up [--detach]`, `down` and `test`,
   plus `itf contracts map|new|check`. Nothing before `up` touches hardware. `down` unwinds from observed state,
   never by replaying the plan.
5. **Parts declare themselves in code.** `@capability("exec.command")` wraps a factory, `@state("platform.up",
   after=..., breaks=...)` an action with `@<action>.probe`. A slot is a parameter whose annotation (the consumer's
   own Protocol) carries `__contract__`; `config: <dataclass>` is the settings schema. The label is
   `<pack>.<function>`; code outside any pack is the pack `project`. Contract names accept `@major`; when both
   sides give one they must agree.
6. **Override files** are compositions holding only what changes, merged by role like an include (`with:` and
   `bind:` merged, other keys replaced). They replace bench values.
7. **Tests ask for roles:** `@itf.requires("<role>", contract=..., shape=[...])` and `target.<role>`. Which role
   names a project uses is its convention; a policy can enforce it.
8. **Packs load from labels.** `docker.exec` loads `docker` (the module `score.itf.packs.docker.plugin`, or an
   entry point `score_itf.packs`). Test targets do not list packs for the planner to find; the Bazel `itf_target`
   lists the packs its labels may name, and a label naming another pack fails the build.
9. **Bazel:** `itf_target(name, src, overrides, packs, data, srcs, contracts, env, files)` compiles the
   composition during the build and writes its plan; `py_itf_test(target = ...)` runs tests against it. The
   composition reaches the test as it is (no generated document, no hooks). The `itf_target` is the one place that
   supplies the composition's `${NAME}` values: `files` maps a name to a built file's label (tests get the file and
   its path), `env` gives the other values; tests inherit both. Compiling uses each file's label in place of its
   path, so a plan check never builds what the composition points at.
10. **Facades keep old APIs.** A project maps the composed roles onto its old classes in a thin layer of its own
    (`examples/examples/legacy`); the composition does not change.

## No trust

Nothing is accepted because a name matches. Each rule comes from the party that cares about it: a slot's expected
shape (checked against the offering factory's published shape, at composition time), an action's claims (every
other action's, at composition time), a part's settings schema, a pack's host prerequisites (`itf doctor`), a
test's requirement (at collection), an action's own probe (right after it runs, and again before reuse and at
teardown) and a contract's conformance checks (in CI). The engine holds every party to its own word and to its
neighbours'.

## What this removes

- Separate provider, action, variant, member and node names: a part has one label and its role is chosen by the
  composition.
- Pack lists in test targets and in `pytest_plugins`: derived from labels.
- The namespace registry and the three identifier forms.
- Bench values keyed by member name.
- Mapping capabilities to packs: a composition lists factories, it does not fill slots.
- `@provides` and `@delivers`: replaced by `@capability` and `@state`.
- The recipe-era commands (`itf explain`, `itf migrate`, `itf init`) and the Bazel rules `itf_recipe` and
  `itf_bench`.

## Consequences

- A project that wants contracts of its own needs no registration, review or release: it names them, maps them,
  and adds definitions when it wants meaning, versions or conformance.
- A project action is always considered when planning. When it makes a state true that a pack's action also makes
  true, every composition that uses the state says which with `by:`.
- An override cannot remove a role; a different kind of target is a different composition (use `include:` for the
  shared part).
- The error for two actions making one state true is raised at composition time and names both, so the choice is
  never silent.

## Open questions

1. Whether a list form (`- ssh.exec`) is clearer when the same factory is used twice, or the role key is enough.
2. Whether a composition should name its goals, or default them to every state some action's probe can check.
3. How a project action can order itself relative to a pack's action without replacing it (a `relations:`
   section of the composition is being added for this).
