# Authoring a recipe and tests from requirements

Worked example: `test/integration` runs one capability-gated suite (`suite/`) against many recipes
(`recipes/`: host, container, container + SSH, DLT with a bench-local action, QEMU with the console
opened before boot, and a Starlark twin). Its README shows which tests each recipe selects.

## 1. Decompose a requirement

| Requirement says | Look for | Lands in |
|---|---|---|
| a device/core ("the gateway", "the safety core") | — | a **scope** name (`gw`, `sc`) |
| something to talk to or control ("SSH", "UART", "container") | capability | `setup.nodes` |
| a precondition ("once booted", "while logging") | state | `init.goals` / `relations` |
| an ordering ("record the whole boot") | relation | `init.relations[].requires` |
| "record X during Y" (logs, pcap) | the recording state | goal **and** `Y requires X` |
| "X restarts Y" | relation | `init.relations[].invalidates` |
| a check ("answers ping", "logs contain") | capability members | test body |
| an artifact to keep | capability member | `itf_teardown` hook |

Example: *"The QNX VM shall be reachable over SSH and its console shall show the boot."*

| Item | Token | Provider / action | Plugin target |
|---|---|---|---|
| the VM | `itf.capabilities.platform.instance` | `qemu.instance`, `qemu.start_platform` | `//score/itf/packs/qemu` |
| console | `itf.capabilities.exec.console` | `qemu.console`, `qemu.open_console` | (same) |
| "show the boot" | relation: `platform.up requires console.open` | — | — |
| SSH endpoint + login | `descriptor.endpoint`, `descriptor.credentials` | `qemu.endpoint`, `qemu.credentials` | (same) |
| SSH | `itf.capabilities.exec.shell` | `ssh.shell`, `ssh.open_session` (also delivers `network.reachable`) | `//score/itf/packs/ssh` |

## 2. Recipe

Write `recipe.yaml` (see yaml.md) or Python hooks; the conftest loads it. Declare only nodes the
tests or actions need; realization is lazy. Required config is marked `!` in `v_recipe_node`.
A bench-specific condition (a daemon this bench starts) may be an action in the conftest itself:

```python
@delivers("bench.daemon.running", name="bench.start_daemon", requires=("itf.states.platform.up",),
          uses={"process": "itf.capabilities.exec.process"})
def start_daemon(process): ...

@start_daemon.probe
def daemon_running(process) -> bool: ...
```

Guard real hardware: refuse to run unless an explicit flag is given, before ITF probes anything
(`pytest_configure` raising `pytest.UsageError` unless `--itf-plan` or `--bench-live`).

## 3. Tests

A test that should run on several platforms asks only for contracts (`exec.command`, `files.transfer`)
and asserts behaviour any provider must have; `test/integration/suite` is the model. A requirement about
ordering ("recording before the console opens") is expressed by a relation and checked in the plan, not
asserted in a test body.

- One `@itf.requires(token, scope=...)` per capability and scope the test touches; add `shape=[...]`
  for members not every provider has. A recipe without it deselects the test with a reason
  (`--itf-strict-gating` turns that into a failure), so one test file serves several recipes.
- Call only members `v_provider_api` lists, with their signatures.
- States are the recipe's job: no test powers, boots or opens sessions directly.
- Test names and assertion messages state the requirement.

## 4. Gaps

A requirement needing a capability, member or state the catalog lacks is a gap: report it with the
closest rows, write the test against the proposed token gated with `@itf.requires`, and propose a
provider in an existing pack or a new pack (SKILL.md §6). Never work around it with direct I/O.

## 4a. Logging and lifecycle hooks

Write logs so that someone can follow a run from the log alone.

- INFO is the story: one line per milestone. Bring-up phases, `itf_verify` checks, each scenario and its verdict, each command with its exit code, file transfers, artifacts saved in `itf_teardown`.
- DEBUG is the detail: command payloads, raw output, connection attempts, console lines. Nothing needed to follow the story belongs here.
- WARNING and ERROR mean something went wrong. Do not use them for expected outcomes such as a command that exits non-zero on purpose.
- Use `itf_verify` to check that the bench is healthy before the first test (boot finished, services up), and `itf_teardown` to save evidence (console transcript, container log) even when tests fail.
- When bring-up, a startup check or a teardown hook fails, ITF prints a `=== ITF: ... failed ===` section (what failed, how far the run got, the original cause, the run directory, hints). Make `itf_verify` check names and `detail` strings say what is wrong, since they appear verbatim in it.
- Start every host process (a tool, a capture, a shell) with `ProcessWrapper` or `ProcessWrapper.run`, never `subprocess` directly. ITF tracks wrapped processes, stops them on a test timeout and at session close, and reports any that were still running; a gate test fails the build on direct spawning.
- Log through `logging.getLogger("<topic>")`, never `print`, so one `--log-cli-level` filter works everywhere.

## 5. Validate

```bash
bazel test //pkg:bench --test_arg=--itf-plan --test_arg=--itf-strict-shapes --test_output=all
bazel test //test/packs:catalog_test     # after changing a pack
```

No diagnostics; the plan orders actions sensibly; gating selects exactly the intended tests.
