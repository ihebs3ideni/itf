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

# Risks, verification and FAQ

## How the implementation was verified

Measured on the implementation branch `ihsa_itf_platform` on 2026-11-03. Container tests ran under rootless
Podman.

| Check | Result |
|---|---|
| `bazel build //...` | passes |
| `bazel test //test/...` and the format checks | 28 of 28 test targets pass |
| Copyright check | passes |
| Examples (`bazel test //...` in `examples/`) | 20 of 21 pass. Legacy `test_dlt` fails because rootless Podman does not route multicast; it is unchanged from `main` |
| Every commit of the series | passes Bazel analysis (`bazel build --nobuild //...`) |
| Line coverage of `score/itf` by unit tests alone (no containers) | 81%. Pack code that only container and QEMU tests reach is not counted here |
| Functions with cyclomatic complexity of 11 or more | 21, down from 63 during the cleanup. The highest is the SSH client's read loop (34) |
| Generated pages (contract map, contracts reference) | compared with the packs by a test |
| QEMU | **not run** for this verification |
| Mutation testing | **not run** |

## Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Size of the change | Reviewers cannot read 40,000 lines with equal care | The [pull request plan](roadmap.md) cuts it into eight reviewable steps; OCTO (2,500 lines, standard library only) can be reviewed alone |
| Breaking change for every project | Existing tests stop working when the original plugins are removed | The facade example keeps them running with only imports changed; removal is its own pull request, after the facade lands |
| New words | A larger first lesson for test authors | One [glossary](glossary.md); a test author needs three words (role, `@itf.requires`, `target.<role>`); starters and a tutorial |
| Orderings move to target files | A target file that forgets a relation opens SSH before the platform is up | The probe fails with the evidence; the starters show the common relations; `itf graph` shows the order before any run |
| Pack code with low unit coverage | Defects in container and SSH paths are found only by integration tests | Integration compositions run in CI on every change; conformance checks per contract |
| The `sim` pack does not pass the conformance checks of its contracts | A test can pass on a simulation and fail on a real target | [Open decision](open-decisions.md) 4: make the simulations conform and run their checks in CI |
| Detached targets only for `local` and `sim` | `itf up --detach` is refused for containers and QEMU | [Open decision](open-decisions.md) 3 |
| Python 3.14 | `pydantic==2.10.6` has no wheel for 3.14 | [Open decision](open-decisions.md) 10 |

## FAQ

**Do test authors have to learn OCTO?**
No. A test author writes `@itf.requires("command")` and uses `target.command`. OCTO matters to people who write
target files and packs, and its errors name the parts involved and the line to write.

**Is pytest still the runner?**
Yes. The pytest adapter builds the target, deselects tests whose requirements are not met, and gives each test
`target`. The command line and plain Python use the same session.

**Does it need Bazel?**
No. `pytest --itf-target=target.itf.yaml`, `ITF_TARGET`, `itf_target` in `pytest.ini` or `[tool.itf] target`
in `pyproject.toml` work without Bazel. Under Bazel, `itf_target` adds a compile step that fails the build on
a target file that does not compile.

**Why is the file keyed by role and not by part?**
The same part can be used twice (two consoles), and tests and override files need a stable name. Docker Compose
makes the same choice.

**Why does ITF not define the contracts?**
ITF cannot know every project's devices. A contract is any name two parts agree on. ITF maintains the contracts
its own packs use, with definitions and conformance checks, and gives projects tools to map, define and enforce
their own.

**What about hardware shared between pipelines?**
Out of scope. Exclusive use of a board inside one plan is a separate proposal; scheduling between pipelines
belongs to the CI system.

**How does a project with its own `Target` subclass migrate?**
It writes a pack, or parts in its policy (`policy.py` beside its target file): one factory per capability, one
action with a probe per setup step. See the [migration guide](migration.md).

**What happens to itf-core?**
The planner and engine move into ITF. Where the itf-core repository goes afterwards is open decision 11.

**Why "target file" and not "composition"?**
A test gets a target: the system under test and the means to reach it. The file describes that target and the
Bazel rule compiles it, so both are named after it. "Composition" names how ITF builds a target from parts.
