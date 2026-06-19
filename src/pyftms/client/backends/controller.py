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
        self._cli: BleakClient | None = None
        self._training_status_refresh_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()

    async def subscribe(self, cli: BleakClient) -> None:
        """Subscribe for available notifications."""
        if self._subscribed:
            return

        self._cli = cli

        if c := cli.services.get_characteristic(TRAINING_STATUS_UUID):
            await self._read_and_emit_training_status(
                cli, c, initial_data=await cli.read_gatt_char(c, use_cached=False)
            )
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
        self._cli = None
        if self._training_status_refresh_task is not None:
            self._training_status_refresh_task.cancel()
            self._training_status_refresh_task = None

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

        async with self._write_lock:
            self._indicate = asyncio.Future()
            _, resp = await asyncio.wait_for(
                asyncio.gather(
                    cli.write_gatt_char(
                        CONTROL_POINT_UUID,
                        bio.getvalue(),
                        True,
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
        fallback_event, needs_extended_read = self._build_training_status_event(
            data, include_inline_string=False
        )

        if needs_extended_read:
            self._schedule_training_status_refresh(c, fallback_event)
            return

        event, _ = self._build_training_status_event(
            data, include_inline_string=True
        )
        self._cb(event)

    def _build_training_status_event(
        self, data: bytes | bytearray, *, include_inline_string: bool
    ) -> tuple[UpdateEvent, bool]:
        bio = io.BytesIO(data)
        status = TrainingStatusModel._deserialize(bio)

        status_data = UpdateEventData(training_status=status.code)
        needs_extended_read = (
            TrainingStatusFlags.EXTENDED_STRING in status.flags
        )

        if (
            include_inline_string
            and TrainingStatusFlags.STRING_PRESENT in status.flags
            and (b := bio.read())
        ):
            status_data["training_status_string"] = b.decode(
                encoding="utf-8"
            )

        return UpdateEvent("update", status_data), needs_extended_read

    async def _read_and_emit_training_status(
        self,
        cli: BleakClient,
        c: BleakGATTCharacteristic,
        initial_data: bytes | bytearray | None = None,
    ) -> None:
        # FTMS v1.0.1 section 4.10.1.2 requires the client to read the full
        # characteristic value when the Extended String flag is set because the
        # string may exceed the current MTU-sized value. The Wahoo KICKR CORE
        # v2 also sets this flag.
        data = (
            initial_data
            if initial_data is not None
            else await cli.read_gatt_char(c, use_cached=False)
        )
        event, needs_extended_read = self._build_training_status_event(
            data, include_inline_string=True
        )

        if needs_extended_read:
            _LOGGER.debug(
                "Training Status Extended String bit is set; using an "
                "explicit characteristic read to retrieve the full value."
            )
            if initial_data is not None:
                data = await cli.read_gatt_char(c, use_cached=False)
                event, _ = self._build_training_status_event(
                    data, include_inline_string=True
                )

        self._cb(event)

    def _schedule_training_status_refresh(
        self,
        c: BleakGATTCharacteristic,
        fallback_event: UpdateEvent,
    ) -> None:
        if self._cli is None:
            self._cb(fallback_event)
            return

        if (
            self._training_status_refresh_task is not None
            and not self._training_status_refresh_task.done()
        ):
            _LOGGER.debug(
                "Training Status refresh already in flight; skipping "
                "duplicate extended-string read."
            )
            return

        async def _refresh() -> None:
            try:
                await self._read_and_emit_training_status(self._cli, c)
            except Exception:
                _LOGGER.warning(
                    "Failed to refresh Training Status with Extended String; "
                    "emitting status code without training_status_string.",
                    exc_info=True,
                )
                self._cb(fallback_event)

        task = asyncio.create_task(_refresh())
        task.add_done_callback(self._clear_training_status_refresh_task)
        self._training_status_refresh_task = task

    def _clear_training_status_refresh_task(
        self, task: asyncio.Task[None]
    ) -> None:
        if self._training_status_refresh_task is task:
            self._training_status_refresh_task = None
