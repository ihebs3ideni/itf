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

# DR-003-Infra: Starlark Recipes

**Date:** 2026-10-30
**Status:** Proposed; the recipe format it describes (`itf_recipe`) is replaced by compositions and `itf_target`, see
[DR-006](DR-006-target-composition.md). The decision that a build compiles the target description and fails early stands.

> This record follows the Decision Record convention established by the
> Eclipse S-CORE project:
> [eclipse-score/score — docs/design_decisions](https://github.com/eclipse-score/score/tree/main/docs/design_decisions).

## Overview

A test's **policy** is its root `conftest.py`. It implements up to four ITF hooks:

| Hook | Says | Nature |
|---|---|---|
| `itf_setup(ctx)` | what exists: nodes, providers, bindings, aliases | declarative |
| `itf_init(ctx)` | what must hold: goals, relations, assumptions | declarative |
| `itf_verify(session)` | readiness checks after bring-up | code |
| `itf_teardown(session)` | artifacts while the target still runs | code |

and may also define pytest fixtures and bench-local actions or providers (`@delivers`,
`@provides`), which are code too.

A **recipe** is the declarative half as data: it can stand in for `itf_setup` and `itf_init`, and
nothing else. Today a recipe is YAML that the conftest feeds to those two hooks
(`load_setup(ctx, path)` / `load_init(ctx, path)`). This record proposes writing recipes in
Starlark instead, as Bazel targets, while the code half of the policy stays in Python, in the
conftest, exactly as today.

## Problem Statement

Under Bazel, YAML recipes have three recurring problems:

1. **Built artifacts have no name in YAML.** An image, a kernel or a QEMU configuration is a Bazel
   label, but YAML only knows strings. Each path travels `$(location)` → `env` → `${NAME}` → node
   config: three places to keep in sync per artifact, and a typo surfaces at test time.
2. **Packs and recipe are declared apart.** The recipe names providers (`using: docker.exec`); the
   BUILD file separately lists the plugin targets publishing them. Nothing checks they agree until
   Gate 1 runs inside the test.
3. **A wrong recipe is found late.** Gate 1 and Gate 2 run at test time, after images are built and
   loaded, often on a bench. `--itf-plan` exists but is opt-in, per test.

Composition is limited too: `extends` merges documents, but cannot parameterise ("this bench, for
each of three images") without copying files.

## Proposal

### The recipe target

`@score_itf//bazel:recipe.bzl` provides `itf_recipe` and struct helpers. Bazel evaluates the
Starlark into the **existing recipe document** (the YAML schema, as JSON). The core needs no new
loader: `load_setup`/`load_init` already read JSON.

```starlark
load("@score_itf//bazel:recipe.bzl", "itf_recipe", "location", "node", "relation")

def container(image, load):
    return [
        node("platform", "itf.capabilities.platform.instance", using = "docker.instance",
             config = {"image": image, "bootstrap": location(load)}),   # a label, not a string
        node("command", "itf.capabilities.exec.command", using = "docker.exec"),
        node("process", "itf.capabilities.exec.process", using = "docker.process"),
    ]

itf_recipe(
    name = "dlt_bench",
    nodes = container("score_itf_examples:latest", "//test/resources:image_load") + [
        node("logs", "itf.capabilities.observe.logs", using = "dlt.stream"),
    ],
    goals = ["itf.states.logs.active"],
    relations = [relation("itf.states.logs.active", requires = ["bench.dlt_daemon.running"])],
    plugins = ["//score/itf/packs/docker", "//score/itf/packs/dlt"],
)
```

- `location(label)` puts the file's runfiles path in the config and the file in the test's
  runfiles: no `env`, no `${NAME}`. `${NAME}` still works for values that only exist at run time
  (a lab IP, a secret).
- `plugins` travel with the recipe: `py_itf_test(recipe = ...)` adds them, the document and the
  located files.
- Composition is Starlark: functions, loops, `load()`. `extends = [":base"]` merges documents with
  the YAML rules for reuse without code.

### How it meets the conftest

```starlark
py_itf_test(
    name = "bench",
    srcs = ["conftest.py", "test_bench.py"],   # conftest optional
    recipe = ":dlt_bench",
)
```

With `recipe =`, the test also loads a stock entrypoint, `score.itf.recipes.document`. It
implements `itf_setup` and `itf_init` only, feeding them the generated document. It registers like
any plugin, so the root conftest keeps every role it has today:

| The conftest... | Result |
|---|---|
| does not exist | the recipe is the whole policy |
| implements `itf_verify` / `itf_teardown`, fixtures, bench-local `@delivers` | they run beside the recipe; the recipe may name the bench-local actions' states in goals and relations |
| also implements `itf_setup` / `itf_init` | both contribute: the conftest adds nodes or goals, and where it declares the same node or state differently it **overrides** the recipe (the root conftest outranks every plugin; precedence is data, D-3) |
| loads the document itself (`load_setup(ctx, recipe_document())`) | the explicit form; the recipe then counts as the conftest's own declarations |

So "recipe replaces the first two hooks" holds without forcing anyone to give up Python where the
work is code. Nothing in the core changes: it already merges contributions from several modules
under origin precedence.

### Checking a recipe without hardware

`itf_recipe` also defines `<name>_plan`, a test that resolves both gates on the document with the
declared packs (`--itf-plan --itf-strict-shapes`: nothing constructed, nothing probed) and fails on
any diagnostic. `bazel test //...` checks every recipe hermetically, before an image is built or a
bench is touched. A conftest given as `conftest = "conftest.py"` joins the check, so bench-local
actions the recipe relies on are resolved too.

## Alternatives Considered

| Option | For | Against |
|---|---|---|
| **A. Analysis-time Starlark → JSON, beside the conftest (proposed)** | Labels in config; packs and data declared once; hermetic plan check; no runtime dependency; core unchanged; conftest keeps verify/teardown/fixtures | Requires Bazel; run-time values still via `${ENV}` |
| B. A runtime Starlark interpreter in ITF loading `.star` files like YAML | Works without Bazel | A native dependency in the core path; no labels or Bazel `load()`; a second dialect to document; no build-time check |
| C. YAML with label syntax resolved by the macro | Smallest change | A mini-language inside YAML; packs still declared apart |
| D. Starlark recipes that also carry verify/teardown | One file per bench | Starlark cannot run at test time: checks and artifact collection are code and belong in Python |

## Implementation Status

| Step | State |
|---|---|
| `bazel/recipe.bzl`: `node`, `scope`, `relation`, `assumption`, `state`, `location`; `itf_recipe` writing `<name>.itf.json`, `ItfRecipeInfo`, `<name>_plan` (`plan_test = False` for incomplete bases) | done |
| `score/itf/recipes/document.py`, `recipe_document()` in the core | done |
| `py_itf_test(recipe = ...)` | done |
| YAML `extends` accepting a generated parent by its working-directory path | done |
| Starlark twins: `docker_ssh_starlark` (same 19 tests selected as the YAML recipe), `dlt_stream_starlark` (extends a base; the image's `oci_load` given with `location()`; same 17 tests) | done |
| `//test/integration:recipe_equivalence_test`: the Starlark and YAML `docker_ssh` recipes make the same declarations | done |
| `bazel run //tools/catalog:query -- recipe <member|pack[:variant]>`: a node skeleton in Starlark and YAML | done |
| User guide and agent skill | done |

## Open Questions

- Should `itf_recipe` also accept a YAML `src` (YAML authored, locations resolved by Bazel)?
- Should recipes rank between packs and the conftest (a third origin), so a pack's own declarations
  can never clash with a recipe at equal rank? Today a clash between two plugins is a diagnostic,
  which is safe.
- Where do run-time values live: `${ENV}` as today, or a separate bench-binding document?
