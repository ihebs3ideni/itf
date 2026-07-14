"""SSH/SFTP capability package.

Library exports: Ssh, Sftp, SshEndpoint, SshComponent, SftpComponent, SshCommand.
Plugin wiring lives in ``plugin.py`` (loaded via pytest_plugins).
"""

from __future__ import annotations

from dataclasses import dataclass

from score.itf.plugins.capabilities.ssh.ssh import Ssh
from score.itf.plugins.capabilities.ssh.sftp import Sftp
from score.itf.plugins.capabilities.ssh.ssh_command import SshCommand, SshCommandResult

# Contracts (shared by string value)
CAP_SSH_CONTRACT = "itf/cap/ssh"
CAP_SFTP_CONTRACT = "itf/cap/sftp"
SSH_ENDPOINT_CONTRACT = "itf/net/ssh_endpoint"


@dataclass(frozen=True)
class SshEndpoint:
    """Structured SSH connection parameters."""

    host: str
    port: int = 22
    username: str = "root"
    password: str = ""
    pkey_path: str = ""

    @classmethod
    def from_mapping(cls, data: dict) -> "SshEndpoint":
        return cls(
            host=str(data["host"]),
            port=int(data.get("port", 22)),
            username=str(data.get("username", "root")),
            password=str(data.get("password", "")),
            pkey_path=str(data.get("pkey_path", "")),
        )


class SshComponent:
    """Factory for SSH connections from an endpoint."""

    def __init__(self, endpoint: SshEndpoint):
        self._endpoint = endpoint

    def connect(self, timeout: int = 15, n_retries: int = 5, retry_interval: int = 1, **overrides):
        """Return an Ssh context manager pre-configured with endpoint details."""
        return Ssh(
            target_ip=overrides.get("target_ip", self._endpoint.host),
            port=overrides.get("port", self._endpoint.port),
            timeout=timeout,
            n_retries=n_retries,
            retry_interval=retry_interval,
            pkey_path=overrides.get("pkey_path", self._endpoint.pkey_path) or None,
            username=overrides.get("username", self._endpoint.username),
            password=overrides.get("password", self._endpoint.password),
        )

    ssh = connect


class SftpComponent:
    """Factory for SFTP connections from an endpoint."""

    def __init__(self, endpoint: SshEndpoint):
        self._endpoint = endpoint

    def connect(self, ssh_connection=None):
        """Return an Sftp context manager."""
        return Sftp(ssh_connection, self._endpoint.host, self._endpoint.port)

    sftp = connect


__all__ = [
    "Ssh",
    "Sftp",
    "SshCommand",
    "SshCommandResult",
    "SshEndpoint",
    "SshComponent",
    "SftpComponent",
    "CAP_SSH_CONTRACT",
    "CAP_SFTP_CONTRACT",
    "SSH_ENDPOINT_CONTRACT",
]
