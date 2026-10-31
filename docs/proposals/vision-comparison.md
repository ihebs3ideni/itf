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

# Report: current implementation versus a platform built around OCTO

**Status:** Discussion material. Compares what the branch `ihsa_itf_facelift` delivers today with a
reimagined product built around OCTO's core idea, and weighs both. It proposes no immediate change.

## The two shapes in one paragraph each

**Current implementation.** ITF is a pytest framework with a planner inside. Packs publish capability
and state contracts; a recipe (a root `conftest.py`, YAML, or a Starlark target) chooses providers and
goals; OCTO resolves construction and action order before tests run; tests ask for contracts by token
and are gated by what the recipe provides. The pytest adapter owns the session: bring-up, startup
checks, teardown hooks and unwind. A SQLite catalog and a generated marketplace describe what packs
offer.

**Reimagined platform.** The bench is data and ITF is its compiler. Five artifacts are first-class:
versioned **contracts** with definitions and executable conformance suites; **packs** as separately
versioned modules that pass those suites; **recipes**, Starlark by default; **plans**, produced at build
time, cached and diffed in review; and **evidence**, a structured record of every run. Pytest is one
runtime among several: an interactive bench CLI (`itf up`, `itf shell`, `itf down`) and a daemon for
shared hardware consume the same plans. OCTO's extensible kinds add **resources** (exclusive hardware,
allocated by the planner) and **observations** (logs and captures wired before a test). Coverage and
bench selection are computed from plans before anything runs.

## Comparison by dimension

| Dimension | Current implementation | Reimagined platform |
|---|---|---|
| Contracts | A token plus the shapes providers publish; no definition of its own; the marketplace borrows a provider's description | Versioned definition (meaning, members, guarantees) with an owner and an executable conformance suite |
| Trust in a provider | Catalog conformance checks that some provider meets every declared expectation (member names) | Each provider passes the contract's behavioural conformance suite, against its sim variant in CI |
| Packs | Directories in one module, released together | Separate Bazel modules, versioned, declaring contract versions |
| Recipes | Python conftest, YAML, or Starlark (implemented, optional) | Starlark first; YAML as an interchange format |
| When a recipe is checked | At test time, or opt-in with `--itf-plan` and `plan_test` targets | At build time, always; plans are cached artifacts |
| Reviewing a change | Read the recipe and code | Also read the plan diff ("this adds a step before `platform.up`") |
| Runtime | The pytest adapter owns the session | Runner-agnostic core; pytest, a bench CLI and a bench daemon all consume plans |
| Working with a bench by hand | Not supported; write a test or drive `Session` from Python | `itf up`, `itf shell`, `itf down`, reusing whatever probes say already holds |
| Shared hardware | One session per test run | A daemon keeps a bench in a known state and serves several runs |
| Exclusive resources | Not modelled; conflicts appear at run time | A resources kind; the planner allocates and reports conflicts |
| Observing during a test | DLT and pcap as capabilities a test or recipe wires itself | An observations kind; wired by the planner, turned into evidence |
| Evidence | Run directory with plans, probe results and logs; failure report sections; teardown evidence in examples | An evidence store and viewer across runs: timings, flaky probes, drift |
| Coverage | Gating per run; a hand-written matrix in the integration README | A static matrix computed from plans: which tests run on which bench |
| Bench selection | The test target names its recipe | Match a suite against an inventory of benches described as recipes |
| Onboarding | README, how-to guides, catalog CLI (SQL-shaped), marketplace; no starter | Start path, starter benches, contract pages with conformance status, `itf explain` |
| Migration for existing users | A copyable legacy layer runs the original tests | The same, plus a longer road: more concepts to adopt |

## Current implementation

### Positives

- **It exists and works.** 8 reviewable commits; core, packs, examples, integration suite and docs; tests
  pass locally, with known environment limits listed in the status page.
- **Familiar to its users.** Pytest stays the entry point: fixtures, markers and reports behave as
  before, which lowers the cost of adoption for the S-CORE community.
- **Small conceptual surface.** Contracts, providers, recipes, two hooks for declarations and two for
  code. A newcomer can learn it in an afternoon once the docs lead them well.
- **A real migration path.** The legacy layer runs the original tests with only imports changed, and the
  breaking change is a single commit that can wait for a major release.
