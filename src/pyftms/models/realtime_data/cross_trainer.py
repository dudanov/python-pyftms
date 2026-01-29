# Copyright 2024, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import dataclasses as dc

from ...client.properties import MovementDirection
from .common import (
    BaseModel,
    EnergyData,
    InclinationData,
    RealtimeSpeedData,
    model_meta,
)


@dc.dataclass(frozen=True)
class ElevationGainData(BaseModel):
    elevation_gain_positive: int = dc.field(
        metadata=model_meta(
            format="u2",
        ),
    )
    """Elevation Gain Positive"""

    elevation_gain_negative: int = dc.field(
        metadata=model_meta(
            format="u2",
        ),
    )
    """Elevation Gain Negative"""


@dc.dataclass(frozen=True)
class StepRateData(BaseModel):
    step_rate_instant: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2",
        ),
    )
    """Step Rate Instant"""

    step_rate_average: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2",
        ),
    )
    """Step Rate Average"""


@dc.dataclass(frozen=True)
class CrossTrainerData(RealtimeSpeedData):
    distance_total: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u3",
            features_bit=2,
        ),
    )
    """Total Distance"""

    step_rate: StepRateData | None = dc.field(
        default=None,
        metadata=model_meta(
            features_bit=6,
        ),
    )
    """Step Rate Data"""

    stride_count: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2",
            features_bit=8,
        ),
    )
    """Stride Count"""

    elevation_gain: ElevationGainData | None = dc.field(
        default=None,
        metadata=model_meta(
            features_bit=4,
        ),
    )
    """Elevation Gain Data"""

    inclination: InclinationData | None = dc.field(
        default=None,
        metadata=model_meta(
            features_bit=3,
        ),
    )
    """Inclination and Ramp Angle Data"""

    resistance_level: float | None = dc.field(
        default=None,
        metadata=model_meta(
            format="s2.1",
            features_bit=7,
        ),
    )
    """Resistance Level"""

    power_instant: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="s2",
            features_bit=14,
        ),
    )
    """Instantaneous Power"""

    power_average: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="s2",
            features_bit=14,
        ),
    )
    """Average Power"""

    energy: EnergyData | None = dc.field(
        default=None,
        metadata=model_meta(
            features_bit=9,
        ),
    )
    """Energy Data"""

    heart_rate: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u1",
            features_bit=10,
        ),
    )
    """Heart Rate"""

    metabolic_equivalent: float | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u1.1",
            features_bit=11,
        ),
    )
    """Metabolic Equivalent"""

    time_elapsed: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2",
            features_bit=12,
        ),
    )
    """Elapsed Time"""

    time_remaining: int | None = dc.field(
        default=None,
        metadata=model_meta(
            format="u2",
            features_bit=13,
        ),
    )
    """Remaining Time"""

    movement_direction: MovementDirection = dc.field(
        init=False,
        metadata=model_meta(),
    )
    """Movement Direction"""

    def __post_init__(self, mask: int):
        md = (
            MovementDirection.BACKWARD
            if mask & 0x8000
            else MovementDirection.FORWARD
        )
        object.__setattr__(self, "movement_direction", md)
