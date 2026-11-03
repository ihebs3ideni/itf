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

# Discussion post

Text for the Eclipse S-CORE discussion that opens the review.

---

**Title:** Proposal: ITF builds test targets from self-describing parts (target composition)

**Summary.** Today an ITF target is a `Target` class with one subclass and one pytest plugin per environment. I
propose that ITF builds the target, meaning the system under test and everything needed to reach it, from parts
listed in a target file. A small planner, OCTO, checks the parts against each other and plans bring-up before
anything starts. Tests ask for what they need and run on every target that has it.

**Why.**
1. A new device means a new `Target` subclass.
2. Bring-up order is code inside each plugin.
3. Tests are written per environment and fail at run time elsewhere.
4. Mistakes show up after a container or VM has started.
5. A target cannot be validated, drawn or brought up without running tests.

**What it looks like.**

```python
@itf.requires("command")
def test_hello(target):
    assert target.command.exec("echo -n hi") == (0, "hi")
```

```yaml
# target.itf.yaml
capabilities:
  platform:
    factory: docker.platform
    with:
      image: ubuntu:24.04
  command: docker.exec
goals:
  - platform.up
```

```starlark
itf_target(name = "target", src = "target.itf.yaml", packs = ["@score_itf//score/itf/packs/docker"])
py_itf_test(name = "test_hello", srcs = ["test_hello.py"], target = ":target")
```

Changing `command: docker.exec` to `ssh.exec` or `localhost.exec` moves the same test to another target. A target
file that does not fit together fails `bazel build`. `itf up` and `itf down` bring a target up from a terminal.

**Existing tests.** ITF drops the original plugins. A facade example runs ITF's original integration tests with
only their imports changed; projects copy it and migrate tests one at a time.

**Cost.** About 40,000 added lines (a quarter of them tests), new words (one glossary page), a hermetic C/C++
toolchain, and a breaking change softened by the facade.

**Read.**
- RFC: `docs/proposals/rfc.md`
- Decision record: `docs/decisions/DR-002-arch-target-composition.md`
- Architecture, glossary, rationale, migration guide, roadmap, risks and FAQ: `docs/proposals/`
- Implementation: branch `ihsa_itf_platform`

**Questions for the community** (details in `docs/proposals/open-decisions.md`):
1. Land the change as eight re-cut pull requests showing only the final design?
2. Which contracts that ITF's packs use should be `stable` in the first release?
3. Should the legacy facade live in ITF as an example for one release?
4. Docker detach by container labels now, QEMU later?
5. Archive itf-core, or keep it as OCTO's standalone home?
