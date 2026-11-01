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
"""`@capability` and `@state`: slots, settings, labels, errors."""

import sys
from dataclasses import dataclass
from typing import Protocol

import pytest

from score.itf.core import DuplicateLabel, capability, state
from score.itf.core.engine.publish import _STAGING


class Shell(Protocol):
    __contract__ = "exec.shell"

    def run(self, command: str) -> str: ...


class Versioned(Protocol):
    __contract__ = "exec.shell@2"

    def run(self, command: str) -> str: ...


class NoContract(Protocol):
    def run(self, command: str) -> str: ...


@dataclass
class Settings:
    port: int = 22


class Exec:
    def exec(self, command): ...


def staged(label):
    return next(d for d in _STAGING[__name__] if d.label == label)


def test_a_capability_factory_has_a_label_from_its_function_name():
    @capability("exec.command")
    def run_it(shell: Shell) -> Exec: ...

    descriptor = staged("project.run_it")
    assert descriptor.pack == "project"
    assert descriptor.contract == "exec.command"
    assert run_it.__itf_label__ == "project.run_it"


def test_label_overrides_the_function_name():
    @capability("exec.command", label="exec")
    def make(shell: Shell) -> Exec: ...

    assert staged("project.exec").impl.endswith(".make")


def test_a_slot_takes_its_contract_and_shape_from_its_annotation():
    @capability("exec.command", label="slotted")
    def make(shell: Shell) -> Exec: ...

    (need,) = staged("project.slotted").needs
    assert (need.slot, need.contract) == ("shell", "exec.shell")
    assert {m.name for m in need.expected.members} == {"run"}  # `__contract__` is not a member


def test_the_published_shape_is_the_return_annotation():
    @capability("exec.command", label="shaped")
    def make() -> Exec: ...

    assert {m.name for m in staged("project.shaped").gives.members} == {"exec"}


def test_gives_overrides_the_return_annotation():
    @capability("exec.command", label="untyped", gives=("exec", "extra"))
    def make(): ...

    assert {m.name for m in staged("project.untyped").gives.members} == {"exec", "extra"}


def test_a_generator_factory_publishes_what_it_yields():
    from collections.abc import Iterator

    @capability("exec.command", label="yielding")
    def make() -> Iterator[Exec]:
        yield Exec()

    assert {m.name for m in staged("project.yielding").gives.members} == {"exec"}


def test_a_dataclass_named_config_is_the_settings_schema():
    @capability("exec.command", label="configured")
    def make(config: Settings) -> Exec: ...

    schema = staged("project.configured").config_schema
    assert [f.name for f in schema.fields] == ["port"]
    assert schema.validate({"port": "x"}) and not schema.validate({"port": 2})


def test_major_is_split_from_the_contract_and_from_a_slot():
    @capability("exec.command@1", label="majored")
    def make(shell: Versioned) -> Exec: ...

    descriptor = staged("project.majored")
    assert (descriptor.contract, descriptor.major) == ("exec.command", 1)
    assert descriptor.need_majors == {"shell": 2}


def test_an_unannotated_parameter_is_an_error_naming_it():
    with pytest.raises(TypeError) as error:

        @capability("exec.command", label="bad")
        def make(shell): ...

    assert "'shell'" in str(error.value) and "__contract__" in str(error.value)


def test_an_annotation_without_a_contract_is_an_error_naming_the_parameter():
    with pytest.raises(TypeError, match="'shell'"):

        @capability("exec.command", label="bad")
        def make(shell: NoContract): ...


def test_config_must_be_a_dataclass():
    with pytest.raises(TypeError, match="'config'.*dataclass"):

        @capability("exec.command", label="bad")
        def make(config: dict): ...


def test_an_action_has_slots_after_breaks_and_also():
    @state("shell.open", after=("platform.up",), breaks=("shell.closed",), also=("network.reachable",), label="open")
    def open_it(shell: Shell) -> None: ...

    descriptor = staged("project.open")
    assert (descriptor.state, descriptor.after, descriptor.breaks, descriptor.also) == (
        "shell.open",
        ("platform.up",),
        ("shell.closed",),
        ("network.reachable",),
    )
    assert [n.slot for n in descriptor.uses] == ["shell"]


def test_a_state_list_given_as_a_string_is_an_error():
    with pytest.raises(TypeError, match="tuple"):

        @state("shell.open", after="platform.up")
        def open_it(): ...


def test_a_probe_takes_the_actions_slots():
    @state("shell.open", label="probed")
    def open_it(shell: Shell) -> None: ...

    @open_it.probe
    def is_open(shell: Shell) -> bool: ...

    assert staged("project.probed").probe.endswith("is_open")
    with pytest.raises(TypeError, match="probe"):

        @open_it.probe
        def wrong(other: Shell) -> bool: ...


def test_probe_for_names_a_state_the_action_also_makes():
    @state("shell.open", also=("network.reachable",), label="two")
    def open_it(shell: Shell) -> None: ...

    @open_it.probe_for("network.reachable")
    def reachable(shell: Shell) -> bool: ...

    assert staged("project.two").extra_probes == {
        "network.reachable": reachable.__module__ + ":" + reachable.__qualname__
    }
    with pytest.raises(TypeError, match="also"):
        open_it.probe_for("other.state")


def test_the_same_label_twice_in_a_module_is_an_error():
    @capability("exec.command", label="twice")
    def first() -> Exec: ...

    with pytest.raises(DuplicateLabel, match="project.twice"):

        @capability("exec.command", label="twice")
        def second() -> Exec: ...


def test_the_same_label_in_two_modules_is_an_error_when_published(tmp_path, monkeypatch):
    from score.itf.core.engine import registry
    from score.itf.core.engine.publish import publish

    for name in ("dup_one", "dup_two"):
        (tmp_path / f"{name}.py").write_text(
            "from score.itf.core import capability\n\n@capability('x.y', label='clash')\ndef make(): ...\n",
            encoding="utf-8",
        )
    monkeypatch.syspath_prepend(str(tmp_path))
    import dup_one
    import dup_two

    try:
        reg = registry.register_modules([(dup_one, "conftest"), (dup_two, "conftest")])
        with pytest.raises(DuplicateLabel, match="project.clash"):
            publish(reg)
    finally:
        for name in ("dup_one", "dup_two"):
            sys.modules.pop(name, None)


def test_the_pack_is_the_pack_yaml_name_above_the_module(tmp_path, monkeypatch):
    package = tmp_path / "mypack_dir"
    package.mkdir()
    (package / "pack.yaml").write_text("name: acme\nversion: 1\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "parts.py").write_text(
        "from score.itf.core import capability, state\n\n"
        "@capability('x.y')\ndef thing(): ...\n\n"
        "@state('x.up', label='go')\ndef go(): ...\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    import mypack_dir.parts as parts

    try:
        assert parts.thing.__itf_label__ == "acme.thing"
        assert parts.go.__itf_label__ == "acme.go"
    finally:
        for name in [n for n in sys.modules if n.startswith("mypack_dir")]:
            del sys.modules[name]
