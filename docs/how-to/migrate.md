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

# Migrate from the original plugin API

ITF does not ship the original plugins (`docker_plugin`, `qemu_plugin`, `dlt_plugin`, `core_dump_plugin`) or the
`Target` class. A project with many tests written against them keeps them running with a **facade of its own**: a
composition built from the original options, and a conftest with helpers presenting the composed target in the
old shape. `examples/examples/legacy` is such a project, ready to copy:

- `targets/docker.itf.yaml`, `targets/qemu.itf.yaml` (and `*_dlt.itf.yaml`, which include them): what
  `--docker-image` and `--qemu-config` declared, as compositions with `${LEGACY_*}` settings.
- `conftest.py`: the original options (which select the composition, as `--itf-target` would), and the `target`,
  `docker_configuration`, `dlt_config`, `dlt` and `dlt_on_target` fixtures.
- `legacy_itf/`: `LegacyTarget` (`execute`, `upload`, ... over the composed roles, found by contract), the
  original `Ssh`, `Sftp`, ping and DLT helpers, `requires_capabilities`.
- The original test cases, with only their `score.itf.plugins.*` imports changed to `legacy_itf.*`.

Migrate tests one at a time to the new API below, then delete the facade. Differences seen through it: with
QEMU, DLT recording starts after the machine booted, not before; the container is renewed per test unless
`--keep-target`, as before.

## Mapping

| Original | New |
|---|---|
| `plugins = [".../plugins:docker_plugin"]`, `--docker-image=X` | `packs = ["//score/itf/packs/docker"]` on the `itf_target`; `platform: factory: docker.platform` with `image: X` in `with:` (or in an override file) |
| `--docker-image-bootstrap=$(location :load)` | `with: bootstrap: ${LOAD}` with `env = {"LOAD": "$(location :load)"}` |
| `docker_configuration` fixture | the platform's settings: `environment`, `command`, `init`, `shm_size`, `volumes` (strings), `ports` |
| `--qemu-config/--qemu-kernel/--qemu-rootfs/--qemu-disk` | `qemu.platform` with `config_file`, `kernel`, `rootfs`, `disk` |
| `target.execute(cmd)` returning `(int, bytes)` | `target.command.exec(cmd)` returning `(int, str)` (`command: docker.exec` or `ssh.exec`) |
| `target.execute_async` / `wrap_exec` | `target.process.spawn(...)` / `WrappedProcess(target.process, ...)` |
| `target.upload` / `download` | `target.files.upload` / `download` (`files: docker.files` or `ssh.files`, which is SFTP) |
| `target.restart()` | `target.platform.restart()` then `session.reach(...)`, or `session.renew("platform")` |
| `target.ssh()` / `execute_command_output` | `target.shell` (`shell: ssh.shell`): `run`, `exec`, `exec_lines` |
| `target.sftp()` | `target.files` with `files: ssh.files` (`exists`, `listdir`, `upload_dir`, ...) |
| `target.ping()` / `ping_lost()` | `target.ping.wait_up()` / `wait_down()` (`ping: ping.pinger`) |
| `target.get_ip()` / `get_gateway()` | `target.platform.ip()` / `gateway()` (docker) |
| `@requires_capabilities("exec")` | `@itf.requires("command")` |
| `DltReceive` / `DltWindow` | `logs: dlt.receive`: `target.logs.lines()`, `record()`, `window()` |
| `dlt_on_target` fixture | `//score/itf/packs/dlt:on_target`, same fixture, transport as `"tcp"` or `"udp"` |

`examples/examples/legacy` (original tests on the facade) and `test/integration` (the same ground in the new API)
show both side by side.
