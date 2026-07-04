# ITF Framework Extension Plan (Draft)

## 1) Context

ITF currently uses a pytest-fixture-driven lifecycle:
- Core fixture contract: `target_init -> target`
- Target plugins (Docker, QEMU) implement setup/teardown in fixture bodies
- Supporting plugins (DLT) start services via fixtures
- QEMU readiness checks run ad hoc (`pre_tests_phase`)

The new architecture introduces a framework extension layer with explicit high-level lifecycle hooks and a unified immutable test context.

## 2) Objective

Add a framework-level orchestration layer that:
- Preserves existing test API compatibility (`target` fixture still works)
- Introduces explicit public lifecycle hooks for target/system test orchestration
- Internally orchestrates domain-specific hook families (target, capability, environment, simulation, service, observability, checks)
- Works in tandem with the core `Target` API, where the target object owns capability state and capability plugins extend it
- Includes a first-class capability spec contract so targets can declare structured attachment data for each capability
- Models executors as transport/back-end attachments resolved onto the target by plugins
- Treats concrete target implementations like Docker as plugins that are composed by the core testing framework
- Standardizes setup/teardown order and diagnostics

## 3) Scope

### In scope
- Public lifecycle hook specification and internal domain hook family design
- Orchestration rules between lifecycle hooks and domain hooks
- Hook ownership model
- `TestContext` contract
- Backward compatibility adapter from legacy fixture style
- Migration plan for built-in plugins
- Validation and documentation plan

### Out of scope (first iteration)
- Large refactors of unrelated Target APIs
- Changing Bazel plugin registration model
- Breaking test-facing API changes

## 4) Requirements

### Functional requirements
1. A framework plugin must execute a deterministic two-level lifecycle:
   - Public session lifecycle hooks (once per session/scope)
   - Public test-case lifecycle hooks (once per test case)
2. Target creation must be a major explicit lifecycle step, owned by exactly one target plugin for a given run.
3. The created target must declare its baseline supported behaviors/capabilities and the interfaces it answers to, including the attachment data needed to use each capability.
4. Capability declarations must use a structured capability spec contract, not just raw capability names, so plugins can validate and consume attachment data consistently.
5. The core `Target` object remains the single source of truth for capability state via `has_capability`, `get_capabilities`, `add_capability`, and `remove_capability`.
6. The core `Target` API must dispatch `execute`, `upload`, `download`, and `restart` through resolved executor backends when the transport is not native.
7. Capability plugins must augment the created target rather than replace target ownership.
8. Multiple contributors may participate in capability augmentation, executor attachment, services, and checks.
9. Setup must fail early with actionable diagnostics when required providers are missing.
10. Cleanup must always run in reverse dependency/order-safe sequence, even on failures.
11. Existing tests using `target` fixture must continue to work.
12. `evaluate_oracles` must produce a verdict per test case, with optional session aggregation.
13. `collect_evidence` must support both per-test-case evidence and session-level evidence manifests.
14. Framework hooks must accept pytest-native objects at the appropriate scope:
   - Session hooks: `pytest_session`, `pytest_config`
   - Test-case hooks: `item` (pytest `Item`), optional `request`
   - Report-aware hooks: `report` / `call` phase info
15. Pytest remains the source of truth for final pass/fail status; framework verdict logic must map into pytest-native outcomes.
16. Public lifecycle hooks must remain small and stable even if the internal domain hook families evolve.
17. Domain hooks must not be exposed as the primary user-facing contract; they are orchestrated internally by the framework plugin.
18. The framework must expose a reusable capability-spec contract for target-declared capabilities, transport metadata, and plugin-consumable attachment details.

### Non-functional requirements
1. Minimal regression risk for current Docker/QEMU/DLT flows.
2. Clear observability/logging at each lifecycle stage.
3. Predictable plugin composition independent of incidental fixture interactions.
4. Easy extension path for real-target and mock-target plugins.

