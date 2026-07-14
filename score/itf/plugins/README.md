# ITF Plugins

Plugins extend ITF by implementing lifecycle hooks. They are organized into five
categories with clear separation of concerns.

## Categories

| Directory | Role | Coupling |
|---|---|---|
| `targets/` | Provide `ctf/target` + inherent capabilities | Owns the DUT anchor |
| `capabilities/` | Additive capabilities that require facts from any target | Only requires contracts |
| `env/` | Environment controllers (heartbeat, faults, network chaos) | May require `itf/net/*` |
| `domain/` | Persist data (results, artifacts, history) | Observer — no contracts |
| `utility/` | Observe and report (dashboards, governance) | Observer — no contracts |

## Available Plugins

### Targets

- **[docker](targets/docker/README.md)** — Docker containers as test targets
- **[qemu](targets/qemu/README.md)** — QEMU virtual machines as test targets
- **[mock](targets/mock/README.md)** — In-memory mock for plugin development

### Capabilities

- **[ssh](capabilities/ssh/README.md)** — SSH/SFTP execution and file transfer
- **[ping](capabilities/ping/README.md)** — ICMP reachability checks
- **[dlt](capabilities/dlt/README.md)** — Diagnostic Logging and Trace capture
- **[console](capabilities/console/README.md)** — Serial console over COM/UART ports

### Environment

- **[udp_heartbeat](env/udp_heartbeat/README.md)** — Periodic UDP heartbeat simulation

### Domain

- **[sqlite_logger](domain/sqlite_logger/README.md)** — Persist results to SQLite

### Utility

- **[dashboard](utility/dashboard/README.md)** — Live web UI + offline snapshots
- **[governance](utility/governance/README.md)** — Namespace and composition linter

## Design Rules

1. **No cross-imports** — a target never imports a capability; a utility never imports a target
2. **String coupling only** — plugins agree on contract strings, not Python imports
3. **Ship independently** — each plugin can live in its own repo/package
4. **Implement only needed hooks** — skip phases that don't apply
