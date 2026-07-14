"""DLT capability package.

Library exports: DltReceive, DltWindow, DltOnTargetComponent, Protocol.
Plugin wiring lives in ``plugin.py`` (loaded via pytest_plugins).
"""

from score.itf.plugins.capabilities.dlt.dlt_receive import DltReceive, Protocol
from score.itf.plugins.capabilities.dlt.components import DltOnTargetComponent

# Contracts
CAP_DLT_ON_TARGET_CONTRACT = "itf/cap/dlt_on_target"


def __getattr__(name):
    # Lazy import DltWindow since it depends on python_dlt third-party
    if name == "DltWindow":
        from score.itf.plugins.capabilities.dlt.dlt_window import DltWindow

        return DltWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DltReceive",
    "DltWindow",
    "DltOnTargetComponent",
    "Protocol",
    "CAP_DLT_ON_TARGET_CONTRACT",
]
