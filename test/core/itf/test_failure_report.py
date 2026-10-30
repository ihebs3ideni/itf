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
"""The failure report: a `=== ... ===` section a person can read, built from what the session knows."""

import pytest

from score.itf.core.session import NotReady, Session


def _failure(recipe, tmp_path):
    session = Session([recipe], run_dir=tmp_path)
    session.resolve()
    with pytest.raises(NotReady) as raised:
        session.bring_up()
    session.close()
    return raised.value.failure


def test_a_failing_action_is_reported_with_its_cause_and_how_far_bring_up_got(tmp_path):
    text = _failure("boom_recipe", tmp_path).render(width=100)
    assert text.splitlines()[0].startswith("=") and "ITF: bring-up failed" in text.splitlines()[0]
    for label in ("What failed", "Delivers", "Position", "Why", "Done before", "Not run", "Evidence"):
        assert label in text
    assert "boom_pack" in text, "names the action, not only its state"
    assert str(tmp_path) in text, "points at where the run's evidence is"


def test_a_probe_that_disagrees_with_its_action_says_so_in_plain_words(tmp_path):
    text = _failure("liar_recipe", tmp_path).render(width=100)
    assert "returned without error" in text and "lie_state" in text


def test_failed_startup_checks_are_listed_first_with_the_passing_ones_after(tmp_path):
    failure = _failure("checks_fail_recipe", tmp_path)
    assert failure.title == "ITF: startup checks failed"
    verdicts = [label for label, _ in failure.rows]
    assert verdicts.index("FAILED") < verdicts.index("PASSED")


def test_generic_hints_follow_how_the_cause_reads():
    from score.itf.core.engine.failure import hints_for

    assert hints_for("ConnectionRefusedError: Connection refused")
    assert hints_for("TimeoutError: timed out")
    assert hints_for("something nobody has seen before") == ()


def test_teardown_problems_are_reported_and_a_clean_close_reports_none(tmp_path):
    clean = Session(["shell_recipe"], run_dir=tmp_path / "clean")
    clean.resolve()
    clean.bring_up()
    clean.close()
    assert clean.close_problems() is None

    broken = Session(["two_teardowns_recipe"], run_dir=tmp_path / "broken")
    broken.resolve()
    broken.bring_up()
    broken.close()
    text = broken.close_problems().render(width=100)
    assert "ITF: teardown problems" in text and "hook" in text
