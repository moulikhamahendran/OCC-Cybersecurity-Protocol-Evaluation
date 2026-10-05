# Oracle Cloud Network Requirements

For the WireGuard hub VM:

Required inbound traffic:

- TCP 22 from trusted administration sources for SSH
- UDP 443 from WireGuard peers

Do NOT expose TCP 51821 publicly.

wg-easy Web UI access:

Mac -> SSH tunnel -> Oracle localhost:51821

Example:

ssh -L 51821:127.0.0.1:51821 ubuntu@ORACLE_PUBLIC_IP

Then browse locally to:

http://127.0.0.1:51821

The Oracle VCN security list / network security group and the VM
firewall must both permit the chosen WireGuard UDP port.

The VM must retain a stable public endpoint for peer configs.
