---
name: itf
description: 'Discover and use ITF (score_itf): find what packs provide (capabilities, states, providers, actions) in the SQLite pack catalog, then write a recipe (Python hooks or YAML) and pytest tests, run them with Bazel, or drive ITF from plain Python. Use when: asked what ITF can do on a target/bench; "which pack/provider gives X"; writing or reviewing a recipe, conftest, YAML, BUILD py_itf_test or ITF test; migrating a legacy ITF test (target.execute, docker_plugin); writing a new pack; checking whether a requirement is coverable or needs a new pack.'
argument-hint: 'A requirement, a capability/state token, a pack, or "how do I ..."'
---

# ITF: discover with the catalog, compose with a recipe, test by contract

ITF builds a test target from **packs**. A pack publishes:

| Thing | Form | Example |
|---|---|---|
| capability (contract) | `itf.capabilities.<area>.<name>` | `itf.capabilities.exec.command`: something a test holds |
| provider | short name, chosen with `using:` | `docker.exec`, `ssh.exec`: implementations of that capability |
| member | what a test may call on a node | `exec(command, timeout) -> tuple[int, str]` |
| state | `itf.states.<area>.<name>` | `itf.states.shell.open`: a condition that can hold |
| action | short name; `requires` / `invalidates` other states | `ssh.open_session` |
| entrypoint | module a recipe loads (a `py_itf_plugin` target) | `score.itf.packs.ssh.plugin` = `//score/itf/packs/ssh` |

A **recipe** is the test's root `conftest.py`: it wires nodes (`itf_setup`) and states goals
(`itf_init`), in Python or YAML. **Tests** ask only for capability tokens. OCTO, the planner, turns
the recipe into a construction order (Gate 1) and an action plan (Gate 2) before any test runs.

**Contract rule:** nothing imports a pack: not a test, not a recipe, not another pack. Packs are
loaded through `py_itf_plugin` / `pytest_plugins`; consumers write their *own* Protocols and the
planner checks at each seam that the provider's shape covers them.

## 1. Discover: the catalog is a SQLite database

```bash
Q="bazel run --noshow_progress --ui_event_filters=-info,-debug //tools/catalog:query --"
# the first lines of output are still Bazel's own ("Target ... up-to-date"); the result follows
$Q schema                          # ALWAYS first: tables, views, column comments
$Q search "<requirement sentence>" # full-text candidates; "no matches" = likely gap
$Q sql "SELECT ..." [--json]       # any read-only query
$Q serve --port 8799               # browsable catalog on 127.0.0.1 (run in background, stop after)
# The same catalog is published with the docs as the pack marketplace (catalog.html). After changing a
# pack, refresh it: bazel run //tools/catalog:build -- --out docs/_generated/catalog.html
$Q recipe docker.instance          # a node skeleton in Starlark and YAML, required config as placeholders
```

It is built from the packs' own decorators on every run, so it cannot drift from the code.

| Question | Query |
|---|---|
| who provides a capability, from which entrypoint | `SELECT * FROM v_capability_providers WHERE capability = ?` |
| what a test may call, with signatures | `SELECT provider, member, signature, doc FROM v_provider_api WHERE capability = ?` |
| how to write the node (slots, config; `!` = required) | `SELECT * FROM v_recipe_node WHERE provider = ?` |
| what makes a state true, what it needs, what it destroys | `SELECT * FROM v_state_deliverers WHERE state = ?` |
| config keys, defaults, secrets | `SELECT * FROM provider_config WHERE provider = ?` |

Walk prerequisites recursively: a deliverer's `requires` are states whose deliverers come from other
entrypoints the test must load too (`shell.open` → `platform.up`). One action may deliver several
states, each with its own probe (`also` relation, e.g. `ssh.open_session` → `shell.open` +
`network.reachable`). **Choose an entrypoint variant.** When a provider is listed under several entrypoints (for example
`tcpdump.capture` under `pcap.plugin` and `pcap.host`), compare the `requires` column of
`v_state_deliverers` per entrypoint and take the variant whose prerequisites the bench can meet: a
bench with no platform node cannot use an action that requires `platform.up`. Load only one
deliverer per state.

**Map an entrypoint to a Bazel label.** `score.itf.packs.<pack>.plugin` is the target named after the
pack, `//score/itf/packs/<pack>`; `score.itf.packs.<pack>.<variant>[.plugin]` is `:<variant>`, so
`pcap.host` is `//score/itf/packs/pcap:host` and `pcap.sim.plugin` is `:sim`. From another Bazel module
(such as `examples/`) use the prefix `@score_itf//score/itf/packs/...`. Each pack's BUILD file lists its
`py_itf_plugin` targets.

