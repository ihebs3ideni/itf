# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
from contextlib import contextmanager, nullcontext

from score.itf.plugins.core import Target
from score.itf.plugins.qemu.qemu_process import QemuProcess
from score.itf.plugins.qemu.serial_console import SerialProcess

from score.itf.core.com.ssh import Ssh
from score.itf.core.com.sftp import Sftp
from score.itf.core.com.ping import ping, ping_lost


QEMU_BASE_CAPABILITIES = ["ssh", "sftp"]


class QemuTarget(Target):
    def __init__(self, process, config, enable_serial_exec=False):
        capabilities = QEMU_BASE_CAPABILITIES.copy()
        if enable_serial_exec:
            capabilities.append("exec")
        super().__init__(capabilities=capabilities)
        self._process = process
        self._config = config
        self._enable_serial_exec = enable_serial_exec

    def kill_process(self):
        self._process.stop()

    def restart_process(self):
        self._process.restart()

    def exec(self, command: str, env: dict = None, cwd: str = None, timeout: float = 30.0):
        """Execute a command on the QEMU target using serial channels.

        This method is available when serial channels are enabled. It provides
        direct command execution without requiring SSH.

        :param str command: The command to execute.
        :param dict env: Optional environment variables.
        :param str cwd: Optional working directory.
        :param float timeout: Command timeout in seconds. Default 30s.
        :return: SerialProcess handle for monitoring the command.
        :rtype: SerialProcess
        :raises RuntimeError: If serial channels are not available.
        """
        if not self._enable_serial_exec:
            raise RuntimeError(
                "exec() requires serial channels to be enabled. "
                "Set 'enable_serial_channels: true' in QEMU config."
            )
        
        channel_pool = self._process.channel_pool
        if not channel_pool:
            raise RuntimeError("Serial channel pool is not available.")
        
        # Build full command with optional env and cwd
        full_command = command
        if cwd:
            full_command = f"cd {cwd} && {full_command}"
        if env:
            env_str = " ".join(f"{k}={v}" for k, v in env.items())
            full_command = f"{env_str} {full_command}"
        
        return SerialProcess(channel_pool, full_command, timeout=timeout)

    def ssh(
        self,
        timeout: int = 15,
        port: int = None,
        n_retries: int = 5,
        retry_interval: int = 1,
        pkey_path: str = "",
        username: str = "root",
        password: str = "",
        ext_ip: bool = False,
    ):
        """Create SSH connection to target.

        :param int timeout: Connection timeout in seconds. Default is 15 seconds.
        :param int port: SSH port, if None use default port from config.
        :param int n_retries: Number of retries to connect. Default is 5 retries.
        :param int retry_interval: Interval between retries in seconds. Default is 1 second.
        :param str pkey_path: Path to private key file. If empty, password authentication is used.
        :param str username: SSH username. Default is 'root'.
        :param str password: SSH password.
        :param bool ext_ip: Use external IP address if True, otherwise use internal IP address.
        :return: Ssh connection object.
        :rtype: Ssh
        """
        ssh_ip = self._config.networks[0].ip_address
        ssh_port = port if port else self._config.ssh_port
        return Ssh(
            target_ip=ssh_ip,
            port=ssh_port,
            timeout=timeout,
            n_retries=n_retries,
            retry_interval=retry_interval,
            pkey_path=pkey_path,
            username=username,
            password=password,
        )

    def sftp(self, ssh_connection=None):
        ssh_ip = self._config.networks[0].ip_address
        ssh_port = self._config.ssh_port
        return Sftp(ssh_connection, ssh_ip, ssh_port)

    def ping(self, timeout, wait_ms_precision=None):
        return ping(
            address=self._config.networks[0].ip_address,
            timeout=timeout,
            wait_ms_precision=wait_ms_precision,
        )

    def ping_lost(self, timeout, interval=1, wait_ms_precision=None):
        return ping_lost(
            address=self._config.networks[0].ip_address,
            timeout=timeout,
            interval=interval,
            wait_ms_precision=wait_ms_precision,
        )


@contextmanager
def qemu_target(test_config):
    """Context manager for QEMU target setup."""
    # Get serial channel config with defaults
    qemu_cfg = test_config.qemu_config
    enable_serial = getattr(qemu_cfg, "enable_serial_channels", False)
    num_serial = getattr(qemu_cfg, "num_serial_channels", None)
    guest_device_prefix = getattr(qemu_cfg, "guest_device_prefix", "/dev/ttyS")
    
    with QemuProcess(
        test_config.qemu_image,
        qemu_cfg.qemu_ram_size,
        qemu_cfg.qemu_num_cores,
        network_adapters=[adapter.name for adapter in qemu_cfg.networks],
        port_forwarding=qemu_cfg.port_forwarding
        if hasattr(qemu_cfg, "port_forwarding")
        else [],
        enable_serial_channels=enable_serial,
        num_serial_channels=num_serial,
        guest_device_prefix=guest_device_prefix,
    ) if test_config.qemu_image else nullcontext() as qemu_process:
        target = QemuTarget(qemu_process, qemu_cfg, enable_serial_exec=enable_serial)
        yield target
