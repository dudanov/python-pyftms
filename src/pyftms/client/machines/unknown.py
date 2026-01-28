# Copyright 2025, Christian Kündig
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import close_stale_connections, establish_connection

from .. import const as c
from ..backends import FtmsCallback
from ..client import DisconnectCallback, FitnessMachine
from ..properties import MachineType
from ..properties.device_info import DIS_UUID

_LOGGER = logging.getLogger(__name__)

# Mapping of data UUID to machine type
_UUID_TO_MACHINE_TYPE: dict[str, MachineType] = {
    c.TREADMILL_DATA_UUID: MachineType.TREADMILL,
    c.CROSS_TRAINER_DATA_UUID: MachineType.CROSS_TRAINER,
    c.ROWER_DATA_UUID: MachineType.ROWER,
    c.INDOOR_BIKE_DATA_UUID: MachineType.INDOOR_BIKE,
}

# All data UUIDs to subscribe to for type detection
_ALL_DATA_UUIDS = tuple(_UUID_TO_MACHINE_TYPE.keys())


class Unknown:
    """
    Unknown Machine Type - Wrapper/Proxy Pattern.

    Used for devices that advertise FTMS but don't include proper service_data
    to determine the machine type. This class:

    1. Connects and subscribes to all possible data UUIDs
    2. Detects the actual type from which UUID sends data first
    3. Creates and wraps the actual client (Treadmill, CrossTrainer, etc.)
    4. Proxies all attribute access to the wrapped client

    After detection, this instance behaves exactly like the detected client type.
    The caller doesn't need to swap objects - just keep using this instance.

    **Important**: Store `detected_machine_type` in config, not UNKNOWN.
    """

    def __init__(
        self,
        ble_device: BLEDevice,
        adv_data: AdvertisementData | None = None,
        *,
        timeout: float = 2.0,
        on_ftms_event: FtmsCallback | None = None,
        on_disconnect: DisconnectCallback | None = None,
        detection_timeout: float = 10.0,
        **kwargs: Any,
    ) -> None:
        self._device = ble_device
        self._adv_data = adv_data
        self._timeout = timeout
        self._on_ftms_event = on_ftms_event
        self._on_disconnect = on_disconnect
        self._detection_timeout = detection_timeout
        self._kwargs = kwargs

        self._detected_type: MachineType | None = None
        self._detection_event = asyncio.Event()
        self._wrapped_client: FitnessMachine | None = None
        self._cli: BleakClient | None = None

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the wrapped client after detection."""
        # Avoid infinite recursion for our own attributes
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        _LOGGER.debug(
            "Unknown.__getattr__(%s): wrapped_client=%s",
            name,
            type(self._wrapped_client).__name__ if self._wrapped_client else None,
        )

        if self._wrapped_client is not None:
            return getattr(self._wrapped_client, name)

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'. "
            "Type detection not complete - call connect() and wait_for_detection() first."
        )

    @property
    def machine_type(self) -> MachineType:
        """Machine type - returns detected type if available, otherwise UNKNOWN."""
        if self._wrapped_client is not None:
            return self._wrapped_client.machine_type
        return MachineType.UNKNOWN

    @property
    def is_connected(self) -> bool:
        """Current connection status."""
        if self._wrapped_client is not None:
            return self._wrapped_client.is_connected
        return self._cli is not None and self._cli.is_connected

    @property
    def name(self) -> str:
        """Device name or BLE address."""
        return self._device.name or self._device.address

    @property
    def address(self) -> str:
        """Bluetooth address."""
        return self._device.address

    async def wait_for_detection(self, timeout: float | None = None) -> MachineType:
        """
        Wait for the machine type to be detected.

        Args:
            timeout: Maximum time to wait. Uses detection_timeout from __init__ if None.

        Returns:
            The detected MachineType.

        Raises:
            asyncio.TimeoutError: If detection times out.
        """
        if self._detected_type is not None:
            return self._detected_type

        await asyncio.wait_for(
            self._detection_event.wait(),
            timeout=timeout or self._detection_timeout,
        )

        if self._detected_type is None:
            raise ValueError("Detection completed but no type detected")

        return self._detected_type

    def _handle_disconnect(self, cli: BleakClient) -> None:
        """Handle disconnection during detection phase."""
        _LOGGER.debug("Unknown: Disconnected during detection.")
        self._cli = None

    def _on_data_notify(self, uuid: str):
        """Create a notification handler for a specific UUID."""

        def handler(char: BleakGATTCharacteristic, data: bytearray) -> None:
            machine_type = _UUID_TO_MACHINE_TYPE.get(uuid)
            if not machine_type:
                return

            if self._detected_type is not None:
                # Already detected - check if this is a different type
                if machine_type != self._detected_type:
                    _LOGGER.error(
                        "Unknown: Device is sending data for MULTIPLE machine types! "
                        "Already detected as %s, but also received data for %s (UUID %s). "
                        "This device may be misconfigured or have firmware issues. "
                        "Data: %s",
                        self._detected_type.name,
                        machine_type.name,
                        uuid,
                        data.hex(" ").upper(),
                    )
                return

            self._detected_type = machine_type
            self._detection_event.set()
            _LOGGER.info(
                "Unknown: Detected machine type %s from UUID %s",
                machine_type.name,
                uuid,
            )

        return handler

    async def connect(self) -> None:
        """
        Connect, detect machine type, and initialize the wrapped client.

        After this completes, the Unknown instance proxies to the real client.
        """
        if self._wrapped_client is not None:
            # Already detected and wrapped - just reconnect wrapped client
            await self._wrapped_client.connect()
            return

        # Phase 1: Connect for type detection
        await close_stale_connections(self._device)

        _LOGGER.debug("Unknown: Connecting for type detection.")

        self._cli = await establish_connection(
            client_class=BleakClient,
            device=self._device,
            name=self.name,
            disconnected_callback=self._handle_disconnect,
            services=[c.FTMS_UUID, DIS_UUID],
        )

        _LOGGER.debug("Unknown: Subscribing to all data UUIDs for detection.")

        # Subscribe to all data UUIDs
        for uuid in _ALL_DATA_UUIDS:
            try:
                char = self._cli.services.get_characteristic(uuid)
                if char:
                    await self._cli.start_notify(uuid, self._on_data_notify(uuid))
                    _LOGGER.debug("Unknown: Subscribed to UUID %s", uuid)
            except Exception as e:
                _LOGGER.debug("Unknown: Failed to subscribe to UUID %s: %s", uuid, e)

        # Wait for type detection
        try:
            detected = await self.wait_for_detection()
        except asyncio.TimeoutError:
            _LOGGER.warning("Unknown: Type detection timed out")
            if self._cli and self._cli.is_connected:
                await self._cli.disconnect()
            self._cli = None
            raise

        _LOGGER.info("Unknown: Detection complete, creating %s client", detected.name)

        # Disconnect detection client
        if self._cli and self._cli.is_connected:
            await self._cli.disconnect()
        self._cli = None

        # Phase 2: Create and connect the real client
        from . import get_machine

        cls = get_machine(detected)
        self._wrapped_client = cls(
            self._device,
            self._adv_data,
            timeout=self._timeout,
            on_ftms_event=self._on_ftms_event,
            on_disconnect=self._on_disconnect,
        )
        _LOGGER.debug(
            "Unknown: Created wrapped client %s, connecting...",
            type(self._wrapped_client).__name__,
        )

        await self._wrapped_client.connect()
        _LOGGER.debug(
            "Unknown: Wrapped client connected. machine_type=%s, live_properties=%s",
            self._wrapped_client.machine_type,
            self._wrapped_client.live_properties,
        )

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._wrapped_client is not None:
            await self._wrapped_client.disconnect()
        elif self._cli is not None and self._cli.is_connected:
            await self._cli.disconnect()
            self._cli = None

    def set_ble_device_and_advertisement_data(
        self, ble_device: BLEDevice, adv_data: AdvertisementData | None
    ) -> None:
        """Update BLE device and advertisement data."""
        self._device = ble_device
        self._adv_data = adv_data
        if self._wrapped_client is not None:
            self._wrapped_client.set_ble_device_and_advertisement_data(ble_device, adv_data)
