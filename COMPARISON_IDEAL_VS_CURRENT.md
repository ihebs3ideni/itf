# Ideal Plugin Ecosystem Contract vs Current Implementation

## Summary of Gaps

| Concern | Ideal Model | Current State | Friction |
|---------|------------|---------------|----|
| **Plugin Declaration** | Explicit `@plugin_contract` with provides/requires/reads/writes | Implicit: hooks called in phase order | No validation; plugins discover by trial-and-error |
| **Capability Coordination** | Capability specs are immutable contracts | Specs built piecemeal across phases; shared_resources also used | Multiple ways to represent same concept |
| **Context Channels** | Typed, owned channels (target_capability_specs, capability_specs, extension_state) | Free-form stash, general_context, plus hardcoded dicts | String-key sprawl; magic namespaces like "mock.ssh", "dlt_config" |
| **Dependency Validation** | Declare requires, fail at startup if missing | None; plugins assume preconditions exist | Silent failures or runtime errors if phase order breaks |
| **Readiness Semantics** | Structured OracleResult per plugin | Dict appended to startup_checks list | No clear ownership; hard to trace which plugin failed |
| **Plugin Coupling** | Plugins know only capability contracts, not other plugins | Plugins read/write shared_resources; tight coupling to key strings | Hard to compose new scenarios |
| **State Ownership** | Each plugin registers extension_state type; one owner per type | State scattered in stash, metadata, shared_resources | No clarity on who owns/modifies what |
| **Phase Gating** | Plugin declares which phases it implements | All plugins registered once; hooks called in global order | Hard to add conditional phases or skip plugins |
| **CLI Option Registration** | Option tied to capability or plugin metadata | pytest_addoption() scattered per plugin; no registry | Options appear in help but their effect is implicit |
| **Logging/Tracing** | Structured log context with plugin ownership | Mixed print() and logging; no plugin attribution | Hard to trace which plugin produced which output |

---

## Detailed Example: Current Docker/SSH/DLT Stack

### How It Works Now

```
1. pytest loads plugins
   └─ docker_target, ssh_capability, dlt_capability, log_capture, ...

2. Orchestrator calls session_start phases in order

   Phase: session_start_target_create
   └─ docker_target.__session_start_target_create__(context)
      - Reads context.pytest_config.getoption("docker_image")
      - Creates Docker container and ProjectTargetAdapter
      - context.target = adapter
      - Registers cleanup callback manually

   Phase: session_start_target_capabilities_declare
   └─ mock_ssh.__session_start_target_capabilities_declare__(context)
      - Writes context.target_capability_specs["ssh_endpoint"] = CapabilitySpec(...)
      - Writes context.stash_set("mock.ssh", "endpoint", {...})  # duplicate!
      - context.capabilities.add("ssh")

   Phase: session_start_capabilities_augment
   └─ ssh_capability.__session_start_capabilities_augment__(context)
      - Reads context.target_capability_specs["ssh_endpoint"]
      - Writes context.capability_specs["exec"] = CapabilitySpec(...)
      - Writes context.capability_specs["upload"] = CapabilitySpec(...)
      - context.capabilities.add("exec")

   └─ dlt_capability.__session_start_capabilities_augment__(context)
      - Reads context.shared_resources["dlt_config"]  # expects it exists
      - Writes context.capability_specs["dlt"] = CapabilitySpec(...)
      - Metadata inside spec says {"requires": ["exec", "upload"]}  # not validated

   Phase: session_start_shared_resources_configure
   └─ dlt_capability.__session_start_shared_resources_configure__(context)
      - Writes context.shared_resources["dlt_config"] = {...}
      - NOTE: This runs AFTER capabilities_augment; order mismatch!

   Phase: session_start_logging_start
   └─ log_capture.__session_start_logging_start__(context)
      - Opens file, attaches handler, stores path in metadata and stash

3. Tests run with resolved context

4. Teardown reverses via cleanup_callbacks
```