## 5) Public Lifecycle Contract (Stable Framework API)

This is the primary contract exposed by the framework. Plugin authors may map their implementations to internal domain hook families, but the public lifecycle remains the stable orchestration surface.

### 5.1 Session lifecycle hooks

### `resolve_test_profile(context, pytest_session, pytest_config) -> TestProfile`
- Purpose: Produce the final run profile used to drive target, environment, and capability orchestration.
- Cardinality: single orchestrated lifecycle step.

### `resolve_capabilities(context, pytest_session) -> CapabilityView`
- Purpose: Produce the effective capability view for the run, starting from the target baseline capability specs held on the `Target` object, validating them against the capability-spec contract, and applying capability plugin augmentation.
- Cardinality: single orchestrated lifecycle step.

### `create_target(context, pytest_session, pytest_config) -> TargetHandle`
- Purpose: Instantiate/connect the concrete target object.
- Cardinality: single orchestrated lifecycle step; exactly one target provider.

### `pre_target_setup(context, pytest_session) -> None`
- Purpose: Run setup that must happen after target creation but before broader environment bring-up.
- Cardinality: single orchestrated lifecycle step.

### `create_environment(context, pytest_session) -> EnvironmentView`
- Purpose: Provision host-side dependencies and supporting runtime environment.
- Cardinality: single orchestrated lifecycle step.

### `create_simulation(context, pytest_session) -> SimulationView`
- Purpose: Start or connect simulators/emulators when required by the profile.
- Cardinality: single orchestrated lifecycle step.

### `start_services(context, pytest_session) -> ServiceView`
- Purpose: Start service, logging, metrics, and similar supporting plugins.
- Cardinality: single orchestrated lifecycle step.

### `startup_checks(context, pytest_session) -> StartupCheckReport`
- Purpose: Validate readiness before tests consume the context.
- Cardinality: single orchestrated lifecycle step.

### `test_ready(context, pytest_session) -> FrozenTestContext`
- Purpose: Finalize immutable context exposed to tests.
- Cardinality: core orchestrator only.

### 5.3 Capability Spec Contract

The framework should define a structured capability-spec contract that target plugins and capability plugins can share.

Minimum expectations:
- capability name / identifier
- transport or access mode implied by the capability
- attachment metadata needed to use the capability
- optional validation rules and defaults
- plugin-consumable fields for executor attachment and runtime adaptation

This contract should be the common input to `resolve_capabilities`, `capability_augment`, and `executor_attach`.

### `cleanup(context, pytest_session, exitstatus) -> CleanupResult`
- Purpose: Reverse-order teardown and result aggregation.
- Cardinality: single orchestrated lifecycle step.

### 5.2 Test-case lifecycle hooks

### `before_test_case(context, tc, item, request) -> None`
- Purpose: Per-test isolation/reset and baseline snapshot.
- Cardinality: optional multi-contributor.

### `execute_test_case(context, tc, item) -> TestExecutionResult`
- Purpose: Execute the user test body/scenario.
- Cardinality: framework core invocation.

### `evaluate_oracles(context, tc, item, execution_result, call_report) -> TestVerdict`
- Purpose: Apply assertions and domain oracles (timing windows, signal plausibility, state-machine invariants, KPIs).
- Cardinality: mandatory per test case; optional multi-contributor with merged verdict details.

### `collect_evidence(context, tc, item, execution_result, reports, verdict) -> TestCaseEvidence`
- Purpose: Gather and link test-specific logs/traces/captures/artifact references.
- Cardinality: mandatory per test case; optional multi-contributor.

### `after_test_case(context, tc, item, reports, verdict) -> None`
- Purpose: Per-test teardown and resource hygiene checks.
- Cardinality: optional multi-contributor.

### 5.3 Optional report-phase hook

### `on_test_report(context, tc, item, when, report, call) -> None`
- Purpose: React to pytest-native setup/call/teardown reports for advanced bookkeeping.
- Cardinality: optional multi-contributor.

