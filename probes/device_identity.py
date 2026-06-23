"""Identify LAN devices using MAC OUI, DNS, mDNS, and HTTP fingerprinting."""

from __future__ import annotations

import json
import platform
import re
import subprocess
from dataclasses import asdict, dataclass, field

from agent.config import Settings
from probes.ssh_runner import SSHConfig, run_remote_command

# Common OUIs — avoids rate-limited public APIs during routine discovery.
OUI_VENDORS: dict[str, str] = {
    "F492BF": "Ubiquiti Inc",
    "C4411E": "Belkin International (Linksys)",
    "A4307A": "Samsung Electronics",
    "DCA632": "Raspberry Pi Foundation",
    "B827EB": "Raspberry Pi Foundation",
    "E4C32A": "Apple Inc",
    "A4D1D2": "Apple Inc",
    "F01898": "Apple Inc",
    "3C22FB": "Apple Inc",
    "ACBC32": "Apple Inc",
}


@dataclass
class DeviceIdentity:
    ip: str
    mac: str
    state: str = ""
    hostname: str | None = None
    vendor: str | None = None
    device_type: str | None = None
    identification_methods: list[str] = field(default_factory=list)
    notes: str | None = None
    confidence: str = "low"  # low | medium | high

    def suggested_name(self) -> str:
        if self.hostname:
            base = self.hostname.split(".")[0]
            return re.sub(r"[^a-zA-Z0-9_-]", "-", base).lower().strip("-")
        if self.device_type:
            return f"{self.device_type}-{self.ip.split('.')[-1]}"
        if self.vendor:
            slug = re.sub(r"[^a-zA-Z0-9]", "", self.vendor.split()[0]).lower()
            return f"{slug}-{self.ip.split('.')[-1]}"
        return f"device-{self.ip.split('.')[-1]}"


def is_locally_administered(mac: str) -> bool:
    first_byte = int(mac.split(":")[0], 16)
    return bool(first_byte & 0x02)