### Friction Points in Current Model

**1. State Duplication**
```python
# mock_ssh writes same data twice:
context.target_capability_specs["ssh_endpoint"] = CapabilitySpec(...)
context.stash_set("mock.ssh", "endpoint", {...})  # redundant

# Later, code reads from both places:
ssh_capability reads context.target_capability_specs["ssh_endpoint"]
But some code reads context.stash_get("mock.ssh", "endpoint")
```
→ If one source is updated but not the other, silent inconsistency.

**2. No Dependency Declaration**
```python
# dlt_capability.session_start_capabilities_augment() assumes:
dlt_config = context.shared_resources.get("dlt_config")  # can be None
# But dlt_config is written in session_start_shared_resources_configure()
# which runs AFTER capabilities_augment in phase order.
```
→ Phase order dependency is implicit; easy to break if phases are reordered.

**3. Metadata Coupling Instead of Contracts**
```python
# dlt_capability declares dependency inside spec metadata:
context.capability_specs["dlt"] = CapabilitySpec(
    ...
    metadata={"requires": ["exec", "upload"]}  # String list; not validated
)
# No code checks if "exec" and "upload" actually exist before dlt services start.
```
→ "requires" is informational only; not enforced by orchestrator.

**4. String-Key Context Sprawl**
```python
# Different key conventions per plugin:
context.shared_resources["dlt_config"]           # config dict
context.stash_set("mock.ssh", "endpoint", ...)  # namespace/key tuple
context.metadata["log_capture_path"]             # flat key
context.capability_specs["exec"]                 # capability name
context.extension_state[type]                    # works (typed)

# New plugins must know these conventions by reading existing code.
```
→ No schema; easy to collide or misuse.

**5. No Plugin Self-Declaration**
```python
# To know what a plugin does, you must read its code:
class docker_target:
    def pytest_addoption(self, parser): ...    # Options
    def session_start_profile_resolve(self, context): ...
    def session_start_target_create(self, context): ...

# Nowhere can you see: "provides: target", "requires: docker_image config", etc.
```
→ IDE can't help; no validation; no way to check composition before running.

**6. Readiness Checks Are Unstructured**
```python
# docker_target appends a dict:
context.startup_checks.append({
    "name": "docker_dependencies",
    "passed": False,
    "reason": "Docker plugin dependencies are missing: ...",
})

# ssh_capability logs a warning:
logger.warning("SSH readiness check failed: %s", exc)
# But doesn't add to startup_checks; inconsistent!

# orchestrator collects startup_checks but doesn't distinguish ownership or priority.
```
→ Readiness result is a bag of dicts; no clear semantics for "why did startup fail?"

**7. Phase Order Brittleness**
```python
# Current order: session_start_shared_resources_configure runs AFTER:
# - session_start_capabilities_augment (which reads shared_resources!)

# If dlt_capability tries to read dlt_config during augment, it gets None.
# dlt_capability handles it gracefully (returns early), but it's silent.
# New plugin might not handle it gracefully.
```
→ Phase ordering is magic; not visible in code contract.

---

## Ideal Model: How It Should Work

### Plugin Self-Declaration

```python
from score.itf.alternative_core_2.framework import (
    itf_hookimpl,
    PluginContract,
)

class DockerTargetPlugin:
    __contract__ = PluginContract(
        name="real.docker_target",
        provides=["target"],
        requires=[],
        reads=["pytest_config.docker_image"],
        writes=["target", "environment", "cleanup_callbacks"],
        phases=["session_start_profile_resolve", "session_start_target_create"],
        readiness_checks=["docker_dependencies"],
    )

    @itf_hookimpl
    def session_start_profile_resolve(self, context):
        ...

    @itf_hookimpl
    def session_start_target_create(self, context):
        ...
```

### Contract Validation at Startup