## 5.4 Hook timing model (authoritative)

1. Session start (before any test case): all hooks in 5.1 up to `test_ready`.
2. Per test case:
   - before pytest call: `before_test_case`
   - test execution: `execute_test_case` (delegates to pytest engine)
   - after call report: `evaluate_oracles`
   - after teardown report: `collect_evidence`, then `after_test_case`
3. Session end (after all test cases): `cleanup`.

## 6) Internal Domain Hook Families (Framework-Managed)

These hooks are not the primary public contract. They are invoked by the framework plugin while executing the public lifecycle hooks in Section 5.

### 6.1 Target domain hooks

### `target_create(context, pytest_session, pytest_config) -> TargetHandle`
- Owned by exactly one target plugin; returns the concrete `Target` implementation.

### `target_declare_capabilities(context, pytest_session, target) -> TargetCapabilityDeclaration`
- Owned by the same target plugin that created the target; should describe the target's baseline capability specs, transport/connection model, and any metadata needed by executor/capability plugins to attach behavior.

### `target_pre_setup(context, pytest_session, target) -> None`
- Optional target-owned setup after creation.

### 6.2 Capability domain hooks

### `capability_augment(context, pytest_session, target) -> CapabilityContribution`
- Owned by zero-to-many capability plugins; must extend the existing target using the core `Target` API (`add_capability`/`remove_capability`) and may attach backend adapters or helpers by consuming the target's capability spec data.

### `executor_attach(context, pytest_session, target) -> ExecutorContribution`
- Owned by zero-to-many target or capability plugins.
- Attaches executor backends to the target for capabilities such as `exec`, `upload`, `download`, and `restart`.
- May choose a backend based on target description (for example SSH, serial console, Docker exec, or TCP).

### 6.3 Environment domain hooks

### `environment_create(context, pytest_session, target) -> EnvContribution`
- Owned by zero-to-many environment plugins.

### 6.4 Simulation domain hooks

### `simulation_create(context, pytest_session, target) -> SimulationContribution`
- Owned by zero-to-many simulation plugins.

### 6.5 Service and observability domain hooks

### `service_start(context, pytest_session, target) -> ServiceContribution`
- Owned by zero-to-many service plugins.

### `logging_start(context, pytest_session, target) -> ObservabilityContribution`
- Owned by zero-to-many logging/trace plugins.

### `metrics_start(context, pytest_session, target) -> ObservabilityContribution`
- Owned by zero-to-many metrics plugins.

### 6.6 Check domain hooks

### `startup_check(context, pytest_session, target) -> CheckResult`
- Owned by zero-to-many check plugins.

## 7) Orchestration Rules

1. The public lifecycle in Section 5 is the stable contract.
2. The framework plugin dispatches each public lifecycle step into one or more internal domain hook families from Section 6.
3. `create_target` must dispatch only to the target domain and require exactly one provider.
4. `resolve_capabilities` must:
   - read the baseline declaration from the created target / target plugin
   - run all capability augmentation hooks
   - run executor attachment hooks when a capability requires a transport/backend implementation
   - merge the final capability view using the locked policy from Section 11
5. `create_environment`, `create_simulation`, and `start_services` may each dispatch to multiple domain contributors.
6. `start_services` is the orchestration point for service, logging, and metrics domain hooks.
7. `startup_checks` must dispatch to all check-domain contributors and apply the locked startup-check policy from Section 11.
8. Public lifecycle hook names should stay stable even if internal domain hooks are renamed or split later.
9. Capability enablement should be additive: a plugin may call `target.add_capability(...)`, while `target.remove_capability(...)` remains available for controlled teardown or capability masking when needed.
10. Executor attachment is distinct from capability flags: a capability can exist without a transport backend, but core methods like `execute()` must fail fast if no executor backend is resolved.

