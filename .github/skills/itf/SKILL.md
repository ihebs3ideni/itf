---
name: itf
description: 'Compose and test targets with ITF (score_itf): write a composition (`*.itf.yaml`, roles, factories, goals, overrides), pytest tests that require roles, `itf_target` and `py_itf_test(target = ...)` in Bazel, and the project''s own parts (`@capability`, `@state`). Use when: asked what ITF can do on a target; writing or reviewing a composition, override file, conftest, BUILD itf_target/py_itf_test or ITF test; "which factory gives X"; migrating a legacy ITF test (target.execute, docker_plugin) or a recipe; writing a pack; defining, mapping or enforcing a contract (`itf contracts map|new|check`); choosing a starter; validating, graphing, bringing up or tearing down a target (`itf validate|plan|graph|up|down|test`).'
argument-hint: 'A requirement, a role or factory label, a state, a contract name, or "how do I ..."'
---

# ITF: compose a target from self-describing parts, test by role

ITF is a platform to compose test targets from parts that describe themselves. OCTO plans from those
descriptions, and only those, before anything exists. Nothing is trusted on its name. Use these words and no
others (full text: `docs/concepts/model.md`):

| Word | What it is | Example |
|---|---|---|
| capability contract | a name for what a test uses; fulfilled by a capability factory | `exec.command` |
| state contract | a name for a condition; fulfilled by an action with a probe | `platform.up` |
| factory | `@capability("exec.command")`; label `<pack>.<function>` | `docker.exec`, `ssh.shell` |
| action | `@state("platform.up", after=..., breaks=...)` with `@<action>.probe` | `docker.start` |
| composition | a target: roles, settings, goals; a `*.itf.yaml` file | `target.itf.yaml` |
| role | the key of a composition's `capabilities:`; `target.<role>` | `command` |
| scope | one device of a multi-device target | `gw` |

A part outside any pack is `project.<name>`. An override file is a composition holding only what changes (the
values of one bench), merged by role.

**ITF knows no contracts.** A contract is whatever name two parts agree on. Definitions are optional. ITF
provides discovery (`itf contracts map`), skeletons (`itf contracts new --from-usage`) and enforcement
(`itf contracts check --policy`). The ITF team's contracts are a supported set, not a standard.

**Everything is explicit, nothing is required.** Goals are listed, not inferred; no part enters a target unless
listed; an empty composition is valid.

**Contract rule:** nothing imports a pack. Consumers write their *own* Protocols (a class with
`__contract__ = "<contract>"` and only the members they use); the planner checks at each seam that the
offering shape covers them.

## 0. Start from a starter

`examples/examples/starter/{container,ssh,serial}`: each has `target.itf.yaml` (with `# CHANGE:` marks),
`bench.itf.yaml` (an override file), a conftest (`itf_verify`, `itf_teardown`), one test and a `BUILD` with
`itf_target` and `py_itf_test(target = ...)`. Copy the closest, change the marks. Other examples:
`exec_everywhere` (one test file, four compositions), `itf` (docker, dlt, qemu), `vendor_contract` (a vendor's
own contract), `plain_python`, `legacy` (a facade over the original API).

## 1. The lifecycle

| Command | Does | Hardware |
|---|---|---|
| `itf validate [target.itf.yaml] [--override f]` | every metadata rule | no |
| `itf plan` | the plan, readable; `--json` | no |
| `itf graph` | roles, wiring and bring-up sequence, Mermaid | no |
| `itf up [--detach]` / `itf down` | bring up and verify / unwind from observed state | yes |
| `itf test` | run the tests against the composition | yes |
| `itf doctor` | host prerequisites of the packs | reads |
| `itf contracts map` / `new <name> --from-usage` / `check --policy p.yaml` | discover, scaffold, enforce | no |

Under Bazel `itf` is `bazel run @score_itf//score/itf/cli:itf --`; run it in the folder with the composition
and the conftest. `bazel build //pkg:<itf_target>` compiles a composition and writes `<name>.plan.json`: a wrong
composition fails the build with rendered diagnostics. Prefer `validate`, `plan` and `graph` to explore; use `up`
only when the user asks for a live target, never on real hardware to "check".

