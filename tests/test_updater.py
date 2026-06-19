from pyftms.client.backends import DataUpdater
from pyftms.models import IndoorBikeData


class _FakeRealtimeModel:
    def __init__(self, data):
        self._data = data

    def _asdict(self):
        return self._data


class _FakeSerializer:
    def __init__(self, *payloads):
        self._payloads = iter(payloads)

    def deserialize(self, _data):
        return _FakeRealtimeModel(next(self._payloads))


def test_updater_uses_stable_snapshot_for_callback_event():
    events = []
    updater = DataUpdater(IndoorBikeData, events.append)
    updater._serializer = _FakeSerializer(
        {"speed_instant": 5.0},
        {"cadence_instant": 90.0},
    )

    updater._on_notify(None, bytearray(b"\x00"))
    first_event_data = events[0].event_data

    updater._on_notify(None, bytearray(b"\x00"))

    assert first_event_data == {"speed_instant": 5.0}
    assert events[1].event_data == {"cadence_instant": 90.0}
