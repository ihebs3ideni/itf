# ctf-governance

Ecosystem **governance** and **integration** checks for the
[CTF composition engine](../FrameWorkRevamp).

CTF is deliberately semantic-agnostic: any plugin can contribute any contract.
That freedom needs a governor. This package is that governor — a **separate,
optional** layer that observes an assembled ecosystem and reports problems.

> Dependency direction is one-way: `ctf-governance` depends on `ctf`.
> `ctf` never depends on `ctf-governance`.

## What it does

| Capability | Where |
| --- | --- |
| **Namespacing validation** — enforce `<org>/<domain>/<name>` contract names | `naming.py` |
| **Catalog / discovery** — who provides & requires what, across all plugins | `catalog.py` |
| **Duplicate / collision detection** — same contract from two plugins, UNIQUE point collisions | `catalog.py` |
| **CLI** — dump the ecosystem catalog (`ctf-catalog`) | `cli.py` |
| **In-session enforcement** — governance is itself a CTF plugin (`off`/`warn`/`strict`, default `off`) | `plugin.py` |

Contract **version** compatibility checks are intentionally out of scope for now.

## Install (shared venv with `ctf`)

Both packages share one venv (the PEP 660 editable-install constraint from
`ctf` applies here too):

```bash
cd ../FrameWorkRevamp
.venv/bin/python -m pip install -e ".[test]"           # ctf
.venv/bin/python -m pip install -e "../FrameWorkRevampGovernance[test]"  # ctf-governance
```

## Offline catalog

```bash
# Each argument is an importable module that registers CTF hookimpls.
ctf-catalog examples.ecosystem.target_ecu examples.ecosystem.capability_doip
ctf-catalog --strict --format json mypkg.plugin_a mypkg.plugin_b
```

## In-session governance

Governance is **opt-in**: although the package installs as a pytest plugin, it
does nothing until you set a mode. Enable it via an ini setting:

```ini
[pytest]
ctf_governance = strict   # off | warn | strict  (default: off)
```

In `strict` mode a namespace violation raises a `CompositionError`, so the run
stops **cleanly** through CTF's own error boundary (no `INTERNALERROR`).
