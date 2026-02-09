"""Data models for the backend."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DeviceType(Enum):
    SIMULATOR = "simulator"
    PHYSICAL = "physical"


class DeviceState(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class ConnectionType(Enum):
    USB = "USB"
    WIFI = "WiFi"
    UNKNOWN = "Unknown"


class TunnelStatus(Enum):
    """Status of a device tunnel connection."""
    NO_TUNNEL = "no_tunnel"          # No tunnel exists for this device
    DISCOVERING = "discovering"       # Querying tunneld for tunnel info
    CONNECTED = "connected"           # Tunnel validated and working
    STALE = "stale"                   # Tunnel may be stale, needs revalidation
    DISCONNECTED = "disconnected"     # Tunnel exists but device unreachable
    ERROR = "error"                   # Error state


@dataclass
class RSDTunnel:
    """RSD tunnel connection info for iOS 17+ devices."""
    address: str
    port: int
    udid: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.address) and self.port > 0

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "port": self.port,
            "udid": self.udid
        }


@dataclass
class TunnelState:
    """Per-device tunnel state managed by TunnelManager."""
    udid: str
    status: TunnelStatus = TunnelStatus.NO_TUNNEL
    tunnel_info: Optional[RSDTunnel] = None
    last_validated: float = 0.0       # Timestamp of last successful validation
    last_queried: float = 0.0         # Timestamp of last tunneld query
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "udid": self.udid,
            "status": self.status.value,
            "tunnelInfo": self.tunnel_info.to_dict() if self.tunnel_info else None,
            "lastValidated": self.last_validated,
            "lastQueried": self.last_queried,
            "error": self.error
        }


# Product type to display name mapping
PRODUCT_NAME_MAP = {
    "iPhone17,1": "iPhone 16 Pro",
    "iPhone17,2": "iPhone 16 Pro Max",
    "iPhone16,1": "iPhone 15 Pro",
    "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone15,2": "iPhone 14 Pro",
    "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone14,2": "iPhone 13 Pro",
    "iPhone14,3": "iPhone 13 Pro Max",
}


@dataclass
class Device:
    """iOS device (simulator or physical)."""
    id: str
    name: str
    type: DeviceType
    state: DeviceState
    rsd_tunnel: Optional[RSDTunnel] = None
    product_type: Optional[str] = None
    connection_type: ConnectionType = ConnectionType.UNKNOWN

    @property
    def product_name(self) -> str:
        if self.product_type:
            return PRODUCT_NAME_MAP.get(self.product_type, self.product_type)
        return self.name

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "state": self.state.value,
            "productType": self.product_type,
            "productName": self.product_name,
            "connectionType": self.connection_type.value,
            "rsdTunnel": self.rsd_tunnel.to_dict() if self.rsd_tunnel else None,
        }
