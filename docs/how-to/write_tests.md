# Write tests

An ITF test has three parts: the **BUILD target** (which packs, which data), the **recipe** (the
root `conftest.py`: which nodes exist and which states must hold) and the **tests** (which
contracts they use).

## The recipe

Python hooks, or YAML loaded by them; both produce the same declarations.

```python
from score.itf.core import hookimpl

@hookimpl
def itf_setup(ctx):
    ctx.add("platform", "itf.capabilities.platform.instance", using="docker.instance",
            config={"image": "ubuntu:24.04"})
    ctx.add("command", "itf.capabilities.exec.command", using="docker.exec")

@hookimpl
def itf_init(ctx):
    ctx.goal("itf.states.platform.up")
```

YAML equivalent, loaded with `load_setup(ctx, path)` / `load_init(ctx, path)`:

```yaml
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

- `extends: [base.yaml]` derives a recipe from another, merging nodes by name.
- Node `config` values expand `${NAME}` and `${NAME:-default}`: pass Bazel-built paths with
  `py_itf_test(env = {"NAME": "$(location //label)"})`, secrets from the environment.
- Several devices: `ctx.scope("gw").add(...)` / `setup.scopes.gw.nodes`; tests use `target.gw.x`.
  Share a node with `alias` (`.name` is the root); a device never falls back to the root.
- Order follows from state relations, never from the order of lines: `init.relations` adds
  `requires`/`invalidates` to the action producing a state (e.g. open the console before the
  platform starts, to record the boot).
- `itf_verify(session)` runs readiness checks after bring-up (`session.check(name, ok)`);
  `itf_teardown(session)` collects artifacts while the target still runs.

## Starlark recipes

Under Bazel, a recipe can also be a target (DR-003). It stands in for `itf_setup`/`itf_init`; a
conftest in `srcs` keeps `itf_verify`, `itf_teardown`, fixtures and bench-local actions.

```starlark
load("@score_itf//bazel:recipe.bzl", "itf_recipe", "location", "node")

itf_recipe(
    name = "bench",
    nodes = [
        node("platform", "itf.capabilities.platform.instance", using = "docker.instance",
             config = {"image": "my_image:latest", "bootstrap": location("//images:load")}),
        node("command", "itf.capabilities.exec.command", using = "docker.exec"),
    ],
    goals = ["itf.states.platform.up"],
    plugins = ["@score_itf//score/itf/packs/docker"],
)

py_itf_test(name = "test", srcs = ["test_bench.py"], recipe = ":bench")
```

- `location(label)` puts a Bazel-built file's path in the config and the file in the runfiles.
- Composition is Starlark: put node lists in `.bzl` functions; `extends = [":base"]` merges
  recipes like YAML `extends` (`plan_test = False` on an incomplete base).
- Each recipe gets `<name>_plan`, a test resolving both gates without building or starting anything.
- `bazel run //tools/catalog:query -- recipe <provider>` prints a node skeleton.

## The tests

```python
import score.itf as itf

@itf.requires("itf.capabilities.exec.command")
def test_kernel(target):
    code, output = target.command.exec("uname -s")
    assert code == 0 and output.strip() == "Linux"
```

- `@itf.requires(token, scope=..., shape=[...])` selects a test only when the recipe provides the
  contract (and members); otherwise it is **deselected with a reason** before anything starts.
- `target.<node>` / `target.<scope>.<node>` return the objects; call only the members the catalog
  lists for the provider (`bazel run //tools/catalog:query -- sql "SELECT * FROM v_provider_api"`).
- Change state through the planner: `target.reach("itf.states.shell.open")` re-establishes what an
  action (e.g. `target.platform.restart()`) invalidated; `target.renew("platform")` rebuilds a node
  and everything bound to it, then reaches the goals again.
- Per-test isolation is a fixture you own, at the scope you choose:

  ```python
  @pytest.fixture(autouse=True)
  def fresh_container(target):
      target.renew("platform")
  ```

- Asynchronous processes: `WrappedProcess(target.process, "/usr/bin/app", wait_on_exit=True)`
  from `score.itf.core.process`, for any `itf.capabilities.exec.process` provider.

## The BUILD target

```starlark
py_itf_test(
    name = "bench",
    srcs = ["conftest.py", "test_bench.py"],
    data = ["recipe.yaml"],
    plugins = ["@score_itf//score/itf/packs/docker"],   # the packs the recipe's providers come from
    env = {...},
)
```

`--test_arg=--itf-plan` resolves and prints the plan and gating without constructing anything;
`--test_arg=--itf-strict-gating` fails deselected tests instead.
