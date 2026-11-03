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

# Migration guide

The proposal removes the original plugins (`docker_plugin`, `qemu_plugin`, `dlt_plugin`, `core_dump_plugin`) and
the `Target` class from ITF. This guide says how a project moves, and how it keeps existing tests running while it
does. The words are those of the [glossary](glossary.md).

## Three steps

1. **Keep running.** Copy the example facade (`examples/examples/legacy` on the implementation branch) into the
   project. Change only the imports of existing tests from `score.itf.plugins.*` to the facade's module. The
   tests run on a target file built from the original options.
2. **Move tests one at a time.** When a test is touched, change it to `@itf.requires("<role>")` and
   `target.<role>`. Both kinds of test run in the same suite.
3. **Delete the facade** when no test uses it.

## What the facade contains

| File | Purpose |
|---|---|
| `targets/docker.itf.yaml`, `targets/qemu.itf.yaml` | what `--docker-image` and `--qemu-config` declared, as target files with `${LEGACY_*}` settings |
| `targets/policy.py` | the project's policy beside the target files: readiness checks and evidence |
| `conftest.py` | the original options (which select the target file) and the fixtures `target`, `docker_configuration`, `dlt_config`, `dlt`, `dlt_on_target` |
| `legacy_itf/` | `LegacyTarget` (`execute`, `upload`, ... over the composed roles), the original SSH, SFTP, ping and DLT helpers, `requires_capabilities` |

ITF's own original integration tests run on this facade with only their imports changed.

Known differences seen through the facade:

- With QEMU, DLT recording starts after the machine has booted, not before.
- The container is replaced per test unless `--keep-target`, as before. The facade calls
  `session.discard("platform")`, applies the per-test settings to the new platform, and then reaches the goals.

## Mapping

| Original | Proposed |
|---|---|
| `plugins = [".../plugins:docker_plugin"]`, `--docker-image=X` | `packs = ["@score_itf//score/itf/packs/docker"]` on the `itf_target`; `platform: factory: docker.platform` with `image: X` under `with:` |
| `--docker-image-bootstrap=$(location :load)` | `with: bootstrap: ${LOAD}` and `files = {"LOAD": ":load"}` on the `itf_target` |
| `docker_configuration` fixture | the platform's settings: `environment`, `command`, `init`, `shm_size`, `volumes`, `ports` |
| `--qemu-config`, `--qemu-kernel`, `--qemu-rootfs`, `--qemu-disk` | `qemu.platform` with `config_file`, `kernel`, `rootfs`, `disk` |
| `target.execute(cmd)` returning `(int, bytes)` | `target.command.exec(cmd)` returning `(int, str)` |
| `target.execute_async`, `wrap_exec` | `target.process.spawn(...)`, `WrappedProcess(target.process, ...)` |
| `target.upload`, `download` | `target.files.upload`, `download` |
| `target.restart()` | `session.renew("platform")` |
| `target.ssh()`, `execute_command_output` | `target.shell` (`shell: ssh.shell`): `run`, `exec`, `exec_lines` |
| `target.sftp()` | `target.files` with `files: ssh.files` |
| `target.ping()`, `ping_lost()` | `target.ping.wait_up()`, `wait_down()` |
| `target.get_ip()`, `get_gateway()` | `target.platform.ip()`, `gateway()` |
| `@requires_capabilities("exec")` | `@itf.requires("command")` |
| `DltReceive`, `DltWindow` | `logs: dlt.receive`: `target.logs.lines()`, `record()`, `window()` |
| `dlt_on_target` fixture | `//score/itf/packs/dlt:on_target`, the same fixture |

## Writing a pack instead of a plugin

A plugin that subclassed `Target` becomes a pack: a directory with a `pack.yaml` and decorated functions. A
method of the old class becomes a member of the object a factory returns; a setup step becomes an action with a
probe.

```python
@dataclass
class RelaySettings:
    port: str


class Relay(Protocol):                 # what the action expects of the relay
    __contract__ = "acme/power.relay"

    def switch(self, on: bool) -> None: ...
    def read(self) -> bool: ...


@capability("acme/power.relay")
def relay(config: RelaySettings) -> UsbRelay:
    return UsbRelay(config.port)


@state("acme/power.on")
def power_on(relay: Relay) -> None:
    relay.switch(True)


@power_on.probe
def is_on(relay: Relay) -> bool:
    return relay.read()
```

A project's own parts live in its policy, `policy.py` beside its target file; their labels are `local.<name>`.
Keep pytest fixtures in `conftest.py`: ITF code found in a conftest is an error that points to `policy.py`.

## Effort

| Project | Expected work |
|---|---|
| Uses only Docker or QEMU with `execute`, `upload`, `ssh` | copy the facade, change imports; tests keep running the same day |
| Has its own plugin or `Target` subclass | write a pack or project parts for it; a few functions per capability |
| Depends on fixture ordering between plugins | express the order as `relations:` in the target file |
