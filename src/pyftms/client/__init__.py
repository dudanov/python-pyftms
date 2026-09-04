# Copyright 2024, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakDeviceNotFoundError
from bleak.uuids import normalize_uuid_str

from .backends import (
    ControlEvent,
    FtmsCallback,
    SetupEvent,
    SetupEventData,
    SpinDownEvent,
    SpinDownEventData,
    UpdateEvent,
    UpdateEventData,
)
from .client import DisconnectCallback, FitnessMachine
from .const import FTMS_UUID
from .errors import NotFitnessMachineError
from .machines import get_machine
from .manager import PropertiesManager
from .properties import (
    DeviceInfo,
    MachineType,
    MovementDirection,
    SettingRange,
    get_machine_type_from_service_data,
)

_LOGGER = logging.getLogger(__name__)


def get_client(
    ble_device: BLEDevice,
    adv_or_type: AdvertisementData | MachineType,
    *,
    timeout: float = 2,
    on_ftms_event: FtmsCallback | None = None,
    on_disconnect: DisconnectCallback | None = None,
    **kwargs: Any,
) -> FitnessMachine:
    """
    Creates an `FitnessMachine` instance from [Bleak](https://bleak.readthedocs.io/) discovered
    information: device and advertisement data. Instead of advertisement data, the `MachineType` can be used.

    Parameters:
    - `ble_device` - [BLE device](https://bleak.readthedocs.io/en/latest/api/index.html#bleak.backends.device.BLEDevice).
    - `adv_or_type` - Service [advertisement data](https://bleak.readthedocs.io/en/latest/backends/index.html#bleak.backends.scanner.AdvertisementData) or `MachineType`.
    - `timeout` - Control operation timeout. Defaults to 2.0s.
    - `on_ftms_event` - Callback for receiving fitness machine events.
    - `on_disconnect` - Disconnection callback.
    - `**kwargs` - Additional keyword arguments for backwards compatibility.

    Return:
    - `FitnessMachine` instance.
    """

    adv_data = None

    if isinstance(adv_or_type, AdvertisementData):
        adv_data = adv_or_type
        try:
            adv_or_type = get_machine_type_from_service_data(adv_or_type)
        except NotFitnessMachineError:
            # Fallback: some devices advertise FTMS UUID but omit FTMS service data.
            # If FTMS UUID is present, instantiate a placeholder client so we can
            # connect and detect the real machine type from GATT characteristics.
            # Note: post-connect code will probe notifiable data characteristics
            # (2ACD/2ACE/2AD1/2AD2) and switch the type accordingly.
            if normalize_uuid_str(FTMS_UUID) in (adv_data.service_uuids or []):
                _LOGGER.debug(
                    "FTMS UUID present but no FTMS service data; proceeding with placeholder client. Actual type will be detected after connect."
                )
                adv_or_type = MachineType.INDOOR_BIKE
            else:
                raise

    cls = get_machine(adv_or_type)

    return cls(
        ble_device,
        adv_data,
        timeout=timeout,
        on_ftms_event=on_ftms_event,
        on_disconnect=on_disconnect,
        kwargs=kwargs,
    )


async def discover_ftms_devices(
    discover_time: float = 10,
    **kwargs: Any,
) -> AsyncIterator[tuple[BLEDevice, MachineType]]:
    """
    Discover FTMS devices.

    Parameters:
    - `discover_time` - Discover time. Defaults to 10s.
    - `**kwargs` - Additional keyword arguments for backwards compatibility.

    Return:
    - `AsyncIterator[tuple[BLEDevice, MachineType]]` async generator of `BLEDevice` and `MachineType` tuples.
    """

    devices: set[str] = set()

    async with BleakScanner(
        service_uuids=[normalize_uuid_str(FTMS_UUID)],
        kwargs=kwargs,
    ) as scanner:
        try:
            async with asyncio.timeout(discover_time):
                async for dev, adv in scanner.advertisement_data():
                    if dev.address in devices:
                        continue

                    try:
                        machine_type = get_machine_type_from_service_data(adv)

                    except NotFitnessMachineError:
                        continue

                    devices.add(dev.address)

                    _LOGGER.debug(
                        " #%d - %s: address='%s', name='%s'",
                        len(devices),
                        machine_type.name,
                        dev.address,
                        dev.name,
                    )

                    yield dev, machine_type

        except asyncio.TimeoutError:
            pass


async def get_client_from_address(
    address: str,
    *,
    scan_timeout: float = 10,
    timeout: float = 2,
    on_ftms_event: FtmsCallback | None = None,
    on_disconnect: DisconnectCallback | None = None,
    **kwargs: Any,
) -> FitnessMachine:
    """
    Scans for fitness machine with specified BLE address. On success creates and return an `FitnessMachine` instance.

    Parameters:
    - `address` - The Bluetooth address of the device on this machine (UUID on macOS).
    - `scan_timeout` - Scanning timeout. Defaults to 10.0s.
    - `timeout` - Control operation timeout. Defaults to 2.0s.
    - `on_ftms_event` - Callback for receiving fitness machine events.
    - `on_disconnect` - Disconnection callback.
    - `**kwargs` - Additional keyword arguments for backwards compatibility.

    Return:
    - `FitnessMachine` instance if device found successfully.
    """

    async for dev, machine_type in discover_ftms_devices(
        scan_timeout, kwargs=kwargs
    ):
        if dev.address.lower() == address.lower():
            return get_client(
                dev,
                machine_type,
                timeout=timeout,
                on_ftms_event=on_ftms_event,
                on_disconnect=on_disconnect,
                kwargs=kwargs,
            )

    raise BleakDeviceNotFoundError(address)


__all__ = [
    "discover_ftms_devices",
    "get_client",
    "get_client_from_address",
    "MachineType",
    "NotFitnessMachineError",
    "UpdateEvent",
    "SetupEvent",
    "ControlEvent",
    "SpinDownEvent",
    "FtmsCallback",
    "SetupEventData",
    "UpdateEventData",
    "SpinDownEventData",
    "MovementDirection",
    "DeviceInfo",
    "SettingRange",
    "PropertiesManager",
    "DisconnectCallback",
]
