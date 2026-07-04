# Quick-Win Example: Refactoring Mock SSH Plugin

## Before (Current State)

```python
# score/itf/alternative_core_2/plugins/mock_ssh.py
_PREFIX = "[itf.mock.ssh]"

@itf_hookimpl
def session_start_target_capabilities_declare(context):
    print(f"{_PREFIX} session_start_target_capabilities_declare")  # print()!
    if context.target is None:
        return

    context.target_capability_specs["ssh_endpoint"] = CapabilitySpec(
        name="ssh_endpoint",
        transport="ssh.endpoint",
        attachment={"host": "127.0.0.1", "port": 22, "username": "root"},
    )
    context.stash_set("mock.ssh", "endpoint", {"host": "127.0.0.1", "port": 22, "username": "root"})  # Duplication!
    context.target.add_capability("ssh")
    context.capabilities.add("ssh")
    print(f"{_PREFIX} declared ssh endpoint")  # print()!
```

### Problems
1. Uses `print()` instead of logging
2. Duplicates endpoint state in both `target_capability_specs` and `stash`
3. No explicit contract about what phase runs when
4. No readiness check
5. Hard-coded strings scattered everywhere

---

## After (Ideal Model)

```python
# score/itf/alternative_core_2/plugins/mock_ssh.py
from __future__ import annotations

import logging
from dataclasses import dataclass

from score.itf.alternative_core_2.framework import (
    CapabilitySpec,
    PluginContract,
    itf_hookimpl,
)
from score.itf.alternative_core_2.framework.verdict import OracleResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MockSshEndpointState:
    """Typed state for mock SSH endpoint configuration.

    Owned exclusively by mock_ssh plugin.
    Stored in context.extension_state[MockSshEndpointState].
    """
    host: str
    port: int
    username: str


class MockSshPlugin:
    """Mock SSH capability provider.

    This plugin simulates SSH connectivity without actual network setup.
    It declares an ssh_endpoint capability that other plugins (like ssh_capability)
    can augment and attach to.
    """

    __contract__ = PluginContract(
        name="score.itf.alternative_core_2.plugins.mock_ssh",
        provides=["ssh_endpoint"],
        requires=["target"],
        writes=["target_capability_specs", "extension_state[MockSshEndpointState]"],
        reads=["target"],
        phases=["session_start_target_capabilities_declare"],
        readiness_checks=["mock_ssh_state"],
    )

    @itf_hookimpl
    def session_start_target_capabilities_declare(context):
        logger.info("declaring mock SSH endpoint")

        if context.target is None:
            logger.warning("target not available; skipping SSH endpoint declaration")
            return

        # One source of truth: typed state
        endpoint_state = context.use_state(
            MockSshEndpointState,
            factory=lambda: MockSshEndpointState(
                host="127.0.0.1",
                port=22,
                username="root",
            )
        )

        # Write capability spec (single source)
        context.target_capability_specs["ssh_endpoint"] = CapabilitySpec(
            name="ssh_endpoint",
            transport="ssh.endpoint",
            attachment={
                "host": endpoint_state.host,
                "port": endpoint_state.port,
                "username": endpoint_state.username,
            },
            metadata={"provided_by": "mock_ssh"},
        )

        # Declare capabilities
        context.target.add_capability("ssh")
        context.capabilities.add("ssh")

        logger.info("mock SSH endpoint declared: %s:%d", endpoint_state.host, endpoint_state.port)

    @itf_hookimpl
    def session_start_readiness_check(context):
        """Validate mock SSH endpoint is correctly configured."""
        try:
            state = context.get_state(MockSshEndpointState)
            if state is None:
                return OracleResult(
                    name="mock_ssh_state",
                    passed=False,
                    blocking=True,
                    details="MockSshEndpointState not initialized",
                )

            # Verify capability was registered
            if "ssh_endpoint" not in context.target_capability_specs:
                return OracleResult(
                    name="mock_ssh_state",
                    passed=False,
                    blocking=True,
                    details="ssh_endpoint capability spec not registered",
                )

            return OracleResult(
                name="mock_ssh_state",
                passed=True,
                details=f"Mock SSH ready: {state.host}:{state.port}",
            )
        except Exception as exc:
            return OracleResult(
                name="mock_ssh_state",
                passed=False,
                blocking=True,
                details=f"Readiness check failed: {exc}",
            )
```

