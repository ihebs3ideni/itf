"""``ctf/cap/file_transfer`` -- move files to and from the target."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

#: The reserved framework contract for this capability.
CONTRACT = "ctf/cap/file_transfer"


@runtime_checkable
class FileTransfer(Protocol):
    """Copy files between host and target."""

    def upload(self, local_path: str, remote_path: str) -> None:
        """Copy a host file at ``local_path`` to ``remote_path`` on the target."""
        ...

    def download(self, remote_path: str, local_path: str) -> None:
        """Copy ``remote_path`` from the target to ``local_path`` on the host."""
        ...
