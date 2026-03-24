import io
import logging

import pytest

from pyftms.models import (
    MachineStatusModel,
    TrainingStatusCode,
    TrainingStatusFlags,
    TrainingStatusModel,
    TreadmillData,
)
from pyftms.serializer import BaseModel, ModelSerializer, get_serializer
from pyftms.models import training_status as training_status_module


@pytest.mark.parametrize(
    "model,data,result",
    [
        (
            TreadmillData,
            b"\x00\x00\x00\x00",
            {"speed_instant": 0},
        ),
        # Testing `hassio-ftms` issue #3: https://github.com/dudanov/hassio-ftms/issues/3
        (
            TreadmillData,
            b"\x9c\x25\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
            {
                "speed_instant": 0,
                "distance_total": 0,
                "heart_rate": 0,
                "time_elapsed": 0,
                "step_count": 0,
                "inclination": 0,
                "ramp_angle": 0,
                "elevation_gain_positive": 0,
                "elevation_gain_negative": 0,
                "energy_total": 0,
                "energy_per_hour": 0,
                "energy_per_minute": 0,
            },
        ),
        (
            MachineStatusModel,
            b"\x05\x69\x00",
            {"code": 5, "target_speed": 1.05},
        ),
    ],
)
def test_realtime_data(model: type[BaseModel], data: bytes, result: dict):
    s = get_serializer(model)

    assert isinstance(s, ModelSerializer)
    assert s.deserialize(data)._asdict() == result


@pytest.fixture(autouse=True)
def reset_training_status_unknown_state():
    training_status_module._LOGGED_UNKNOWN_FLAG_VALUES.clear()
    training_status_module._LOGGED_UNKNOWN_CODE_VALUES.clear()


def test_training_status_flags_masks_unknown_bits_and_logs_once(caplog):
    with caplog.at_level(logging.WARNING, logger="pyftms.models.training_status"):
        flags = TrainingStatusFlags(155)
        flags_again = TrainingStatusFlags(155)

    assert flags == (
        TrainingStatusFlags.STRING_PRESENT | TrainingStatusFlags.EXTENDED_STRING
    )
    assert flags.raw_value == 155
    assert flags.reserved_bits == 152
    assert flags.has_reserved_bits is True
    assert flags_again.raw_value == 155

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "pyftms.models.training_status"
    ]
    assert len(messages) == 1
    assert "TrainingStatusFlags value 155 (0x9B)" in messages[0]
    assert "outside the FTMS-defined flag bits" in messages[0]
    assert "masked to 3 (0x03)" in messages[0]
    assert "reserved/RFU bits 152 (0x98)" in messages[0]


def test_training_status_flags_known_value_has_no_reserved_bits():
    flags = TrainingStatusFlags.STRING_PRESENT

    assert flags.raw_value == 1
    assert flags.reserved_bits == 0
    assert flags.has_reserved_bits is False


def test_training_status_code_reserved_value_is_cached_and_logs_once(caplog):
    with caplog.at_level(logging.WARNING, logger="pyftms.models.training_status"):
        code = TrainingStatusCode(93)
        code_again = TrainingStatusCode(93)

    assert code is code_again
    assert code.name == "RESERVED_93"
    assert code.raw_value == 93
    assert code.is_reserved is True

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "pyftms.models.training_status"
    ]
    assert len(messages) == 1
    assert "TrainingStatusCode value 93 (0x5D)" in messages[0]
    assert "outside the FTMS-defined range 0x00-0x0F" in messages[0]


def test_training_status_code_known_value_is_not_reserved():
    assert TrainingStatusCode.IDLE.raw_value == 1
    assert TrainingStatusCode.IDLE.is_reserved is False


def test_training_status_model_deserializes_non_standard_values():
    model = TrainingStatusModel._deserialize(io.BytesIO(b"\x9B\x5D"))

    assert model.flags.raw_value == 155
    assert model.flags.reserved_bits == 152
    assert model.flags.has_reserved_bits is True
    assert model.code == TrainingStatusCode(93)
    assert model.code.name == "RESERVED_93"
    assert model.code.raw_value == 93
    assert model.code.is_reserved is True