## 2. Write a composition

```yaml
capabilities:
  platform:
    factory: docker.platform
    with:
      image: ubuntu:24.04
  command: docker.exec          # short form: just the factory
goals:
  - platform.up
```

Wiring comes from what factories need (one candidate: bound; several: `bind:`). A state two listed packs could
make true needs `by:` (the compiler names both). Details: `references/yaml.md`. Swapping is changing one label:
`command: docker.exec` becomes `command: ssh.exec`; the test does not change.

Which composition a run uses is configuration, never conftest code: `--itf-target`, `ITF_TARGET`, `itf_target`
in `pytest.ini`, `[tool.itf] target`, or `py_itf_test(target = ...)` (overrides: `--itf-override`, `ITF_OVERRIDE`,
`itf_override`, `[tool.itf] override`, `itf_target(overrides = [...])`).

## 3. Write tests

```python
import score.itf as itf

@itf.requires("command", contract="exec.command", shape=["exec"])
def test_hello(target):
    assert target.command.exec("echo -n hi") == (0, "hi")
```

`@itf.requires(role, contract=..., shape=[...], scope=...)`: a target without the role (or contract, or
members) deselects the test with the reason. Use only members the contract's shape lists. Change state with
`session.reach("shell.open")` and `session.renew("platform")`. Readiness and evidence are conftest hooks
(`itf_verify(session)` with `session.check(name, ok)`, `itf_teardown(session)`). Details: `references/authoring.md`.

## 4. Project parts, contracts, packs

- A factory or action written in the root conftest is `project.<function>`. A project action is always
  considered: if it makes a state true that a pack's action also makes true, compositions need `by:`.
- Define a contract only when it adds something: `itf contracts new <name> --from-usage`, then fill the
  `TODO`s; add `conformance:` for a checks module. Enforce conventions with `itf contracts check --policy`
  (rules: `namespaces`, `roles`, `forbid_stability`). Example: `examples/examples/vendor_contract`.
- A pack is a directory with `pack.yaml` (`name`, `version`, `prerequisites`), `providers.py` (`@capability`),
  `steps.py` (`@state`), `plugin.py`; loaded from labels (`score.itf.packs.<name>.plugin` or the entry point
  `score_itf.packs`). Each pack README has its label table. See `docs/how-to/plugins.md`.

## 5. Bazel

```starlark
load("@score_itf//:defs.bzl", "itf_target", "py_itf_test")

itf_target(name = "ecu", src = "ecu.itf.yaml", packs = ["@score_itf//score/itf/packs/docker"], srcs = ["conftest.py"])
py_itf_test(name = "smoke", srcs = ["conftest.py", "test_smoke.py"], target = ":ecu")
```

`itf_target(name, src, overrides, packs, data, srcs, contracts, env, files)`: `packs` are the packs the factory
labels may name (another pack fails the build), `srcs` the conftest so project parts take part in the plan, `files`
the built files the composition names as `${NAME}` (`{"ITF_IMAGE_LOAD": "//images:load"}`) and `env` its other
`${NAME}` values. Tests (`py_itf_test(target = ...)`) inherit both: never add `data`/`$(location)` for them. Container tests need `DOCKER_HOST` passed with `--test_env`.

## 6. Without pytest, and legacy

`from score.itf import Session; s = Session(target="x.itf.yaml"); s.resolve(); s.bring_up(); s.target.command...;
s.close()`. A facade keeps an old API (`examples/examples/legacy`, `docs/how-to/migrate.md`).

## Checklist before answering

1. Roles named as the project's convention; labels `<pack>.<name>` that exist (read the pack README).
2. `itf validate` (or the `itf_target` build) passes; read `itf graph` for the order.
3. Tests ask for roles, not machines; no pack imports; YAML in block style.
4. New contract names: run `itf contracts map`; no disagreements.
