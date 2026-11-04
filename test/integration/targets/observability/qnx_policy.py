"""Multicast routing for the QNX observability guest."""

from typing import Protocol

from score.itf.core import state


class Command(Protocol):
    __contract__ = "exec.command"

    def exec(self, command: str) -> tuple[int, bytes]: ...


@state("traffic.ready", label="configure_multicast")
def configure_multicast(command: Command) -> None:
    code, output = command.exec("route add -net 224.0.0.0/4 -iface vtnet0")
    if code != 0:
        raise RuntimeError(f"guest multicast routing failed: {output!r}")


@configure_multicast.probe
def multicast_route_ready(command: Command) -> bool:
    code, output = command.exec("route -n get 239.255.42.99")
    return code == 0 and b"vtnet0" in output
