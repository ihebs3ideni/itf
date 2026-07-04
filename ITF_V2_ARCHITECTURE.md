# ITF v2: Clean Contract-Based Architecture

## Overview

This is a clean implementation of the ITF (Integration Test Framework) v2 with contract-based plugin orchestration. The design emphasizes:

- **Explicit contracts** - Plugins declare what they provide, require, and read/write
- **Typed state channels** - No magic string keys; IDE-friendly context access
- **Structured readiness** - OracleResult objects with clear semantics
- **Phase-ordered orchestration** - Deterministic startup/teardown
- **Composition validation** - Fail fast if plugins don't compose

## Architecture

### Core Framework (`score/itf/framework/`)

#### 1. Contract System (`contract.py`)
- `PluginContract`: Dataclass declaring plugin capabilities and dependencies
- `@plugin_contract`: Decorator for class-level contract attachment

```python
@plugin_contract(
    name="score.itf.plugins.mock_target",
    provides=["target"],
    requires=[],
    writes=["target"],
    phases=["session_start_target_create"],
)
class MockTargetPlugin:
    ...
```

#### 2. Verdict System (`verdict.py`)
- `VerdictType`: Enum (PASS, FAIL, SKIP, WARN)
- `OracleResult`: Structured readiness check result

```python
OracleResult.fail_check(
    name="ssh_ready",
    details="SSH executor not initialized",
    blocking=True,
)
```

#### 3. Context Hub (`context.py`)
- `ItfContext`: Central coordination point
- `ContextState[T]`: Typed state container (replaces magic string keys)

Channels:
- `target`: The system under test
- `target_capability_specs`: Capabilities declared by target
- `capabilities`: Union of all capabilities
- `shared_resources`: Non-test-specific shared state (config, services)
- `extension_state`: Plugin-owned typed state (type -> value)
- `startup_checks`: Readiness check results

```python
# Typed state (clean, IDE-friendly)
@dataclass
class MockTargetState:
    hostname: str
    is_running: bool

state = context.use_state(MockTargetState, owner="mock_target",
                          factory=lambda: MockTargetState(...))

# Old way (deprecated)
context.stash_set("mock.target", "hostname", "...")  # Magic strings!
```

#### 4. Hooks System (`hooks.py`)
- `ItfHooks`: Hook specification with 10 startup phases
- `STARTUP_PHASES`: Ordered tuple for deterministic execution

Phases (in order):
1. `session_start_profile_resolve` - Read config/options
2. `session_start_target_create` - Create system under test
3. `session_start_target_prepare` - Prepare/configure target
4. `session_start_target_capabilities_declare` - List target capabilities
5. `session_start_capabilities_augment` - Derived capabilities
6. `session_start_shared_resources_configure` - Shared data/services config
7. `session_start_services_start` - Start services
8. `session_start_logging_start` - Start logging/capture
9. `session_start_readiness_check` - Validate everything
10. `session_start_environment_freeze` - Final setup complete

#### 5. Orchestrator (`orchestrator.py`)
- `ItfSessionOrchestrator`: Validates composition and executes phases
- `CompositionError`: Raised if plugins don't compose
- `run_itf_session_start()`: Entry point

Validation:
1. Each plugin has `__contract__`
2. All requires are provided by some plugin
3. Warns on channel write conflicts

### Plugins (`score/itf/plugins/`)

Each plugin:
1. Declares a `@plugin_contract`
2. Defines typed state dataclass
3. Implements relevant hook methods
4. Uses `context.use_state()` for data
5. Returns `OracleResult` from readiness checks

#### 1. Mock Target Plugin (`mock_target.py`)
- **Provides**: `target`
- **State**: `MockTargetState` (hostname, running status)
- **Phases**: profile_resolve, target_create, target_prepare
- **Output**: Creates mock container, registers cleanup

#### 2. Mock SSH Plugin (`mock_ssh.py`)
- **Provides**: `ssh_endpoint`, `exec`, `upload`
- **Requires**: `target` (created by mock_target)
- **State**: `MockSshEndpointState` (host, port, username)
- **Phases**: target_capabilities_declare, capabilities_augment
- **Output**: Declares SSH endpoint, derives exec/upload from it

#### 3. Log Capture Plugin (`log_capture.py`)
- **Provides**: `log_capture`
- **State**: `LogCaptureState` (file handle, formatters, redirects)
- **Phases**: shared_resources_configure, logging_start, logging_stop
- **Output**: Writes structured logs to file with format:
  ```
  [YYYY-MM-DD HH:MM:SS.mmm] [LVL] [source] message
  ```

#### 4. JSON Report Plugin (`json_report.py`)
- **Provides**: `json_report`
- **State**: `TestReportState` (test results, timing)
- **Phases**: shared_resources_configure, environment_freeze, cleanup
- **Output**: Writes JSON report with:
  - Global: session timing, target info, capabilities, readiness checks
  - Per-test: name, path, outcome, duration, errors
  - Summary: total/passed/failed/skipped counts

