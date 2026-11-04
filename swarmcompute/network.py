"""Detect interface addresses; never promise that a firewall makes them reachable."""

import ipaddress
import shutil
import socket
import subprocess

import psutil


def addresses(port=8787):
    result = [{"kind": "local", "url": f"http://localhost:{port}"}]
    for infos in psutil.net_if_addrs().values():
        for info in infos:
            if info.family != socket.AF_INET:
                continue
            ip = ipaddress.ip_address(info.address)
            if ip.is_loopback or ip.is_link_local:
                continue
            tail = ip in ipaddress.ip_network("100.64.0.0/10")
            if ip.is_private or tail:
                item = {
                    "kind": "tailscale" if tail else "LAN",
                    "url": f"http://{ip}:{port}",
                }
                if item not in result:
                    result.append(item)
    hostname = socket.gethostname().split(".")[0] + ".local"
    try:
        socket.gethostbyname(hostname)
        result.append(
            {"kind": "mDNS (if clients resolve it)", "url": f"http://{hostname}:{port}"}
        )
    except OSError:
        pass
    if shutil.which("tailscale"):
        try:
            import json

            value = json.loads(
                subprocess.check_output(
                    ["tailscale", "status", "--json"],
                    timeout=3,
                    stderr=subprocess.DEVNULL,
                )
            )
            dns = value.get("Self", {}).get("DNSName", "").rstrip(".")
            if dns:
                result.append({"kind": "MagicDNS", "url": f"http://{dns}:{port}"})
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return result
