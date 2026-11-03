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

# Architecture

This paper describes the parts of the proposed ITF and how a run flows through them. The words are those of the
[glossary](glossary.md). Paths are those of the implementation branch `ihsa_itf_platform`.

## Layers

```text
  fronts      pytest adapter        itf command line        score.itf.Session        Bazel rules
                     \                    |                     /                       |
  session             score.itf.core.Session: resolve, bring_up, reach, discard, renew, close
                                          |                                     itf_target
  engine     target file frontend, registry, realization, bring-up, evidence, unwind    py_itf_test
                                          |
  planner    OCTO: claims in, plan or diagnostics out (standard library only)
                                          |
  parts      packs: docker, qemu, ssh, net, ping, dlt, pcap, serial, localhost, core_dump, sim; the policy
  optional   contract library: map, skeletons, contract rules, conformance
```

| Layer | Directory | Depends on | Knows |
|---|---|---|---|
| OCTO | `score/itf/core/octo` | the Python standard library | claims, scopes, contracts as strings. No ITF, no pytest, no domain word |
| engine | `score/itf/core/engine`, `frontends` | OCTO | how to load a target file and packs, build parts, run actions and probes, unwind, write evidence |
| session | `score/itf/core/session.py` | engine | one run of one target file |
| fronts | `score/itf/core/adapters`, `score/itf/cli`, `bazel/` | session | how a user starts a run |
| packs | `score/itf/packs/<name>` | `score.itf.core` decorators only | their own devices and tools. A pack never imports another pack |
| contract library | `score/itf/contracts` | engine (read only) | contract definitions, contract rules, conformance |

A gate in CI checks that `score/itf/core` names no domain thing (no "docker", "ssh", "dlt").

## A part

A part is a decorated function. Everything ITF needs to know about it is in its signature.

```python
@dataclass
class Settings:
    port: int = 22


class Platform(Protocol):              # the consumer's own Protocol; packs share no code
    __contract__ = "platform.instance"

    def ip(self) -> str: ...


@capability("descriptor.endpoint")     # a capability factory; label docker.endpoint
def endpoint(platform: Platform, config: Settings) -> Endpoint:
    return Endpoint(platform.ip(), config.port)


@state("platform.up", breaks=("platform.down",))   # an action; label docker.start
def start(platform: Platform) -> None:
    platform.start()


@start.probe
def is_running(platform: Platform) -> bool:
    return platform.running()
```

| Declared by | Read as |
|---|---|
| `@capability("<contract>")` | the capability contract this factory fulfils |
| `@state("<state>", after=, breaks=, also=)` | the state this action makes true, the states it needs first, the states it ends, further states it makes true |
| `@<action>.probe` | the check that the state holds |
| each parameter's annotation | a slot: the contract (`__contract__`) and the expected shape (the Protocol's members) |
| `config: <dataclass>` | the settings schema: names, types, defaults, secrets |
| the return annotation | the published shape |
| the function name, or `label=` | the label, `<pack>.<name>` |

The decorators attach a descriptor (`__itf_part__`) to the function. Importing a pack registers nothing
globally; a session reads the descriptors of the packs its target file names.

## A run

```text
 target.itf.yaml ─┐
 override files ───────┼─> merge by role ─> claims ─> OCTO gate 1 ─> target plan ─┐
 policy.py ────────────┘   (frontend)      (registry)  (what exists)               │
                                                       OCTO gate 2 ─> action plan ─┤  resolve(): pure, builds nothing
                                                       (what happens, from goals)  │
 ──────────────────────────────────────────────────────────────────────────────────┘
 bring_up(): build factories in plan order ─> run each action ─> its probe must pass ─> itf_verify hooks
 tests:      gating deselects tests whose @itf.requires is not met; target.<role> is the built object
 close():    itf_teardown hooks ─> probe what holds ─> unwind from what is observed ─> evidence.json/.html
```

1. **Load.** The frontend reads the target file, its includes and override files, and merges them by role. It
   finds the packs from the labels (or `packs:`) and the project's policy (`policy.py`) beside the target file.
2. **Claims.** The registry turns each part's descriptor and each target file entry into OCTO claims: roles,
   slots, shapes, settings, states, relations, assumptions.
3. **Gate 1: what must exist.** OCTO picks the factory of each role, binds each slot (explicit `bind`, else the
   sole candidate in the scope, else an error), compares shapes and orders construction.
