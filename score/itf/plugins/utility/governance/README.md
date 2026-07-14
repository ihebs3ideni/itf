# Governance Plugin

Validates composition integrity at session start: enforces namespace
conventions, prevents alias conflicts, and detects duplicate providers.
Think of it as a **linter for your DUT composition**.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.utility.governance.plugin",
]
```

## Configuration

Set the mode via `pytest.ini` / `pyproject.toml`:

```ini
[tool.pytest.ini_options]
itf_governance = "strict"   # off | warn | strict
```

Or override via CLI:

```bash
pytest --itf-governance=strict tests/
```

## Modes

| Mode | Behavior |
|---|---|
| `off` | No validation — for development |
| `warn` | Log violations as warnings, don't fail — for migration |
| `strict` | Violations abort the session — for CI / production |

## Contracts

This plugin is a **utility validator** — it does not provide or require any
contracts. It accesses the registry directly after the aliases phase.

## Validation Rules

### Namespace Policy

- Contracts must start with `ctf/` or `itf/` prefix
- At least 2 slash-separated segments
- Segments must be lower-snake identifiers (`a-z0-9_`)

### Alias Validation

- Alias names cannot be empty
- Cannot shadow DUT methods (`require`, `available`, `provides`, `disable`, `enable`, etc.)
- Cannot contain `/` characters
- Target contract must exist in the registry

### Duplicate Detection

- Each contract must be owned by exactly one provider OR one descriptor, never both

## Example Output (warn mode)

```
WARNING: [GOV-NS001] Contract "MyPlugin/exec" violates namespace policy: must start with ctf/ or itf/
WARNING: [GOV-AL002] Alias "require" shadows a DUT method
WARNING: [GOV-DUP01] Contract "itf/cap/exec" has both a provider and a descriptor
```

## Use Cases

- **CI gates** — catch contract typos before tests run
- **Migration** — gradually enforce conventions in warn mode
- **Multi-team** — prevent namespace collisions across plugin repos
