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

# Open decisions

Each entry gives the question, the options and a recommendation. The community decides; the recommendation is
the author's.

## 1. Detached targets for containers and QEMU

`itf down` runs in a later process and must find what `itf up --detach` created. Only factories that can observe
earlier work allow it: today `localhost.platform` and the simulated platform.

| Option | Cost |
|---|---|
| A. Keep refusing for Docker and QEMU | The most common target cannot be left running |
| B. `docker.platform` labels its container and network; a later process finds them by label | Small change in one pack; keeps "unwind from what is observed" |
| C. A state file written by `up`, read by `down` | A second source of truth beside the probes |

**Recommendation: B for Docker now; QEMU later, through a pidfile the QEMU part owns.**

## 2. Conformance of the `sim` pack

`sim.exec` claims `exec.command` but does not return shell exit codes or stderr; the simulated platform exposes
`running` as an attribute where the check calls `running()`.

| Option | Cost |
|---|---|
| A. Make the simulations conform; run their checks in CI | Some simulation code |
| B. Let simulations claim weaker contracts | Suites written for `exec.command` stop running on simulations |
| C. Exempt simulations from conformance | Hides the problem |

**Recommendation: A**, and a rule that a pack's CI passes conformance for every factory it ships.

## 3. One role key, or also a list form

Target files key capabilities by role. A list form (`- ssh.exec`) would be shorter where no role name is needed.

**Recommendation:** keep the role key only. One form is easier to teach and to merge.

## 4. The contracts ITF supports

ITF maintains the contracts its own packs use (`exec.command`, `exec.shell`, `exec.process`, `files.transfer`,
`platform.instance`, `descriptor.endpoint`, `descriptor.credentials`, `observe.logs`, `platform.up`, `shell.open`, and others in each pack's `contracts/`). Once released, their
names and members are public API.

**Decide:** which of them are marked `stable` in the first release, and which `experimental`.

## 5. Where the legacy facade lives

| Option | Cost |
|---|---|
| A. As an example in ITF (`examples/legacy`) | ITF carries code for an API it no longer ships |
| B. In a separate repository | Projects must find it; it can drift from ITF |

**Recommendation: A**, for one release, then remove it.

## 6. Python 3.14

`pydantic==2.10.6` has no wheel for Python 3.14.

**Recommendation:** move the pin to a release with 3.14 wheels and regenerate the lock files, in its own pull
request.

## 7. Tests that need multicast

Legacy `test_dlt` fails under rootless Podman, which does not route multicast.

**Recommendation:** tag it so local runs skip it with the reason; CI with a rootful engine keeps running it.

## 8. Removing a relation in an override file

An override file can add relations but not remove one: relations of one state are joined when files merge. An
override that turns a container target into a real machine (`remove: true` on the platform role) therefore keeps
the target file's `shell.open after platform.up`, and must `assume: platform.up`.

| Option | Cost |
|---|---|
| A. Keep joining; a real machine gets its own target file, sharing parts with `include:` | One more file per kind of target |
| B. `remove: true` on a relation entry, as on a role | One more merge rule to learn |
| C. Drop relations that name a state no listed action makes and nothing assumes | An inference: a forgotten action would silently lose its ordering |

**Recommendation: A for now**; revisit B if real projects ask for it. C is ruled out: it guesses.
