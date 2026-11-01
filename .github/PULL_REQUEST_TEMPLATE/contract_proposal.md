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

<!-- Use this template for a pull request that adds or changes a contract definition ITF supports (in a pack's
     `contracts/` directory). ITF knows no contracts: any name works without a definition. Definitions are the
     supported set the ITF team maintains, with conformance checks. Guide: docs/how-to/contracts.md. -->

## Contract

Name: `<area>.<name>`  (a capability contract, fulfilled by capability factories, or a state contract, made true by actions)
Suggested role: `<one lowercase word>`  (capabilities only: the role compositions give it, `target.<role>`)
Version: 1
Stability: experimental

## Problem

What can a test not do today, or not do portably? Name the targets and the tests that need it. Say why
an existing contract does not cover it.

## Definition

- [ ] `score/itf/packs/<pack>/contracts/<area>.yaml` has the definition: summary, description, members with
      signature and semantics, guarantees, `see_also`, `conformance`. Block style only.
- [ ] Every member is required unless a real factory cannot offer it; optional members say how a test
      gates on them (`shape=`).
- [ ] The text says what a test must not rely on.
- [ ] `itf contracts map` shows no disagreement for the name, and `itf contracts check --policy tools/contracts_policy.yaml`
      exits 0 (add the new namespace to the policy if it has one).
- [ ] `bazel run //score/itf/cli:itf -- contracts map --format html --output docs/_generated/catalog.html` and
      `bazel run //score/itf/cli:itf -- contracts reference --output docs/reference/contracts.md` were run.

## Conformance checks

Which checks in the pack's `conformance_<area>.py` hold a factory to each guarantee? List them, or
say why a guarantee cannot be checked. `itf contracts check --policy <file> --targets <composition> --conformance`
runs them against a composition.

## Capability factories and actions

A contract needs both, in this pull request or linked:

- [ ] At least one **real** capability factory (hardware, a daemon, a real service) or action: its label.
- [ ] At least one **simulation** that behaves like the device, not a stub that accepts calls: its label.
- [ ] Both pass the conformance checks (`bazel test //test/integration:conformance_...`).
- [ ] Each declares the contract it keeps (`@capability("<area>.<name>@1")`, `@state("<area>.<name>")`).

## Owners

Who maintains the definition and answers questions about it? Name at least two people or a team.

## Versioning

- [ ] New contract, or: this change adds an optional member only (the major stays).
- [ ] A removal, a required member added, or a changed meaning is a new major and is explained here.
- [ ] A contract this replaces is marked `deprecated` with `replaced_by`.