## 8) Data Model Requirements (TestContext)

`TestContext` should include at minimum:
- `target`
- `target_capabilities`
- `test_intent`
- `profile`
- `resource_allocation`
- `capabilities`
- `environment`
- `simulation`
- `services`
- `observability`
- `config`
- `artifacts` (optional)
- `metadata` (plugin provenance, timings)
- `evidence_index` (session + tc evidence linkage)

Behavioral constraints:
- Immutable after `test_ready`
- Internal resource handles may be stateful, but top-level context container is frozen
- Deterministic serialization for debugging where possible

## 9) Compatibility Requirements

1. Keep `target` fixture as a compatibility alias/adaptor (`target = context.target`).
2. Maintain `--keep-target` semantics for fixture scope behavior.
3. Support legacy plugin style (`target_init`) via adapter during migration window.
4. Emit deprecation warnings only after new path is validated.
5. Preserve current plugin loading semantics from Bazel + pytest registration.
6. Hooks must not bypass pytest result machinery; critical oracle failures must map to pytest failure semantics.

## 10) Migration Plan (Phased)

### Phase 1: Foundation
- Add framework module (`hookspec`, `orchestrator`, `context`, `verdict`, `evidence`)
- Define internal domain hook families and orchestrator dispatch rules
- Add no-op/default implementations
- Add compatibility bridge to current fixture model

### Phase 2: Built-in plugin migration
- Docker: move lifecycle from fixture body into a plugin-backed target domain behind `create_target`, with core providing the test shell and orchestration
- DLT: migrate service startup/teardown into service/logging domain hooks behind `start_services`
- QEMU: migrate target creation and checks into target-domain and check-domain hooks
- Introduce capability plugin augmentation path on top of created targets
- Document the backend-dispatch pattern for capabilities that can be fulfilled by multiple transports (for example exec over SSH, serial console, or TCP)
- Add per-test-case hooks (`before_test_case`, `evaluate_oracles`, `collect_evidence`)

### Phase 3: Hardening
- Add ordering/error diagnostics
- Add cleanup aggregation and reporting
- Add migration guides and deprecation timeline

## 11) Verification Plan

### Unit tests
- Hook ordering and cardinality enforcement
- Public lifecycle to domain-hook dispatch behavior
- Target baseline capability declaration and capability augmentation merge behavior
- Cleanup on partial-failure scenarios
- Context immutability guarantees
- Per-test verdict merge semantics
- Per-test and session evidence indexing semantics
- Pytest item/report propagation into framework hooks

### Integration tests
- Docker-only run
- Docker + DLT run
- QEMU-only run
- QEMU + DLT run
- Legacy `target_init` plugin compatibility run
- Evidence output contains both session and per-test bundles
- Oracle evaluation result is available per test case

## 12) Risks and Mitigations

1. Risk: Plugin interaction regressions
   - Mitigation: Compatibility adapter + staged migration + integration matrix
2. Risk: Unclear hook ownership
   - Mitigation: explicit public lifecycle contract plus domain-specific ownership and startup validation errors
3. Risk: Cleanup leaks
   - Mitigation: mandatory registered cleanup stack with reverse execution

## 13) Decisions Status

### 13.1 Locked decisions

1. Capability merge policy
   - Chosen: union + conflict warnings
   - Rejected: prioritized contributors
   - Rationale: the target owns the baseline capability declaration, and capability plugins extend it additively; conflicts should be surfaced without introducing hidden precedence rules.

2. Startup check policy
   - Chosen: collect-all then fail by default; support optional fail-fast on first critical check
   - Rationale: collect-all gives better diagnostics during bench bring-up and integration, while fail-fast remains available for time-sensitive or safety-critical runs.

3. Evidence storage format
   - Chosen: file tree + JSON index for V1
   - Deferred evolution: file tree + sqlite index
   - Rationale: JSON is simple, inspectable, and sufficient for the initial implementation; sqlite can be introduced later if indexing/query needs grow.

