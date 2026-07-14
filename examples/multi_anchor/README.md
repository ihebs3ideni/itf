# Multi-Device Example: Two-SoC ECU

This example models a real automotive ECU with two system-on-chips running
different operating systems inside a single physical device:

| SoC | OS | Capabilities | Flash Tool |
|-----|-----|-------------|-----------|
| **Safety** (device=`"safety"`) | AUTOSAR Classic | Console, Ping, Flash | Lauterbach TRACE32 |
| **Integration** (device=`"integ"`) | Linux 6.1 | SSH, Ping, Flash | Android Fastboot |

Both share a common **device layer** (root descriptor `hw/device`) —
the physical power rail, JTAG probe, and USB hub.

## Architecture

```
              Root Registry (shared facts)
              ┌─────────────────────────────┐
              │ hw/device = {name, psu, ..} │
              └──────────────┬──────────────┘
                   ┌─────────┴─────────┐
                   │                   │
     Safety Assembly              Integ Assembly
     (own registry)               (own registry)
     ┌─────────────────┐         ┌──────────────────────┐
     │ ctf/target      │         │ ctf/target           │
     │ trace32/flash   │         │ fastboot/flash       │
     │ cap/flash       │←bind    │ cap/flash       ←bind│
     │ cap/console     │         │ itf/cap/ssh          │
     │ itf/cap/ping    │         │ itf/cap/ping         │
     └─────────────────┘         └──────────────────────┘
```

Each device has its own Registry and Assembly. Contract strings are plain —
`"ctf/target"` means the same thing in both scopes. Isolation comes from
*where* you register, not from mangling the string.

## Key Concepts Demonstrated

### 1. Per-Device Assemblies (No Contract Tagging)

Each device is a **scope** — its own registry and assembly. Same contracts,
fully isolated resolution:

```python
# Providers are defined once with plain contracts
@provides("ctf/target")
@requires("hw/device")  # cascades from root
def safety_soc(device): ...

@provides("ctf/target")
@requires("hw/device")
def integration_soc(device): ...

# Registration determines scope
with registry.device("safety") as dev:
    dev.register(safety_soc)

with registry.device("integ") as dev:
    dev.register(integration_soc)
```

### 2. Plugin-Specific Flashers + Bindings

Each flasher "plugin" owns its own contract. A generic `cap/flash` capability
delegates to whichever tool is bound in that scope:

```python
# Two flasher plugins — different contracts
@provides("trace32/flash")
@requires("trace32/config")
def trace32_flasher(config): ...

@provides("fastboot/flash")
@requires("fastboot/config")
def fastboot_flasher(config): ...

# Generic capability — requires abstract "flash/tool"
@provides("cap/flash")
@requires("flash/tool")
def flash_capability(tool):
    return tool  # pass-through

# Bindings wire the generic contract to the right tool per device
registry.device_registry("safety").bind("cap/flash", "flash/tool", "trace32/flash")
registry.device_registry("integ").bind("cap/flash", "flash/tool", "fastboot/flash")
```

Tests just say `dut["safety"]["flash"]` — they never know it's TRACE32.

### 3. Independent Lifecycle

Each device can be rebuilt independently via its DeviceProxy:

```python
dut["integ"].rebuild("ctf/target")   # tears down + rebuilds integration only
# safety is completely untouched
```

### 4. Descriptor Cascade (Shared Facts)

The root registry holds shared hardware info. Device registries inherit it
automatically — no need to repeat:

```python
registry.add_descriptor(Descriptor("hw/device", {...}))  # root

# Device providers can @requires("hw/device") — resolves from root
@provides("ctf/target")
@requires("hw/device")
def safety_soc(device): ...
```

### 5. Asymmetric Capabilities

Safety has console but no SSH. Integration has SSH but no console.
Device-level availability checks:

```python
assert not dut["safety"].available("itf/cap/ssh")
assert not dut["integ"].available("cap/console")
```

### 6. Device-Local Aliases

Each DeviceProxy has its own alias table:

```python
dut["safety"].alias("flash", "cap/flash")
dut["safety"]["flash"]  # → Trace32Flasher
dut["integ"]["flash"]   # → FastbootFlasher
```

## Running

```bash
cd /path/to/itf
python -m pytest examples/multi_anchor/ -v --rootdir=examples/multi_anchor
```

## File Structure

```
multi_anchor/
├── conftest.py         # Device + SoC anchors + device tags + per-SoC capability minting
├── test_multi_soc.py   # Tests for all patterns above
└── README.md           # This file
```
