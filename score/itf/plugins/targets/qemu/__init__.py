"""QEMU target package.

Library exports: qemu_target, QemuRuntime, load_configuration.
Plugin wiring lives in ``plugin.py`` (loaded via pytest_plugins).
"""

from score.itf.plugins.targets.qemu.runtime import qemu_target
from score.itf.plugins.targets.qemu.config import load_configuration

__all__ = ["qemu_target", "load_configuration"]
