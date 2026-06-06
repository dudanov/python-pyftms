"""
Bluetooth diagnostic script.
Scans ALL nearby BLE devices (no UUID filter) and shows advertisement details.
Run with: python diagnose_bt.py
"""

import asyncio
from bleak import BleakScanner
from bleak.uuids import normalize_uuid_str

FTMS_UUID = normalize_uuid_str("1826")
SCAN_TIME = 10  # seconds


async def main():
    print(f"Scanning ALL BLE devices for {SCAN_TIME}s (no filter)...\n")

    found = {}

    def callback(device, adv):
        if device.address not in found:
            found[device.address] = (device, adv)

    async with BleakScanner(detection_callback=callback):
        await asyncio.sleep(SCAN_TIME)

    if not found:
        print("No BLE devices found at all.")
        print("Possible causes:")
        print("  - Bluetooth adapter not available")
        print("  - BlueZ not running (check: sudo systemctl status bluetooth)")
        print("  - Home Assistant holding exclusive access to the adapter")
        return

    print(f"Found {len(found)} BLE device(s):\n")

    ftms_devices = []

    for addr, (dev, adv) in sorted(found.items()):
        has_ftms = FTMS_UUID in (adv.service_uuids or [])
        marker = "  <-- FTMS (fitness machine!)" if has_ftms else ""
        print(f"  [{addr}] {dev.name or '(no name)'}{marker}")
        print(f"    RSSI: {adv.rssi} dBm")
        if adv.service_uuids:
            print(f"    Service UUIDs: {list(adv.service_uuids)}")
        if adv.service_data:
            print(f"    Service Data:  {adv.service_data}")
        if adv.manufacturer_data:
            mfr = {k: v.hex() for k, v in adv.manufacturer_data.items()}
            print(f"    Manufacturer:  {mfr}")
        print()

        if has_ftms:
            ftms_devices.append((dev, adv))

    print("-" * 60)
    if ftms_devices:
        print(f"FTMS devices found: {len(ftms_devices)}")
        for dev, adv in ftms_devices:
            has_service_data = FTMS_UUID in (adv.service_data or {})
            print(f"  {dev.address} ({dev.name})")
            print(f"    Has FTMS service data: {has_service_data}")
            if not has_service_data:
                print("    NOTE: No FTMS service data -> requires GATT fallback")
    else:
        print("No FTMS devices found in the raw scan.")
        print("Check that the bike is powered on and in Bluetooth range.")


asyncio.run(main())
