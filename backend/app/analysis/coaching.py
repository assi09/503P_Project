"""Which everyday habits this person's own data supports, for coaching (`habit_options`).

The agent may suggest only levers from this fixed, non-medical list, and only when the person's
own data supports them: the model words a suggestion but never invents one. Each lever is a
comparison of the target metric between two groups of the person's own days (earlier against later
bedtimes, regular against irregular ones, the morning after a hard day against other mornings,
more against less active days, days without a late meal or a stressful day against days with
one). The tests are corrected together for their number (Benjamini-Hochberg), so a lever is
"supported" only when the difference holds up after asking several questions at once, and goes the
helpful way.
"""

from dataclasses import dataclass

import pandas as pd

from app.analysis.evidence import Evidence, ToolError, Window
from app.analysis.habits import BETTER, HARD_QUANTILE, TAG_PREFIX
from app.analysis.report import clock
from app.analysis.screen import benjamini_hochberg
from app.analysis.tools import _round, _two_sample, _values

ALPHA = 0.05
MIN_GROUP = 5
REGULAR_MINUTES = 30
SLEEP = ("sleep_minutes", "sleep_efficiency", "deep_sleep_minutes", "awake_in_bed_minutes")
MORNING = ("recovery_score", "hrv_ms", "resting_hr", "stress_score")


@dataclass(frozen=True)
class _Test:
    lever: str
    label: str  # the habit, in plain words
    better_group: str  # the days the habit describes
    other_group: str
    better: pd.Series
    other: pd.Series


def _split(values: pd.Series, mask: pd.Series) -> tuple[pd.Series, pd.Series]:
    mask = mask.reindex(values.index).fillna(False).astype(bool)
    return values[mask], values[~mask]


def _tests(frame: pd.DataFrame, metric: str, values: pd.Series) -> tuple[list[_Test], float | None]:
    tests: list[_Test] = []
    split_at = None
    if "bedtime_hour" in frame.columns and metric != "bedtime_hour" and metric in SLEEP + MORNING:
        bed = frame["bedtime_hour"].reindex(values.index)
        if bed.notna().sum() >= 2 * MIN_GROUP:
            split_at = float(bed.median())
            early, late = _split(values, bed <= split_at)
            tests.append(
                _Test(
                    "earlier_bedtime",
                    f"being in bed by {clock(split_at)}",
                    f"nights in bed by {clock(split_at)}",
                    "later nights",
                    early,
                    late,
                )
            )
            regular, irregular = _split(values, (bed - split_at).abs() * 60 <= REGULAR_MINUTES)
            tests.append(
                _Test(
                    "regular_bedtime",
                    "a regular bedtime, within half an hour of your usual",
                    "nights near your usual bedtime",
                    "less regular nights",
                    regular,
                    irregular,
                )
            )
    if "strain" in frame.columns and metric in MORNING:
        strain = frame["strain"]
        hard_day = strain >= strain.quantile(HARD_QUANTILE)
        # The morning after: the target on day d against strain on day d - 1.
        after_hard = hard_day.shift(1).reindex(values.index)
        rest, hard = _split(values, after_hard == False)  # noqa: E712 (NaN is neither)
        hard = values[after_hard == True]  # noqa: E712
        tests.append(
            _Test(
                "rest_after_hard_day",
                "an easier day after your hardest training days",
                "mornings after an ordinary day",
                "mornings after a hard day",
                rest,
                hard,
            )
        )
    if "active_zone_minutes" in frame.columns and metric in SLEEP:
        azm = frame["active_zone_minutes"].reindex(values.index)
        if azm.notna().sum() >= 2 * MIN_GROUP:
            active, quiet = _split(values, azm >= azm.median())
            tests.append(
                _Test(
                    "active_days",
                    "more active days",
                    "your more active days",
                    "less active days",
                    active,
                    quiet,
                )
            )
    for tag, lever, label in (
        ("late_meal", "earlier_dinner", "an earlier dinner"),
        ("stress", "wind_down", "a wind-down routine on stressful days"),
    ):
        column = f"{TAG_PREFIX}{tag}"
        if column in frame.columns and metric in SLEEP + MORNING:
            flags = frame[column].reindex(values.index)
            without, with_tag = values[flags == 0], values[flags == 1]
            tests.append(
                _Test(
                    lever,
                    label,
                    f"days without {tag.replace('_', ' ')}",
                    "days with it",
                    without,
                    with_tag,
                )
            )
    return tests, split_at


def habit_options(frame: pd.DataFrame, metric: str, window: Window) -> Evidence:
    """The levers from the list that this person's data supports for improving `metric`."""
    if metric not in BETTER:
        raise ToolError(f"{metric} has no better direction to coach towards")
    values = _values(frame, metric, window)
    tests, split_at = _tests(frame, metric, values)
    usable = [t for t in tests if len(t.better) >= MIN_GROUP and len(t.other) >= MIN_GROUP]
    results = [(t, _two_sample(t.better, t.other)) for t in usable]
    q_values = benjamini_hochberg([r["p_value"] for _, r in results]) if results else []
    up = BETTER[metric] == "up"
    levers = []
    for (test, result), q in zip(results, q_values, strict=True):
        helpful = (result["difference"] > 0) == up and result["difference"] != 0
        levers.append(
            {
                "lever": test.lever,
                "habit": test.label,
                "supported": bool(q < ALPHA and helpful),
                "q_value": _round(q, 4),
                "group": test.better_group,
                "other_group": test.other_group,
                "mean_with": _round(test.better.mean(), 2),
                "mean_without": _round(test.other.mean(), 2),
                "difference": result["difference"],
                "n_with": len(test.better),
                "n_without": len(test.other),
            }
        )
    levers.sort(key=lambda lever: (not lever["supported"], lever["q_value"]))
    uses_bedtime = split_at is not None and any(
        lever["lever"] in ("earlier_bedtime", "regular_bedtime") for lever in levers
    )
    stats: dict = {"supported": any(lever["supported"] for lever in levers), "levers": levers}
    if uses_bedtime:
        stats["split_at"] = _round(split_at, 3)  # a clock time, so answers may quote it
    return Evidence(
        tool="habit_options",
        metrics=(metric, "bedtime_hour") if uses_bedtime else (metric,),
        windows=(window,),
        n=len(values),
        sufficient=bool(levers),
        stats=stats,
    )
