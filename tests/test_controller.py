import asyncio
import logging

from pyftms.client.backends.controller import MachineController
from pyftms.models import TrainingStatusCode


class FakeCharacteristic:
    uuid = "2ad3"


class FakeServices:
    def __init__(self, characteristic):
        self._characteristic = characteristic

    def get_characteristic(self, uuid):
        if uuid == self._characteristic.uuid:
            return self._characteristic
        return None


class FakeClient:
    def __init__(self, characteristic, responses):
        self.services = FakeServices(characteristic)
        self._responses = list(responses)
        self.read_calls = []
        self.notify_callbacks = {}

    async def read_gatt_char(self, characteristic, *, use_cached=False, **kwargs):
        self.read_calls.append((characteristic, use_cached))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def start_notify(self, characteristic, callback):
        self.notify_callbacks[characteristic.uuid] = callback


def test_subscribe_reads_full_training_status_when_extended_string_is_set():
    async def scenario():
        events = []
        characteristic = FakeCharacteristic()
        client = FakeClient(
            characteristic,
            [
                b"\x03\x05Wo",
                b"\x03\x05Workout",
            ],
        )
        controller = MachineController(events.append)

        await controller.subscribe(client)

        assert len(events) == 1
        assert events[0].event_data["training_status"] == TrainingStatusCode(5)
        assert events[0].event_data["training_status_string"] == "Workout"
        assert client.read_calls == [
            (characteristic, False),
            (characteristic, False),
        ]
        assert characteristic.uuid in client.notify_callbacks

    asyncio.run(scenario())


def test_notify_extended_string_refresh_deduplicates_reads():
    async def scenario():
        events = []
        characteristic = FakeCharacteristic()
        client = FakeClient(characteristic, [b"\x03\x05Workout"])
        controller = MachineController(events.append)
        controller._cli = client

        controller._on_training_status(characteristic, b"\x03\x05Wo")
        controller._on_training_status(characteristic, b"\x03\x05Wo")

        assert controller._training_status_refresh_task is not None
        await controller._training_status_refresh_task
        await asyncio.sleep(0)

        assert len(events) == 1
        assert events[0].event_data["training_status"] == TrainingStatusCode(5)
        assert events[0].event_data["training_status_string"] == "Workout"
        assert client.read_calls == [(characteristic, False)]
        assert controller._training_status_refresh_task is None

    asyncio.run(scenario())


def test_notify_extended_string_refresh_failure_falls_back_to_status(caplog):
    async def scenario():
        events = []
        characteristic = FakeCharacteristic()
        client = FakeClient(characteristic, [RuntimeError("read failed")])
        controller = MachineController(events.append)
        controller._cli = client

        with caplog.at_level(
            logging.WARNING, logger="pyftms.client.backends.controller"
        ):
            controller._on_training_status(characteristic, b"\x03\x05Wo")
            assert controller._training_status_refresh_task is not None
            await controller._training_status_refresh_task
            await asyncio.sleep(0)

        assert len(events) == 1
        assert events[0].event_data == {
            "training_status": TrainingStatusCode(5)
        }
        assert "Failed to refresh Training Status with Extended String" in caplog.text

    asyncio.run(scenario())


def test_training_status_without_extended_string_uses_inline_payload():
    events = []
    controller = MachineController(events.append)
    characteristic = FakeCharacteristic()

    controller._on_training_status(characteristic, b"\x01\x05Workout")

    assert len(events) == 1
    assert events[0].event_data["training_status"] == TrainingStatusCode(5)
    assert events[0].event_data["training_status_string"] == "Workout"
