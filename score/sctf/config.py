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


# Default retry settings: try COUNT times, waiting DELAY_S between each attempt
RETRY_COUNT = 150
RETRY_DELAY_S = 0.5

# Default duration in seconds for given operation to end
TIMEOUT_S = 15

# Setup test duration, accessible from code to cleanup all spawned processes
TEST_TIMEOUT_S = 60

# Whether to print temporary file system after the test
FILE_SYSTEM_PRINT = False

# Whether to copy temporary file system to test outputs for post-test analysis
FILE_SYSTEM_COPY = "COVERAGE" in os.environ

# Whether to enable DLT logging daemon to log to console, this may be verbose
DLT_LOGS_IN_CONSOLE = True

# Override application logging
APPLICATION_LOGGING_OVERRIDE = True
APPLICATION_LOGGING_OVERRIDE_CONFIG = {
    "logLevel": "kDebug",
    "logMode": "kRemote|kConsole|kFile",
    "logLevelThresholdConsole": "kDebug",
    "contextConfigs": [],
    "dynamicDatarouterIdentifiers": True,
}

# Override someip_config.json network interfaces, don't use production values
SOMEIP_CONFIG_OVERRIDE = True
SOMEIP_CONFIG_OVERRIDE_INTERFACES_FROM = [
    "160.48.199.77",  # Used by bindings, as the processor contacting the xPAD
    "160.48.199.101",  # mPAD High PP / IPNEXT PP
    "160.48.199.34",  # mPAD PP
]
SOMEIP_CONFIG_OVERRIDE_INTERFACES_TO = "127.0.0.1"

# Some SCTF environments require executionDependency NOT to be removed
EXEC_CONFIG_EXECUTION_DEPENDENCY = "executionDependency"
# Whether to override the exec_config.json by removing chosen elements
EXEC_CONFIG_OVERRIDE = True
EXEC_CONFIG_OVERRIDE_REMOVE = [
    "resourceGroup",
    "schedulingPolicy",
    "schedulingPriority",
    "userId",
    "primaryGroupId",
    "secondaryGroupIds",
    EXEC_CONFIG_EXECUTION_DEPENDENCY,
]
EXEC_CONFIG_OVERRIDE_ADD = {"inheritSecondaryGroups": True}

# Additional tool to run applications under, i.e. valgrind, strace, gdb
# The command should be a string that will be used as a prefix before the tested applications
RUN_APPS_UNDER_TOOL = os.getenv("RUN_APPS_UNDER_TOOL", default="")

# List of apps to run under the tool defined in RUN_APPS_UNDER_TOOL
RUN_APPS_UNDER_LIST = os.getenv("RUN_APPS_UNDER_LIST", default="").split(",")
