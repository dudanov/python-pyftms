# Copyright 2024-2025, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import functools
import logging
import operator
from enum import Flag, auto

from bleak.backends.scanner import AdvertisementData
from bleak.uuids import normalize_uuid_str

from ..const import FTMS_UUID
from ..errors import NotFitnessMachineError

_LOGGER = logging.getLogger(__name__)


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
    UNKNOWN = auto()
    """Unknown Machine Type. Used during discovery when device type cannot be determined
    from advertisement data. The actual type is detected by subscribing to all data UUIDs."""


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
        # Check if device advertises FTMS UUID but lacks proper service_data
        has_ftms_uuid = any(
            normalize_uuid_str(uuid) == normalize_uuid_str(FTMS_UUID)
            for uuid in adv_data.service_uuids
        )
        if has_ftms_uuid:
            _LOGGER.info(
                "Device %r advertises FTMS but lacks service_data. "
                "Using UNKNOWN type - will detect from data UUIDs on connect.",
                adv_data.local_name,
            )
            return MachineType.UNKNOWN
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
