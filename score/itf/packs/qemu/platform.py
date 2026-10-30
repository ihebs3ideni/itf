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
"""The QEMU process behind `qemu.instance`, booting copy-on-write overlays of its images."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass

from score.itf.core.process import ProcessWrapper

from .config import QemuConfigModel, load_configuration
from .image_format import get_image_format
from .qemu import Qemu

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformConfig:
    config_file: str
    kernel: str | None = None
    rootfs: str | None = None
    disk: str | None = None
    binary_dir: str = "/usr/bin"


def create_overlay(base_image: str) -> str:
    """A temporary qcow2 overlay backed by `base_image`, so the image itself is never modified."""
    fd, overlay = tempfile.mkstemp(suffix=".qcow2", prefix="qemu_overlay_")
    os.close(fd)
    code, _, stderr = ProcessWrapper.run(
        "qemu-img", ["create", "-f", "qcow2", "-b", base_image, "-F", get_image_format(base_image), overlay]
    )
    if code != 0:
        raise RuntimeError(f"qemu-img create failed ({code}): {stderr}")
    logger.info("Created qcow2 overlay %s (backing %s)", overlay, base_image)
    return overlay


def _absolute(path: str | None) -> str | None:
    return os.path.abspath(path) if path else None


class QemuPlatform:
    """`itf.capabilities.platform.instance`: one QEMU process, its console on stdio."""

    qemu_config: QemuConfigModel
    console: PipeConsole | None
    kernel: str | None
    rootfs: str | None
    disk: str | None

    def __init__(self, config: dict):
        self.qemu_config = load_configuration(config["config_file"])
        self.kernel = _absolute(config.get("kernel"))
        self.rootfs = _absolute(config.get("rootfs"))
        self.disk = _absolute(config.get("disk"))
        self.binary_dir = config.get("binary_dir", "/usr/bin")
        if not (self.kernel or self.rootfs):
            raise ValueError("a QEMU platform needs a kernel, a rootfs, or both")
        self.console = None
        self._qemu: Qemu | None = None
        self._overlays: list[str] = []

    def start(self) -> None:
        rootfs = create_overlay(self.rootfs) if self.rootfs else None
        disk = create_overlay(self.disk) if self.disk else None
        self._overlays = [o for o in (rootfs, disk) if o]
        c = self.qemu_config
        self._qemu = Qemu(
            self.kernel,
            c.qemu_ram_size,
            c.qemu_num_cores,
            machine=c.qemu_machine,
            network_adapters=[n.name for n in c.networks],
            port_forwarding=c.port_forwarding,
            rootfs=rootfs,
            kernel_cmdline=c.qemu_kernel_cmdline,
            disk=disk,
            binary_dir=self.binary_dir,
        )
        logger.info("Starting QEMU (kernel=%s, rootfs=%s, disk=%s)", self.kernel, self.rootfs, self.disk)
        self.console = self._qemu.start().console

    def running(self) -> bool:
        return self._qemu is not None and self._qemu._subprocess is not None and self._qemu._subprocess.is_running()

    def stop(self) -> None:
        try:
            if self._qemu is not None and self._qemu._subprocess is not None:
                logger.info("Stopping QEMU")
                self._qemu.stop()
        finally:
            self._qemu = None
            for overlay in self._overlays:
                if os.path.exists(overlay):
                    os.unlink(overlay)
            self._overlays = []

    def restart(self) -> None:
        """Power-cycle the VM: a fresh QEMU process booting fresh overlays."""
        self.stop()
        self.start()
