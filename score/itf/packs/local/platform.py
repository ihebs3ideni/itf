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
"""The host as a platform (`local.instance`): a working directory created at start, removed at stop."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformConfig:
    root: str | None = None


class LocalPlatform:
    """Nothing to boot: `start` creates the working directory commands run in."""

    root: Path | None
    is_local: bool = True

    def __init__(self, config: dict):
        self._configured_root = config.get("root")
        self.root = None
        self._owned = False

    def start(self) -> None:
        if self._configured_root:
            self.root = Path(self._configured_root).absolute()
            self.root.mkdir(parents=True, exist_ok=True)
        else:
            self.root = Path(tempfile.mkdtemp(prefix="itf-local-"))
            self._owned = True

    def running(self) -> bool:
        return self.root is not None and self.root.is_dir()

    def restart(self) -> None:
        """Nothing survives a host restart that matters here; the working directory stays."""

    def stop(self) -> None:
        if self._owned and self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
        self.root = None
