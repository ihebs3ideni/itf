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
from dataclasses import dataclass, field
import json

import pytest

from score.itf.core.engine.config import ConfigSchema
from score.itf.core.session import ConfigValidationFailed, DescribeResult, Session


@dataclass(frozen=True)
class Settings:
    image: str
    name: str
    ports: str = ""
    token: str | None = field(default=None, metadata={"sensitive": True})


def test_schema_validates_missing_unknown_and_wrong_types_without_echoing_values():
    schema = ConfigSchema.from_dataclass(Settings)
    issues = schema.validate({"image": 3, "port": "x", "token": 123})
    assert "config.name: required str" in issues
    assert "config.image: expected str" in issues
    assert "config.port: unknown key; did you mean 'ports'?" in issues
    assert "config.token: expected str | null" in issues
    assert schema.validate({"image": "demo", "name": "a", "token": None}) == ()
    assert schema.redact({"image": "demo", "token": "secret"})["token"] == "[redacted]"
    assert all("secret" not in str(issue) for issue in issues)


def test_schema_rejects_unsupported_annotation_at_publication():
    @dataclass
    class Nested:
        data: dict

    with pytest.raises(TypeError, match="scalar"):
        ConfigSchema.from_dataclass(Nested)


def test_config_fails_before_gate_2_or_construction_and_writes_diagnostics(tmp_path, monkeypatch):
    import config_recipe

    monkeypatch.setattr(config_recipe, "CONFIG", {"port": "bad", "porrt": 1})
    config_recipe.CONSTRUCTED.clear()
    session = Session(["config_recipe"], plan_only=True, run_dir=tmp_path)
    with pytest.raises(ConfigValidationFailed) as failure:
        session.resolve()

    assert session._init_claims == frozenset()
    assert config_recipe.CONSTRUCTED == []
    assert "main.client (fixture.client)" in str(failure.value)
    assert "config.host: required str" in str(failure.value)
    assert "did you mean 'port'?" in str(failure.value)
    assert "config.host" in (tmp_path / "diagnostics.txt").read_text()
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["config_issues"] and plan["config_schemas"]["fixture.client"]
    page = (tmp_path / "target.html").read_text()
    start = page.index('id="itf-data">') + len('id="itf-data">')
    node = json.loads(page[start : page.index("</script>", start)])["items"]["n|main.client"]
    assert "config.host: required str" in node["config_issues"]
    assert any(field["name"] == "port" and field["default"] == 8000 for field in node["config_schema"])


def test_sensitive_config_is_redacted_in_all_artifacts(tmp_path, monkeypatch):
    import config_recipe

    monkeypatch.setattr(config_recipe, "CONFIG", {"host": "localhost", "token": "private-value"})
    session = Session(["config_recipe"], plan_only=True, run_dir=tmp_path).resolve()
    for name in ("claims.json", "plan.json", "target.html"):
        text = (tmp_path / name).read_text()
        assert "private-value" not in text
        assert "[redacted]" in text
    schema = json.loads((tmp_path / "plan.json").read_text())["config_schemas"]["fixture.client"]
    assert any(entry["name"] == "token" and entry["sensitive"] for entry in schema)
    assert "private-value" not in DescribeResult(session).render()
    assert "[redacted]" in DescribeResult(session).render()


def test_numeric_float_config_accepts_integer_but_not_bool():
    @dataclass
    class Timeout:
        duration: float

    schema = ConfigSchema.from_dataclass(Timeout)
    assert schema.validate({"duration": 5}) == ()
    assert schema.validate({"duration": True}) == ("config.duration: expected float",)


def test_config_errors_are_collected_across_scopes_before_any_factory_runs(tmp_path, monkeypatch):
    import config_recipe

    monkeypatch.setattr(config_recipe, "CONFIG", {"port": "bad"})
    monkeypatch.setattr(config_recipe, "EXTRA_CONFIG", {"host": 7})
    config_recipe.CONSTRUCTED.clear()
    with pytest.raises(ConfigValidationFailed) as failure:
        Session(["config_recipe"], run_dir=tmp_path).resolve()

    assert {ref for ref, _, _ in failure.value.issues} == {"main.client", "other.client"}
    assert config_recipe.CONSTRUCTED == []
    assert len(json.loads((tmp_path / "plan.json").read_text())["config_issues"]) >= 2
