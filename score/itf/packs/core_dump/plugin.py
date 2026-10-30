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
"""Entrypoint: with --extract-core-dumps, copy core files off every scope that offers
`itf.capabilities.exec.command` and `itf.capabilities.files.transfer`, at teardown while the target
still runs. Scopes lacking either are skipped with a warning."""

import logging
import os

from score.itf.core import hookimpl

from .extract import extract_core_dumps

logger = logging.getLogger(__name__)

COMMAND = "itf.capabilities.exec.command"
FILES = "itf.capabilities.files.transfer"
_options: dict = {}


def pytest_addoption(parser):
    group = parser.getgroup("itf-core-dump")
    group.addoption(
        "--extract-core-dumps",
        action="store_true",
        default=False,
        help="copy core dump files from the target to the host before teardown",
    )
    group.addoption(
        "--core-dumps-output-dir",
        default=os.path.join(os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", "/tmp"), "coredumps"),
        help="where extracted core dumps go (default: $TEST_UNDECLARED_OUTPUTS_DIR/coredumps)",
    )


def pytest_configure(config):
    _options.update(enabled=config.getoption("extract_core_dumps"), out=config.getoption("core_dumps_output_dir"))


def _first(view, token: str):
    """The first node of `token` in this scope; a view's plan lists only its own scope's nodes."""
    names = sorted(n["name"] for n in view.plan()["target"]["nodes"] if n["contract"] == token)
    return view.get(names[0]) if names else None


@hookimpl
def itf_teardown(session):
    if not _options.get("enabled"):
        return
    target = session.target
    for label, view in [("target", target)] + [(name, getattr(target, name)) for name in target.scopes()]:
        if not (view.has(COMMAND) and view.has(FILES)):
            logger.warning("%s offers no %s and %s: skipping core dump extraction", label, COMMAND, FILES)
            continue
        output = _options["out"] if view.scope is None else os.path.join(_options["out"], view.scope)
        os.makedirs(output, exist_ok=True)
        extract_core_dumps(_first(view, COMMAND), _first(view, FILES), output)
