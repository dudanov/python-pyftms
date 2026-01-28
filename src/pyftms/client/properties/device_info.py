# Copyright 2024-2025, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import TypedDict

from bleak import BleakClient

DIS_UUID = "180a"
"""Device Information Service"""

_CHARACTERISTICS_MAP = {
    "manufacturer": "2a29",
    "model": "2a24",
    "serial_number": "2a25",
    "sw_version": "2a28",
    "hw_version": "2a27",
    "fw_version": "2a26",
}

_LOGGER = logging.getLogger(__name__)


class DeviceInfo(TypedDict, total=False):
    """Device Information"""

    manufacturer: str
    """Manufacturer"""
    model: str
    """Model"""
    serial_number: str
    """Serial Number"""
    sw_version: str
    """Software Version"""
    hw_version: str
    """Hardware Version"""
    fw_version: str
    """Firmware Version"""


async def read_device_info(cli: BleakClient) -> DeviceInfo:
    """Read Device Information"""

    _LOGGER.debug("Reading Device Information...")

    result = DeviceInfo()

    if srv := cli.services.get_service(DIS_UUID):
        for k, v in _CHARACTERISTICS_MAP.items():
            if c := srv.get_characteristic(v):
                data = await cli.read_gatt_char(c)
                result[k] = data.decode()

    # Use fw_version as sw_version fallback if sw_version is missing/placeholder
    sw = result.get("sw_version", "").strip()
    fw = result.get("fw_version", "").strip()
    is_placeholder = lambda v: not v or v.strip("0") == ""
    if is_placeholder(sw) and not is_placeholder(fw):
        result["sw_version"] = fw

    _LOGGER.debug("Device Info: %s", result)

    return result
