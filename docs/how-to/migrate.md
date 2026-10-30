# Migrate from the original plugin API

ITF no longer ships the original plugins (`docker_plugin`, `qemu_plugin`, `dlt_plugin`,
`core_dump_plugin`) or the `Target` class. A project with many tests written against them keeps
them running with a **legacy infra layer of its own**: a recipe built from the original options and
a conftest with helpers presenting the new target in the old shape. `examples/examples/legacy` is
such a project, ready to copy:

- `recipes/docker.yaml`, `recipes/qemu.yaml`: what `--docker-image` and `--qemu-config` declared.
- `conftest.py`: the original options, and the `target`, `docker_configuration`, `dlt_config`,
  `dlt` and `dlt_on_target` fixtures, on top of the recipe.
- `legacy_itf/`: `LegacyTarget` (`execute`, `upload`, ... over contracts), the original `Ssh`,
  `Sftp`, ping and DLT helpers, `requires_capabilities`.
- The original test cases, with only their `score.itf.plugins.*` imports changed to `legacy_itf.*`.

Migrate tests one at a time to the new API below, then delete the layer.

Differences seen through the example layer: with QEMU, DLT recording starts after the machine
booted, not before; the container is renewed per test unless `--keep-target`, as before.

## Mapping

| Original | New |
|---|---|
| `plugins = [".../plugins:docker_plugin"]`, `--docker-image=X` | `plugins = ["//score/itf/packs/docker"]`, node `docker.instance` with `config: {image: X}` |
| `--docker-image-bootstrap=$(location :load)` | `config: {bootstrap: ${LOAD}}` with `env = {"LOAD": "$(location :load)"}` |
| `docker_configuration` fixture | node config: `environment`, `command`, `init`, `shm_size`, `volumes` (strings), `ports` |
| `--qemu-config/--qemu-kernel/--qemu-rootfs/--qemu-disk` | `qemu.instance` config `config_file`, `kernel`, `rootfs`, `disk` |
| `target.execute(cmd)` → `(int, bytes)` | `target.command.exec(cmd)` → `(int, str)` (`docker.exec` or `ssh.exec`) |
| `target.execute_async` / `wrap_exec` | `target.process.spawn(...)` / `WrappedProcess(target.process, ...)` |
| `target.upload` / `download` | `target.files.upload` / `download` (`docker.files` or `sftp.files`) |
| `target.restart()` | `target.platform.restart()` then `target.reach(...)`, or `target.renew("platform")` |
| `target.ssh()` / `execute_command_output` | `target.shell` (`ssh.shell`): `run`, `exec`, `exec_lines` |
| `target.sftp()` | `target.files` with `sftp.files` (`exists`, `listdir`, `upload_dir`, ...) |
| `target.ping()` / `ping_lost()` | `target.ping.wait_up()` / `wait_down()` (`icmp.ping`) |
| `target.get_ip()` / `get_gateway()` | `target.platform.ip()` / `gateway()` (docker) |
| `@requires_capabilities("exec")` | `@itf.requires("itf.capabilities.exec.command")` |
| `DltReceive` / `DltWindow` | `dlt.receive` provider: `target.logs.lines()`, `record()`, `window()` |
| `dlt_on_target` fixture | `//score/itf/packs/dlt:on_target`, same fixture, transport as `"tcp"`/`"udp"` |

`examples/examples/legacy` (original tests on the legacy layer) and `test/integration` (the same
ground in the new API) show both side by side.
