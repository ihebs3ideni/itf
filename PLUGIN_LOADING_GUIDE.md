# Dynamic Plugin Loading Guide

## Overview

ITF v2 supports flexible plugin loading from multiple sources:
1. **Entry points** - Plugins registered via setuptools/pyproject.toml
2. **Directory scanning** - Auto-discover plugins from a directory
3. **Explicit list** - Specify plugins by module path
4. **Environment variables** - Configure plugins via env vars
5. **Default plugins** - Built-in plugins if nothing specified

## Usage Modes

### 1. Using Default Plugins

By default, ITF loads the four built-in plugins:

```bash
python -m score.itf.runner -- -v
```

Loads:
- `mock_target` - Provides mock system under test
- `mock_ssh` - Provides SSH endpoint and exec/upload capabilities
- `log_capture` - Captures structured logs to file
- `json_report` - Exports test results to JSON

### 2. Specifying Plugins Explicitly

Load only specific plugins:

```bash
python -m score.itf.runner --plugins score.itf.plugins.mock_target score.itf.plugins.mock_ssh -- -v
```

Or use module:Class syntax:

```bash
python -m score.itf.runner --plugins score.itf.plugins.log_capture:LogCapturePlugin -- -v
```

### 3. Scanning a Plugin Directory

Auto-discover plugins from a directory:

```bash
python -m score.itf.runner --plugin-dir ./my_plugins -- -v
```

Directory should contain Python files with classes named `*Plugin` that have `__contract__`:

```python
# ./my_plugins/custom_validator.py

@plugin_contract(...)
class CustomValidatorPlugin:
    ...
```

### 4. Using Environment Variables

Configure plugins via environment:

```bash
# Specify plugins (colon-separated)
export ITF_PLUGINS="score.itf.plugins.mock_target:score.itf.plugins.mock_ssh"
python -m score.itf.runner -- -v

# Specify plugin directory
export ITF_PLUGIN_DIR="/path/to/plugins"
python -m score.itf.runner -- -v
```

### 5. Combining Multiple Sources

Load from entry points, directory, and explicit list (all three):

```bash
python -m score.itf.runner \
    --plugins score.itf.plugins.mock_target \
    --plugin-dir ./custom_plugins \
    -- -v
```

Resolution order:
1. Entry points (if `--no-entry-points` not specified)
2. Plugin directory (if specified)
3. Explicit plugins (if specified)
4. Defaults (if nothing specified)

Plugins are merged (duplicates skipped).

### 6. Disabling Entry Points

Use only explicit sources:

```bash
python -m score.itf.runner --no-entry-points --plugins score.itf.plugins.mock_target -- -v
```

## Creating Custom Plugins

### Minimal Example

```python
from dataclasses import dataclass
from score.itf.framework import plugin_contract, itf_hookimpl, OracleResult

@dataclass
class MyPluginState:
    """Plugin state (optional but recommended)."""
    config: dict

@plugin_contract(
    name="my_org.plugins.my_plugin",
    provides=["my_capability"],
    requires=[],
    writes=["shared_resources"],
    phases=["session_start_environment_freeze"],
    readiness_checks=["my_plugin_ready"],
    description="My custom plugin",
)
class MyPlugin:
    """My plugin implementation."""

    @itf_hookimpl
    def session_start_environment_freeze(self, context):
        """Initialize during environment freeze."""
        state = context.use_state(
            MyPluginState,
            owner="my_plugin",
            factory=lambda: MyPluginState(config={}),
        )
        context.shared_resources["my_data"] = state.config

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        """Check plugin is ready."""
        if "my_data" in context.shared_resources:
            return OracleResult.pass_check(name="my_plugin_ready")
        else:
            return OracleResult.fail_check(
                name="my_plugin_ready",
                details="Not initialized",
                blocking=True,
            )
```

### Full Example with Multiple Phases

See [examples/plugins/hello_world.py](../examples/plugins/hello_world.py)

## Plugin Contract Specification

Every plugin must have `@plugin_contract` with:

```python
@plugin_contract(
    name="org.scope.plugin_name",              # Fully qualified name
    provides=["capability1", "capability2"],   # What this plugin provides
    requires=["capability1"],                   # What it needs from other plugins
    writes=["target", "shared_resources"],     # Context channels written to
    reads=["pytest_config"],                   # Context channels read from
    phases=[                                    # Lifecycle phases implemented
        "session_start_target_create",
        "session_start_environment_freeze",
    ],
    readiness_checks=["plugin_ready"],         # Readiness check names
    description="Human-readable description",   # For documentation
)
```

## Lifecycle Phases (Ordered)

Plugins implement hooks for phases they care about:

1. **session_start_profile_resolve** - Read config/options
2. **session_start_target_create** - Create system under test
3. **session_start_target_prepare** - Prepare/configure target
4. **session_start_target_capabilities_declare** - List capabilities
5. **session_start_capabilities_augment** - Extend/derive capabilities
6. **session_start_shared_resources_configure** - Setup shared data
7. **session_start_services_start** - Start services
8. **session_start_logging_start** - Start logging
9. **session_start_readiness_check** - Validate everything
10. **session_start_environment_freeze** - Final setup