4. **Gate 2: what must happen.** From the goals, OCTO picks the action for each state (`by:`, else the sole
   candidate whose slots can all be filled), adds the actions' and the target file's orderings and orders the
   steps. Cycles, conflicts and unmet states are diagnostics with a code, the parties involved and a fix.
5. **Bring-up.** The engine builds factories in order, runs each action, then its probe. A probe that fails stops
   the run with the evidence collected so far. Actions whose state already holds are skipped when their probe
   says so.
6. **Tests.** The pytest adapter gates tests against the composed target before any test runs, and gives each
   test `target`. Tests change state only through the session: `reach`, `discard`, `renew`.
7. **Unwind.** Teardown starts from what the probes observe, not from the plan, so it also works after a crash
   and from a later process (`itf down`). Every host process ITF started goes through `ProcessWrapper` and is
   reaped.

## Fronts

| Front | Entry | Notes |
|---|---|---|
| pytest | `py_itf_test`, or `pytest` with the adapter installed | `--itf-target`, `--itf-override`; `@itf.requires`; `target` fixture |
| command line | `itf validate\|plan\|graph\|up [--detach]\|down\|test\|doctor\|diff\|evidence` | `validate`, `plan`, `graph` and `diff` never touch hardware |
| contract tools | `itf contracts map\|new\|check\|reference` | optional; read packs, target files and tests without running anything |
| Python | `score.itf.Session(target=..., overrides=...)` | for runners other than pytest |
| Bazel | `itf_target`, `py_itf_test(target=...)` | the target file is compiled during `bazel build` |

All fronts find the target file the same way: an explicit value, then `ITF_TARGET`, then `itf_target`
in `pytest.ini`, then `[tool.itf] target` in `pyproject.toml`.

## Bazel

```text
 itf_target(src, overrides, packs, srcs, data, env, files)
   ├─ compile action: itf validate on label placeholders ─> plan.json   (fails bazel build on an error)
   └─ ItfTargetInfo: target file, overrides, policy, packs, runfiles, env, files
                     │
 py_itf_test(target = ":x") ─> sets ITF_TARGET/ITF_OVERRIDE, adds packs and files to runfiles
```

- The target file reaches the test as written; no document is generated from it.
- `files` maps a `${NAME}` to a built file's label; `env` gives other values. Compiling uses each file's label in
  place of its path, so checking a plan never builds an image or a kernel.
- A label in the target file that names a pack not listed in `packs` fails the build.

## Packs on the implementation branch

| Pack | Factories (examples) | Actions (examples) |
|---|---|---|
| localhost | `localhost.platform`, `localhost.exec`, `localhost.process`, `localhost.files` | `localhost.start` |
| docker | `docker.platform`, `docker.exec`, `docker.process`, `docker.files`, `docker.endpoint` | `docker.start` |
| qemu | `qemu.platform`, `qemu.endpoint`, `qemu.credentials`, `qemu.console` | `qemu.start`, `qemu.open_console` |
| ssh | `ssh.shell`, `ssh.exec`, `ssh.process`, `ssh.files` | `ssh.open` |
| net | `net.endpoint`, `net.key`, `net.password` | |
| ping | `ping.pinger` | `ping.await_boot` |
| serial | `serial.console`, `serial.pty_console`, `serial.exec` | `serial.open` |
| dlt | `dlt.receive`, `dlt.receive_tcp`, `dlt.stream`, `dlt.multicast` | `dlt.start_receive`, `dlt.subscribe`, `dlt.join` |
| pcap | `pcap.capture` | `pcap.start`, `pcap.start_on_host` |
| core_dump | | none: an `itf_teardown` hook that collects core dumps |
| sim | simulations of the platform, exec and log factories, for tests of ITF itself | |

Each pack ships the definitions and conformance checks of the contracts it uses, in its `contracts/` directory.

## Evidence

Every run writes `itf-run/` under Bazel's undeclared outputs: the plan, the bring-up log, each probe result,
`evidence.json` and `evidence.html`. A failed plan or bring-up adds a report naming the failing part, the
diagnostic and the fix.

## What OCTO keeps from itf-core

OCTO is the itf-core planner with three removals: node derivation, the switch that relaxed shape checks, and
binding actions by role name. Everything else (claims, the two gates, precedence of origins, diagnostics) is
unchanged. The [rationale](rationale.md) lists each itf-core decision and what became of it.
