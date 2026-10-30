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

# Modeling a target

Use this guide when deciding what to declare as a capability, a provider, a state or a config value. For the API walkthrough, start with the [write tests](../how-to/write_tests.md); for the planner without the runtime, see [OCTO](../../score/itf/core/octo/README.md).

## Decide what each fact is

| Question | Use | Example |
|---|---|---|
| Can another component name, bind, inspect or replace this *object* independently? | Capability contract and one or more provider implementations | `itf.capabilities.descriptor.endpoint`, `power.supply` |
| Is it one particular instance, with its own identity or lifetime? | Node in a scope | `gw.diag_endpoint`, `gw.shell` |
| Is it a setting of one provider instance rather than an object with identity? | Node `config` | retry timeout, image name, output path |
| Is it a condition that can be checked and may need work to establish? | State contract, action and preferably probe | `itf.states.shell.open`, `itf.states.application.running` |
| Is it only the desired end condition for this scope? | Goal in `itf_init` | `gw.goal("itf.states.shell.open")` |

Sharing one scalar value across recipes does **not** make it a capability. Reuse a recipe variable or YAML inheritance for repeated config. Conversely, the same contract token on several nodes does **not** mean one object: node identity is `(scope, name)`, while an alias is another name for an existing object.

## Design a capability

Name the contract for the role it offers, not the library that implements it: `itf.capabilities.exec.shell`, not `paramiko.client`. Provide at least one provider for that token; the policy chooses it with `using=` if more than one exists. Publish what consumers can rely on using `gives=` or a return type. Declare dependencies as named `needs=` slots, with `expect(token, shape)` when their required members cannot be inferred from an annotation. Do not import another pack's concrete type merely to describe a slot.

Keep construction free of external side effects: the provider creates a handle; an action establishes its running state. Generator providers may `yield` the handle and clean it up after the yield. If a capability has a separate lifetime, needs to be bound from multiple consumers or can be swapped independently, it should usually be its own node rather than a nested config dictionary.

Provider-owned **config** declares scalar settings for that provider. Use a dataclass schema to make required/optional keys discoverable and validated at planning time:

```python
from dataclasses import dataclass
from score.itf.core import provides

@dataclass(frozen=True)
class CaptureConfig:
    interface: str
    out_dir: str = "artifacts/capture"

@provides("itf.capabilities.observe.capture", name="capture.process", config_schema=CaptureConfig)
def make_capture(config):
    ...
```

The factory still receives a dictionary; the schema checks it, it does not coerce values or change what the factory receives. Only flat scalar fields (`str`, `int`, `float`, `bool` and nullable variants) are supported, so OCTO claims stay immutable and JSON-friendly. Defaults are documented by the schema but must still be applied by the factory when a key is absent. Unknown keys and missing/wrongly typed required fields are errors after Gate 1 and before any probe or construction, including `--itf-plan`. A dataclass field with `metadata={"sensitive": True}` redacts its value from ITF artifacts and the plan display; **do not put credentials in config unless you have considered other loggers and sinks as well**. Unselected/overridden claims without a known provider cannot be reliably classified as sensitive. Packs without a schema retain legacy behavior.

**Slots versus config:** `shell` has a slot `endpoint: itf.capabilities.descriptor.endpoint` because another independently named node supplies it. `connect_timeout` is config because it only tunes this shell provider. If two shells use the same endpoint, bind both slots to one endpoint node; if both use the same timeout, simply reuse the scalar in their recipes.

## Design a state

Give it a name for a condition that can hold, not an imperative procedure (`itf.states.shell.open`, not `open_session_now`). The action should do only the work needed to establish it. A cheap read-only probe should answer whether it already holds. Declare `requires=` for states that must hold first; declare `invalidates=` for states the action destroys. `uses=` names capabilities the action needs to do its work; those are objects, not prerequisite states. Keep the action and probe consistent with the scope whose state they claim to establish.

If a procedure changes more than one state, use `also_delivers` only when the *same invocation* really establishes both. If an action changes the validity of a different state (for instance restarting a platform closes an existing connection), mark the other state as invalidated. Use an assumption only when the environment supplies a fact ITF cannot probe or establish; assumptions are not evidence and remain visible in the plan.

## Choose node identity and scope

**Two instances of one contract in one scope.** Give them different node names and bind ambiguous slots explicitly. For example, `gw.control_endpoint` and `gw.log_endpoint` may both be `itf.capabilities.descriptor.endpoint`. Bind `shell.endpoint` to the former and `logs.endpoint` to the latter. Same contract, different instances and ports. A bare contract token is not an identity.

**Two devices on one target.** A policy is one target; put each device's nodes and goals in its own device scope (`gw`, `adas`), reached by tests as `target.gw`, `target.adas`. The same name, such as `shell`, is safe in both: `gw.shell` and `adas.shell` are distinct objects. Their `itf.states.shell.open` states are also distinct (`gw:itf.states.shell.open`, `adas:itf.states.shell.open`). Adding a second device does not require changing the first device's pack.

**One supply controlling two devices.** Put the *physical supply controller* in the target's root scope (top-level `ctx.add`), then alias it into each device scope that uses it — a device never sees a root node it did not alias. Both aliases point to the same realized instance:

```python
# itf_setup
ctx.add("supply", "power.supply", using="lab.supply",
        config={"address": "192.0.2.10"})
ctx.scope("gw").alias("supply", ".supply")
ctx.scope("adas").alias("supply", ".supply")
```

If each device has its own independently controlled output, model the output/channel identity separately (for example one channel node per device, each bound to the shared controller). Define `powered` separately in each device scope when its truth can differ per device. If a single output necessarily switches *both* devices together, do not pretend their power states can vary independently: model that shared fact in the root scope or make the coupling explicit in the policy.

**One supply per device.** Add `gw.supply` and `adas.supply` as two nodes (possibly with the same `power.supply` contract and provider but different addresses). Do not alias one to the other; each has its own construction, teardown and state. The choice between an alias and a new node should reflect physical ownership, not a desire to shorten the recipe.

## Quick review before adopting a pack

- Could two consumers swap this object independently? If yes, use a contract and slot, not duplicated config.
- Does the proposed state have a meaningful probe? If not, say why, and do not claim an unverified condition is observed.
- Are `requires` and `invalidates` about truth, not the intended order in a script?
- Does the selected provider declare its required config, and does `--itf-plan` validate every scope before construction?
- Do shared aliases match actual shared hardware/lifetime? Are separately controllable resources separately named?

The [pack reference](../reference/plugins.rst) and `bazel run //tools/catalog:query` list the providers and their configuration; `test/packs/sim` composes two devices with a shared, aliased capture.