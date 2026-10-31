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

# Roadmap: composable targets in ITF

Each phase is independently shippable and leaves ITF working. Phases 1 to 4 correspond to the PR
series in the [PR plan](pr-plan.md). Dates are deliberately absent: they depend on review capacity.

| Phase | Outcome | Exit criteria |
|---|---|---|
| 0. Discussion | Community agrees on direction (DR-002) | DR-002 accepted or amended; open questions answered |
| 1. Foundation | Hermetic toolchain, core and OCTO in the repo, original API untouched | `bazel test //test/core/...` green; no behaviour change for existing users |
| 2. Packs | Docker, QEMU, SSH, DLT, ping, pcap, serial, local, core_dump as packs, with catalog | `test/packs` and sim bench green; catalog conformance test green |
| 3. Compatibility | Examples and a copyable legacy layer; then the original plugins leave ITF | `examples/legacy` runs ITF's original tests; ITF tests green without them |
| 4. New-style tests | One capability-gated suite across recipes; examples; docs; agent skill | Each recipe selects the documented tests; migration guide reviewed |
| 4b. Starlark recipes (optional) | Recipes as Bazel targets with hermetic plan checks ([DR-003](../decisions/DR-003-infra-starlark-recipes.md)) | Implemented as a prototype (`bazel/recipe.bzl`, two integration targets, equivalence test). To do: DR-003 accepted, examples ported, one downstream trial |
| 5. Adoption | Downstream projects migrate; feedback fed back to packs | At least two downstream suites on the new API |
| 6. Legacy layers retired | Projects migrate their old tests and delete their layers | No downstream project depends on `examples/legacy` |

Current state of each phase: see [Status](status.md). Phases 1 to 4 are implemented on `ihsa_itf_facelift`;
phases 0, 5 and 6 depend on the community and downstream projects.

## Candidate follow-ups (not committed)

- Packs as separate Bazel modules with their own versions.
- Opt-in per-test target lifetime in the adapter, if fixtures calling `renew` prove insufficient.
- Project test kit: a runnable container/native bundle for suppliers (itf-core design note 11.3).
- Pack kinds: separate capability packs from policy packs and pytest plugins, enforced by a gate and shown in the catalog.
- Onboarding and contract discovery: contract definitions, a contracts reference, starter templates and a tutorial ([proposal](onboarding.md)).
- ITF with and without Bazel: core and packs as wheels, entry-point discovery, `[tool.itf]` configuration ([plan](packaging.md)).
- Exclusive hardware in a plan: providers mark held config fields, conflicting nodes are rejected at plan time ([proposal](exclusive-hardware.md)).
- ITF as target composition, OCTO first: parts, compositions, no-trust checks, a lifecycle CLI ([proposal](composition.md)).
- The ITF model: member names owned by contracts, packs and variants instead of provider names, recipe and bench values, a single source of truth per fact ([proposal](model.md)).
- More packs: CAN, DoIP, UDS, power supplies, network management (itf-core has designs and code).
- Remote resource reservation for shared benches.

## What would change the plan

- Reviewers prefer smaller steps: split phase 2 per pack (the PR plan already orders them by
  dependency).
- The zig-based toolchain is unacceptable: phase 1 becomes a host-toolchain requirement or a
  separate opt-in config, and the packs that build C code (dlt, pcap) become optional.
- Projects need more of the original API than the example layer covers: extend `examples/legacy`, never ITF.
