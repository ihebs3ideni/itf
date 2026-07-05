from __future__ import annotations

import json

from ctf_governance.cli import main


def test_cli_text_output_healthy(capsys):
    rc = main(["tests.plugins.good"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "CONTRACTS" in out
    assert "score/doip/client" in out
    assert "0 error(s)" in out


def test_cli_reports_errors_nonzero(capsys):
    rc = main(["tests.plugins.dup_a", "tests.plugins.dup_b"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "duplicate-provider" in out


def test_cli_strict_fails_on_warnings(capsys):
    # bad_namespace only trips a warning; --strict should still fail.
    rc = main(["--strict", "tests.plugins.bad_namespace"])
    assert rc == 1


def test_cli_json_output(capsys):
    rc = main(["--format", "json", "tests.plugins.good"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["summary"]["errors"] == 0
    contracts = {c["contract"] for c in payload["contracts"]}
    assert "score/doip/client" in contracts


def test_cli_import_error_returns_2(capsys):
    rc = main(["tests.plugins.does_not_exist"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "could not load plugin" in err
