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

# Pull request plan

The implementation is a series of 8 commits on top of `main` (branch `ihsa_itf_facelift`). Each
commit builds; the final tree passes the full local test run. Proposed PRs, in merge order, one
concern each:

| PR | Commit | Reviewers should check | Size |
|---|---|---|---|
| 1. Build | `build: hermetic C/C++ toolchain and new third-party dependencies` | Toolchain choice, glibc target, new locked requirements | small |
| 2. Core | `feat(core): ITF core with the OCTO planner` | API surface, gates (OCTO has no dependencies, core has no domain words), `renew`, per-state probes | large, mostly moved code with its tests |
| 3. Packs | `feat(packs): docker, qemu, ssh, ...` | Contracts, config schemas, topic-module layout, catalog conformance | large; may split per pack |
| 4. Examples | `examples: recipes and contracts; a legacy infra project ...` | The legacy layer covers the original tests; examples module builds | medium |
| 5. Removal | `feat!: ship the core and packs only; remove the original plugins and Target` | Breaking change; migration guide; release notes | medium (deletions) |
| 6. Tests | `test(integration): one capability-gated suite ...` | Gating decisions per recipe (README matrix), recipes | medium |
| 7. Starlark | `feat(bazel): Starlark recipes (DR-003)` | Implemented and tested; optional, so it can be deferred until DR-003 is accepted | small |
| 8. Docs | `docs: packs, recipes and contracts ...` | Accuracy against code; migration guide | medium |

Notes for reviewers:

- PR 2 is mostly code carried over from the `itf-core` prototype and ITF's own process and
  utility modules; the diff to read is the registry (pack-aware contributor identity), `renew`,
  per-state probes, and the adapter.
- PRs 1 to 4 add without breaking anything; PR 5 is the breaking change and should land in a
  major release, after projects have copied the legacy layer.

## Verification before opening each PR

```bash
bazel build //...
bazel test //test/core/... //test/packs/...
bazel test //test/integration/...          # needs Docker
(cd examples && bazel test //...)          # examples and the legacy layer
bazel run //:format.check
```
