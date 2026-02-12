# Branch: `feature/unified-environment-abstraction`

> **Base:** `full-port-from-eclipse-score-itf` (which itself is based on `main`)
>
> **Total diff vs main:** 136 files changed, 5384 insertions, 1173 deletions
>
> This branch contains two logical change sets:
> 1. **Full port from eclipse-score-itf** — restructures ITF and adds SCTF (130 files)
> 2. **Unified Environment abstraction** — the focus of this document (14 files, 1328 insertions)

---

## Summary

This branch introduces a **unified `Environment` abstraction** that allows both **ITF** (Integration Test Framework) and **SCTF** (Software Component Test Framework) to share container/sandbox infrastructure. Previously:

- **ITF** used Docker directly via the Python Docker SDK
- **SCTF** used Bubblewrap (`bwrap`) for lightweight Linux namespace sandboxing

These two paths shared zero code. Now, a common `Environment` interface lets SCTF tests run under **Docker**, **Bubblewrap**, or **no sandbox at all** — selected at build time via a Bazel flag.

---

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `0bf318b` | feat | Full port from eclipse-score-itf: add SCTF + restructured ITF |
| `8759139` | feat | Unified Environment abstraction for ITF and SCTF |
| `0e4397f` | fix | Docker SDK `import_image` API correction |
| `b05b29f` | test | Add docker backend test target for `test_simple_environment` |
| `20aead1` | fix | Starlark syntax in `py_sctf_test` and add `main` attr for docker target |
| `cd30e09` | feat | Switch SCTF backend from per-target param to build flag with `select()` |

---

## Architecture

### Environment ABC

A new package at `score/itf/core/environment/` provides three interchangeable backends:

```
Environment (ABC)  ──  score/itf/core/environment/base.py
├── setup()                    Prepare the sandbox/container
├── teardown()                 Destroy it
├── execute(path, args, cwd)   → ProcessHandle
├── stop_process(handle)       → exit_code
├── is_process_running(handle) → bool
├── copy_to(host, env)         File transfer into environment
├── copy_from(env, host)       File transfer out of environment
└── __enter__ / __exit__       Context manager support
```

| Backend | Class | How it works |
|---------|-------|-------------|
| **Bubblewrap** | `BwrapEnvironment` | Constructs `bwrap` CLI with bind-mounts and PID namespace. Spawns processes via `psutil.Popen`. |
| **Docker** | `DockerEnvironment` | Creates containers from images (`from_image()`) or sysroot tarballs (`from_sysroot()`). Runs binaries via `docker exec`. |
| **None** | `NoopEnvironment` | Runs binaries directly on the host — useful for debugging without isolation. |

`ProcessHandle` is a dataclass that uniformly tracks spawned processes regardless of backend (PID, exit code, backend-specific references).

### Backend Selection via Bazel Flag

Instead of duplicating test targets per backend, the backend is selected at build time:

```
┌─────────────────────────────────────────────────┐
│  .bazelrc alias                                 │
│    --config=sctf-docker                         │
│         ↓                                       │
│  Bazel string_flag                              │
│    --//bazel:sctf_backend=docker                │
│         ↓                                       │
│  select() in py_sctf_test.bzl                   │
│    deps += [requirement("docker")]              │
│    args += ["--sctf-backend=docker"]            │
│         ↓                                       │
│  basic_sandbox.py plugin                        │
│    reads --sctf-backend, creates                │
│    DockerEnvironment / BwrapEnvironment / Noop  │
└─────────────────────────────────────────────────┘
```

---

## Files Changed (environment abstraction only)

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `score/itf/core/environment/__init__.py` | 25 | Package init, re-exports all backends |
| `score/itf/core/environment/base.py` | 146 | `Environment` ABC + `ProcessHandle` dataclass |
| `score/itf/core/environment/bwrap.py` | 369 | Bubblewrap backend (refactored from `BwrapSandbox`) |
| `score/itf/core/environment/docker_env.py` | 371 | Docker backend (`from_image` and `from_sysroot` modes) |
| `score/itf/core/environment/noop.py` | 161 | No-sandbox backend |
| `score/itf/core/environment/BUILD` | 47 | Bazel targets (`:environment` and `:environment_lite`) |

### Modified Files

| File | Change |
|------|--------|
| `bazel/BUILD` | Added `string_flag` for `sctf_backend` + 3 `config_setting`s |
| `bazel/py_sctf_test.bzl` | Replaced `backend` param with `select()` on flag; disabled precompilation |
| `.bazelrc` | Added `sctf-bwrap`, `sctf-docker`, `sctf-none` config aliases |
| `test/BUILD` | Cleaned up to single `test_simple_environment` target |
| `score/sctf/plugins/basic_sandbox.py` | Added `--sctf-backend` pytest option + environment factory |
| `score/sctf/sandbox/sandbox.py` | Added deprecation notice + re-exports from new package |
| `score/sctf/BUILD` | Added `//score/itf/core/environment` dependency |
| `score/itf/plugins/docker.py` | Delegates to `DockerEnvironment` instead of raw Docker SDK |
| `score/itf/plugins/BUILD` | Added `//score/itf/core/environment` dependency |

---

## Usage

### Running SCTF tests with different backends

```bash
# Bwrap (default)
bazel test //test:test_simple_environment --config=sctf

# Docker
bazel test //test:test_simple_environment --config=sctf --config=sctf-docker

# No sandbox
bazel test //test:test_simple_environment --config=sctf --config=sctf-none
```

### Running without Bazel (pytest directly)

```bash
cd /home/iheb/workspace/itf

# Bwrap
TEST_UNDECLARED_OUTPUTS_DIR=/tmp/out PYTHONPATH=. \
  python -m pytest test/test_simple_environment.py \
  -p score.sctf.plugins.basic_sandbox --sctf-backend=bwrap -v

# Docker
TEST_UNDECLARED_OUTPUTS_DIR=/tmp/out PYTHONPATH=. \
  python -m pytest test/test_simple_environment.py \
  -p score.sctf.plugins.basic_sandbox --sctf-backend=docker -v

# None
TEST_UNDECLARED_OUTPUTS_DIR=/tmp/out PYTHONPATH=. \
  python -m pytest test/test_simple_environment.py \
  -p score.sctf.plugins.basic_sandbox --sctf-backend=none -v
```

### Writing new SCTF tests

Test code is backend-agnostic. The environment is injected via the `basic_sandbox` fixture:

```python
# test_my_component.py
import logging

logger = logging.getLogger(__name__)

def test_my_component(basic_sandbox):
    """Run a binary inside the sandbox and verify it works."""
    env = basic_sandbox.environment  # unified Environment object

    # Execute a binary inside the environment
    handle = env.execute("/usr/bin/echo", ["hello"])
    exit_code = env.stop_process(handle, timeout=5)
    assert exit_code == 0

    logger.info("Component test passed!")
```

BUILD file — just one target, backend chosen at build time:

```starlark
load("//:defs.bzl", "py_sctf_test")

py_sctf_test(
    name = "test_my_component",
    srcs = ["test_my_component.py"],
)
```

### Backward Compatibility

The `basic_sandbox` fixture exposes both:
- `basic_sandbox.sandbox` — legacy `BwrapSandbox` object (for existing tests)
- `basic_sandbox.environment` — new unified `Environment` instance

Existing tests using `basic_sandbox.sandbox` continue to work unchanged.

---

## Verified Test Results

All three backends tested and passing via Bazel:

| Backend | Command | Result |
|---------|---------|--------|
| bwrap | `--config=sctf` | PASSED (1.2s) |
| docker | `--config=sctf --config=sctf-docker` | PASSED (2.4s) |
| none | `--config=sctf --config=sctf-none` | PASSED |

---

## Known Limitations

- **Not fully hermetic:** `bwrap` binary and Docker daemon are host dependencies, not managed by Bazel
- **Tags can't use `select()`:** The `requires-docker` tag cannot be conditionally applied via the build flag (Bazel limitation). Currently omitted — Docker tests work but won't be automatically filtered by CI tag-based test selection
- **ITF partial integration:** ITF's `docker.py` plugin delegates container lifecycle to `DockerEnvironment` but ITF tests still access the raw container object directly via `target.container.exec_run()`
