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

# Get started

New to ITF? Read [Start here](start_here.md) and follow the [tutorial](tutorial.md) first. This page shows the
smallest real test, file by file.

## Add ITF

```starlark
# MODULE.bazel
bazel_dep(name = "score_itf", version = "...")
```

```
# .bazelrc
common --registry=https://raw.githubusercontent.com/eclipse-score/bazel_registry/main/
common --registry=https://bcr.bazel.build
```

## A first test

```yaml
# target.itf.yaml: what the target is made of
capabilities:
  platform:
    factory: docker.platform
    with:
      image: ubuntu:24.04
  command: docker.exec
goals:
  - platform.up
```

```python
# test_hello.py
import score.itf as itf

@itf.requires("command")
def test_hello(target):
    assert target.command.exec("echo -n 'Hello from target!'") == (0, "Hello from target!")
```

```starlark
# BUILD
load("@score_itf//:defs.bzl", "itf_target", "py_itf_test")

itf_target(
    name = "target",
    src = "target.itf.yaml",
    packs = ["@score_itf//score/itf/packs/docker"],
)

py_itf_test(
    name = "test_hello",
    srcs = ["test_hello.py"],
    target = ":target",
)
```

`platform`, `command` are roles. `docker.platform` and `docker.exec` are factory labels: `<pack>.<name>`, and the
pack is where they come from. `platform.up` is the goal: the state the target must reach. The test asks for a role,
and gets `target.command`.

```bash
bazel build :target                       # compile the composition: target.plan.json; nothing runs
bazel test :test_hello --test_arg=--itf-plan --test_output=all    # the plan and the gating
bazel test :test_hello
```

Without Bazel, name the composition in `pytest.ini` (`itf_target = target.itf.yaml`), in `pyproject.toml`
(`[tool.itf]` with `target = "target.itf.yaml"`), with `ITF_TARGET`, or per run with
`pytest --itf-target target.itf.yaml`. A conftest is only for code (`itf_verify`, `itf_teardown`, fixtures,
the project's own parts), and this test needs none.

## Add readiness and evidence: the conftest

```python
# conftest.py
from score.itf.core import hookimpl

@hookimpl
def itf_verify(session):
    """Checked once after bring-up: a target that cannot answer fails here, with a named check."""
    code, output = session.target.command.exec("echo -n ready")
    session.check("command.answers", code == 0 and output.strip() == "ready", detail=f"exit {code}")

@hookimpl
def itf_teardown(session):
    """Collect evidence while the target still runs, before it is unwound."""
```

Put `conftest.py` in the test's `srcs` and in the `itf_target`'s `srcs`, so the project's own parts take part in
the plan.

## Test properties in the JUnit report

Add score_tooling's `attribute_plugin` to the `plugins` list and decorate tests with `@add_test_properties(...)`:

```starlark
py_itf_test(
    name = "test_hello",
    srcs = ["test_hello.py"],
    plugins = ["@score_itf//:attribute_plugin"],
    target = ":target",
)
```

## Next

- **Choose a starter**: [Start here](start_here.md).
- **Write tests**: [Write tests](write_tests.md): compositions, overrides, devices, gating, reach and renew.
- **Learn the words**: [the model](../concepts/model.md).
- **Find factories**: each pack's README has its label table; [the pack reference](../reference/plugins.rst).
- **Write a pack**: [Write a pack](plugins.md).
