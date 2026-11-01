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
"""Readiness and evidence for the container starter."""

import logging
import os
from pathlib import Path

from score.itf.core import hookimpl


log = logging.getLogger("starter.container")
EVIDENCE = Path(os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", ".")) / "evidence"


@hookimpl
def itf_verify(session):
    """Checked once after bring-up: the container runs and answers a command."""
    target = session.target
    code, output = target.command.exec("echo -n ready")
    session.check("command.answers", code == 0 and output.strip() == "ready", detail=f"exit {code}, output {output!r}")
    session.check("platform.running", target.platform.running())


@hookimpl
def itf_teardown(session):
    """Saves the container's output while it still runs, before it is removed."""
    container = getattr(session.target.platform, "container", None)
    if container is None:
        return
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / "container.log"
    path.write_bytes(container.logs())
    log.info("teardown: container output saved to %s", path)
