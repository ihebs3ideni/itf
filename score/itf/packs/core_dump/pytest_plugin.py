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
"""Pytest entrypoint of the core_dump pack: the --extract-core-dumps and --core-dumps-output-dir
options, mapped onto the environment variables the runner-agnostic `plugin` reads."""

import os

from .plugin import DIR_ENV, ENABLE_ENV


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
        default=None,
        help="where extracted core dumps go (default: $TEST_UNDECLARED_OUTPUTS_DIR/coredumps)",
    )


def pytest_configure(config):
    if config.getoption("extract_core_dumps"):
        os.environ[ENABLE_ENV] = "1"
    if config.getoption("core_dumps_output_dir"):
        os.environ[DIR_ENV] = config.getoption("core_dumps_output_dir")