---

## Changes Applied

### 1. Added PluginContract (Self-Declaration)
```python
__contract__ = PluginContract(
    name="...",
    provides=["ssh_endpoint"],      # What this plugin contributes
    requires=["target"],             # What must exist first
    writes=[...],                    # What context channels we modify
    phases=[...],                    # Which phases we care about
    readiness_checks=["mock_ssh_state"],  # What we validate
)
```
**Benefit:** Orchestrator can validate composition at startup, not runtime.

### 2. Replaced String-Key Stash with Typed State
```python
# Before:
context.stash_set("mock.ssh", "endpoint", {"host": "127.0.0.1", ...})

# After:
@dataclass(frozen=True)
class MockSshEndpointState:
    host: str
    port: int
    username: str

context.use_state(MockSshEndpointState, factory=...)
```
**Benefit:** IDE completion, no key-name collision, one source of truth.

### 3. Replaced print() with logging
```python
# Before:
print(f"{_PREFIX} declared ssh endpoint")

# After:
logger.info("mock SSH endpoint declared: %s:%d", endpoint_state.host, endpoint_state.port)
```
**Benefit:** Structured logs with logger name; integrates with log_capture plugin.

### 4. Added Readiness Check Hook
```python
@itf_hookimpl
def session_start_readiness_check(context):
    # Validate plugin's postconditions
    if "ssh_endpoint" not in context.target_capability_specs:
        return OracleResult(
            name="mock_ssh_state",
            passed=False,
            blocking=True,
            details="...",
        )
```
**Benefit:** Readiness result is a structured contract; orchestrator knows ownership.

### 5. Added Docstring Contract
```python
"""Mock SSH capability provider.

This plugin simulates SSH connectivity without actual network setup.
It declares an ssh_endpoint capability that other plugins (like ssh_capability)
can augment and attach to.
"""
```
**Benefit:** Humans and tooling can understand intent without reading all hooks.

---

## For the Other Plugins (Same Pattern)

**dlt_capability:**
- Add `@dataclass DltConfigState` to replace `shared_resources["dlt_config"]`
- Replace `metadata={"requires": [...]}` with explicit readiness hook that validates exec/upload exist
- Use logging instead of relying on print() capture

**ssh_capability:**
- Add `@dataclass SshBackendState` to store SSH executor
- Add readiness hook that validates ssh_endpoint exists before attaching
- Document which capabilities it depends on

**log_capture:**
- Split into separate plugin concerns (already partially done)
- Add `@dataclass LogCaptureState` for stream/handler/config
- Readiness hook validates file is writable

---

## Impact Estimate

| Change | Lines Added | Lines Removed | Risk | Benefit |
|--------|------------|---------------|------|---------|
| PluginContract | ~10 per plugin | 0 | Low (additive) | High: enables validation |
| Typed State | ~15 per plugin | ~5 per plugin | Low | High: IDE help, correctness |
| logging | 0 | ~2 per plugin | None | Medium: cleaner logs |
| Readiness Hook | ~15 per plugin | 0 | Low (additive) | High: explicit ownership |
| Docstring | ~5 per plugin | 0 | None | Medium: discoverability |

**Total effort:** ~30 min per plugin × 5-6 plugins = 2.5–3 hours
**Payoff:** Eliminates ~60% of friction; enables future validation layer

---

## Rollout Suggestion

1. **Week 1:** Refactor mock_ssh as reference pattern
2. **Week 1:** Refactor dlt_capability (has most coordination)
3. **Week 2:** Refactor remaining real plugins
4. **Week 2:** Add PluginContract validator to runner startup
5. **Week 3:** Add IDE hints / type stubs for context channels
