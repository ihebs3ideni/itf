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
"""`itf plan`, `up`, `doctor` and `diff` on a composition."""

from __future__ import annotations

import json

import pytest

from score.itf.cli import doctor, main as cli
from score.itf.cli.main import main

LOCAL = """
capabilities:
  platform: local.platform
  command: local.exec
goals:
  - platform.up
"""


def write(tmp_path, name="target.itf.yaml", text=LOCAL):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_plan_prints_roles_with_their_factories_contracts_and_actions(tmp_path, capsys):
    assert main(["plan", write(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "roles (2):" in out
    assert "command (local.exec)" in out and "[exec.command]" in out
    assert "platform.up by local.start" in out


def test_plan_json_and_output(tmp_path, capsys):
    target = write(tmp_path)
    assert main(["plan", target, "--json", "--output", str(tmp_path / "plan.json")]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert [n["name"] for n in plan["target"]["nodes"]] == ["command", "platform"]
    assert (tmp_path / "plan.json").is_file()


def test_the_configured_target_is_used_when_none_is_given(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ITF_TARGET", write(tmp_path))
    assert main(["plan"]) == 0
    assert "command (local.exec)" in capsys.readouterr().out


def test_an_override_changes_a_value_by_role(tmp_path, capsys):
    target = write(
        tmp_path,
        text=LOCAL.replace(
            "platform: local.platform", "platform:\n    factory: local.platform\n    with:\n      root: /one"
        ),
    )
    over = write(tmp_path, "lab.yaml", "capabilities:\n  platform:\n    with:\n      root: /two\n")
    assert main(["plan", target, "--override", over, "--json"]) == 0
    nodes = {n["name"]: n for n in json.loads(capsys.readouterr().out)["target"]["nodes"]}
    assert nodes["platform"]["config"] == {"root": "/two"}


def test_a_composition_that_does_not_compile_exits_1_with_the_diagnostics(tmp_path, capsys):
    target = write(tmp_path, text="capabilities:\n  command: local.exec\n")
    assert main(["plan", target]) == 1
    err = capsys.readouterr().err
    assert "plan failed at gate 1" in err and "Candidates: local.platform" in err


def test_a_malformed_composition_is_reported_not_a_traceback(tmp_path, capsys):
    assert main(["plan", write(tmp_path, text="parts: {}\n")]) == 1
    assert "composition rejected" in capsys.readouterr().err


def test_no_composition_is_a_clear_message(capsys):
    assert main(["plan"]) == 1
    assert "no composition" in capsys.readouterr().err


class Terminal:
    def isatty(self):
        return True

    def read(self, *_):
        return ""


@pytest.fixture
def console(monkeypatch):
    seen = {}
    monkeypatch.setattr("sys.stdin", Terminal())

    def interact(banner="", readfunc=None, local=None, exitmsg=None):
        seen["local"] = local
        seen["roles"] = local["target"].names()

    monkeypatch.setattr(cli.code, "interact", interact)
    return seen


def test_up_opens_a_console_with_target_and_session_then_closes(tmp_path, console, capsys):
    assert main(["up", write(tmp_path), "--run-dir", str(tmp_path / "run")]) == 0
    assert console["roles"] == ("command", "platform")
    assert console["local"]["session"]._closed
    out = capsys.readouterr().out
    assert "command (local.exec)" in out and "evidence:" in out


def test_up_without_a_terminal_brings_up_prints_and_unwinds(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.code, "interact", lambda **_: pytest.fail("no console without a terminal"))
    assert main(["up", write(tmp_path), "--run-dir", str(tmp_path / "run")]) == 0
    assert "command (local.exec)" in capsys.readouterr().out


def probes(monkeypatch, **results):
    for key, name in {"engine": "probe_container_engine", "kvm": "probe_kvm", "paramiko": "probe_paramiko"}.items():
        ok = results.get(key, True)
        monkeypatch.setattr(doctor, name, lambda ok=ok, key=key: (ok, f"{key} probe"))


def test_doctor_checks_the_packs_the_composition_names(tmp_path, monkeypatch, capsys):
    probes(monkeypatch, engine=False)
    target = write(tmp_path, text="capabilities:\n  platform: docker.platform\n")
    assert main(["doctor", target]) == 1
    out = capsys.readouterr().out
    assert "packs: docker" in out and "[ FAIL ] container engine reachable" in out and "DOCKER_HOST" in out


def test_doctor_skips_what_no_listed_pack_needs(tmp_path, monkeypatch, capsys):
    probes(monkeypatch, engine=False)
    assert main(["doctor", write(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "packs: local" in out and "container engine" not in out and "no required check failed" in out


def test_diff_compares_two_plans(tmp_path, capsys):
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    assert main(["plan", write(tmp_path), "--json", "--output", str(one)]) == 0
    other = write(tmp_path, "o.yaml", LOCAL.replace("command: local.exec", "command: local.process"))
    assert main(["plan", other, "--json", "--output", str(two)]) == 0
    capsys.readouterr()
    assert main(["diff", str(one), str(one)]) == 0
    assert main(["diff", str(one), str(two)]) == 1
    assert "command" in capsys.readouterr().out
