# SCTF — Software Component Test Framework

SCTF is a Docker-based testing component within the ITF ecosystem.
It packages your build artifacts (binaries, shared libraries) into an OCI
container image at build time and provides a pytest-driven harness to execute
and observe them at test time.

## Why `py_sctf_test` and `py_itf_test` are separate macros

At first glance the two macros look similar — both produce a `py_test` that
runs pytest against a Docker container.  However, they solve fundamentally
different problems and merging them would weaken both.

### What each macro does

| | `py_itf_test` | `py_sctf_test` |
|---|---|---|
| **Image source** | A pre-built, externally-provided image (`--docker-image=ubuntu:24.04`) | Builds an OCI image *from your Bazel deps* at analysis time |
| **Build graph** | Lightweight — `py_test` wrapped in `test_as_exec` | Heavy — `collect_solibs` → `pkg_tar` → `oci_image` → `oci_tarball` (5+ intermediate targets) |
| **Plugin model** | Composable `py_itf_plugin` structs — user picks and combines `docker`, `qemu`, `dlt`, etc. | Hardcodes `score.sctf.plugins` + the ITF docker plugin; extra plugins are plain strings |
| **Execution model** | `test_as_exec` (cross-platform exec config support) | Direct `py_test` (Linux-only by convention) |
| **Test fixture** | `target` — a `DockerTarget` wrapping the raw docker-py container | `docker_sandbox` — yields an `Environment` with structured process tracking (`ProcessHandle`), `execute()` / `stop_process()` lifecycle |
| **Use case** | *"I have a container; run tests against it"* (integration testing) | *"Package my software into a container and test it there"* (component testing) |

### Why merging would hurt

1. **Unnecessary OCI pipeline overhead.**
   Most ITF Docker tests point at an existing image (`ubuntu:24.04`,
   `linuxserver/openssh-server`, …).  They have zero build artifacts to
   package.  Merging would either force the OCI pipeline on every test
   (wasted build time) or require a flag to skip it — adding complexity
   with no benefit.

2. **Conflicting plugin architectures.**
   `py_itf_test` uses the `py_itf_plugin` struct system: each plugin
   declares its `py_library`, `enabled_plugins`, `args`, `data`,
   `data_as_exec`, and `tags`.  The macro iterates over the list
   generically.  `py_sctf_test` hardcodes its plugin set because it
   *must* always have the SCTF plugin and the ITF docker plugin — those
   are not optional.  Cramming both models into one macro means either
   special-casing SCTF inside the generic loop or duplicating the
   generic loop inside SCTF, neither of which is cleaner than two
   focused macros.

3. **Different `py_test` wrappers.**
   `py_itf_test` wraps `py_test` in `test_as_exec` to support
   cross-platform execution configurations (data built for exec vs
   target platform).  `py_sctf_test` emits a plain `py_test` because
   its OCI pipeline already handles all packaging.  A merged macro
   would need conditional wrapper selection — another `if` branch with
   no upside.

4. **Divergent lifecycle contracts.**
   The `target` fixture (ITF) and `docker_sandbox` fixture (SCTF)
   expose different APIs to test code.  `target` proxies the raw
   docker-py container (`exec_run`, `get_ip`, `ssh()`).  `docker_sandbox`
   exposes the `Environment` interface (`execute()`, `stop_process()`,
   `copy_to()`, `copy_from()`) with process-handle tracking.  These
   are intentionally different abstractions — one is thin and direct,
   the other is structured and observable.

### Where shared code lives

The macros are separate, but they share everything that *should* be
shared:

- **`score.itf.core.docker.DockerContainer`** — the single source of
  truth for Docker SDK interactions (container lifecycle, exec, file
  copy).  Both `DockerTarget` (ITF plugin) and `DockerEnvironment`
  (SCTF) delegate to it.
- **`score.itf.core.docker.get_docker_client()`** — shared client
  factory with the `http+docker://` compatibility patch.
- **`sctf_docker` plugin in `plugins.bzl`** — allows `py_itf_test` to
  compose with SCTF if ever needed, without merging the macros.

### Decision

Keep two macros.  Each has a single, well-defined responsibility.
Shared infrastructure lives in `score.itf.core.docker`.  If a future
use case requires both OCI packaging *and* the ITF plugin system,
compose them via the `sctf_docker` plugin struct rather than merging
the macros.
