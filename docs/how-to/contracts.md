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

# Use, define and enforce contracts

Contracts are your project's own. A contract is **whatever name two parts agree on**: a factory fulfils
`exec.command`, a test or another part expects `exec.command`, and ITF checks that the shapes they publish and
expect fit. ITF ships no vocabulary you must follow; it is the platform that lets a project **discover** its
contracts (`itf contracts map`), **define** them (a definition file, optional) and **enforce** its rules
(`itf contracts check --rules`). The ITF team maintains the contracts its own packs use, with conformance checks,
as a supported set, not a standard. The reasoning is in
[the decision record on target composition](../decisions/DR-002-arch-target-composition.md); the worked example is
`examples/examples/vendor_contract`. The words are defined in the glossary of
[the model](../concepts/model.md#the-vocabulary).

## Names

A contract name is any string two parts agree on: `exec.command`, `platform.up`, `acme/power.relay`,
`acme/led`. `@major` after a name pins a major (`acme/power.relay@1`): when both sides give one, they must
agree. Whether a contract is a capability or a state comes from the part: a factory fulfils a capability
contract, an action makes a state contract true. Roles are named by the target file (`command`, `power`); a
definition may suggest one.

## Use a contract in a test

```python
@itf.requires("command", contract="exec.command", shape=["exec"])
def test_run_a_command(target):
    target.command.exec("echo hi")
```

The test asks for a role, and may narrow the ask: the contract (with `@major`) and the members it uses. A target
that lacks any of them deselects the test with the reason.

## Discover: `itf contracts map`

```
itf contracts map target.itf.yaml                          # text, on standard output
itf contracts map target.itf.yaml --format json            # for tools (text, json, mermaid or html)
itf contracts map --format html --output contract_map.html      # a browsable page; without a target file: every pack
```

With no target file it maps every pack (`--packs docker,ssh` narrows it); `--tests PATH...` adds the tests to read
and `--definitions DIR` a directory of definitions. This is the **contract map**; ITF's own is generated into
`docs/_generated/catalog.html` and served with these docs.

For every contract name in use, from the loaded parts and tests, it shows who offers it and with which shape,
who needs it and expecting which members, which tests ask for it, whether a definition exists, and every
disagreement: a part expecting a member no offerer has, two definitions of one name, a major nobody offers.
Names with no definition are fine; they are simply listed as undefined.

## Define: a definition file

A definition is optional. It adds meaning, members, a version, a stability, a suggested role and a conformance
suite. Start from what is observed:

```
itf contracts new acme/led --from-usage target.itf.yaml
```

The command writes the skeleton itself, to `contracts/acme_led.yaml` (or the file named by `--out`), and never
overwrites an existing file; there is nothing to redirect. A definition looks like this:

```yaml
contracts:
  - contract: acme/power.relay
    kind: capability
    role: power
    version: 1
    stability: experimental
    summary: Switch a power relay on and off and read its state.
    members:
      - name: "on"
        signature: "() -> None"
        semantics: Closes the relay.
      - name: toggle
        signature: "() -> bool"
        semantics: Flips the relay. Optional.
        required: false
    guarantees:
      - A relay starts open (off).
    conformance: acme.conformance
```

Definitions are found in a pack's `contracts/` directory, in a project directory named by
`itf_target(contracts = [...])` or `ITF_CONTRACTS_PATH`, and in an installed distribution with an entry point in
the group `score_itf.contracts`. Fields: `contract`, `kind` (capability or state), `version`, `summary`,
`description`, `members` (`name`, `signature`, `semantics`, `required`), `guarantees`, `role`, `stability`
(`experimental`, `stable`, `deprecated`), `replaced_by`, `conformance`, `see_also`, `probe`. A deprecated
contract makes a plan warn, naming `replaced_by`.

Without a definition a target file still compiles: wiring and gating use names, and the no-trust checks use the
shapes the parts publish and expect.

## Conformance

A `conformance:` module holds `CHECKS`, keyed by contract name; a check takes the offered object and raises
through `expect`, so any runner can execute it:

```python
from score.itf.contracts.conformance import check, expect

@check()
def on_closes_the_relay_and_off_opens_it(node):
    node.on()
    expect(node.is_on() is True, "after on() returns, is_on() must be true")

@check(shape=("toggle",))        # applies only to a node that offers the optional member
def toggle_flips(node): ...

CHECKS = {"acme/power.relay": [on_closes_the_relay_and_off_opens_it, toggle_flips]}
```

A test file with `from score.itf.contracts.pytest_conformance import test_conformance` and the plugin
`//score/itf/contracts:conformance` runs every check against every part of the target that claims its contract.
A fulfilling part for real hardware passes the same suite as the simulation.

## Enforce: `itf contracts check`

```yaml
# rules.yaml
namespaces:
  - acme                    # contracts in this namespace (acme/...) need a definition
roles:
  power: acme/power.relay   # the role `power` is always an acme/power.relay
forbid_stability:
  - deprecated              # no target file may use a deprecated contract
```

```
itf contracts check --rules rules.yaml target.itf.yaml      # exit 1 on violations, for pipelines
itf contracts check --rules rules.yaml a.itf.yaml b.itf.yaml     # any number of target files
itf contracts check --rules rules.yaml --conformance a.itf.yaml  # and run the conformance checks against them
```

`itf contracts reference --output docs/reference/contracts.md` writes the Markdown reference of the defined contracts.

## Version and deprecate

A change that removes or changes a member is a new major: a new name with `@2` for the offering side, and the
old definition marked `stability: deprecated` with `replaced_by`. Plans warn about deprecated contracts and a
contract rules can forbid them. Adding an optional member (`required: false`) does not change the major; tests that need
it say so with `shape`.

## Propose a contract for the ITF supported set

The ITF team's own contracts live in the `contracts/` directory of the pack that fulfils them, with conformance
checks beside them. To propose one, open a pull request with the definition, the conformance checks, a factory
that passes them and a target file in `test/integration/targets/` that exercises it (use the contract proposal
template).