**Slots may be filled from another pack.** A provider's `needs` slots (endpoint, credentials, platform) name
contracts whose providers can live in another pack, whose label the test must list too: `ssh.shell`
needs an endpoint and credentials, so an SSH-over-container recipe lists `docker` (platform and
`docker.endpoint`), `net` (`password.credentials`) and `ssh`.

**Note** that a provider built on another capability is a separate node: `serial.exec`
(`exec.command`) needs a node for the console it runs on (`exec.console`), and a test using
`exec.command` reaches it through its own node.

## 2. Use it from pytest (Bazel)

```starlark
load("@score_itf//:defs.bzl", "py_itf_test")

py_itf_test(
    name = "bench",
    srcs = ["conftest.py", "test_bench.py"],          # conftest.py is the recipe
    data = ["recipe.yaml", "//images:load"],
    env = {"ITF_IMAGE_LOAD": "$(location //images:load)"},   # reaches YAML as ${ITF_IMAGE_LOAD}
    plugins = ["@score_itf//score/itf/packs/docker", "@score_itf//score/itf/packs/ssh"],
)
```

```python
# conftest.py — Python hooks, or YAML through load_setup/load_init (both may be mixed)
from pathlib import Path
from score.itf.core import hookimpl, load_init, load_setup

RECIPE = Path(__file__).with_name("recipe.yaml")

@hookimpl
def itf_setup(ctx):            # what exists: ctx.add / ctx.alias / ctx.scope("gw").add ...
    load_setup(ctx, RECIPE)

@hookimpl
def itf_init(ctx):             # what must hold: ctx.goal / ctx.relate / ctx.assume / ctx.state
    load_init(ctx, RECIPE)

@hookimpl
def itf_verify(session):       # optional readiness checks after bring-up, before tests
    session.check("platform.running", session.target.platform.running())
```

```python
# test_bench.py
import score.itf as itf

@itf.requires("itf.capabilities.exec.command")              # deselected (not failed) if absent
@itf.requires("itf.capabilities.files.transfer", shape=["exists"])   # needs that member too
def test_upload_lands(target, tmp_path):
    target.files.upload(str(tmp_path / "f"), "/tmp/f")       # node names come from the recipe
    assert target.command.exec("test -f /tmp/f")[0] == 0
```

- Write tests against contracts, not platforms: gate each on what it uses and run the same files
  against several recipes (`test/integration`); each target selects what its platform supports.
- `target.<node>` is a root node, `target.<scope>.<node>` a device scope's. Never import a pack.
- States are the recipe's job. A test changes bench state only through the planner:
  `target.reach("itf.states.shell.open")` (after a restart), `target.renew("platform")`
  (fresh objects: dismantles the node and everything bound to it, re-reaches the goals). Per-test
  freshness is a pytest fixture of the scope you want that calls `renew`.
- One generic conftest can serve several targets: `load_setup(ctx, Path(os.environ["ITF_CONFIG"]))`
  (and `load_init`) with `py_itf_test(data = ["r.yaml"], env = {"ITF_CONFIG": "$(location r.yaml)"})`
  per recipe, or use a Starlark recipe (below). To run one test file against several recipes, give
  nodes the same names by role in every recipe (`command`, `files`, `console`), because tests reach
  nodes by name; ignore the default names the `recipe` skeleton prints.