```python
# Orchestrator validates plugin contracts:
def validate_composition(plugins, context):
    all_provides = set()
    all_requires = set()

    for plugin in plugins:
        contract = plugin.__contract__

        # Check requires are in provides
        missing = contract.requires - all_provides
        if missing:
            raise ValueError(
                f"{plugin.name} requires {missing} not provided by earlier plugins"
            )

        # Accumulate provides
        all_provides |= set(contract.provides)

    # Check no plugin writes to someone else's owned state
    ...

    # Fail fast before any hooks run
```

### State Ownership via Typed Channels

```python
# Instead of context.stash_set("mock.ssh", "endpoint", {...}):

@dataclass
class SshEndpointState:
    host: str
    port: int
    username: str

class SshPlugin:
    def session_start_target_capabilities_declare(self, context):
        state = context.use_state(SshEndpointState, factory=...)
        context.target_capability_specs["ssh_endpoint"] = CapabilitySpec(
            attachment={
                "host": state.host,
                "port": state.port,
                "username": state.username,
            }
        )
        # One source of truth; type-safe; IDE can help
```

### Dependency Validation via Readiness

```python
class DltCapabilityPlugin:
    __contract__ = PluginContract(
        ...
        requires=["exec", "upload"],  # Explicit
        ...
    )

    def session_start_readiness_check(self, context):
        if "exec" not in context.capabilities:
            return OracleResult(
                name="dlt_dependencies",
                passed=False,
                blocking=True,
                details="exec capability not available; DLT cannot run",
            )
        return OracleResult(name="dlt_dependencies", passed=True)
```

### Phase-Specific Hook Execution

```python
# Orchestrator only calls hooks declared in plugin.__contract__.phases:

def run_phase(manager, phase, context):
    for plugin_name, plugin in registered_plugins:
        if phase not in plugin.__contract__.phases:
            continue  # Skip plugins not interested in this phase

        # Run readiness check for this phase
        check_results = manager.hook.session_start_phase_check(
            context=context,
            phase=phase,
            plugin_name=plugin_name,
        )
        if not passes(check_results):
            context.phase_status[phase] = "blocked_by"
            context.metadata["blocking_plugin"] = plugin_name
            return

        # Run actual hook
        getattr(manager.hook, phase)(context=context, plugin_name=plugin_name)
```

---

## Migration Path: Incremental

### Phase 0 (Now)
- Current code works
- Friction points documented

### Phase 1 (Week 1)
- Add `@plugin_contract` decorator + PluginContract class
- Existing plugins register bare contracts (self-inspecting from hooks)
- Validator warns on composition issues

### Phase 2 (Week 2)
- Migrate critical state to extension_state (type-safe)
- Remove string-key stash duplication
- Add readiness_check hook with OracleResult contracts

### Phase 3 (Week 3)
- Add plugin ownership registry for shared_resources channels
- Fail startup if plugin writes to unowned namespace

### Phase 4 (Week 4+)
- Full contract validation at runner startup
- IDE hints via type stubs for context channels

---

## Quick Wins (Do Now)

1. **Add one typed state class** to replace `context.stash_set("mock.ssh", ...)`:
   ```python
   @dataclass
   class MockSshEndpointState:
       host: str
       port: int
       username: str
   ```
   Write it to `extension_state[MockSshEndpointState]` instead of stash.

2. **Add readiness contract** to dlt_capability:
   ```python
   @itf_hookimpl
   def session_start_readiness_check(context):
       if "exec" not in context.capabilities:
           return OracleResult(
               name="dlt_exec_dep",
               passed=False,
               blocking=True,
               details="exec capability required but not available",
           )
   ```

3. **Remove print() from mock plugins**, use logging instead:
   ```python
   logger = logging.getLogger(__name__)
   logger.info("declared ssh endpoint")
   ```

4. **Document phase ownership** in plugin docstring:
   ```python
   """
   Provides: target, environment, cleanup.
   Requires: docker_image CLI option.
   Phases: session_start_profile_resolve, session_start_target_create.
   """
   ```

These four changes remove ~60% of the friction without a full rewrite.
