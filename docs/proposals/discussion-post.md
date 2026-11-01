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

# Discussion post (draft)

**Title:** Proposal: compose ITF targets from packs and contracts instead of a Target class

**Summary.** ITF models a target as one class with fixed methods, subclassed per environment. I
propose composing targets from packs that publish capability and state contracts, wired by a recipe
and ordered by a small planner (OCTO); projects keep old tests running with a small legacy layer.

**Why.** (1) New devices fork a shared class. (2) Bring-up order is hard-coded per plugin.
(3) Tests duplicate intent per platform. (4) Mistakes show up after the VM is running.

**What it looks like.** A test:

```python
@itf.requires("itf.capabilities.exec.command")
def test_hello(target):
    assert target.command.exec("echo -n hi") == (0, "hi")
```

A recipe picks the provider (`docker.exec`, `ssh.exec`, `local.exec`); the same test runs on each.
In the prototype, one suite of capability-gated tests runs against a host, a container, a
container with SSH, DLT benches and QEMU machines, and each recipe selects the tests it supports.

**What about existing tests.** ITF drops the original plugins; projects keep old tests running with
a small legacy layer of their own (recipe + conftest + adapters over the new nodes). An example
layer runs ITF's original integration tests with only their imports changed.

**Cost.** New vocabulary (contracts, states, probes), a hermetic C/C++ toolchain addition, a
larger repository.

**Decision record:** DR-002 (architecture). **Roadmap and PR plan:** in `docs/proposals`.
**Prototype:** branch `ihsa_itf_facelift`, 8 commits.

**Questions for the community.** Should the example legacy layer live in ITF or elsewhere? Session-scoped bring-up as default? Packs as
separate Bazel modules? Where should `itf-core` live afterwards?
