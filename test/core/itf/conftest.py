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
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

from score.itf.core.engine.publish import _STAGING  # noqa: E402


@pytest.fixture(autouse=True)
def _artifacts_beside_each_nested_run(monkeypatch):
    """Nested pytest runs write itf-run/ in their own root, not in this Bazel test's outputs."""
    monkeypatch.delenv("TEST_UNDECLARED_OUTPUTS_DIR", raising=False)
    for name in ("ITF_TARGET", "ITF_OVERRIDE", "ITF_TARGET_DOCUMENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _staging_stays_with_the_test():
    """Parts declared inside a test are staged under the test module; they must not leak into the next test."""
    before = {k: list(v) for k, v in _STAGING.items()}
    yield
    for key in set(_STAGING) - set(before):
        del _STAGING[key]
    for key, staged in before.items():
        _STAGING[key] = staged
