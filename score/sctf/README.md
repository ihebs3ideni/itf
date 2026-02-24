# SCTF — Software Component Test Framework

SCTF is a Docker-based testing component within the ITF ecosystem.
It packages your build artifacts (binaries, shared libraries) into an OCI
container image at build time and provides a pytest-driven harness to execute
and observe them at test time.

## Architecture

SCTF is built on top of the ITF plugin system.  There are two orthogonal
pieces:

1. **`sctf_docker()` plugin** — A `py_itf_plugin` factory that can build
   an OCI image from your deps *and* wire it into `py_itf_test`.
2. **`sctf_image()`** — A standalone Bazel macro for building an OCI image
   independently (useful when sharing one image across multiple tests).

There is **only one test macro** (`py_itf_test`) for all test types — ITF
integration tests, SCTF component tests, QEMU tests, etc.  Test behavior
is determined entirely by the plugins list.

### Execution Model

```
┌─────────────────────────────────────────┐
│             Host (pytest)               │
│                                         │
│  py_itf_test                            │
│    ├─ -p score.itf.plugins.core         │
│    ├─ -p score.itf.plugins.docker       │
│    └─ -p score.sctf.plugins             │
│                                         │
│  docker_sandbox fixture                 │
│    └─ DockerEnvironment.from_image()    │
│         └─ DockerContainer (shared)     │
│              └─ docker-py SDK           │
├─────────────────────────────────────────┤
│           Docker Container (SUT)        │
│                                         │
│  OCI image built by sctf_image()        │
│    ├─ base: @ubuntu_24_04               │
│    ├─ layer: solibs (shared libraries)  │
│    └─ layer: tarballs (binaries, data)  │
│                                         │
│  Tests call execute(), copy_to(), etc.  │
└─────────────────────────────────────────┘
```

## Usage

### BUILD file

`sctf_docker()` supports two usage patterns.  Choose based on whether the
image is used by one test or shared across several.

#### Single test, single image *(recommended for one-off tests)*

Use `name` to let `sctf_docker()` create the image inline — simplest,
no extra declarations needed:

```starlark
load("@score_itf//:defs.bzl", "py_itf_test")
load("@score_itf//score/itf/plugins:plugins.bzl", "sctf_docker")

py_itf_test(
    name = "test_my_component",
    srcs = ["test_my_component.py"],
    plugins = [sctf_docker(
        name = "my_image",            # creates sctf_image targets automatically
        deps = [":my_binary_package"],
        # base_image = "@ubuntu_24_04",  # optional, this is the default
    )],
    size = "large",
    timeout = "moderate",
)
```

`deps` is optional — omit it for a bare base-image container:

```starlark
py_itf_test(
    name = "test_base_only",
    srcs = ["test_base_only.py"],
    plugins = [sctf_docker(name = "my_base_image")],
)
```

#### Shared image across multiple tests *(recommended for shared images)*

Declare the image once with `sctf_image()`, then reference it by name
via the `image` parameter.  This keeps target creation visible at the
top level of the BUILD file — the idiomatic Bazel pattern:

```starlark
load("@score_itf//:defs.bzl", "py_itf_test", "sctf_image")
load("@score_itf//score/itf/plugins:plugins.bzl", "sctf_docker")

sctf_image(
    name = "my_image",
    base_image = "@ubuntu_24_04",
    deps = [":my_binary_package"],
)

py_itf_test(
    name = "test_a",
    srcs = ["test_a.py"],
    plugins = [sctf_docker(image = "my_image")],
    size = "large",
    timeout = "moderate",
)

py_itf_test(
    name = "test_b",
    srcs = ["test_b.py"],
    plugins = [sctf_docker(image = "my_image")],
    size = "large",
    timeout = "moderate",
)
```

> **Note:** Avoid calling `sctf_docker(name=...)` once, storing the result
> in a variable, and passing it to multiple `py_itf_test` targets.  While
> that works, it hides Bazel target creation inside a variable assignment,
> making the BUILD file harder to read.  Prefer `sctf_image()` +
> `sctf_docker(image=...)` for the shared case.

### Test file

```python
def test_my_binary(docker_sandbox):
    """The docker_sandbox fixture provides a running container."""
    handle = docker_sandbox.environment.execute(
        "/opt/bin/my_app", ["--config=/etc/app.yaml"]
    )

    # Verify the process ran successfully
    docker_sandbox.environment.stop_process(handle)
    assert handle.exit_code == 0
```

### Key fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `docker_sandbox` | session | A `Bunch` with `.environment` (DockerEnvironment) and `.tmp_workspace` |

### Key APIs

| Method | Description |
|--------|-------------|
| `environment.execute(binary, args, cwd=None, env=None, detach=False)` | Run a process in the container |
| `environment.stop_process(handle, timeout=5)` | Stop a running process |
| `environment.is_process_running(handle)` | Check if a process is still alive |
| `environment.copy_to(src, dst)` | Copy a file from host to container |
| `environment.copy_from(src, dst)` | Copy a file from container to host |

## Design Decisions

### Why `sctf_docker()` is a factory function, not a static struct

Unlike `docker`, `qemu`, or `dlt` which are static plugin structs,
`sctf_docker()` is a function that returns a struct.  This is because:
- When using `name`, it must call `sctf_image()` to create the OCI build
  pipeline before returning the plugin struct.
- When using `image`, the tarball label and `--docker-image` arg depend on
  which `sctf_image()` the test references.

### Why the SCTF plugin doesn't register `--docker-image`

The ITF Docker plugin (`score.itf.plugins.docker`) already registers
`--docker-image` and `--docker-image-bootstrap`.  The SCTF plugin simply
reads these options.  The `sctf_docker()` factory ensures both plugins are
always loaded together by listing both in `enabled_plugins`.  This avoids
option registration conflicts and keeps a single source of truth.

### Where shared code lives

- **`score.itf.core.docker.DockerContainer`** — Single source of truth
  for Docker SDK interactions (container lifecycle, exec, file copy).
  Both `DockerTarget` (ITF plugin) and `DockerEnvironment` (SCTF)
  delegate to it.
- **`score.itf.core.docker.get_docker_client()`** — Shared client
  factory with the `http+docker://` compatibility patch.

## OCI Image Pipeline

The `sctf_image()` macro creates the following intermediate targets:

```
deps ──► collect_solibs ──► pkg_tar (solibs)  ──┐
deps ──► collect_tarballs ──► remap_tar ────────┤
                                                 ├──► oci_image ──► oci_tarball
                                 base_image ────┘
```

- `{name}_solibs` — Shared libraries extracted from transitive deps
- `{name}_solibs_tarball` — Solibs packed into tar.gz at `/usr/bazel/lib`
- `{name}_tarballs` — Tarballs from deps (pkg_tar outputs)
- `{name}_sysroot_remapped` — Sysroot with `/sbin` → `/usr/sbin` remap
- `{name}_image` — OCI image
- `{name}_image_tarball` — Docker-loadable tarball (main output)
