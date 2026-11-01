# The composition format

A composition is a YAML (or JSON) document, usually `*.itf.yaml`. Keys, in order: `include`, `capabilities`,
`goals`, `assume`, `scopes`. Unknown keys are errors naming what exists. Block style only (no `{...}`/`[...]`).

```yaml
include:                          # merged first, in order; this file wins
  - base.itf.yaml
capabilities:                     # keyed by role: the name tests use (`target.command`)
  platform:
    factory: docker.platform      # <pack>.<name>
    with:                         # settings, checked against the factory's config dataclass
      image: my-image:latest
  command: docker.exec            # short form: just the factory
  shell:
    factory: ssh.shell
    bind:                         # only when a slot has more than one candidate: slot -> role
      endpoint: lab_endpoint
goals:                            # states to reach; nothing is inferred
  - platform.up
  - state: console.open
    by: serial.open               # only when two actions (of listed packs or the project) could make it true
assume:                           # a state that holds without ITF
  - state: rack.ready
    owner: lab
    reason: the rack keeps it on
scopes:                           # one more device
  gw:
    capabilities:
      command: ssh.exec
    goals:
      - shell.open
    share:
      - platform                  # gw uses the root's platform role
```

- Role = `target.<role>`; factory = `<pack>.<function>` (a part in the project's conftest: `project.<function>`).
- `with:` values may read the environment: `${NAME}` or `${NAME:-default}`; a value that is exactly one reference is
  read as a YAML scalar (`port: ${SSH_PORT:-22}` is an integer); `$${` is a literal `${`.
- The actions considered are those of the packs of the listed factories plus the project's own. A goal two of them
  could make true needs `by:`; a slot with two candidates needs `bind:`.
- Scopes: roles of a scope are `target.<scope>.<role>`; a scope never falls back to the root, `share:` lists the
  root roles it uses. A role named like a scope or a handle member is rejected.

## Override files

An override file has the composition's own shape and only what changes. Files merge by role, in order (includes
first, then the target, then each override): `with:` and `bind:` keys are merged, any other key replaces; goals
and assumptions merge by state. A role cannot be removed.

```yaml
# bench.itf.yaml
capabilities:
  platform:
    with:
      image: my-image:debug
```

## Where a run finds them

`--itf-target`, `ITF_TARGET`, `itf_target` (ini), `[tool.itf] target`; overrides: `--itf-override` (repeatable),
`ITF_OVERRIDE`, `itf_override` (ini), `[tool.itf] override`. Bazel: `py_itf_test(target = ":x")` sets them from the
`itf_target`. `Session(target=..., overrides=[...])` without pytest. `itf validate|plan|graph|up|down|test` take the
composition as an argument or from the same configuration.
