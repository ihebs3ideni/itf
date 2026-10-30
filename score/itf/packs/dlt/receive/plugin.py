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
"""Entrypoint: DLT through the bundled dlt-receive, recorded to a file and queried with python-dlt."""

pytest_plugins = ["score.itf.packs.dlt.receive.providers", "score.itf.packs.dlt.receive.steps"]
