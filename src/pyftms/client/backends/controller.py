# Copyright 2024-2025, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import asyncio
import io
import logging
from typing import cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...models import (
    CodeSwitchModel,
    ControlCode,
    ControlIndicateModel,
    ControlModel,
    MachineStatusCode,
    MachineStatusModel,
    ResultCode,
    SpinDownSpeedData,
    StopPauseCode,
    TrainingStatusFlags,
    TrainingStatusModel,
)
from ..const import (
    CONTROL_POINT_UUID,
    PAUSE,
    STATUS_UUID,
    STOP,
    TRAINING_STATUS_UUID,
)
from .event import (
    ControlEvent,
    FtmsCallback,
    SetupEvent,
    SetupEventData,
    SpinDownEvent,
    SpinDownEventData,
    UpdateEvent,
    UpdateEventData,
)

_LOGGER = logging.getLogger(__name__)


def _to_setup_event_data(model: CodeSwitchModel) -> SetupEventData:
    result = model._asdict(nested=True)

    result.pop("code")

    if not result:
        return {}

    assert len(result) == 1

    k, v = next(iter(result.items()))

    # Handle 'target_time_x'
    if k[-1].isdecimal():
        k = k[:-2]

    return cast(SetupEventData, {k: v})  # unsafe cast


def _simple_status_events(m: MachineStatusModel) -> ControlEvent | None:
    match m.code:
        case MachineStatusCode.RESET:
            return ControlEvent(event_id="reset", event_source="other")

        case MachineStatusCode.STOP_PAUSE:
            value = (
                STOP
                if StopPauseCode(m.stop_pause) == StopPauseCode.STOP
                else PAUSE
            )
            return ControlEvent(event_id=value, event_source="user")

        case MachineStatusCode.STOP_SAFETY:
            return ControlEvent(event_id="stop", event_source="safety")

        case MachineStatusCode.START_RESUME:
            return ControlEvent(event_id="start", event_source="user")


def _simple_control_events(m: ControlModel) -> ControlEvent | None:
    """Handle simple control requests after success operation indication"""
    match m.code:
        case ControlCode.RESET:
            return ControlEvent(event_id="reset", event_source="callback")

        case ControlCode.STOP_PAUSE:
            value = (
                STOP
                if StopPauseCode(m.stop_pause) == StopPauseCode.STOP
                else PAUSE
            )
            return ControlEvent(event_id=value, event_source="callback")

        case ControlCode.START_RESUME:
            return ControlEvent(event_id="start", event_source="callback")


class MachineController:
    _indicate: asyncio.Future[bytes]

    def __init__(self, callback: FtmsCallback) -> None:
        self._subscribed = False
        self._auth = False
        self._cb = callback
        self._write_lock = asyncio.Lock()

    async def subscribe(self, cli: BleakClient) -> None:
        """Subscribe for available notifications."""
        if self._subscribed:
            return

        if c := cli.services.get_characteristic(TRAINING_STATUS_UUID):
            self._on_training_status(c, await cli.read_gatt_char(c))
            await cli.start_notify(c, self._on_training_status)

        if c := cli.services.get_characteristic(STATUS_UUID):
            await cli.start_notify(c, self._on_machine_status)

        if c := cli.services.get_characteristic(CONTROL_POINT_UUID):
            await cli.start_notify(c, self._on_indicate)

        self._subscribed = True

    def reset(self):
        """Resetting state. Call while disconnection event."""
        self._subscribed = False
        self._auth = False

    def _on_indicate(self, c: BleakGATTCharacteristic, data: bytes) -> None:
        """Control indication callback."""
        if not self._indicate.done():
            self._indicate.set_result(data)

    async def write_command(
        self,
        cli: BleakClient,
        code: ControlCode | None = None,
        *,
        timeout: float = 2.0,
        **kwargs,
    ) -> ResultCode:
        """Writing command to control point."""
        # Auto-Request control
        if not self._auth and code != ControlCode.REQUEST_CONTROL:
            await self.write_command(
                cli,
                ControlCode.REQUEST_CONTROL,
                timeout=timeout,
            )

        bio = io.BytesIO()

        request = ControlModel(code=code, **kwargs)
        request._serialize(bio)

        # Write to control point

        await self.subscribe(cli)

        # The spec requires Write, but some machines (e.g. Moov Walk Plus)
        # only permit Write Without Response on the control point.
        c = cli.services.get_characteristic(CONTROL_POINT_UUID)
        response = c is None or "write" in c.properties

        async with self._write_lock:
            self._indicate = asyncio.Future()
            _, resp = await asyncio.wait_for(
                asyncio.gather(
                    cli.write_gatt_char(
                        CONTROL_POINT_UUID,
                        bio.getvalue(),
                        response,
                    ),
                    self._indicate,
                ),
                timeout=timeout,
            )

        bio = io.BytesIO(resp)

        indicate = ControlIndicateModel._deserialize(bio)

        if indicate.request_code != request.code:
            raise ValueError("Response on another request?..")

        if indicate.result_code != ResultCode.SUCCESS:
            return indicate.result_code

        if request.code == ControlCode.RESET:
            self._auth = False

        elif request.code == ControlCode.REQUEST_CONTROL:
            self._auth = True

            return ResultCode.SUCCESS

        elif request.spin_down is not None:
            data = SpinDownEventData(code=request.spin_down)

            s = SpinDownSpeedData._get_serializer()

            if speed_bytes := bio.read(s.get_size()):
                data["target_speed"] = s.deserialize(speed_bytes)

            assert not bio.read(1)

            event = SpinDownEvent(event_id="spin_down", event_data=data)

            self._cb(event)

            return ResultCode.SUCCESS

        # Writing is success. Firing events and update settings data.

        if event := _simple_control_events(request):
            # reset, start, stop, pause handled
            self._cb(event)

            return ResultCode.SUCCESS

        # Handling setup requests with parameters

        event = SetupEvent(
            event_id="setup",
            event_data=_to_setup_event_data(request),
            event_source="callback",
        )

        self._cb(event)

        return ResultCode.SUCCESS

    def _on_machine_status(
        self, c: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Machine Status notification callback."""
        bio = io.BytesIO(data)
        status = MachineStatusModel._deserialize(bio)

        # Handle loosing control
        if status.code == MachineStatusCode.LOST_CONTROL:
            self._auth = False
            return

        if status.code == MachineStatusCode.RESET:
            self._auth = False

        if p := _simple_status_events(status):
            # reset, start, stop (and safety), pause handled
            return self._cb(p)

        event = SetupEvent(
            event_id="setup",
            event_data=_to_setup_event_data(status),
            event_source="other",
        )

        self._cb(event)

    def _on_training_status(
        self, c: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Training Status notification callback."""
        bio = io.BytesIO(data)
        status = TrainingStatusModel._deserialize(bio)

        status_data = UpdateEventData(training_status=status.code)

        if TrainingStatusFlags.STRING_PRESENT in status.flags:
            if b := bio.read():
                status_data["training_status_string"] = b.decode(
                    encoding="utf-8"
                )

        event = UpdateEvent(event_id="update", event_data=status_data)

        self._cb(event)
