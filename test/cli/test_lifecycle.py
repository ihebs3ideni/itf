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
"""`itf validate`, `graph`, `up --detach`, `down` and `test`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import cli_parts  # noqa: E402

from score.itf.cli import main as cli  # noqa: E402
from score.itf.cli.main import main  # noqa: E402

DEFINITIONS = str(Path(__file__).parent / "definitions")

SIM = """
capabilities:
  platform:
    factory: sim.docker_platform
    with:
      name: box
      state_dir: {state}
  command: sim.docker_exec
goals:
  - platform.up
"""


def write(tmp_path, text, name="target.itf.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


@pytest.fixture
def project(monkeypatch):
    """The project's own parts, as `conftest.py` would hold them."""
    monkeypatch.setattr(cli, "project_conftest", lambda: cli_parts)


# ---- validate -----------------------------------------------------------------------------------------------


def test_validate_says_ok_and_constructs_nothing(tmp_path, capsys):
    target = write(tmp_path, SIM.format(state=tmp_path / "state"))
    assert main(["validate", target]) == 0
    assert "ok:" in capsys.readouterr().out
    assert not (tmp_path / "state").exists()


def test_validate_uses_the_configured_target(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ITF_TARGET", write(tmp_path, SIM.format(state=tmp_path)))
    assert main(["validate"]) == 0


def test_validate_exits_1_with_the_gate_diagnostics(tmp_path, capsys):
    assert main(["validate", write(tmp_path, "capabilities:\n  command: sim.docker_exec\n")]) == 1
    err = capsys.readouterr().err
    assert "plan failed at gate 1" in err and "Candidates: sim.docker_platform" in err


def test_validate_reports_a_wrong_setting_with_the_role(tmp_path, capsys):
    text = "capabilities:\n  platform:\n    factory: sim.docker_platform\n    with:\n      nam: x\n"
    assert main(["validate", write(tmp_path, text)]) == 1
    assert "platform (sim.docker_platform)" in capsys.readouterr().err


def test_validate_reports_an_unknown_factory_and_a_relation_naming_nothing(tmp_path, capsys):
    assert main(["validate", write(tmp_path, "capabilities:\n  command: sim.nope\n")]) == 1
    assert "not a known capability factory" in capsys.readouterr().err
    text = SIM.format(state=tmp_path) + "relations:\n  - state: ghost.state\n    after:\n      - platform.up\n"
    assert main(["validate", write(tmp_path, text, "r.itf.yaml")]) == 1
    assert "no listed action makes 'ghost.state'" in capsys.readouterr().err


def test_validate_checks_the_parts_against_their_definitions(tmp_path, monkeypatch, project, capsys):
    monkeypatch.setenv("ITF_CONTRACTS_PATH", DEFINITIONS)
    target = write(tmp_path, "capabilities:\n  dial: project.dial\n")
    assert main(["validate", target]) == 1
    assert "project.dial offers acme/dial without turn, which its definition requires" in capsys.readouterr().err
    monkeypatch.delenv("ITF_CONTRACTS_PATH")
    assert main(["validate", target]) == 0


# ---- plan ---------------------------------------------------------------------------------------------------


def test_plan_names_the_action_of_each_step(tmp_path, capsys):
    assert main(["plan", write(tmp_path, SIM.format(state=tmp_path))]) == 0
    assert "platform.up by sim.docker_start" in capsys.readouterr().out


# ---- graph --------------------------------------------------------------------------------------------------


def test_graph_topology_has_roles_factories_contracts_and_slots(tmp_path, capsys):
    target = write(tmp_path, SIM.format(state=tmp_path))
    assert main(["graph", target, "--kind", "topology"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("flowchart LR")
    assert 'n_command["command<br/>sim.docker_exec<br/>exec.command"]' in out
    assert 'n_platform["platform<br/>sim.docker_platform<br/>platform.instance"]' in out
    assert "n_command -->|platform| n_platform" in out


def test_graph_topology_draws_scopes_and_shares(tmp_path, capsys):
    text = SIM.format(state=tmp_path) + (
        "scopes:\n  gw:\n    capabilities:\n      command: sim.docker_exec\n    share:\n      - platform\n"
    )
    assert main(["graph", write(tmp_path, text), "--kind", "topology"]) == 0
    out = capsys.readouterr().out
    assert 'subgraph s_gw["scope gw"]' in out
    assert "n_gw_platform -.->|shares| n_platform" in out
    assert "n_gw_command -->|platform| n_platform" in out


def test_graph_sequence_marks_probes_goals_after_and_breaks(tmp_path, project, capsys):
    text = (
        "capabilities: {}\ngoals:\n  - acme/x\n  - acme/y\n  - acme/z\n"
        "relations:\n  - state: acme/y\n    after:\n      - acme/x\n"
    )
    assert main(["graph", write(tmp_path, text), "--kind", "sequence"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("flowchart TB")
    assert "project.make_y<br/>probe: skipped when it holds" in out  # a probe: the step can be skipped
    assert "project.make_x<br/>no probe: always runs" in out
    assert "|after acme/x|" in out and "|breaks acme/x|" in out
    assert "classDef goal" in out


def test_graph_both_is_two_fenced_blocks_and_the_default(tmp_path, capsys):
    target = write(tmp_path, SIM.format(state=tmp_path))
    assert main(["graph", target]) == 0
    out = capsys.readouterr().out
    assert out.count("```mermaid") == 2 and "%% topology" in out and "%% sequence" in out
    assert main(["graph", target, "--kind", "sequence", "--format", "mermaid"]) == 0
    assert "```" not in capsys.readouterr().out


def test_graph_from_a_target_that_does_not_compile_exits_1(tmp_path, capsys):
    assert main(["graph", write(tmp_path, "capabilities:\n  command: sim.docker_exec\n")]) == 1


# ---- up --detach and down -----------------------------------------------------------------------------------


def test_detach_leaves_it_up_and_down_takes_it_down_in_a_fresh_session(tmp_path, capsys):
    state = tmp_path / "state"
    target = write(tmp_path, SIM.format(state=state))
    run = ["--run-dir", str(tmp_path / "run")]
    assert main(["up", "--detach", target, *run]) == 0
    assert "detached" in capsys.readouterr().out
    assert (state / "box.up").is_file()  # nothing unwound it
    assert main(["down", target, *run]) == 0
    out = capsys.readouterr().out
    assert "observed (1): platform.up" in out and "dismantled (1): platform" in out
    assert not (state / "box.up").exists()
    assert main(["down", target, *run]) == 0
    assert "nothing held" in capsys.readouterr().out


def test_up_without_detach_unwinds_what_it_built(tmp_path, capsys):
    state = tmp_path / "state"
    assert main(["up", write(tmp_path, SIM.format(state=state)), "--run-dir", str(tmp_path / "run")]) == 0
    assert not (state / "box.up").exists()


def test_detach_and_down_are_refused_for_a_factory_that_cannot_observe(tmp_path, capsys):
    target = write(tmp_path, SIM.format(state="").replace("      state_dir: \n", ""))
    run = ["--run-dir", str(tmp_path / "run")]
    assert main(["up", "--detach", target, *run]) == 1
    err = capsys.readouterr().err
    assert "--detach refused" in err and "platform (sim.docker_platform)" in err and "observes=True" in err
    assert main(["down", target, *run]) == 1
    assert "down refused" in capsys.readouterr().err


def test_local_observes_only_with_a_root(tmp_path, capsys):
    plain = write(tmp_path, "capabilities:\n  platform: local.platform\ngoals:\n  - platform.up\n")
    assert main(["down", plain, "--run-dir", str(tmp_path / "run")]) == 1
    rooted = write(
        tmp_path,
        f"capabilities:\n  platform:\n    factory: local.platform\n    with:\n      root: {tmp_path / 'bench'}\n"
        "goals:\n  - platform.up\n",
        "rooted.itf.yaml",
    )
    run = ["--run-dir", str(tmp_path / "run")]
    assert main(["up", "--detach", rooted, *run]) == 0
    assert (tmp_path / "bench").is_dir()
    assert main(["down", rooted, *run]) == 0
    assert not (tmp_path / "bench").exists()


# ---- test ---------------------------------------------------------------------------------------------------


def test_test_configures_the_target_and_hands_the_rest_to_pytest(tmp_path, monkeypatch):
    import pytest as pytest_module

    seen = {}
    monkeypatch.setattr(pytest_module, "main", lambda args: seen.update(args=args) or 0)
    monkeypatch.setattr(cli, "_adapter_is_installed", lambda: False)
    monkeypatch.delenv("ITF_TARGET", raising=False)
    target = write(tmp_path, SIM.format(state=tmp_path))
    assert main(["test", "--target", target, "-k", "fast", "tests/"]) == 0
    assert seen["args"] == ["-p", cli.ADAPTER, "-k", "fast", "tests/"]
    import os

    assert os.environ["ITF_TARGET"] == target
    monkeypatch.delenv("ITF_TARGET")


def test_test_runs_the_tests_against_the_composition(tmp_path, monkeypatch):
    test = tmp_path / "test_it.py"
    test.write_text(
        "import pytest\nfrom score.itf.core import requires\n\n"
        "@requires('command')\ndef test_runs(target):\n    assert target.command.exec('x') == (0, 'ok:x')\n",
        encoding="utf-8",
    )
    target = write(tmp_path, SIM.format(state=tmp_path / "state"))
    monkeypatch.setenv("ITF_TARGET", "")
    assert main(["test", "--target", target, "-p", "no:cacheprovider", "-q", str(test)]) == 0
    monkeypatch.delenv("ITF_TARGET")
