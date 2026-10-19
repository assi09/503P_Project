"""Synthetic daily metrics with planted, known effects.

Produces a table with the same shape as `ingest.takeout.load_daily`, so analysis tools and the agent
can be tested against ground truth: every effect applied to the data is returned alongside it.
Baselines are generic population-level values, not taken from any real export.

The table follows the structure of real Fitbit data: counts are whole numbers, sleep stages add up
to minutes asleep, time in bed is minutes asleep plus minutes awake, and activity minutes fit in a
day. Missing data is planted like any other effect (`MissedNights`, `DeviceOff`, `NewDevice`), so
gaps are part of the ground truth too.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Baseline:
    mean: float
    sd: float
    low: float
    high: float
    digits: int = 0  # decimals Fitbit reports for this metric; 0 for counts


BASELINES = {
    "steps": Baseline(8000, 2500, 0, 40000),
    "calories": Baseline(2300, 250, 1200, 5000, digits=2),
    "distance_km": Baseline(6, 2, 0, 60, digits=3),
    "active_zone_minutes": Baseline(25, 15, 0, 300),
    "cardio_load": Baseline(60, 40, 0, 600, digits=2),
    "resting_hr": Baseline(62, 2, 40, 100, digits=3),
    "hrv_ms": Baseline(45, 8, 5, 150, digits=1),
    "respiratory_rate": Baseline(15, 0.8, 8, 25, digits=1),
    "readiness": Baseline(70, 12, 0, 100),
    "sedentary_minutes": Baseline(600, 80, 0, 1440),
    "lightly_active_minutes": Baseline(200, 50, 0, 1440),
    "moderately_active_minutes": Baseline(20, 12, 0, 1440),
    "very_active_minutes": Baseline(15, 12, 0, 1440),
    "wear_minutes": Baseline(900, 60, 0, 1440),
    "sleep_minutes": Baseline(420, 45, 0, 900),
    "time_in_bed": Baseline(470, 45, 0, 1000),
    "sleep_efficiency": Baseline(90, 4, 0, 100),
    "bedtime_hour": Baseline(-0.5, 0.75, -6, 6, digits=2),
    "sleep_score": Baseline(78, 7, 0, 100),
    "deep_sleep_minutes": Baseline(80, 15, 0, 300),
    "light_sleep_minutes": Baseline(230, 30, 0, 600),
    "rem_sleep_minutes": Baseline(95, 20, 0, 300),
    "awake_in_bed_minutes": Baseline(50, 12, 0, 300),
    "skin_temp_variation_c": Baseline(0, 0.4, -5, 5, digits=3),
}

# Metrics that scale with how long the device was worn, used to simulate low-wear days.
WEAR_DEPENDENT = (
    "steps",
    "calories",
    "distance_km",
    "active_zone_minutes",
    "cardio_load",
    "sedentary_minutes",
    "lightly_active_minutes",
    "moderately_active_minutes",
    "very_active_minutes",
)

STAGES = ("deep_sleep_minutes", "light_sleep_minutes", "rem_sleep_minutes")
ACTIVE = ("lightly_active_minutes", "moderately_active_minutes", "very_active_minutes")
DERIVED = ("time_in_bed",)  # computed from other columns, so effects cannot target it

# Measured while asleep: all missing on a night the device was not worn.
NIGHTLY = (
    "sleep_minutes",
    "time_in_bed",
    "sleep_efficiency",
    "bedtime_hour",
    "sleep_score",
    *STAGES,
    "awake_in_bed_minutes",
    "hrv_ms",
    "respiratory_rate",
    "skin_temp_variation_c",
)

# Days of data a new device needs before Fitbit reports these metrics.
WARMUP_DAYS = {"readiness": 7, "skin_temp_variation_c": 4}


@dataclass(frozen=True)
class Trend:
    """Linear drift of `total_change` spread over [start, end], held at the end value after."""

    metric: str
    start: date
    end: date
    total_change: float


@dataclass(frozen=True)
class Step:
    """Sudden level shift of `delta` from `on` onward."""

    metric: str
    on: date
    delta: float


@dataclass(frozen=True)
class Coupling:
    """`target` follows `driver` from `lag_days` earlier: `strength` target SDs per driver SD."""

    driver: str
    target: str
    lag_days: int
    strength: float


@dataclass(frozen=True)
class LowWear:
    """Device mostly off over [start, end]: wear time drops and activity totals shrink with it."""

    start: date
    end: date
    wear_minutes: float = 300


@dataclass(frozen=True)
class MissedNights:
    """Device not worn overnight on these dates: every sleep-time metric is missing."""

    dates: tuple[date, ...]


@dataclass(frozen=True)
class DeviceOff:
    """No data at all over [start, end]."""

    start: date
    end: date


@dataclass(frozen=True)
class NewDevice:
    """The data starts on the device's first day: no sleep the night before it was worn, and
    metrics that need a personal baseline stay missing for their warm-up period."""


ValueEffect = Trend | Step | Coupling | LowWear
GapEffect = MissedNights | DeviceOff | NewDevice
Effect = ValueEffect | GapEffect


@dataclass
class SyntheticData:
    frame: pd.DataFrame
    effects: tuple[Effect, ...]


def _check_metric(name: str) -> None:
    if name not in BASELINES:
        raise ValueError(f"Unknown metric {name!r}")
    if name in DERIVED:
        raise ValueError(f"{name!r} is derived from other metrics and cannot be targeted")


def _between(index: pd.DatetimeIndex, start: date, end: date) -> np.ndarray:
    return (index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))


def _apply_value(frame: pd.DataFrame, effect: ValueEffect) -> None:
    index = frame.index
    if isinstance(effect, Trend):
        _check_metric(effect.metric)
        start, end = pd.Timestamp(effect.start), pd.Timestamp(effect.end)
        progress = ((index - start) / (end - start)).to_numpy(dtype=float).clip(0, 1)
        frame[effect.metric] += progress * effect.total_change
    elif isinstance(effect, Step):
        _check_metric(effect.metric)
        frame.loc[index >= pd.Timestamp(effect.on), effect.metric] += effect.delta
    elif isinstance(effect, Coupling):
        _check_metric(effect.driver)
        _check_metric(effect.target)
        driver = frame[effect.driver]
        z = ((driver - driver.mean()) / driver.std()).shift(effect.lag_days).fillna(0)
        frame[effect.target] += effect.strength * BASELINES[effect.target].sd * z
    elif isinstance(effect, LowWear):
        days = _between(index, effect.start, effect.end)
        ratio = effect.wear_minutes / frame.loc[days, "wear_minutes"]
        for metric in WEAR_DEPENDENT:
            frame.loc[days, metric] *= ratio
        frame.loc[days, "wear_minutes"] = effect.wear_minutes
    else:
        raise TypeError(f"Unsupported effect {effect!r}")


def _apply_gap(frame: pd.DataFrame, effect: GapEffect) -> None:
    index = frame.index
    if isinstance(effect, MissedNights):
        frame.loc[index.isin(pd.to_datetime(list(effect.dates))), list(NIGHTLY)] = np.nan
    elif isinstance(effect, DeviceOff):
        frame.loc[_between(index, effect.start, effect.end)] = np.nan
    elif isinstance(effect, NewDevice):
        frame.loc[index[:1], list(NIGHTLY)] = np.nan
        for metric, days in WARMUP_DAYS.items():
            frame.loc[index[:days], metric] = np.nan
    else:
        raise TypeError(f"Unsupported effect {effect!r}")


def _make_consistent(frame: pd.DataFrame) -> None:
    """Clip to valid ranges, round like Fitbit, and enforce the identities Fitbit data obeys."""
    for name, b in BASELINES.items():
        frame[name] = frame[name].clip(b.low, b.high).round(b.digits)

    # Stage minutes keep their relative shares but add up exactly to minutes asleep.
    stages = frame[list(STAGES)].clip(lower=1)
    shares = stages.div(stages.sum(axis=1), axis=0)
    asleep = frame["sleep_minutes"]
    frame["deep_sleep_minutes"] = (shares["deep_sleep_minutes"] * asleep).round()
    frame["rem_sleep_minutes"] = (shares["rem_sleep_minutes"] * asleep).round()
    frame["light_sleep_minutes"] = asleep - frame["deep_sleep_minutes"] - frame["rem_sleep_minutes"]
    frame["time_in_bed"] = asleep + frame["awake_in_bed_minutes"]

    # Fitbit's activity minutes cover at most one day.
    room = 1440 - frame[list(ACTIVE)].sum(axis=1)
    frame["sedentary_minutes"] = frame["sedentary_minutes"].clip(upper=room)


def generate(
    start: date, days: int, effects: tuple[Effect, ...] = (), seed: int = 0
) -> SyntheticData:
    """Generate `days` of daily metrics from `start`.

    Value effects are applied in order; gap effects are applied last, so planted changes are
    computed on complete data and then hidden where the gaps are.
    """
    if days < 1:
        raise ValueError("days must be positive")
    rng = np.random.default_rng(seed)
    index = pd.date_range(pd.Timestamp(start), periods=days, freq="D", name="date")
    frame = pd.DataFrame(
        {name: rng.normal(b.mean, b.sd, days) for name, b in BASELINES.items()}, index=index
    )
    for effect in effects:
        if not isinstance(effect, GapEffect):
            _apply_value(frame, effect)
    _make_consistent(frame)
    for effect in effects:
        if isinstance(effect, GapEffect):
            _apply_gap(frame, effect)
    return SyntheticData(frame=frame, effects=tuple(effects))
