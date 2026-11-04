# LAN and optional Tailscale access

The coordinator is the only inbound service. Start `swarm server start --host 0.0.0.0 --port 8787`. Workers use outbound HTTP and expose no service port. `swarm server urls` prints detected interface addresses plus a QR code. These are detected candidates, not a guarantee of network reachability. Dashboard Overview displays the same candidates. mDNS is listed only if the host's `.local` name resolves; the application does not require or install Bonjour. Direct IP remains available.

On the host, test `http://localhost:8787/health`. On the worker, use its browser or `curl http://HOST_IP:8787/health`; PowerShell supports `Invoke-RestMethod http://HOST_IP:8787/health`. Ping can help but ICMP may be blocked even when HTTP works. Verify the machines can route to one another, the server is listening, and the firewall permits the chosen private subnet.

Do not open administrative port 8787 to the public internet. Add firewall access only for your approved network. On Windows, an administrator can use a Private-profile inbound TCP rule scoped with `-RemoteAddress LocalSubnet`; review the actual subnet and firewall profile first. On Linux/UFW use `sudo ufw allow from YOUR_PRIVATE_SUBNET to any port 8787 proto tcp` with your real CIDR, not unrestricted `ufw allow 8787`. On macOS allow incoming connections for the chosen Python executable in System Settings → Network → Firewall → Options on the trusted network. These rules are documented, not installed automatically.

Same Wi-Fi SSID does not guarantee peer connectivity. Campus/hostel routers may enable client isolation, block local traffic or place users on different VLANs. Use a trusted private router, a suitable wired LAN, an authorized Tailscale tailnet, or contact the network administrator. A public unauthenticated tunnel is not a workaround.

Prefer a DHCP reservation for the coordinator. If its address changes, run `swarm server urls`, update bookmarks and the worker's stored server address through a deliberate local configuration change/re-enrollment. Do not assume stale QR codes still resolve. mDNS support differs by OS/network.

## Tailscale (optional)

Install Tailscale explicitly on participating computers and join an authorized tailnet. Use the coordinator's reported 100.64.0.0/10 address or its MagicDNS name. Restrict access with tailnet policy/firewall rules. The same locally hosted application and port are used; Tailscale supplies the encrypted connectivity and does not host the study. No Tailscale account is required for trusted-LAN operation.

HTTP on a trusted LAN is unencrypted. Use Tailscale or properly configured HTTPS before sending credentials/artifacts over shared or untrusted institutional networks. Avoid public exposure of the administrative API.
