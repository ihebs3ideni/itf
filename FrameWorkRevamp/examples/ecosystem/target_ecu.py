"""TARGET plugin: an ECU that publishes facts about itself.

This module imports ONLY the ctf core. It has no idea that DoIP, UDS, or SSH
capabilities exist. It just states, as opaque descriptors: "a DoIP transport is
reachable here" and "an SSH endpoint lives here". Whether anything consumes
those facts is not its concern.
"""

from __future__ import annotations

from ctf.descriptor import Descriptor
from ctf.target import DescriptorTarget


def pytest_ctf_setup(registry, config):
    registry.add_target(
        DescriptorTarget(
            [
                Descriptor("transport/doip", value="10.0.0.1:13400"),
                Descriptor("endpoint/ssh", value="10.0.0.1", metadata={"user": "root"}),
            ]
        )
    )
