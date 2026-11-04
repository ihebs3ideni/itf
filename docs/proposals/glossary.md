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

# Glossary

Every word has one meaning. The proposal, its decision record, the code, the error messages and the
documentation on the implementation branch use these words and no others.

## The words

| Word | Meaning | Example |
|---|---|---|
| **target** | What ITF builds for tests to use: the system under test with everything needed to reach it. Described by a target file, compiled by `itf_target`, used as `target.<role>` in a test and `session.target` in Python | `target.command` |
| **target file** | The `*.itf.yaml` document that describes a target: roles, settings, goals and orderings, with its includes and override files | `target.itf.yaml` |
| **composition** | How ITF builds a target: by composing it from parts. The name of the mechanism, never of a file or a rule | "target composition" |
| **part** | A capability factory or an action: one piece of code that a pack or a project contributes | `docker.exec`, `ssh.open` |
| **capability factory** (factory) | A part that builds something a test uses. Declared with `@capability("<contract>")` | `docker.exec`, `ssh.shell` |
| **action** | A part that makes a state true, with a probe that checks it. Declared with `@state("<state>", ...)` | `docker.start`, `ssh.open` |
| **contract** | Any name that parts agree on, optionally with a version, a shape, a meaning and conformance checks | `exec.command`, `acme/power.relay@1` |
| **capability contract** | A contract fulfilled by a factory: something a test uses | `exec.command` |
| **state contract** | A contract fulfilled by an action: a condition that can be made true and checked | `platform.up` |
| **state** | The name of a condition. `@state` is only the decorator that declares an action | `shell.open` |
| **goal** | A state listed under `goals:`: what must be true once the target is up | `platform.up` |
| **slot** | A parameter of a part: what the part needs, annotated with the part's own Protocol, which carries `__contract__` | `platform: Platform` |
| **shape** | The list of members a factory publishes, or a slot expects. Compared as data | `exec`, `run` |
| **role** | A key under `capabilities:`: the name a placed factory answers to | `command` |
| **label** | The name of a part: `<pack>.<name>`, or `local.<name>` for a part in the project's policy | `docker.exec`, `local.start_daemon` |
| **pack** | A directory with a `pack.yaml` and its parts. The name `local` is reserved for the policy | `docker`, `ssh`, `localhost` |
| **policy** | `policy.py` beside the target file: the project's own ITF code (`itf_verify`, `itf_teardown`, its own parts). ITF loads it, not pytest; it outranks the target file and the packs | `local.start_daemon` |
| **contract rules** | A project's rules over contracts, enforced by `itf contracts check --rules rules.yaml` | `rules.yaml` |
| **scope** | One device of a multi-device target; its roles are `target.<scope>.<role>` | `gw` |
| **override file** | A target file that holds only what changes, merged by role over another | `override.itf.yaml` |
| **assumption** | A state that holds without ITF, listed under `assume:` with an owner and a reason | `platform.up` on a lab board |
| **relation** | An ordering between states that a target file adds under `relations:` | `shell.open` after `platform.up` |
| **plan** | What OCTO resolves from a target file: which factory fills which role, and which actions run in which order | `itf plan` |
| **gate** | One of the two checks that produce a plan. Gate 1 decides what must exist; gate 2 decides what must happen | "plan failed at gate 2" |
| **probe** | A check that says whether a state holds now. It never changes anything | `@open_session.probe` |
| **contract map** | The generated page, and the command `itf contracts map`, listing every contract in use: who offers it, who needs it, which tests ask for it | `catalog.html` |
| **OCTO** | Open Contract Topology Orchestration: the planner that reads part declarations and produces a plan | |
| **ITF** | The product: this framework | |

## Words not used, and what replaces them

These appear in today's ITF or in the implementation branch's history. Reviewers who know those will meet them.

| Not used | Use instead | Why |
|---|---|---|
| `Target` class | the target (`target.<role>`) | The target is composed, not a class |
| plugin (for a provider of target code) | pack | "Plugin" stays only for pytest plugins and the Bazel rule `py_itf_plugin` |
| provider | capability factory | One word for one thing; "provider" also means a Bazel provider |
| node | role (in user text) | "Node" stays inside OCTO's own code |
| recipe; composition file | target file | One word for the file, named after what it describes |
| bench values, bench file | override file | One structure for every kind of change |
| member name | role | Roles are chosen by the target file, not by the contract |
| conftest (for ITF code) | policy (`policy.py`) | A conftest is pytest's, for fixtures; ITF loads the policy itself |
| `project.<name>` | `local.<name>` | Read as "defined here"; reserved, so no pack can shadow it |
| the `local` pack | `localhost` | It is the test host; `local` now means the project's policy |
| contract policy | contract rules | "Policy" is the project's code layer |
| catalog, marketplace | contract map | It maps; it does not sell or register |
| the platform (as a product name) | ITF | "Platform" is a factory's contract (`platform.instance`) |