- **The hard parts are already right.** A pure planner, plan-time gating, probes as evidence, packs that
  cannot import each other, no domain words in the core, tracked processes, readable failure reports.
  Every step of the reimagination builds on these rather than replacing them.

### Negatives

- **Contracts are implicit.** Their meaning lives in provider code; consumers and reviewers have to infer
  it, and nothing checks behaviour, only member names.
- **Late feedback by default.** A wrong recipe is found when the test runs unless someone opts in to plan
  checks.
- **Tied to pytest in practice.** Capability packs are runner-agnostic, but the session, options and
  some packs (`core_dump`, `dlt_on_target`) are pytest-bound, and there is no way to use a bench
  without a test.
- **One release train.** Packs version with the core; a fix in one pack ships everything.
- **Shared benches and exclusive hardware are not modelled.** That is fine for containers and VMs and
  becomes a problem with real labs.
- **Discovery is weak.** See the onboarding proposal.

## Reimagined platform

### Positives

- **Contracts become a stable language.** Definitions plus conformance suites make "this provider
  implements that contract" a tested statement and make the marketplace trustworthy.
- **Errors move to build time.** Plans as build artifacts catch recipe mistakes before images are built
  or benches are booked, and plan diffs make bench changes reviewable.
- **Useful outside tests.** `itf up` gives developers a bench to work on; the same plan then runs the
  tests. That is daily value rather than CI-only value.
- **Scales to labs.** Resources, a bench daemon and bench matching address what breaks first with real
  hardware: contention and scheduling.
- **Better answers to management questions.** Static coverage and an evidence store answer "what is
  tested where" and "what is flaky" without running anything again.
- **Independent packs.** Versioned modules let packs move at their own pace and let projects pin them.

### Negatives

- **Much larger scope.** Contract versioning, conformance suites, a CLI, a daemon, an evidence store and
  two new kinds are each a project. Realistically this is a multi-quarter effort with clear owners.
- **More concepts.** Versions, conformance, resources, observations, runtimes: harder to learn and to
  explain, which works against the onboarding goal unless the start path hides them.
- **Versioning has a cost.** Contract and pack versions need compatibility rules, deprecation policy and
  release work; small teams often underestimate this.
- **Conformance suites are expensive to write well.** A weak suite gives false confidence; a strong one
  needs hardware-in-the-loop runs for real providers.
- **Operational burden.** A bench daemon and an evidence store are services someone must run, secure
  and upgrade.
- **More Bazel.** Starlark-first recipes and plans as build artifacts tie authoring more tightly to
  Bazel; projects that run ITF without Bazel get a worse experience.
- **Community buy-in.** Moving the centre of gravity away from pytest needs agreement from projects that
  are comfortable with the current model, and every new layer is review load.

## Risks of each path

| Path | Main risk | Mitigation |
|---|---|---|
| Stay with the current implementation | Contracts drift in meaning as packs multiply; labs outgrow the model | Do the onboarding proposal's first slice (contract definitions) regardless |
| Go straight to the reimagined platform | Scope stalls before anything ships; reviewers reject the size | Deliver it as increments that each stand alone, starting from the current branch |

## Recommendation

Land the current implementation first; it is the right foundation and its design choices are the ones
the platform needs. Then grow towards the platform in increments that each pay off on their own, in
this order:

1. **Contract definitions and conformance suites** (the onboarding proposal's first slice). Highest
   value for the least new machinery.
2. **Pack kinds and runner-agnostic packs.** Removes the pytest coupling that blocks other runtimes.
3. **`itf up` / `itf down`.** A thin CLI over the existing `Session`; immediate developer value.
4. **Plans as build artifacts** with plan diffs, extending the Starlark recipe work (once DR-003 is
   accepted).
5. **Evidence store, resources kind, bench matching**, when real labs need them.

Stop after any step if the cost outweighs the benefit: each step leaves ITF coherent and usable.

## Related

- [Status](status.md): what the branch delivers today.
- [Onboarding and contract discovery](onboarding.md): step 1 in detail.
- [DR-002](../decisions/DR-002-arch-composable-targets.md) and [DR-003](../decisions/DR-003-infra-starlark-recipes.md).
