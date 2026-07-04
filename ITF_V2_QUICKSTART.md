# ITF v2: Quick Start Guide

Get started with ITF v2 in 5 minutes.

## Installation

ITF v2 is already integrated into the workspace. Import it:

```python
from score.itf.framework import (
    ItfContext,
    ItfHooks,
    run_itf_session_start,
    PluginContract,
    OracleResult,
)
from score.itf.plugins import (
    MockTargetPlugin,
    MockSshPlugin,
    LogCapturePlugin,
    JsonReportPlugin,
)
```

## Minimal Example

```python
from score.itf.framework import ItfContext, ItfHooks, run_itf_session_start
from score.itf.plugins import MockTargetPlugin, MockSshPlugin
import pluggy

# 1. Create plugin manager
pm = pluggy.PluginManager("itf.hook")
pm.add_hookspecs(ItfHooks)

# 2. Register plugins
pm.register(MockTargetPlugin(), name="mock_target")
pm.register(MockSshPlugin(), name="mock_ssh")

# 3. Create context
context = ItfContext()

# 4. Run ITF startup
run_itf_session_start(pm, context)

# 5. Now use the context
print(f"Target: {context.target}")
print(f"Capabilities: {context.capabilities}")
print(f"SSH executor: {context.shared_resources.get('ssh_executor')}")

# 6. Run tests (pytest would handle this)
# ...

# 7. Cleanup (normally handled by orchestrator)
context.run_cleanup()
```

## Using the Runner

```bash
# Run with default plugins
python -m score.itf.runner -- -v

# Run with specific plugins
python -m score.itf.runner --plugins score.itf.plugins.mock_target -- -v

# Run with structured logging
python -m score.itf.runner -- -v --itf-log-capture-file test.log

# Run with JSON report
python -m score.itf.runner -- -v --itf-json-report report.json

# Combine multiple sources
python -m score.itf.runner \
    --plugins score.itf.plugins.mock_target \
    --plugin-dir ./custom_plugins \
    -- -v --itf-log-capture-file test.log --itf-json-report report.json
```

## Creating a Custom Plugin

1. Define typed state:

```python
from dataclasses import dataclass

@dataclass
class MyPluginState:
    value: str = "default"
```

2. Create plugin class:

```python
from score.itf.framework import plugin_contract, itf_hookimpl, OracleResult

@plugin_contract(
    name="my_org.plugins.my_plugin",
    provides=["my_capability"],
    requires=[],
    writes=["shared_resources"],
    phases=["session_start_environment_freeze"],
    readiness_checks=["my_plugin_ready"],
)
class MyPlugin:
    @itf_hookimpl
    def session_start_environment_freeze(self, context):
        state = context.use_state(
            MyPluginState,
            owner="my_plugin",
            factory=lambda: MyPluginState(),
        )
        context.shared_resources["my_data"] = state.value

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        if "my_data" in context.shared_resources:
            return OracleResult.pass_check(name="my_plugin_ready")
        else:
            return OracleResult.fail_check(
                name="my_plugin_ready",
                details="Not initialized",
                blocking=True,
            )
```

3. Use it:

```bash
python -m score.itf.runner --plugins my_org.plugins.my_plugin -- -v
```

## Plugin Phases (In Order)

| Phase | Purpose | Example |
|-------|---------|---------|
| `session_start_profile_resolve` | Read config/options | Load pytest options |
| `session_start_target_create` | Create system under test | Spin up docker container |
| `session_start_target_prepare` | Prepare/configure target | Run setup scripts |
| `session_start_target_capabilities_declare` | Declare capabilities | Register "ssh", "exec" |
| `session_start_capabilities_augment` | Extend capabilities | Add derived capabilities |
| `session_start_shared_resources_configure` | Setup shared data | Create connection pools |
| `session_start_services_start` | Start services | Launch log collectors |
| `session_start_logging_start` | Start logging | Open log file |
| `session_start_readiness_check` | Validate everything | Verify all services ready |
| `session_start_environment_freeze` | Final setup | Snapshot environment |

## Built-in Plugins

### MockTargetPlugin
- **Provides**: `target`
- **Does**: Creates a mock system under test
- **Lifecycle**: profile_resolve, target_create, target_prepare

### MockSshPlugin
- **Provides**: `ssh_endpoint`, `exec`, `upload`
- **Requires**: `target`
- **Does**: Declares SSH endpoint and derives capabilities
- **Lifecycle**: target_capabilities_declare, capabilities_augment

### LogCapturePlugin
- **Provides**: `log_capture`
- **Does**: Captures structured logs to file
- **Format**: `[YYYY-MM-DD HH:MM:SS.mmm] [LVL] [source] message`
- **Lifecycle**: shared_resources_configure, logging_start, logging_stop

