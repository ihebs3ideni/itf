# Get started

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
# recipe.yaml
setup:
  nodes:
    - name: platform
      contract: itf.capabilities.platform.instance
      using: docker.instance
      config:
        image: ubuntu:24.04
    - name: command
      contract: itf.capabilities.exec.command
      using: docker.exec
init:
  goals:
    - itf.states.platform.up
```

```python
# conftest.py: the recipe
from pathlib import Path
from score.itf.core import hookimpl, load_init, load_setup

RECIPE = Path(__file__).with_name("recipe.yaml")

@hookimpl
def itf_setup(ctx):
    load_setup(ctx, RECIPE)

@hookimpl
def itf_init(ctx):
    load_init(ctx, RECIPE)
```

```python
# test_hello.py
import score.itf as itf

@itf.requires("itf.capabilities.exec.command")
def test_hello(target):
    assert target.command.exec("echo -n 'Hello from target!'") == (0, "Hello from target!")
```

```starlark
# BUILD
load("@score_itf//:defs.bzl", "py_itf_test")

py_itf_test(
    name = "test_hello",
    srcs = ["conftest.py", "test_hello.py"],
    data = ["recipe.yaml"],
    plugins = ["@score_itf//score/itf/packs/docker"],
)
```

```bash
bazel test //:test_hello --test_arg=--itf-plan --test_output=all   # see the plan; nothing runs
bazel test //:test_hello
```

## Test properties in the JUnit report

Add score_tooling's `attribute_plugin` to the `plugins` list and decorate tests with
`@add_test_properties(...)`:

```starlark
py_itf_test(
    name = "test_hello",
    srcs = ["conftest.py", "test_hello.py"],
    data = ["recipe.yaml"],
    plugins = [
        "@score_itf//score/itf/packs/docker",
        "@score_itf//:attribute_plugin",
    ],
)
```

## Next

- **Write tests**: [Write tests](write_tests.md): recipes, YAML, devices, gating, reach and renew.
- **Find capabilities**: `bazel run //tools/catalog:query -- search "<what you need>"`.
- **Write a pack**: [Write a pack](plugins.md).
