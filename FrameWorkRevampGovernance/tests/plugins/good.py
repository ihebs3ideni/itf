"""A well-behaved plugin: namespaced contracts, resolvable requirements."""

from __future__ import annotations

from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor


@provides("score/doip/client")
@requires("score/transport/doip")
def doip_client(transport):
    return {"client": transport}


def provision(ctx):
    ctx.artifacts.add("provisioned")


def pytest_ctf_setup(registry, config):
    registry.add_descriptor(Descriptor("score/transport/doip", value="10.0.0.1:13400"))
    registry.register(doip_client)


def pytest_ctf_steps(steps, config):
    steps.add("ctf_provision", provision, name="good_provision")