### JsonReportPlugin
- **Provides**: `json_report`
- **Does**: Exports test results to JSON
- **Output**: Global info + per-test results + summary
- **Lifecycle**: shared_resources_configure, environment_freeze, cleanup

## Context Channels

### Core Channels

| Channel | Type | Owner | Purpose |
|---------|------|-------|---------|
| `target` | Any | mock_target | System under test |
| `capabilities` | set[str] | Plugins | Available capabilities (union) |
| `shared_resources` | dict | Plugins | Non-test-specific data |
| `extension_state` | dict[type, Any] | Plugins | Typed state (prefer this) |
| `startup_checks` | list[OracleResult] | Plugins | Readiness results |
| `pytest_config` | pytest.Config | pytest | Access CLI options |

### Using Context

```python
# Typed state (recommended)
@dataclass
class MyState:
    value: str

state = context.use_state(MyState, owner="my_plugin",
                         factory=lambda: MyState(value="init"))
state.value = "updated"

# Retrieve state
state = context.get_state(MyState)

# Shared resources (for config, executors, etc.)
context.shared_resources["ssh_executor"] = executor
executor = context.shared_resources.get("ssh_executor")

# Capabilities
context.capabilities.add("exec")
if "exec" in context.capabilities:
    ...

# Readiness checks
result = OracleResult.pass_check("my_check")
context.startup_checks.append(result)
```

## Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or via runner:
python -m score.itf.runner -- -vv
```

Watch the orchestrator:

```
[score.itf.framework.orchestrator] Composition valid: 4 plugins, provides {target, exec, upload, ...}
[score.itf.framework.orchestrator] [PHASE] session_start_target_create
[score.itf.plugins.mock_target] Mock target created: mock-target
...
```

## Common Patterns

### Conditional Execution

```python
@itf_hookimpl
def session_start_logging_start(self, context):
    # Only run if log file specified
    log_file = context.pytest_config.getoption("itf_log_capture_file")
    if not log_file:
        return
    # ... proceed
```

### Dependency on Other Plugins

```python
@plugin_contract(
    requires=["target"],  # Declare requirement
    ...
)
class MyPlugin:
    @itf_hookimpl
    def session_start_capabilities_augment(self, context):
        # Safe to assume context.target exists
        assert context.target is not None
```

### Cleanup

```python
@itf_hookimpl
def session_start_target_create(self, context):
    resource = create_resource()

    def cleanup():
        resource.close()

    context.add_cleanup_callback(cleanup)
```

### State Sharing Between Plugins

```python
# Plugin A stores state
@dataclass
class SharedState:
    config: dict

state = context.use_state(SharedState, owner="plugin_a",
                         factory=lambda: SharedState(config={}))

# Plugin B retrieves it
state = context.get_state(SharedState)
if state:
    value = state.config.get("key")
```

## Performance

- **Startup**: ~100-200ms for typical 4-6 plugin setup
- **Per-plugin**: ~20-50ms for import + instantiation
- **Per-test**: No overhead (orchestration one-time at startup)
- **Memory**: Minimal; one ItfContext + typed states

## Next Steps

1. **Write a test**: See [tests/test_itf_v2_example.py](tests/test_itf_v2_example.py)
2. **Create custom plugin**: Copy [examples/plugins/hello_world.py](examples/plugins/hello_world.py)
3. **Read full guide**: See [ITF_V2_ARCHITECTURE.md](ITF_V2_ARCHITECTURE.md)
4. **Learn plugin loading**: See [PLUGIN_LOADING_GUIDE.md](PLUGIN_LOADING_GUIDE.md)

## Troubleshooting

### Plugin not found
```
ImportError: Cannot import module 'my_plugin'
```
→ Check module path is correct, or use --plugin-dir instead

### Missing contract
```
CompositionError: Plugin X has no __contract__ attribute
```
→ Add `@plugin_contract(...)` decorator to plugin class

### Dependency not provided
```
CompositionError: Plugin X requires 'target' but no plugin provides it
```
→ Load mock_target plugin first, or check plugin order

### Blocking readiness check
```
RuntimeError: Blocking readiness checks failed: docker not installed
```
→ Install missing dependency or disable the plugin

## Questions?

See the full documentation:
- Architecture: [ITF_V2_ARCHITECTURE.md](ITF_V2_ARCHITECTURE.md)
- Plugin loading: [PLUGIN_LOADING_GUIDE.md](PLUGIN_LOADING_GUIDE.md)
- Framework reference: [score/itf/framework/](score/itf/framework/)
- Examples: [examples/plugins/](examples/plugins/)
