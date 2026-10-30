# OCTO: concepts and first plan

OCTO is a pure planner. Give it immutable declarations, get a resolved plan or structured diagnostics. It uses only the Python standard library and does not import, construct, probe, or execute the implementations named in a declaration. You can use it without the ITF engine or a test runner.

## A mental model

Imagine planning a small shop service. A pool needs an endpoint; a migration must wait until the database is ready. OCTO answers two different questions:

1. **Gate 1: what must exist?** Choose providers, connect their required slots to nodes, check offered versus expected shapes, and order construction. Output: `TargetPlan`.
2. **Gate 2: what must happen?** Starting from goals, choose producers, account for requirements and invalidations, and order the steps. Output: `ActionPlan`. Gate 2 uses Gate 1's plan to bind each action's capability slots.

The two plans are descriptions, not running objects. A caller owns loading implementations, making instances, probing real conditions, executing steps, and teardown.

## Vocabulary

| Term | Meaning | Shop example |
|---|---|---|
| **Token** | Stable string identifying a role or condition, not a Python type or instance | `db.pool`, `db_up` |
| **Claim** | One frozen, hashable statement contributed to the planner; it records its `origin` | `NodeClaim(scope="shop", name="pool", ...)` |
| **Capability contract** | The role an object must fill, including any shape it promises and slots it needs | `db.pool` |
| **Provider** | Named way to fulfill a capability contract; its `impl` is an opaque string to OCTO | `acme.pool` implements `db.pool` |
| **Node** | One named occurrence of a contract in a scope, selecting a provider and optional config/bindings | `shop.pool` |
| **Scope** | Namespace for node names and state instances | `shop` |
| **Slot / need** | Named dependency of a provider or action on another capability contract | `endpoint: itf.capabilities.descriptor.endpoint` |
| **Shape** | Data describing members/protocols offered (`gives`) or required (`expected`); checked at a bound slot | `host`, `port` |
| **State contract** | Named condition plus opaque producer and optional probe references, prerequisites and invalidations | `schema_migrated` |
| **Goal** | A state to make true in a scope; pulls its producer and prerequisites into Gate 2 | `shop:schema_migrated` |
| **Diagnostic** | Machine-readable reason resolution could not produce a plan; contains a code and evidence | `SLOT_AMBIGUOUS` |

A *contract* is a role; a *provider* is one possible implementation; a *node* is one planned instance of that role. Multiple nodes may share the same contract and provider but have different names and configuration. An action delivers a *state*, not an object. `requires` describes what must already hold; `invalidates` describes what an action makes false again.

Claims are deliberately plain data. For instance, `ProviderClaim.impl="my_module:make_pool"` names an implementation but OCTO never imports it. `NodeClaim.config` uses hashable scalar values; a caller interprets them when constructing the object. Origin precedence can override a node declaration; conflicting declarations at equal rank are diagnostics. Additive goal, relation and shape-expectation claims combine rather than selecting a winner.

## First plan (no engine)

Run this with the package importable (`pip install -e .` from the repository root):

```python
from score.itf.core.octo import (
    CapabilityContractClaim, GoalClaim, Need, NodeClaim, ProviderClaim,
    Shape, StateContractClaim, resolve_actions, resolve_target,
)

setup = frozenset({
    CapabilityContractClaim(token="itf.capabilities.descriptor.endpoint", gives=Shape.of("host", "port")),
    CapabilityContractClaim(token="db.pool"),
    ProviderClaim(name="acme.endpoint", implements="itf.capabilities.descriptor.endpoint",
                  gives=Shape.of("host", "port"), impl="my_module:make_endpoint"),
    ProviderClaim(name="acme.pool", implements="db.pool", impl="my_module:make_pool",
                  needs=(Need(slot="endpoint", contract="itf.capabilities.descriptor.endpoint",
                              expected=Shape.of("host", "port")),)),
    NodeClaim(scope="shop", name="pool", contract="db.pool", using="acme.pool"),
})
target = resolve_target(setup)
assert target.ok(), target.diagnostics
# Gate 1 derives shop.pool.endpoint to satisfy the pool's endpoint slot.
assert target.plan.node("shop.pool.endpoint").derived

init = frozenset({
    StateContractClaim(token="db_up", scope="shop", impl="my_module:start_db"),
    StateContractClaim(token="schema_migrated", scope="shop", impl="my_module:migrate",
                       requires=frozenset({"db_up"})),
    GoalClaim(scope="shop", states=frozenset({"schema_migrated"})),
})
actions = resolve_actions(init, target.plan)
assert actions.ok(), actions.diagnostics
assert [step.key for step in actions.plan.steps] == ["shop:db_up", "shop:schema_migrated"]
```

The `impl` strings above need not point to real functions to **plan**; the runtime that executes the plan must resolve them. If a gate fails, `.plan` is `None` and `.diagnostics` explains why; do not pass a failed Gate 1 plan to Gate 2. `resolve(setup, init)` is a convenience wrapper for both gates. Plans and claims support `to_json()` / `from_json()` for analysis and interchange; JSON does not package the named implementations.

## How resolution decides

- **Binding:** a node's explicit `bind` wins; otherwise a sole matching node in scope is used; if none exists and there is a sole eligible provider, Gate 1 can derive a node. Ambiguity or incompatible shapes produce diagnostics, not guesses.
- **Shapes:** compare offered `given` against required `expected` at each binding seam. `ShapeExpectationClaim` adds a requirement for every use of a contract, unioned across contributors. `shape_of(type)` can extract a structural footprint, but the planner itself compares `Shape` data.
- **Precedence:** pass `precedence=("base", "override")` for origins ranked lowest to highest. Same-rank conflicting declarations fail; goal/relation/shape expectations add up.
- **Ordering:** Gate 1 constructs prerequisites before consumers. Gate 2 pulls producers transitively from goals and respects `requires` and `invalidates`. `observed_states` are evidence already checked; `assumed_states` skip a producer without evidence and remain visible in the plan.
- **Results:** the same unordered claims give the same result. A diagnostic has a code, subject, gate, and evidence; human-readable remediation belongs to the caller.

For every claim field and edge rule, use the [formal specification](../../docs/octo-kit/10-spec-octo-core.md). For rationale, use the [decisions](../../docs/octo-kit/30-decisions.md). For a runtime using OCTO, start with the [ITF user guide](../../docs/user-guide.md).