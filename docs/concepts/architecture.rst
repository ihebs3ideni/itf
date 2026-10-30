..
   # *******************************************************************************
   # Copyright (c) 2026 Contributors to the Eclipse Foundation
   #
   # See the NOTICE file(s) distributed with this work for additional
   # information regarding copyright ownership.
   #
   # This program and the accompanying materials are made available under the
   # terms of the Apache License Version 2.0 which is available at
   # https://www.apache.org/licenses/LICENSE-2.0
   #
   # SPDX-License-Identifier: Apache-2.0
   # *******************************************************************************

.. _itf_architecture:

Architecture
============

ITF composes a test target from declarations instead of coding it as a class. Three layers, each
depending only on the one below:

.. code-block:: text

   pytest adapter      score/itf/core/adapters/pytest   discovery, gating, bring-up, fixtures
   ITF core            score/itf/core                   session, contexts, realization, probes,
                                                         execution, unwind, YAML frontend
   OCTO                score/itf/core/octo               the planner: pure standard library

Packs (``score/itf/packs``) and recipes (a test's root ``conftest.py``) depend on the core's public
API only, and never on each other. Gates in ``//test/core:gates_test`` keep OCTO free of imports
and both OCTO and the core free of domain words (``ssh``, ``docker``, ``dlt``, ...): domain code
lives in packs.

Contracts instead of a target class
-----------------------------------

A *capability contract* is a role named by a token (``itf.capabilities.exec.command``); a
*provider* is one implementation (``docker.exec``, ``ssh.exec``); a *node* is one named instance
in a scope (``target.command``). A *state contract* is a condition (``itf.states.platform.up``)
with an action that establishes it and a probe that checks it. Docker and QEMU are two providers
of ``itf.capabilities.platform.instance``: a test written against the command contract runs on
either.

Packs never share code. A provider publishes the shape of what it returns; a consumer (another
provider's slot, an action, a test's ``@itf.requires(..., shape=...)``) states the members it
needs with its own Protocol. OCTO compares the two at every seam.

Two gates
---------

Before any test is collected, OCTO resolves:

1. **Gate 1, what must exist**: providers chosen, slots bound, shapes checked, construction order.
2. **Gate 2, what must happen**: from the goals, the actions to run and their order, from
   ``requires`` (what must hold first) and ``invalidates`` (what an action destroys). Probes run
   first, so the plan is the delta from what already holds. Actions sharing an implementation
   collapse into one step that verifies each delivered state with its own probe.

A failure is one diagnostic naming the gate, not hundreds of red tests. ``--itf-plan`` stops here.

Lifecycle
---------

.. code-block:: text

   register → publish → itf_setup → Gate 1 → itf_init → probe → Gate 2 → select (gating)
            → bring-up (execute, verify probes) → itf_verify → tests → itf_teardown → unwind

Objects are realized lazily: a deselected test's capabilities are never built. Tests change state
only through the planner: ``target.reach(state)`` and ``target.renew(node)``, the latter
dismantling a node and its dependents, then reaching the goals again. Per-test isolation is a
pytest fixture calling ``renew``: pytest's scopes decide when, the planner decides what.

Bazel integration
-----------------

``py_itf_test`` builds a ``py_test`` that loads the ITF adapter and the listed ``py_itf_plugin``
targets (packs, or plain pytest plugins), adds their runfiles and environment, and expands
``$(location)`` in ``args`` and ``env``. Packs ship their tools (dlt-receive, tcpdump) as
Bazel-built data found through runfiles; a hermetic C/C++ toolchain builds them. Run artifacts go
to ``$TEST_UNDECLARED_OUTPUTS_DIR/itf-run``. ``//tools/catalog`` builds the pack catalog from the
packs' own decorators.

ITF no longer ships the original ``Target`` API; a project keeps old tests running with its own
legacy layer over the packs (``examples/examples/legacy``); see :doc:`../how-to/migrate`.
