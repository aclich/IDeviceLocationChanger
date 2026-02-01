#!/usr/bin/env python3
"""
Test script to verify RSD tunnel communication is working.

Usage:
    python3 test_tunnel.py [UDID]

If UDID is not provided, uses the first available device.
"""

import asyncio
import sys

async def test_tunnel(udid: str = None):
    from services.device_manager import DeviceManager
    from services.location_service import LocationService
    from services.tunnel_manager import TunnelManager
    from models import RSDTunnel

    print("=" * 60)
    print("RSD Tunnel Communication Test")
    print("=" * 60)

    dm = DeviceManager()
    ls = LocationService()
    tm = TunnelManager()

    # Step 1: List devices
    print("\n[1] Discovering devices...")
    devices = await dm.list_devices()
    print(f"    Found {len(devices)} device(s):")
    for d in devices:
        print(f"      - {d.name} ({d.id}) [{d.type.value}]")

    if not devices:
        print("\n    ERROR: No devices found!")
        return False

    # Step 2: Select device
    print("\n[2] Selecting device...")
    if udid:
        device = dm.get_device(udid)
        if not device:
            print(f"    ERROR: Device {udid} not found!")
            return False
    else:
        # Use first physical device, or first device
        device = next((d for d in devices if d.type.value == "physical"), devices[0])

    print(f"    Selected: {device.name} ({device.id})")

    # Step 3: Start/find tunnel
    print("\n[3] Starting tunnel...")
    result = await tm.start_tunnel(device.id)
    if not result.get("success"):
        print(f"    ERROR: {result.get('error')}")
        return False

    print(f"    Tunnel: {result['address']}:{result['port']}")

    # Update device with tunnel info
    tunnel = RSDTunnel(
        address=result["address"],
        port=result["port"],
        udid=result.get("udid")
    )
    dm.update_tunnel(device.id, tunnel)
    device = dm.get_device(device.id)

    # Step 4: Test RSD connection
    print("\n[4] Testing RSD connection...")
    try:
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService

        rsd = RemoteServiceDiscoveryService((tunnel.address, tunnel.port))
        await rsd.connect()

        # List available services
        print("    Connection successful!")
        print(f"    Product Type: {getattr(rsd, 'product_type', 'N/A')}")
        print(f"    Product Version: {getattr(rsd, 'product_version', 'N/A')}")

        # List some services (different pymobiledevice3 versions use different attributes)
        services = []
        if hasattr(rsd, 'peer_info') and rsd.peer_info:
            services = list(rsd.peer_info.keys())[:10]
        elif hasattr(rsd, 'service_names'):
            services = list(rsd.service_names)[:10]
        if services:
            print(f"    Available services (first 10): {services}")

        await rsd.close()
        print("    RSD connection test: PASSED")

    except Exception as e:
        print(f"    ERROR: {e}")
        return False

    # Step 5: Test location simulation
    print("\n[5] Testing location simulation...")
    test_lat, test_lon = 25.0330, 121.5654  # Taipei 101
    result = await ls.set_location(device, test_lat, test_lon)

    if result.get("success"):
        print(f"    Set location to: {test_lat}, {test_lon}")
        print("    Location simulation test: PASSED")
    else:
        print(f"    ERROR: {result.get('error')}")
        return False

    # Step 6: Clear location
    print("\n[6] Clearing location...")
    result = await ls.clear_location(device)
    if result.get("success"):
        print("    Location cleared")
        print("    Clear location test: PASSED")
    else:
        print(f"    WARNING: {result.get('error')}")

    # Cleanup
    ls.disconnect_all()

    print("\n" + "=" * 60)
    print("All tests PASSED!")
    print("=" * 60)
    return True


def main():
    udid = sys.argv[1] if len(sys.argv) > 1 else None
    success = asyncio.run(test_tunnel(udid))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
