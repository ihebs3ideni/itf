"""End-to-end demonstration of decoupled composition.

The target plugin, the DoIP/UDS/SSH capability plugins, and these tests are all
independent. The DUT is composed by the engine purely from string contracts.
"""

from __future__ import annotations


def test_flash(uds, ssh):
    # uds/client composed from: target -> transport/doip -> doip/client -> uds/client
    assert ssh.run("echo hi") == "[10.0.0.1] echo hi: ok"
    assert uds.read_did(0xF190) == b"ack:read:0xf190"


def test_dut_composes_across_independent_plugins(dut):
    uds = dut.require("uds/client")
    # The UDS capability received a DoIP client built from the target's fact,
    # even though neither plugin imports the other.
    assert uds.doip.endpoint == "10.0.0.1:13400"


def test_lazy_only_builds_requested_capability():
    # Laziness is a property of the composition engine: only the requested
    # subgraph is instantiated. Shown in an isolated session so it is not
    # affected by whatever sibling tests happen to require in the live one.
    import importlib

    from ctf import Registry, compose

    registry = Registry()
    for name in (
        "examples.ecosystem.target_ecu",
        "examples.ecosystem.capability_doip",
        "examples.ecosystem.capability_uds",
        "examples.ecosystem.capability_ssh",
    ):
        importlib.import_module(name).pytest_ctf_setup(registry, None)

    with compose(registry) as dut:
        dut.require("ssh/client")
        # The DoIP/UDS chain was never requested, so it was never instantiated.
        assert "ssh/client" in dut.materialized()
        assert "doip/client" not in dut.materialized()
