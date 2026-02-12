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
import logging


def async_log(fd, logger_name):
    """Captures logs from given pipe"""
    logger = logging.getLogger(logger_name)
    for line in iter(fd.readline, ""):
        message = line.rstrip()
        logger.info(message)
