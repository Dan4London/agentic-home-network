"""CLI: discover and identify LAN devices."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import yaml

from probes.device_identity import discover_devices, identities_to_yaml_records

BASELINE = Path(__file__).resolve().parent.parent / "baseline" / "known_devices.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and identify LAN devices")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write results to baseline/known_devices.yaml",
    )
    args = parser.parse_args()

    identities = discover_devices()

    if args.write_baseline:
        records = identities_to_yaml_records(identities)
        payload = {
            "generated_by": "netops-discover",
            "identification_methods": [
                "mac_oui",
                "reverse_dns",
                "mdns",
                "http_banner",
            ],
            "devices": records,
        }
        BASELINE.write_text(yaml.dump(payload, sort_keys=False, allow_unicode=True))
        print(f"Wrote {len(records)} devices to {BASELINE}")

    if args.json:
        print(json.dumps([asdict(i) for i in identities], indent=2))
        return

    print("=" * 72)
    print("LAN DEVICE DISCOVERY")
    print("=" * 72)
    for d in identities:
        print(f"\n{d.suggested_name()}  [{d.confidence}]")
        print(f"  IP       {d.ip}  ({d.state})")
        print(f"  MAC      {d.mac}")
        if d.hostname:
            print(f"  Hostname {d.hostname}")
        if d.vendor:
            print(f"  Vendor   {d.vendor}")
        if d.device_type:
            print(f"  Type     {d.device_type}")
        if d.identification_methods:
            print(f"  Methods  {', '.join(d.identification_methods)}")
        if d.notes:
            print(f"  Notes    {d.notes}")
    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
