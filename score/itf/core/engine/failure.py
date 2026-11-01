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
"""The failure report: what a person reads when the session cannot get ready.

pytest prints a `=== FAILURES ===` section for a failing test; ITF prints an equivalent section when
bring-up, a startup check or a teardown hook fails, because those failures happen before or after any
test and would otherwise show up as one line of exception text. A report answers four questions in
order: what failed, how far the run got, why (with the original cause), and what to look at next.

Building a report only reads what the session already knows (the plan, how far execution got, the check
results); it runs no action and probes nothing, so it is safe to call from an error path.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from .scopes import display
from .labels import node_label


@dataclass(frozen=True)
class Failure:
    title: str  # section heading, e.g. "ITF: bring-up failed"
    rows: tuple[tuple[str, str], ...]  # (label, value): value may span several lines
    hints: tuple[str, ...] = ()

    def render(self, width: int | None = None) -> str:
        width = width or shutil.get_terminal_size((100, 20)).columns
        label_width = max((len(label) for label, _ in self.rows), default=0)
        lines = [banner(self.title, width)]
        for label, value in self.rows:
            first, *rest = display(value or "-").splitlines() or ["-"]
            lines.append(f"{label.ljust(label_width)}  {first}")
            lines.extend(f"{' ' * label_width}  {line}" for line in rest)
        if self.hints:
            lines.append("")
            lines.append("What to try")
            lines.extend(f"  - {hint}" for hint in self.hints)
        lines.append("=" * width)
        return "\n".join(lines)


def banner(title: str, width: int) -> str:
    """`===== title =====` the way pytest draws its section headings."""
    text = f" {title} "
    side = max((width - len(text)) // 2, 3)
    return "=" * side + text + "=" * (width - side - len(text))


# Generic advice keyed on how a failure reads. Domain knowledge (what a particular pack's error means)
# does not belong here: the core names no technology, so these hints only use words every cause shares.
_HINTS = (
    (
        ("connection refused", "connection aborted", "no route to host", "unreachable"),
        "the target did not accept a connection: check that the service is running and the address and port are right",
    ),
    (
        ("timed out", "timeout"),
        "something did not answer in time: look at the console or service log for the target, "
        "and raise the timeout only after you know why it is slow",
    ),
    (
        ("permission denied", "operation not permitted"),
        "an access problem: check the user, file modes and capabilities",
    ),
    (
        ("no such file", "not found"),
        "a file or program is missing: check the path in the composition and what the environment provides",
    ),
)


def hints_for(cause: str) -> tuple[str, ...]:
    text = cause.lower()
    return tuple(hint for needles, hint in _HINTS if any(n in text for n in needles))


def _short(impl: str) -> str:
    return impl.replace(":", ".", 1) if impl else "?"


def _states(ids) -> str:
    return ", ".join(ids) or "-"


def bring_up_failure(error, action_plan, target_plan, run_dir) -> Failure:
    """Why an action failed or its probe said no, and how far bring-up got."""
    step = error.step
    steps = list(action_plan.steps)
    position = next((i for i, s in enumerate(steps) if s.key == getattr(step, "key", None)), None)
    probe_failed = bool(getattr(error, "states", ()))
    cause = (
        "the action returned without error, but the check that proves it worked says "
        f"{_states(error.states)} does not hold"
        if probe_failed
        else f"{type(error.cause).__name__}: {error.cause}"
        if error.cause is not None
        else str(error)
    )
    rows = [
        ("What failed", f"action {_short(step.impl)}" if step is not None else str(error)),
        ("Delivers", _states(step.delivers) if step is not None else "-"),
    ]
    if step is not None and step.requires:
        rows.append(("Needed first", _states(step.requires)))
    if position is not None:
        rows.append(("Position", f"step {position + 1} of {len(steps)}"))
    rows.append(("Why", cause))
    rows.append(("Done before", _done(error.executed, error.skipped)))
    pending = [s.key for s in steps[position + 1 :]] if position is not None else []
    rows.append(("Not run", ", ".join(pending) or "-"))
    if step is not None and step.uses:
        rows.append(("Used nodes", ", ".join(f"{slot}={ref}" for slot, ref in step.uses)))
    rows.append(("Target", ", ".join(node_label(n.ref, n.provider) for n in target_plan.nodes) or "-"))
    rows.append(("Evidence", f"{run_dir}  (log, plans and probe results of this run)"))
    return Failure("ITF: bring-up failed", tuple(rows), hints_for(str(error.cause or error)))


def _done(executed, skipped) -> str:
    parts = []
    if executed:
        parts.append(f"ran {', '.join(executed)}")
    if skipped:
        parts.append(f"reused (already held) {', '.join(skipped)}")
    return "; ".join(parts) or "nothing: this was the first step"


def checks_failure(results, run_dir) -> Failure:
    """Every startup check with its verdict, failing ones first with their detail."""
    failing = [c for c in results if c.essential and not c.ok]
    rows = []
    for check in failing:
        rows.append(("FAILED", f"{check.name}" + (f": {check.detail}" if check.detail else "")))
    for check in results:
        if check not in failing:
            verdict = "passed" if check.ok else "failed (not essential)"
            rows.append((verdict.upper() if check.ok else "WARNING", check.name))
    rows.append(("Evidence", f"{run_dir}"))
    hints = (
        "a startup check is an itf_verify hook: fix what it names, or the target is not in the state the checks expect",
    )
    return Failure("ITF: startup checks failed", tuple(rows), hints)


def teardown_failure(teardown_results, unwind_report, run_dir, leaked=()) -> Failure | None:
    """Problems found while closing the session; None when it closed cleanly."""
    rows = [("hook", f"{name}: {detail}") for name, ok, detail in teardown_results if not ok]
    if unwind_report is not None:
        rows += [("node", f"{ref}: {detail}") for ref, detail in unwind_report.errors]
    rows += [("process", f"{description} was still running at close and was terminated") for description in leaked]
    if not rows:
        return None
    rows.append(("Evidence", f"{run_dir}"))
    hints = ("the run itself is not affected; a node that could not be dismantled may still be running",)
    if leaked:
        hints += ("start host processes through ProcessWrapper and stop them in the node's teardown",)
    return Failure("ITF: teardown problems", tuple(rows), hints)
