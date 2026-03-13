# Copyright 2024, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import dataclasses as dc
import io
import logging
from typing import Any, cast, override

from ...serializer import BaseModel, get_serializer, model_meta

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True)
class RealtimeData(BaseModel):
    mask: dc.InitVar[int]

    @override
    @classmethod
    def _deserialize_asdict(cls, src: io.IOBase) -> dict[str, Any]:
        mask, kwargs = cast(int, get_serializer("u2").deserialize(src)), {}
        kwargs["mask"] = mask
        mask ^= 1

        for field, serializer in cls._iter_fields_serializers():
            if mask & 1:
                try:
                    kwargs[field.name] = serializer.deserialize(src)
                except EOFError:
                    # Data was truncated - more data may arrive in next packet
                    break

            mask >>= 1

            if not mask:
                break

        remaining = src.read()
        if remaining:
            _LOGGER.debug("Extra bytes in data stream ignored: %s", remaining.hex())

        return kwargs

    @override
    @classmethod
    def _calc_size(cls) -> int:
        return super()._calc_size() + 2


@dc.dataclass(frozen=True)
class RealtimeSpeedData(RealtimeData):
    speed_instant: float | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2.01",
        ),
    )
    """Instantaneous Speed"""

    speed_average: float | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2.01",
            features_bit=0,
        ),
    )
    """Average Speed"""


@dc.dataclass(frozen=True)
class InclinationData(BaseModel):
    inclination: float | None = dc.field(
        default=None,
        metadata=model_meta(
            format="s2.1",
        ),
    )
    """Inclination"""

    ramp_angle: float | None = dc.field(
        default=None,
        metadata=model_meta(
            format="s2.1",
        ),
    )
    """Ramp Angle"""


@dc.dataclass(frozen=True)
class EnergyData(BaseModel):
    energy_total: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2",
        ),
    )
    """Total Energy"""

    energy_per_hour: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2",
        ),
    )
    """Per Hour Energy"""

    energy_per_minute: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u1",
        ),
    )
    """Per Minute Energy"""
