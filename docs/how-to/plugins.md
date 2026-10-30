# Write a pack

A pack is a set of pytest plugin modules that publish providers (`@provides`) and actions
(`@delivers`). Recipes load it by Bazel label; tests reach it only by contract token.

## Layout

```
score/itf/packs/<pack>/
  __init__.py      one-line description (shown in the catalog)
  <topic>.py       implementation: classes, config dataclasses, the Protocols they expect
  providers.py     @provides factories only: import from topic modules, declare
  steps.py         @delivers actions and their probes only
  plugin.py        pytest_plugins = ["...providers", "...steps"]   (the entrypoint)
  sim/             an offline variant, when the real one needs hardware or a daemon
  BUILD            py_library(name = "lib") + one py_itf_plugin per entrypoint
```

## Providers

```python
@provides("itf.capabilities.exec.command", name="docker.exec",
          needs={"platform": "itf.capabilities.platform.instance"})
def make_exec(platform: Platform) -> DockerExec:   # Platform: a Protocol in this pack
    return DockerExec(platform)
```

- What a provider gives is its return annotation's shape; what a slot needs is its parameter's
  annotation (a local `Protocol`). Use `expect(token, shape)` only when no annotation says it.
- Never import another pack: declare your own Protocol for what you use. The planner checks at
  every seam that the provider's shape covers it; `//test/packs:catalog_test` checks that every
  expectation some pack declares is met by some provider.
- Constructing has no side effects: connecting, starting, spawning is an action. Yield the object
  and clean up after the `yield` for teardown.
- Config is flat scalars, declared with `config_schema=` (a dataclass); mark secrets with
  `field(metadata={"sensitive": True})`.

## Actions

```python
@delivers("itf.states.shell.open", name="ssh.open_session", requires=("itf.states.platform.up",),
          also_delivers=("itf.states.network.reachable",), uses={"shell": "itf.capabilities.exec.shell"})
def open_session(shell: Shell) -> None:
    shell.connect()

@open_session.probe
def is_session_open(shell: Shell) -> bool:
    return shell.is_connected()

@open_session.probe_for("itf.states.network.reachable")
def is_reachable(shell: Shell) -> bool:
    return accepts_connections(shell.endpoint)
```

A probe is read-only and cheap; it lets ITF skip an action whose state already holds and verify it
afterwards. One action may deliver several states, each with its own probe (`probe_for`).
`invalidates=` names states an action destroys (a reboot invalidates open sessions).

## BUILD

```starlark
py_library(name = "lib", srcs = glob(["**/*.py"]) + ["//score/itf/packs:init"],
           data = [":tool_bin"], deps = ["//score/itf/core"])
py_itf_plugin(name = "<pack>", enabled_plugins = ["score.itf.packs.<pack>.plugin"], py_library = ":lib")
```

Binaries a pack runs are built by Bazel and found through runfiles (see the dlt and pcap packs).
Add unit tests under `test/packs/`; a pack's own tests may import its modules.
