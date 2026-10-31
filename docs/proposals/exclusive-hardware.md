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

# Proposal: exclusive hardware in a plan

**Status:** Design agreed, not implemented.

## Problem

Some things a node uses cannot be shared: a serial device has one owner, a fixed published host port can be
bound once, a relay channel drives one load. Each node looks valid on its own, so a recipe with two nodes on
`/dev/ttyUSB0` or two containers publishing port 23230 passes planning and fails at run time with an
unrelated-looking error.

## Decision

- **The provider author declares what is exclusive**, because exclusivity depends on the medium, not on the
  contract: commands over SSH are shareable, commands over a serial line are not. The declaration sits in
  the config schema providers already publish, next to `sensitive`.
- **A recipe may add keys** only the bench knows (a rack slot, the relay a board is wired to), never remove
  one, so a recipe cannot hide a real clash.
- **Two nodes holding the same key in one plan is an error**, reported when the plan is made.
- **Observations need no new kind.** They stay capabilities and states; scoping a recording to a test is the
  runner's job (pytest fixtures).
- **A resources kind is only for pools** ("any free relay channel"), where the planner must choose and bind
  units before Gate 1. Sharing a board between runs belongs to a reservation service in front of ITF.

## How it flows

```
pack import          recipe              Session.resolve()                          everything after
───────────          ──────              ─────────────────────────────────────      ────────────────
@provides(config=    nodes: + holds:     Gate 1 ─► config check ─► hold check ─►    Gate 2, bring-up,
  SerialConfig)      (extra keys)        (target   (exists)        (new)    Gate 2  tests, renew:
  device: holds(                          plan)                                     holds not used
    "serial")
```

### 1. The pack declares (when it is imported)

```python
@dataclass
class SerialConfig:
    device: Annotated[str, holds("serial")]
    baudrate: int = 115200
```

`ConfigSchema.from_dataclass` (`score/itf/core/engine/config.py`) records `holds="serial"` on the field as it
records `sensitive` today. `publish()` already collects every provider's schema into `Catalog.config_schemas`.

| Provider | Field | Held | Key |
|---|---|---|---|
| `serial.console` | `device` | yes | `serial:/dev/ttyUSB0` |
| `docker.instance` | a fixed published host port | yes | `tcp:<host>:23230` |
| `docker.instance` | a port published as "any free port" | no | chosen at run time, nothing to clash |
| `ssh.shell` | `host` | no | many sessions per host are normal |
| a relay pack | `channel` | yes | `relay:psu1/3` |

### 2. The recipe may add keys

```yaml
nodes:
  - name: board
    using: ssh.shell
    config:
      host: 10.0.0.7
    holds:
      - slot:rack2/4
```

The keys travel with the node declaration (`scope.add(..., holds=[...])`), so the usual precedence applies:
if the project's conftest redeclares the node, its version wins. OCTO carries them as opaque data, like
`config`.

### 3. The check, once, at plan time

In `Session.resolve()`, after Gate 1 and in the same pass that validates each node's config against its
provider's schema:

1. For each node and each field marked `holds(kind)` that has a value, build `kind:normalise(value)`. An
   empty field yields nothing.
2. Add the node's recipe keys.
3. Group the keys across nodes; two or more nodes on one key is a conflict.
4. Report conflicts like config issues: `resolve()` stops before Gate 2, so nothing is planned further,
   built or started.

### 4. Where it shows

| Run | On a clash |
|---|---|
| `pytest` | an `=== ITF: recipe rejected ===` section before any test |
| `--itf-plan`, `itf plan` | the same report, exit 1 |
| Bazel `py_itf_test(recipe = ...)`, `itf_plan` | `bazel build` fails |
| `itf up` | nothing is brought up |

```
.console: holds serial:/dev/ttyUSB0, also held by .debug_console
  Fix: give one of them another device, or remove one node
```

On success the plan JSON lists each node's held keys, so `itf diff` shows when a change makes a node hold
something, and a reservation service can read which units a run needs. The catalog, the marketplace and
`itf explain` list each provider's held fields.

### 5. When it is not used

Holds are a plan-time check only. Bring-up, probes, tests, teardown and `renew` never look at them, and `renew`
rebuilds from the same plan, so there is nothing to recheck.

## Limits

- Keys compare as written. `/dev/ttyUSB0` and `/dev/serial/by-id/...`, or `localhost:2222` and
  `127.0.0.1:2222`, are the same thing under different names. A provider may supply a normaliser for its kind,
  but the planner cannot inspect a remote machine, so the check catches clashes, not every alias.
- One plan only. Two jobs reaching for the same board is for a reservation service.
- Values from `${VAR}` are expanded before planning and checked like literals.

## Work

1. `holds(kind)` in the config schema, with an optional normaliser per kind.
2. `holds` on node declarations (recipe document, `scope.add`, Starlark `node()`).
3. The check in `Session.resolve()` and a rendered diagnostic.
4. Held keys in the plan JSON; held fields in the catalog and `itf explain`.
5. Mark the fields in the serial, docker and relay-like packs; tests for clash, no clash, recipe-added keys
   and empty fields.