def lookup_vendor(mac: str) -> str | None:
    oui = mac.replace(":", "").replace("-", "").upper()[:6]
    if oui in OUI_VENDORS:
        return OUI_VENDORS[oui]
    if is_locally_administered(mac):
        return None
    try:
        import urllib.request

        req = urllib.request.Request(
            f"https://api.macvendors.com/{mac}",
            headers={"User-Agent": "agentic-home-netops/0.1"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read().decode().strip()
            if body and not body.startswith("{"):
                OUI_VENDORS[oui] = body
                return body
    except Exception:
        pass
    return None


def resolve_reverse_dns(ip: str) -> str | None:
    try:
        result = subprocess.run(
            ["dig", "+short", "-x", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        host = result.stdout.strip().splitlines()[0].rstrip(".") if result.stdout.strip() else ""
        return host or None
    except Exception:
        return None


def resolve_mdns_hostname(ip: str) -> str | None:
    """Best-effort mDNS PTR lookup (macOS dns-sd)."""
    if platform.system() != "Darwin":
        return None
    try:
        proc = subprocess.run(
            ["dns-sd", "-Q", ip],
            capture_output=True,
            text=True,
            timeout=4,
        )
        for line in proc.stdout.splitlines():
            if ip in line and ".local" in line:
                match = re.search(r"(\S+\.local)", line)
                if match:
                    return match.group(1).rstrip(".")
    except Exception:
        pass
    return None


def http_server_banner(ip: str) -> str | None:
    try:
        result = subprocess.run(
            ["curl", "-sI", "--max-time", "2", f"http://{ip}/"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        for line in result.stdout.splitlines():
            if line.lower().startswith("server:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def infer_device_type(
    vendor: str | None,
    hostname: str | None,
    locally_admin: bool,
    http_server: str | None,
) -> tuple[str | None, str | None]:
    """Return (device_type, notes)."""
    host = (hostname or "").lower()
    notes: list[str] = []

    if "unifi" in host or (vendor and "ubiquiti" in vendor.lower()):
        return "router", "UniFi gateway"
    if "linksys" in host or (vendor and "linksys" in vendor.lower()):
        dtype = "mesh_node"
        if http_server and "lighttpd" in http_server.lower():
            notes.append(f"Web UI ({http_server})")
        return dtype, "; ".join(notes) or "Linksys/Belkin Wi-Fi hardware"
    if "iphone" in host:
        return "phone", "Apple iPhone (hostname)"
    if "ipad" in host:
        return "tablet", "Apple iPad (hostname)"
    if host.startswith("mac.") or host == "mac":
        return "laptop", "Apple Mac (hostname)"
    if "samsung" in host or (vendor and "samsung" in vendor.lower()):
        return "tv_or_iot", "Samsung device (TV, phone, or appliance)"
    if vendor and "raspberry" in vendor.lower():
        return "probe", "Raspberry Pi"
    if locally_admin and not vendor:
        return "client", "Privacy/randomised MAC — likely phone or laptop"
    if http_server:
        notes.append(f"HTTP server: {http_server}")
    return None, "; ".join(notes) if notes else None


def local_host_ip_and_mac() -> tuple[str | None, str | None]:
    """Return (ip, mac) if we can determine this machine's LAN address."""
    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        ip = result.stdout.strip() or None
        if not ip:
            return None, None
        ifconfig = subprocess.run(["ifconfig", "en0"], capture_output=True, text=True, timeout=3)
        mac_match = re.search(r"ether ([0-9a-f:]+)", ifconfig.stdout, re.I)
        mac = mac_match.group(1).lower() if mac_match else None
        return ip, mac
    except Exception:
        return None, None


def identify_device(ip: str, mac: str, state: str = "") -> DeviceIdentity:
    methods: list[str] = []
    locally_admin = is_locally_administered(mac)

    vendor = lookup_vendor(mac)
    if vendor:
        methods.append("mac_oui")

    hostname = resolve_reverse_dns(ip)
    if hostname:
        methods.append("reverse_dns")

    if not hostname:
        mdns = resolve_mdns_hostname(ip)
        if mdns:
            hostname = mdns
            methods.append("mdns")

    http_server = http_server_banner(ip)
    if http_server:
        methods.append("http_banner")

    device_type, notes = infer_device_type(vendor, hostname, locally_admin, http_server)

    local_ip, local_mac = local_host_ip_and_mac()
    if ip == local_ip and (mac == local_mac or locally_admin):
        methods.append("local_host")
        try:
            computer = subprocess.run(
                ["scutil", "--get", "ComputerName"],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout.strip()
        except Exception:
            computer = None
        device_type = "laptop"
        host_label = computer or platform.node()
        notes = f"This machine ({host_label})"
        confidence = "high"
    else:
        confidence = "low"
        if hostname and vendor:
            confidence = "high"
        elif hostname or vendor:
            confidence = "medium"

    return DeviceIdentity(
        ip=ip,
        mac=mac.lower(),
        state=state,
        hostname=hostname,
        vendor=vendor,
        device_type=device_type,
        identification_methods=methods,
        notes=notes,
        confidence=confidence,
    )


def parse_neigh_table(output: str) -> list[dict[str, str]]:
    devices = []
    for line in output.strip().splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].count(".") == 3:
            devices.append({"ip": parts[0], "mac": parts[4].lower(), "state": parts[-1]})
    return devices


def list_lan_devices(settings: Settings | None = None, *, active_scan: bool = True) -> list[dict[str, str]]:
    settings = settings or Settings()
    ssh = SSHConfig(
        host=settings.probe_host,
        user=settings.probe_user,
        password=settings.probe_password,
        key_path=settings.probe_ssh_key,
    )
    if active_scan:
        subnet = ".".join(settings.probe_host.split(".")[:3])
        run_remote_command(
            ssh,
            f"for i in $(seq 1 254); do ping -c 1 -W 1 {subnet}.$i >/dev/null 2>&1 & done; wait",
            timeout=120,
        )
    _, out, _ = run_remote_command(ssh, "ip neigh show")
    return parse_neigh_table(out)


def discover_devices(settings: Settings | None = None) -> list[DeviceIdentity]:
    raw = list_lan_devices(settings)
    probe_ip = (settings or Settings()).probe_host
    identities = [identify_device(d["ip"], d["mac"], d.get("state", "")) for d in raw]

    # Include the probe host itself (not in neighbour table as self)
    if not any(i.ip == probe_ip for i in identities):
        ssh = SSHConfig(
            host=(settings or Settings()).probe_host,
            user=(settings or Settings()).probe_user,
            password=(settings or Settings()).probe_password,
            key_path=(settings or Settings()).probe_ssh_key,
        )
        _, mac_out, _ = run_remote_command(ssh, "cat /sys/class/net/eth0/address")
        mac = mac_out.strip().lower()
        if mac:
            probe = identify_device(probe_ip, mac, "REACHABLE")
            probe.device_type = "probe"
            probe.notes = "Raspberry Pi network probe (social01)"
            probe.confidence = "high"
            identities.append(probe)

    return sorted(identities, key=lambda d: [int(x) for x in d.ip.split(".")])


def identities_to_yaml_records(identities: list[DeviceIdentity]) -> list[dict]:
    records = []
    for d in identities:
        records.append(
            {
                "name": d.suggested_name(),
                "mac": d.mac,
                "ip": d.ip,
                "hostname": d.hostname,
                "vendor": d.vendor,
                "type": d.device_type,
                "confidence": d.confidence,
                "identification_methods": d.identification_methods,
                "notes": d.notes,
            }
        )
    return records


def main() -> None:
    identities = discover_devices()
    print(json.dumps([asdict(i) for i in identities], indent=2))


if __name__ == "__main__":
    main()
