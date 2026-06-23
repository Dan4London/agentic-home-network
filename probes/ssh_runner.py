from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

import paramiko

logger = logging.getLogger(__name__)


@dataclass
class SSHConfig:
    host: str
    user: str
    password: str = ""
    key_path: str = ""


def run_remote_command(config: SSHConfig, command: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command on the probe host via SSH."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=config.host,
            username=config.user,
            password=config.password or None,
            key_filename=config.key_path or None,
            timeout=timeout,
            allow_agent=False,
            look_for_keys=bool(config.key_path),
        )
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode()
        err = stderr.read().decode()
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, out, err
    finally:
        client.close()


def run_local_command(command: str, timeout: int = 30) -> tuple[int, str, str]:
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr
