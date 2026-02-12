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
import os
import sys
import logging
import pytest
from score.itf.core.utils import bazel

logger = logging.getLogger(__name__)


def run(current_file):
    args = (
        sys.argv[1:]
        + [f"--junitxml={os.path.join(bazel.get_output_dir(), 'sctf-results.xml')}"]
        + ["-s", "--show-capture=no"]
        + [current_file]
    )

    sys.exit(pytest.main(args))
