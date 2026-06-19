import pytest
from bleak.backends.scanner import AdvertisementData
from bleak.uuids import normalize_uuid_str

from pyftms import (
    MachineType,
    NotFitnessMachineError,
    get_machine_type_from_advertisement,
    get_machine_type_from_gatt,
    get_machine_type_from_service_data,
)
from pyftms.client.const import (
    CROSS_TRAINER_DATA_UUID,
    FTMS_UUID,
    INDOOR_BIKE_DATA_UUID,
    ROWER_DATA_UUID,
    TREADMILL_DATA_UUID,
)


FTMS_SERVICE_UUID = normalize_uuid_str(FTMS_UUID)


def _advertisement(
    *,
    service_data: dict[str, bytes] | None = None,
    service_uuids: list[str] | None = None,
) -> AdvertisementData:
    return AdvertisementData(
        local_name=None,
        manufacturer_data={},
        service_data=service_data or {},
        service_uuids=service_uuids or [],
        tx_power=None,
        rssi=-60,
        platform_data=(),
    )


class _FakeServices:
    def __init__(self, uuids):
        self._uuids = set(uuids)

    def get_characteristic(self, uuid):
        return object() if uuid in self._uuids else None


class _FakeClient:
    def __init__(self, uuids):
        self.services = _FakeServices(uuids)


def test_get_machine_type_from_advertisement_uses_service_data():
    advertisement = _advertisement(
        service_data={FTMS_SERVICE_UUID: b"\x01\x20"},
        service_uuids=[FTMS_SERVICE_UUID],
    )

    assert get_machine_type_from_advertisement(advertisement) is MachineType.INDOOR_BIKE
    assert get_machine_type_from_service_data(advertisement) is MachineType.INDOOR_BIKE


def test_get_machine_type_from_advertisement_accepts_uuid_only_devices():
    advertisement = _advertisement(service_uuids=[FTMS_SERVICE_UUID])

    assert get_machine_type_from_advertisement(advertisement) is MachineType.INDOOR_BIKE
    with pytest.raises(NotFitnessMachineError):
        get_machine_type_from_service_data(advertisement)


def test_get_machine_type_from_advertisement_rejects_non_ftms_devices():
    advertisement = _advertisement()

    with pytest.raises(NotFitnessMachineError):
        get_machine_type_from_advertisement(advertisement)


@pytest.mark.parametrize(
    ("uuid", "machine_type"),
    [
        (TREADMILL_DATA_UUID, MachineType.TREADMILL),
        (CROSS_TRAINER_DATA_UUID, MachineType.CROSS_TRAINER),
        (ROWER_DATA_UUID, MachineType.ROWER),
        (INDOOR_BIKE_DATA_UUID, MachineType.INDOOR_BIKE),
    ],
)
def test_get_machine_type_from_gatt_uses_data_characteristic(
    uuid, machine_type
):
    assert get_machine_type_from_gatt(_FakeClient([uuid])) is machine_type


def test_get_machine_type_from_gatt_rejects_missing_data_characteristic():
    with pytest.raises(
        NotFitnessMachineError,
        match="No supported FTMS data characteristic found",
    ):
        get_machine_type_from_gatt(_FakeClient([]))