## Usage Example

```python
from score.itf.framework import ItfContext, run_itf_session_start
from score.itf.plugins import MockTargetPlugin, MockSshPlugin
import pluggy

# 1. Create plugin manager
pm = pluggy.PluginManager("itf.hook")
pm.add_hookspecs(ItfHooks)
pm.register(MockTargetPlugin(), name="mock_target")
pm.register(MockSshPlugin(), name="mock_ssh")

# 2. Create context
context = ItfContext()

# 3. Run startup (validates composition, executes phases)
run_itf_session_start(pm, context)

# 4. Now context is fully populated:
#    - context.target: MockTarget instance
#    - context.capabilities: {"ssh", "exec", "upload"}
#    - context.shared_resources["ssh_executor"]: executor for commands

# 5. Run tests with context...

# 6. Run teardown
orchestrator = ItfSessionOrchestrator(pm, context)
orchestrator.execute_teardown()
```

## Plugin Coordination Example

### Example: Mock SSH Augments Capabilities

```
MockTargetPlugin (provides target):
  session_start_target_create() -> context.target = MockTarget(...)

MockSshPlugin (provides ssh_endpoint, requires target):
  session_start_target_capabilities_declare():
    - reads context.target (must exist, provided by MockTargetPlugin)
    - writes context.target_capability_specs["ssh_endpoint"]
    - writes context.capabilities.add("ssh")

  session_start_capabilities_augment():
    - reads context.target_capability_specs["ssh_endpoint"]
    - writes context.shared_resources["ssh_executor"]
    - writes context.capabilities.add("exec")
    - writes context.capabilities.add("upload")

LogCapturePlugin (provides log_capture):
  session_start_logging_start():
    - reads pytest_config.getoption("--itf-log-capture-file")
    - writes context.shared_resources["log_capture_file"]
    - redirects sys.stdout, sys.stderr to file
```

## Key Design Decisions

### 1. Explicit Contracts
- **Why**: Composition errors caught at startup, not runtime
- **Trade-off**: More boilerplate per plugin (5-10 lines)
- **Benefit**: IDE hints, documentation, validation

### 2. Typed State (ContextState[T])
- **Why**: Eliminates magic string keys, enables IDE completion
- **Trade-off**: Must define dataclass per plugin
- **Benefit**: Type safety, single source of truth

### 3. Phase-Ordered Execution
- **Why**: Deterministic ordering ensures no hidden dependencies
- **Trade-off**: Plugins must implement hooks for correct phases
- **Benefit**: Easy to understand flow, easy to debug

### 4. OracleResult for Readiness
- **Why**: Structured results enable rich analysis and reporting
- **Trade-off**: More verbose than boolean returns
- **Benefit**: Can track blocking vs. warning failures, collect details

### 5. Separation of Concerns
- **MockTargetPlugin**: Creates target only (no capabilities)
- **MockSshPlugin**: Declares SSH, derives exec/upload (composition layer)
- **LogCapturePlugin**: Handles all logging concerns
- **JsonReportPlugin**: Handles all reporting concerns

## Migration Path from v1

### Phase 1: Add Contracts (non-breaking)
- Existing plugins add `__contract__` attribute
- Validator logs warnings but doesn't fail
- No other changes needed

### Phase 2: Add Typed States (non-breaking)
- Create `@dataclass` for each plugin's state
- Migrate from `stash_set(ns, key, val)` to `use_state(StateType)`
- Validator ensures proper ownership

### Phase 3: Enforce Contracts (breaking)
- Validator fails at startup if composition invalid
- Requires all plugins to have contracts
- Full validation of read/write channels

## Performance Characteristics

- **Startup**: 10 phases × N plugins = O(10N) hook calls
- **Per-test**: No ITF overhead (tests run as normal pytest)
- **Teardown**: O(N) cleanup callbacks in reverse order
- **Memory**: One ItfContext + typed states (minimal overhead)

## Error Handling

### Composition Errors
- Raised during `validate_composition()` if:
  - Plugin missing `__contract__`
  - Required capability not provided
- Example: `CompositionError: Plugin X requires 'target' but no plugin provides it`

### Blocking Readiness Checks
- Checked after phase `session_start_readiness_check`
- Any `blocking=True` failure stops startup
- Example: `RuntimeError: Blocking readiness checks failed: docker not installed`

### Cleanup Errors
- Logged but don't stop teardown
- Each cleanup callback wrapped in try/except
- Other callbacks still execute if one fails

## Future Enhancements

1. **Dynamic Plugin Loading**: Load plugins from entry points
2. **Phase Dependencies**: Plugins declare which phases they depend on
3. **Async Hooks**: Support async hook implementations
4. **Plugin Dependency Graph**: Visualize plugin composition
5. **Contract Validation Library**: Formal schema validation
6. **Type Stubs**: Generate `.pyi` files for context channels
