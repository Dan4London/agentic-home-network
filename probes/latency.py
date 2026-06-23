from __future__ import annotations

import re

from agent.schemas import HealthStatus, LatencyResult


def parse_ping_output(target: str, output: str) -> LatencyResult:
    """Parse Linux ping -c output into a LatencyResult."""
    loss_match = re.search(r"(\d+(?:\.\d+)?)% packet loss", output)
    packet_loss_pct = float(loss_match.group(1)) if loss_match else 100.0

    sent_match = re.search(r"(\d+) packets transmitted", output)
    recv_match = re.search(r"(\d+) received", output)
    packets_sent = int(sent_match.group(1)) if sent_match else 0
    packets_received = int(recv_match.group(1)) if recv_match else 0

    rtt_match = re.search(
        r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms",
        output,
    )
    rtt_min = rtt_avg = rtt_max = None
    if rtt_match:
        rtt_min = float(rtt_match.group(1))
        rtt_avg = float(rtt_match.group(2))
        rtt_max = float(rtt_match.group(3))

    status = HealthStatus.DOWN if packet_loss_pct >= 50 else HealthStatus.HEALTHY

    return LatencyResult(
        target=target,
        packets_sent=packets_sent,
        packets_received=packets_received,
        packet_loss_pct=packet_loss_pct,
        rtt_min_ms=rtt_min,
        rtt_avg_ms=rtt_avg,
        rtt_max_ms=rtt_max,
        status=status,
    )


def mock_latency(target: str) -> LatencyResult:
    """Static data for offline / Phase-0 plumbing demos."""
    samples = {
        "192.168.1.1": (0, 0.5),
        "1.1.1.1": (0, 6.0),
        "8.8.8.8": (0, 7.0),
    }
    loss, rtt = samples.get(target, (0, 10.0))
    return LatencyResult(
        target=target,
        packets_sent=3,
        packets_received=3,
        packet_loss_pct=float(loss),
        rtt_min_ms=rtt * 0.8,
        rtt_avg_ms=rtt,
        rtt_max_ms=rtt * 1.2,
        status=HealthStatus.HEALTHY,
    )


def measure_latency(
    target: str,
    ssh_config=None,
    mock: bool = False,
    count: int = 3,
) -> LatencyResult:
    if mock:
        return mock_latency(target)

    from probes.ssh_runner import SSHConfig, run_local_command, run_remote_command

    cmd = f"ping -c {count} -W 2 {target}"
    if ssh_config:
        code, out, err = run_remote_command(ssh_config, cmd)
    else:
        code, out, err = run_local_command(cmd)

    combined = out + err
    if code != 0 and "packet loss" not in combined:
        return LatencyResult(
            target=target,
            packets_sent=count,
            packets_received=0,
            packet_loss_pct=100.0,
            status=HealthStatus.DOWN,
        )
    return parse_ping_output(target, combined)


def measure_latency_batch(
    targets: list[str],
    ssh_config=None,
    mock: bool = False,
) -> list[LatencyResult]:
    return [measure_latency(t, ssh_config=ssh_config, mock=mock) for t in targets]
