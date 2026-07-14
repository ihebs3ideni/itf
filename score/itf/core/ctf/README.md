# CTF — Composable Target Framework

A **reusable, test-runner-agnostic** composition engine for building Devices
Under Test (DUT).

## What it does

CTF resolves a deterministic dependency graph of *descriptors* (opaque facts)
and *providers* (factory functions) keyed by string *contracts*. The result is a
composed `DUT` — a lazy, cached view over all resolved resources for a test
session.

## Key concepts

| Concept      | Role                                                        |
|--------------|-------------------------------------------------------------|
| **Contract** | A string key (`"ctf/cap/exec"`) naming a capability or fact |
| **Descriptor** | An opaque value published by a target (e.g. IP address)   |
| **Provider** | A factory (`@provides` / `@requires`) that transforms deps  |
| **Registry** | Single-source-of-truth: one provider per contract           |
| **Assembly** | Session-lived cache + teardown stack                        |
| **DUT**      | Runtime view over the assembly (require, invalidate, query) |

## Design principles

1. **No pytest dependency** — CTF never imports pytest. Integration with test
   runners is the consumer's responsibility (ITF does this for pytest).
2. **Contract-based** — One provider per contract, many consumers.
3. **Deterministic** — Same registry → same resolution order, always.
4. **Lazy + cached** — Resources instantiate on first `require()`, cached for
   the session. Teardown in reverse instantiation order.
5. **Recovery** — `invalidate(contract)` tears down a resource and its
   transitive dependents for mid-run recovery (reflash, reconnect, etc.).
6. **Run modes** — `STRICT` (all must resolve) or `LOOSE` (only the target
   spine must resolve; additive caps that can't resolve become skips).

## Usage (standalone, no pytest)

```python
from score.itf.core.ctf import Registry, compose, provides, requires, Descriptor

registry = Registry()
registry.add_descriptor(Descriptor("my/ip", value="192.168.1.1"))

@provides("my/ping")
@requires("my/ip")
def ping_factory(ip):
    return lambda: f"pinging {ip}"

registry.register(ping_factory)

with compose(registry) as dut:
    ping = dut.require("my/ping")
    print(ping())  # "pinging 192.168.1.1"
```

## Multi-Device Support

Each device gets its own Registry and Assembly. Contract strings are never
modified — the same `"itf/cap/ssh"` contract can exist independently in
multiple device scopes. Descriptor lookups cascade from device → root, so
shared facts (PSU, JTAG probe) are visible to all devices without repetition.

```python
from score.itf.core.ctf import Registry, Descriptor, compose, provides, requires

@provides("my/ping")
@requires("net/ip")
def ping_factory(ip):
    return lambda: f"pinging {ip}"

registry = Registry()

# Shared root descriptor (visible to all devices via cascade)
registry.add_descriptor(Descriptor("hw/psu", {"rail": "12V"}))

# Device scopes — same contracts, independent assemblies
with registry.device("safety") as dev:
    dev.add_descriptor(Descriptor("net/ip", "10.0.0.1"))
    dev.register(ping_factory)

with registry.device("integ") as dev:
    dev.add_descriptor(Descriptor("net/ip", "10.0.0.2"))
    dev.register(ping_factory)

with compose(registry) as dut:
    # Each device has its own "my/ping" — resolved independently
    dut["safety"].require("my/ping")()  # "pinging 10.0.0.1"
    dut["integ"].require("my/ping")()   # "pinging 10.0.0.2"
    dut.devices()                        # frozenset({"safety", "integ"})
```

**Key rules:**
- Contracts are plain strings — no tagging, no mangling
- `registry.device("name")` creates a child registry with parent=root
- Descriptors cascade (device → root); providers are local only
- Each device builds its own Assembly — fully isolated resolution

## Introspection

The DUT provides runtime auto-documentation of providers:

```python
with compose(registry) as dut:
    # Inspect a single contract
    info = dut.inspect("my/ping")
    print(info.return_type)       # type annotation from factory
    print(info.factory_name)      # "ping_factory"
    print(info.requires)          # ("my/ip",)
    print(info.public_methods)    # methods on the resolved object

    # Human-readable help
    print(dut.help())             # formatted docs for all contracts
```

## Bazel

```starlark
deps = ["//score/itf/core/ctf"]
```

## Integration with ITF

ITF wraps CTF with pytest hooks and phased lifecycle management. Users import
the ITF plugin in their conftest:

```python
pytest_plugins = ["score.itf.core.itf_plugin"]
```

This gives them the `dut` fixture, phased hooks (`pytest_itf_declare`,
`pytest_itf_provision`, `pytest_itf_verify`), and automatic lifecycle
management.
