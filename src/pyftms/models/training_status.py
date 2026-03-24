# Copyright 2024, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import dataclasses as dc
import logging
from enum import STRICT, IntEnum, IntFlag, auto

from .common import BaseModel, model_meta

_LOGGER = logging.getLogger(__name__)
_LOGGED_UNKNOWN_FLAG_VALUES: set[int] = set()
_LOGGED_UNKNOWN_CODE_VALUES: set[int] = set()
_DEFINED_TRAINING_STATUS_FLAGS_MASK = 0x03
_MAX_DEFINED_TRAINING_STATUS_CODE = 0x0F


def _format_value(value: int) -> str:
    return f"{value} (0x{value:02X})"


class TrainingStatusFlags(IntFlag, boundary=STRICT):
    """
    Training Status.

    Represents the current training state while a user is exercising.

    Described in section **4.10.1.2: Training Status Field**.
    """

    STRING_PRESENT = auto()
    """Other."""

    EXTENDED_STRING = auto()
    """Idle."""

    @classmethod
    def _missing_(cls, value):
        # FTMS v1.0.1 section 4.10.1.2 defines only bits 0 and 1 in the
        # Training Status flags field. Bits 2-7 are RFU and should not break
        # parsing when devices set them.
        #
        # Observed on a Wahoo KICKR CORE v2:
        # - raw flags: 155 (0x9B)
        # - raw code: 93 (0x5D)
        # These values are outside the public FTMS-defined surface, so we
        # preserve the defined subset and report the reserved portion.
        raw_value = int(value)
        masked = raw_value & _DEFINED_TRAINING_STATUS_FLAGS_MASK
        reserved_bits = raw_value & ~_DEFINED_TRAINING_STATUS_FLAGS_MASK

        if reserved_bits and raw_value not in _LOGGED_UNKNOWN_FLAG_VALUES:
            _LOGGED_UNKNOWN_FLAG_VALUES.add(raw_value)
            _LOGGER.warning(
                "Received TrainingStatusFlags value %s outside the FTMS-defined "
                "flag bits; masked to %s with reserved/RFU bits %s",
                _format_value(raw_value),
                _format_value(masked),
                _format_value(reserved_bits),
            )

        obj = int.__new__(cls, masked)
        obj._value_ = masked
        obj._raw_value_ = raw_value
        obj._reserved_bits_ = reserved_bits
        return obj

    @property
    def raw_value(self) -> int:
        return getattr(self, "_raw_value_", int(self))

    @property
    def reserved_bits(self) -> int:
        return getattr(self, "_reserved_bits_", 0)

    @property
    def has_reserved_bits(self) -> bool:
        return bool(self.reserved_bits)


class TrainingStatusCode(IntEnum, boundary=STRICT):
    """
    Training Status.

    Represents the current training state while a user is exercising.

    Described in section **4.10.1.2: Training Status Field**.

    FTMS v1.0.1 defines values 0x00-0x0F in the Training Status field.
    Values 0x10-0xFF are reserved.
    """

    OTHER = 0
    """Other."""

    IDLE = auto()
    """Idle."""

    WARMING_UP = auto()
    """Warming Up."""

    LOW_INTENSITY_INTERVAL = auto()
    """Low Intensity Interval."""

    HIGH_INTENSITY_INTERVAL = auto()
    """High Intensity Interval."""

    RECOVERY_INTERVAL = auto()
    """Recovery Interval."""

    ISOMETRIC = auto()
    """Isometric."""

    HEART_RATE_CONTROL = auto()
    """Heart Rate Control."""

    FITNESS_TEST = auto()
    """Fitness Test."""

    SPEED_TOO_LOW = auto()
    """Speed Outside of Control Region - Low (increase speed to return to controllable region)."""

    SPEED_TOO_HIGH = auto()
    """Speed Outside of Control Region - High (decrease speed to return to controllable region)."""

    COOL_DOWN = auto()
    """Cool Down."""

    WATT_CONTROL = auto()
    """Watt Control."""

    MANUAL_MODE = auto()
    """Manual Mode (Quick Start)."""

    PRE_WORKOUT = auto()
    """Pre-Workout."""

    POST_WORKOUT = auto()
    """Post-Workout."""

    @classmethod
    def _missing_(cls, value: int):
        value = int(value)

        # Reserved values are cached so repeated notifications reuse the same
        # pseudo-member instead of synthesizing a new enum instance each time.
        pseudo = cls._value2member_map_.get(value)
        if pseudo is not None:
            return pseudo

        if value not in _LOGGED_UNKNOWN_CODE_VALUES:
            _LOGGED_UNKNOWN_CODE_VALUES.add(value)
            _LOGGER.warning(
                "Received reserved TrainingStatusCode value %s outside the "
                "FTMS-defined range 0x00-0x%02X",
                _format_value(value),
                _MAX_DEFINED_TRAINING_STATUS_CODE,
            )

        obj = int.__new__(cls, value)
        obj._value_ = value
        obj._name_ = f"RESERVED_{value}"
        obj._raw_value_ = value
        obj._is_reserved_ = True

        cls._value2member_map_[value] = obj
        return obj

    @property
    def raw_value(self) -> int:
        return getattr(self, "_raw_value_", int(self))

    @property
    def is_reserved(self) -> bool:
        return getattr(self, "_is_reserved_", False)


@dc.dataclass(frozen=True)
class TrainingStatusModel(BaseModel):
    """
    Structure of the Training Status Characteristic.

    Described in section **4.10 Training Status**.
    """

    flags: TrainingStatusFlags = dc.field(
        metadata=model_meta(
            format="u1",
        )
    )
    """Flags Field."""

    code: TrainingStatusCode = dc.field(
        metadata=model_meta(
            format="u1",
        )
    )
    """Training Status Field."""