- Stacked `@itf.requires` decorators mean AND: the test is selected only if every one holds.
- Config formats: `environment` is `"A=1,B=2"`, `ports` is `"22/tcp:2222,3490/tcp"` or `"2222"`,
  `volumes` is `"/host:/in/container:rw,..."` (see each pack's README). Rootless Podman publishes
  ports but exposes no container IPs: map the port and use `docker.endpoint` with `via: published`.
- `py_itf_test` as shown is a complete minimal target: `srcs` lists the conftest and the tests, `data`
  lists the recipe and anything it names, no `main` or other arguments are needed. A pack that compiles
  binaries (pcap, dlt) makes the first build slow, about 5 minutes: run it in the background.
- Validate without hardware: `bazel test //pkg:bench --test_arg=--itf-plan --test_output=all`
  (long: pipe through `grep -E "ERROR|Gating|deselected|::test"` for the quick check)
  (add `--test_arg=--itf-strict-shapes`). A clean plan prints no diagnostics section: a problem prints
  `ERROR: Gate 1 ...` or `Gate 2 ...` with a reason and a fix, and the Gating list shows what is selected
  or deselected and why. Ordering (a relation such as "capture before console") is a property of the
  plan, visible as an edge in `plan.json`, not something a test body can observe.
- Artifacts: `bazel-testlogs/<pkg>/<test>/test.outputs/itf-run/` (`plan.json`, `target.html`,
  `test.log`, `events.jsonl`).

## 3. Use it from Python (no pytest)

```python
from score.itf.core import Session, describe
print(describe(["my_recipe_module"]).render())       # plan only, constructs nothing
session = Session(["my_recipe_module"], run_dir="itf-run")
session.resolve(); session.bring_up()
try:
    print(session.target.command.exec("uname -a"))
finally:
    session.close()                                   # teardown hooks, then unwind
```

The module plays the root conftest: its `pytest_plugins` list names the pack entrypoints.

## 4. YAML recipes

See [references/yaml.md](./references/yaml.md) for the full schema. Essentials: `setup.nodes`
`[{name, contract, using, bind, config}]`, `setup.scopes.<scope>.{nodes, aliases}`, `init.goals`,
`init.relations [{state, requires, invalidates}]`, `init.assumptions`, `init.states [{token, using}]`;
`extends: [base.yaml]` merges by name; node `config` values expand `${NAME}` / `${NAME:-default}`.

### Starlark recipes (Bazel)

`itf_recipe` (`@score_itf//bazel:recipe.bzl`) writes the same document from Starlark. Arguments:
`nodes`, `goals`, `relations`, `assumptions`, `states`, `aliases`, `rebinds`, `scopes`, `extends`,
`plugins` (the packs it needs), `conftest`, `plan_test`; helpers `node(...)`, `scope(...)`,
`relation(...)`, `location(label)` for Bazel-built files. Pass it
with `py_itf_test(recipe = ":r")`; the conftest keeps the code hooks. `bazel test //pkg:r_plan`
checks it without hardware; `bazel run //tools/catalog:query -- recipe <provider>` prints a node.

## Benches without hardware

Prefer a provider that behaves like the device over a stub that only accepts calls:

| Need | Use |
|---|---|
| a host to run commands, processes, files on | `//score/itf/packs/local` (`local.exec`, `local.process`, `local.files`) |
| a serial console that answers | `serial.pty_console`: the console talks to a shell on a pseudo-terminal, so banner, `wait_for`, `run` and `serial.exec` work (a `loop://` port only echoes, so nothing answers) |
| a platform, shell, logs or capture with no daemon | the `:sim` variants of docker, ssh, dlt, pcap |

Generic tests run unchanged on these (they select by capability), and plan mode still validates a
recipe that names real hardware. Phrase a command that must fail as `sh -c 'exit 3'`: on a console, a
bare `exit` ends the session itself.

## 5. Requirements → recipe → tests

Follow [references/authoring.md](./references/authoring.md): decompose the requirement into
capabilities, states, relations and checks; map every item to a catalog row (an item without a row is
a **gap**: gate a test on the proposed token, never fake it); pick providers; write the recipe; write
gated tests; validate with `--itf-plan`.

## 6. Writing a pack

`score/itf/packs/<pack>/`: topic modules (`platform.py`, `session.py`, ...) hold classes, config
dataclasses and the Protocols they expect; `providers.py` only declares `@provides` factories and
`steps.py` only `@delivers` actions with `@<action>.probe` (and `.probe_for(state)` for an
`also_delivers` state); `plugin.py` lists them in `pytest_plugins`; `sim/` holds an offline variant
when the real one needs hardware or a daemon. A plain token in `needs=`/`uses=` plus a Protocol
annotation is enough; use `expect(token, shape)` only where no annotation says it. Constructing a
provider has no side effects (actions connect/start). BUILD: one `py_library(name = "lib")` and one
`py_itf_plugin` per entrypoint; binaries are Bazel-built `data`, found through runfiles. Then
`bazel test //test/packs:catalog_test` checks every pack loads and every expectation is met.

## Rules

- Use only tokens, provider names, members and config keys the catalog holds.
- One deliverer per state per run: load one entrypoint variant, or pin one with `init.states`.
- Never import `score.itf.packs.*` outside its own pack (and that pack's unit tests).
- Write YAML recipes in block style, one key per line: no `{...}` mappings and no `[...]` lists.
- Never put secrets in YAML: credentials name key files or come from `${ENV}`.
- Never touch real hardware to "check": `--itf-plan` is the check.
- Tests written for the original API (`target.execute`, `docker_plugin`) need a project-side legacy
  layer (`examples/examples/legacy`); migrate them with docs/how-to/migrate.md.