## Plugin State Management

Use typed state instead of magic string keys:

```python
# Good: Typed state with IDE completion
@dataclass
class MyState:
    value: str

state = context.use_state(MyState, owner="my_plugin",
                         factory=lambda: MyState(value="init"))
state.value = "updated"

# Legacy: String-key stash (avoid)
context.stash_set("my_plugin", "value", "init")
value = context.stash_get("my_plugin", "value")
```

## Composition Validation

The orchestrator validates plugin composition at startup:

✅ **Valid**: All requires are provided:
```python
# mock_target provides ["target"]
# mock_ssh requires ["target"] ✓ (provided by mock_target)
```

❌ **Invalid**: Missing dependency:
```python
# mock_ssh requires ["target"]
# But no plugin provides ["target"] ✗ (will fail at startup)
```

Error message:
```
CompositionError: Plugin score.itf.plugins.mock_ssh requires 'target'
but no plugin provides it
```

## Readiness Checks

Plugins declare readiness via OracleResult:

```python
@itf_hookimpl
def session_start_readiness_check(self, context):
    """Return readiness status."""
    if problem_detected:
        return OracleResult.fail_check(
            name="plugin_check",
            details="Problem description",
            blocking=True,  # True = fail startup
        )

    return OracleResult.pass_check(
        name="plugin_check",
        details="All good",
    )
```

If any blocking readiness check fails, startup aborts:
```
RuntimeError: Blocking readiness checks failed: Problem description
```

## Advanced: Plugin Discovery Algorithm

When you call `create_plugin_manager()`:

1. **Entry points** (if enabled)
   - Scan for registered entry points in group `itf.plugins`
   - Load each entry point's class

2. **Directory scanning** (if `--plugin-dir` specified)
   - Scan `*.py` files in directory
   - Look for classes: `*Plugin` with `__contract__`
   - Import and instantiate

3. **Explicit list** (if `--plugins` specified)
   - Parse each spec as module path or `module:Class`
   - Import module, get class, instantiate

4. **Environment** (if env vars set)
   - `ITF_PLUGINS=module1:module2` → colon-separated specs
   - `ITF_PLUGIN_DIR=/path/to/plugins` → directory path

5. **Defaults** (if nothing else specified)
   - Load 4 built-in plugins

All loaded plugins are merged (duplicates removed, last one wins).

## Testing Your Plugin

```python
from score.itf.framework import ItfContext, ItfHooks, run_itf_session_start
import pluggy

def test_my_plugin():
    # Create plugin manager
    pm = pluggy.PluginManager("itf.hook")
    pm.add_hookspecs(ItfHooks)

    # Register your plugin
    pm.register(MyPlugin(), name="my_plugin")

    # Create context
    context = ItfContext()

    # Run startup
    run_itf_session_start(pm, context)

    # Verify your plugin's effects
    assert "my_data" in context.shared_resources
```

## Packaging Your Plugin

### Option 1: Standalone Package

```
my_plugin/
  setup.py
  my_plugin/
    __init__.py
    plugin.py
```

setup.py:
```python
setup(
    name="my-itf-plugin",
    packages=["my_plugin"],
    entry_points={
        "itf.plugins": [
            "my_plugin = my_plugin.plugin:MyPlugin",
        ],
    },
)
```

Then install and ITF automatically discovers it:
```bash
pip install my-itf-plugin
python -m score.itf.runner -- -v  # Loads your plugin via entry point
```

### Option 2: Local Plugins Directory

```
project/
  tests/
  plugins/
    custom_plugin.py
```

Run with:
```bash
python -m score.itf.runner --plugin-dir ./plugins -- -v
```

### Option 3: Explicit Module Path

```bash
python -m score.itf.runner --plugins my_package.plugins.my_plugin -- -v
```

## Debugging Plugin Loading

Enable debug logging to see what's loaded:

```bash
python -m score.itf.runner \
    --plugins score.itf.plugins.mock_target \
    -- -vv  # Increases pytest verbosity for logging
```

Output:
```
[score.itf.framework.plugin_loader] Loaded plugin: mock_target from score.itf.plugins.mock_target
[score.itf.framework.plugin_loader] Registered plugin: mock_target
[score.itf.runner] Loaded 1 plugins: ['mock_target']
[score.itf.framework.orchestrator] Discovered plugin: mock_target
[score.itf.framework.orchestrator] Plugin mock_target: provides=['target'], requires=[], phases=[...]
```

## Performance

- Plugin loading: ~10-50ms per plugin (import + instantiation)
- Composition validation: O(N × M) where N=plugins, M=avg capabilities
- Per-test overhead: None (orchestration happens once at startup)

Typical startup with 4-6 plugins: 100-200ms
