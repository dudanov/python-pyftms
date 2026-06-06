# Copyright 2024-2025, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import functools
import operator
from enum import Flag, auto

from bleak import BleakClient
from bleak.backends.scanner import AdvertisementData
from bleak.uuids import normalize_uuid_str

from ..const import (
    CROSS_TRAINER_DATA_UUID,
    FTMS_UUID,
    INDOOR_BIKE_DATA_UUID,
    ROWER_DATA_UUID,
    TREADMILL_DATA_UUID,
)
from ..errors import NotFitnessMachineError


class MachineFlags(Flag):
    """
    Fitness Machine Flags.

    Included in the `Service Data AD Type`.

    Described in section `3.1.1: Flags Field`.
    """

    FITNESS_MACHINE = auto()
    """Fitness Machine Available"""


class MachineType(Flag):
    """
    Fitness Machine Type.

    Included in the Advertisement Service Data.

    Described in section **3.1.2: Fitness Machine Type Field**.
    """

    TREADMILL = auto()
    """Treadmill Machine."""
    CROSS_TRAINER = auto()
    """Cross Trainer Machine."""
    STEP_CLIMBER = auto()
    """Step Climber Machine."""
    STAIR_CLIMBER = auto()
    """Stair Climber Machine."""
    ROWER = auto()
    """Rower Machine."""
    INDOOR_BIKE = auto()
    """Indoor Bike Machine."""


def get_machine_type_from_service_data(
    adv_data: AdvertisementData,
) -> MachineType:
    """Returns fitness machine type from Bluetooth advertisement data.

    Parameters:
        adv_data: Bluetooth [advertisement data](https://bleak.readthedocs.io/en/latest/backends/index.html#bleak.backends.scanner.AdvertisementData).

    Returns:
        Fitness machine type.
    """

    data = adv_data.service_data.get(normalize_uuid_str(FTMS_UUID))

    if data is None or not (2 <= len(data) <= 3):
        raise NotFitnessMachineError(data)

    # Reading mandatory `Flags` and `Machine Type`.
    # `Machine Type` bytes may be reversed on some machines or be a just one
    # byte (it's bug), so I logically ORed them.
    try:
        mt = functools.reduce(operator.or_, data[1:])
        mf, mt = MachineFlags(data[0]), MachineType(mt)

    except ValueError:
        raise NotFitnessMachineError(data)

    if mf and mt:
        return mt

    raise NotFitnessMachineError(data)


async def get_machine_type_from_gatt(cli: BleakClient) -> MachineType:
    """Determines fitness machine type from connected GATT characteristics.

    Used as a fallback when the device advertises the FTMS service UUID but
    does not include machine type information in its advertisement service data
    (e.g. Bodytone DU30).

    Parameters:
        cli: Connected `BleakClient` instance with FTMS service discovered.

    Returns:
        Fitness machine type.
    """

    _UUID_TO_TYPE = (
        (TREADMILL_DATA_UUID, MachineType.TREADMILL),
        (CROSS_TRAINER_DATA_UUID, MachineType.CROSS_TRAINER),
        (ROWER_DATA_UUID, MachineType.ROWER),
        (INDOOR_BIKE_DATA_UUID, MachineType.INDOOR_BIKE),
    )

    for uuid, machine_type in _UUID_TO_TYPE:
        if cli.services.get_characteristic(uuid) is not None:
            return machine_type

    raise NotFitnessMachineError()
