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
"""Entrypoint: with ITF_CORE_DUMPS=1, copy core files off every scope that offers
`command` and `files`, at teardown while the target
still runs. Scopes lacking either are skipped with a warning.

Runner-agnostic: settings come from the environment (ITF_CORE_DUMPS, ITF_CORE_DUMPS_DIR). The pytest
entrypoint (`pytest_plugin`) maps --extract-core-dumps / --core-dumps-output-dir onto them."""

import logging
import os

from score.itf.core import hookimpl

from .extract import extract_core_dumps

logger = logging.getLogger(__name__)

COMMAND = "exec.command"  # contract identifiers: a plan lists nodes by these
FILES = "files.transfer"
ENABLE_ENV = "ITF_CORE_DUMPS"
DIR_ENV = "ITF_CORE_DUMPS_DIR"


def _settings() -> tuple[bool, str]:
    """Enabled flag and output directory, from the environment (the pytest entrypoint sets them from its options)."""
    default_dir = os.path.join(os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", "/tmp"), "coredumps")
    return os.environ.get(ENABLE_ENV) == "1", os.environ.get(DIR_ENV) or default_dir


def _first(view, token: str):
    """The first node of `token` in this scope; a view's plan lists only its own scope's nodes."""
    names = sorted(n["name"] for n in view.plan()["target"]["nodes"] if n["contract"] == token)
    return view.get(names[0]) if names else None


@hookimpl
def itf_teardown(session):
    enabled, out = _settings()
    if not enabled:
        return
    target = session.target
    for label, view in [("target", target)] + [(name, getattr(target, name)) for name in target.scopes()]:
        if not (view.has(COMMAND) and view.has(FILES)):
            logger.warning("%s offers no %s and %s: skipping core dump extraction", label, COMMAND, FILES)
            continue
        output = out if view.scope is None else os.path.join(out, view.scope)
        os.makedirs(output, exist_ok=True)
        extract_core_dumps(_first(view, COMMAND), _first(view, FILES), output)