4. Oracle composition strategy
   - Chosen: run all contributors and aggregate results
   - Rejected: stop on first hard failure
   - Rationale: aggregate execution provides better traceability and richer diagnostics for automotive system tests.

### 13.2 Deferred decisions

1. Context freezing mechanism
   - Options under consideration:
     - dataclass + frozen wrapper
     - immutable mapping + typed accessors
   - Current status: deferred until a small implementation spike confirms which option is more maintainable and easier to use.

2. Legacy adapter sunset
   - Decision needed later: migration window and warning strategy for retiring legacy `target_init` plugins.
   - Current status: intentionally deferred until the compatibility adapter is proven on real built-in plugins.

## 14) Pytest integration mapping (implementation guardrail)

1. `pytest_sessionstart` drives session-start hooks.
2. `pytest_runtest_setup` enters `before_test_case`.
3. `pytest_runtest_call` remains pytest-owned execution path.
4. `pytest_runtest_makereport` provides setup/call/teardown reports to oracle/evidence hooks.
5. `pytest_sessionfinish` drives session-end hooks.

## 15) Immediate Next Step

### File-level implementation tasks

1. Add framework package skeleton
- Create `score/itf/framework/__init__.py`
- Create `score/itf/framework/hookspec.py` for the public lifecycle hooks
- Create `score/itf/framework/domain_hookspec.py` for internal domain hook families
- Create `score/itf/framework/orchestrator.py` for dispatch and lifecycle coordination
- Create `score/itf/framework/context.py` for `TestContext`, per-test context, and shared state models
- Create `score/itf/framework/verdict.py` for verdict/oracle result models
- Create `score/itf/framework/evidence.py` for evidence manifest/index models

2. Add core pytest integration layer
- Extend or refactor `score/itf/plugins/core.py` to register the framework orchestrator with pytest
- Map pytest lifecycle entry points from Section 14 into orchestrator calls
- Preserve current `target` fixture behavior through a compatibility adapter

3. Wire Bazel/python targets for the new framework package
- Update `score/itf/plugins/BUILD` if core plugin dependencies change
- Add or update the relevant `py_library` targets so the new framework package is importable from the core plugin

4. Implement target-domain migration path
- Update `score/itf/plugins/docker.py` to express Docker setup through target-domain hooks behind `create_target`
- Update `score/itf/plugins/qemu/__init__.py` to express QEMU setup through target-domain hooks behind `create_target`
- Keep legacy `target_init` compatibility during migration

5. Implement capability augmentation and executor attachment path
- Add initial capability augmentation support in the framework package
- Update target plugins so baseline capabilities come from the created target object
- Reserve capability-plugin integration points for future plugins even if no standalone capability plugin is migrated in V1
- Document how SSH, console, and native exec backends attach to the same target through executor resolution

6. Implement service and observability migration path
- Update `score/itf/plugins/dlt/__init__.py` to move startup/teardown behind service/logging-style domain hooks used by `start_services`

7. Implement check-domain migration path
- Update `score/itf/plugins/qemu/checks.py` so startup checks are invoked through the check domain and `startup_checks` lifecycle step

8. Add tests for the new orchestration model
- Add unit tests under `test/unit/` for hookspec/orchestrator/context behavior
- Add or update integration tests under `test/integration/` for Docker, QEMU, DLT, and legacy compatibility flows

9. Update documentation after the first working slice
- Update `docs/concepts/architecture.rst`
- Update `docs/concepts/itf_architecture.puml`
- Update `docs/reference/plugins.rst`
- Update `docs/how-to/plugins.md`

### Recommended implementation order

1. Framework package skeleton
2. Core pytest integration in `score/itf/plugins/core.py`
3. Target-domain support and Docker migration
4. QEMU migration and startup checks
5. DLT service/logging migration
6. Tests
7. Docs
