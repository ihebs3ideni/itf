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
from score.sctf.utils.file_utils import *


# Since the dynamic fixture scope function is called early in initialization stage
# the easiest way to pass a parameter is via py_sctf_test(env=...)
def get_filesystem_scope(fixture_name, config):  # pylint: disable=unused-argument
    return os.environ.get("FILE_SYSTEM_SCOPE", "function")  # default scope is "function"
