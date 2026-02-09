"""TCP Port Forwarding Service.

Provides the ability to forward traffic from a specific network interface IP
to localhost, enabling remote debugging without binding to 0.0.0.0.

Example:
    Forward from 10.13.13.5:5173 to 127.0.0.1:5173
    This allows another device on the network to access the local dev server.
"""

import asyncio
import logging
import socket
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PortForwardService:
    """TCP port forwarding service using asyncio."""

    def __init__(self):
        # Active forwarders: key = "listen_ip:port", value = (server, info_dict)
        self._forwarders: Dict[str, Tuple[asyncio.Server, dict]] = {}

    def list_interfaces(self) -> List[dict]:
        """List available network interfaces with IPv4 addresses.

        Returns:
            List of dicts with 'name' and 'ip' keys
        """
        interfaces = []

        try:
            # Method 1: Parse ifconfig output (works on macOS/Linux, catches VPN/tunnel interfaces)
            try:
                import subprocess
                import re
                result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    current_iface = None
                    for line in result.stdout.split('\n'):
                        # Interface name line (e.g., "en0: flags=...")
                        iface_match = re.match(r'^(\w+):', line)
                        if iface_match:
                            current_iface = iface_match.group(1)
                        # IPv4 address line (e.g., "inet 192.168.1.1 netmask...")
                        inet_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', line)
                        if inet_match and current_iface:
                            ip = inet_match.group(1)
                            if ip not in ['127.0.0.1', '0.0.0.0']:
                                interfaces.append({
                                    'name': current_iface,
                                    'ip': ip,
                                })
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            # Method 2: Get addresses using socket (fallback)
            if not interfaces:
                hostname = socket.gethostname()
                for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                    ip = info[4][0]
                    if ip not in ['127.0.0.1', '0.0.0.0']:
                        interfaces.append({
                            'name': hostname,
                            'ip': ip,
                        })

            # Method 3: Try netifaces if available
            try:
                import netifaces
                for iface_name in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(iface_name)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr.get('addr')
                            if ip and ip not in ['127.0.0.1', '0.0.0.0']:
                                # Check if we already have this IP
                                if not any(i['ip'] == ip for i in interfaces):
                                    interfaces.append({
                                        'name': iface_name,
                                        'ip': ip,
                                    })
            except ImportError:
                pass

            # Method 4: Fallback - get local IP by connecting to external server
            if not interfaces:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(('8.8.8.8', 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                    if local_ip and local_ip not in ['127.0.0.1', '0.0.0.0']:
                        interfaces.append({
                            'name': 'default',
                            'ip': local_ip,
                        })
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to list interfaces: {e}")

        # Remove duplicates while preserving order
        seen = set()
        unique_interfaces = []
        for iface in interfaces:
            if iface['ip'] not in seen:
                seen.add(iface['ip'])
                unique_interfaces.append(iface)

        logger.debug(f"Found {len(unique_interfaces)} network interfaces")
        return unique_interfaces

    async def start_forward(
        self,
        listen_ip: str,
        listen_port: int,
        target_ip: str,
        target_port: int
    ) -> dict:
        """Start a TCP port forward.

        Args:
            listen_ip: IP address to listen on (e.g., '10.13.13.5')
            listen_port: Port to listen on
            target_ip: IP address to forward to (e.g., '127.0.0.1')
            target_port: Port to forward to

        Returns:
            dict with 'success' and optional 'error' keys
        """
        key = f"{listen_ip}:{listen_port}"

        # Check if already forwarding
        if key in self._forwarders:
            return {"success": False, "error": f"Already forwarding on {key}"}

        try:
            # Create the forwarder
            async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
                """Handle a client connection by forwarding to target."""
                client_addr = writer.get_extra_info('peername')
                logger.debug(f"[{key}] New connection from {client_addr}")

                target_reader = None
                target_writer = None

                try:
                    # Connect to target
                    target_reader, target_writer = await asyncio.open_connection(
                        target_ip, target_port
                    )

                    # Bidirectional forwarding
                    async def forward(src: asyncio.StreamReader, dst: asyncio.StreamWriter, name: str):
                        try:
                            while True:
                                data = await src.read(8192)
                                if not data:
                                    break
                                dst.write(data)
                                await dst.drain()
                        except (ConnectionResetError, BrokenPipeError):
                            pass
                        except Exception as e:
                            logger.debug(f"[{key}] {name} forward error: {e}")

                    # Run both directions concurrently
                    await asyncio.gather(
                        forward(reader, target_writer, "client->target"),
                        forward(target_reader, writer, "target->client"),
                        return_exceptions=True
                    )

                except ConnectionRefusedError:
                    logger.warning(f"[{key}] Connection refused to {target_ip}:{target_port}")
                except Exception as e:
                    logger.error(f"[{key}] Forward error: {e}")
                finally:
                    # Clean up
                    if target_writer:
                        target_writer.close()
                        try:
                            await target_writer.wait_closed()
                        except Exception:
                            pass
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    logger.debug(f"[{key}] Connection from {client_addr} closed")

            # Start the server
            server = await asyncio.start_server(
                handle_client,
                listen_ip,
                listen_port,
                reuse_address=True
            )

            info = {
                'listenIp': listen_ip,
                'listenPort': listen_port,
                'targetIp': target_ip,
                'targetPort': target_port,
            }

            self._forwarders[key] = (server, info)

            logger.info(f"Started port forward: {listen_ip}:{listen_port} -> {target_ip}:{target_port}")

            return {"success": True, "forward": info}

        except OSError as e:
            if e.errno == 48:  # Address already in use
                return {"success": False, "error": f"Port {listen_port} is already in use on {listen_ip}"}
            elif e.errno == 49:  # Can't assign requested address
                return {"success": False, "error": f"Cannot bind to {listen_ip} - address not available"}
            else:
                return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Failed to start forward: {e}")
            return {"success": False, "error": str(e)}

    async def stop_forward(self, listen_ip: str, listen_port: int) -> dict:
        """Stop a TCP port forward.

        Args:
            listen_ip: IP address being listened on
            listen_port: Port being listened on

        Returns:
            dict with 'success' and optional 'error' keys
        """
        key = f"{listen_ip}:{listen_port}"

        if key not in self._forwarders:
            return {"success": False, "error": f"No forward found for {key}"}

        try:
            server, info = self._forwarders.pop(key)
            server.close()
            await server.wait_closed()

            logger.info(f"Stopped port forward: {key}")
            return {"success": True}

        except Exception as e:
            logger.error(f"Failed to stop forward: {e}")
            return {"success": False, "error": str(e)}

    def list_forwards(self) -> List[dict]:
        """List all active port forwards.

        Returns:
            List of forward info dicts
        """
        return [info for _, info in self._forwarders.values()]

    async def stop_all(self) -> None:
        """Stop all active port forwards."""
        keys = list(self._forwarders.keys())
        for key in keys:
            try:
                server, _ = self._forwarders.pop(key)
                server.close()
                await server.wait_closed()
                logger.debug(f"Stopped forward: {key}")
            except Exception as e:
                logger.error(f"Error stopping forward {key}: {e}")

        logger.info(f"Stopped {len(keys)} port forward(s)")
