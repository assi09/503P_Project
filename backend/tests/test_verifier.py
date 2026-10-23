from datetime import date, timedelta

import pytest

from app.agent.verifier import Claim, check_claim, verify
from app.analysis.evidence import Window
from app.analysis.tools import change_point, compare_windows, correlate, coverage, describe
from app.synthetic import Coupling, Step, generate

START = date(2026, 7, 1)
CHANGE_DAY = START + timedelta(30)


def window(first: int, last: int) -> Window:
    return Window(start=START + timedelta(first), end=START + timedelta(last))


@pytest.fixture(scope="module")
def evidence():
    """A person whose sleep dropped (about 90 minutes) when their bedtime moved an hour later."""
    effects = (
        Step("bedtime_hour", CHANGE_DAY, 1.0),
        Coupling("bedtime_hour", "sleep_minutes", lag_days=0, strength=-0.9),
        Step("sleep_minutes", CHANGE_DAY, -45),
    )
    frame = generate(START, 60, effects, seed=3).frame
    found = {
        "sleep": compare_windows(frame, "sleep_minutes", window(30, 59), window(0, 29)),
        "steps": compare_windows(frame, "steps", window(30, 59), window(0, 29)),
        "shift": change_point(frame, "sleep_minutes", window(0, 59)),
        "link": correlate(frame, "bedtime_hour", "sleep_minutes", window(0, 59)),
        "coverage": coverage(frame, window(0, 59)),
        "short": describe(frame, "sleep_minutes", window(0, 1)),
    }
    assert found["sleep"].stats["p_value"] < 0.001 and found["steps"].stats["p_value"] > 0.05
    return found


def by_id(evidence) -> dict:
    return {e.id: e for e in evidence.values()}


def claim(text, kind="change", ids=("sleep",), metric="sleep_minutes", direction="down", ev=None):
    return Claim(
        text=text,
        kind=kind,
        evidence_ids=[ev[i].id for i in ids] if ev else list(ids),
        metric=metric,
        direction=direction,
    )


def reasons(evidence, text, **kwargs):
    return check_claim(claim(text, ev=evidence, **kwargs), by_id(evidence))


def test_a_supported_change_with_quoted_numbers_passes(evidence):
    stats = evidence["sleep"].stats
    text = (
        f"Your sleep fell by about {abs(stats['difference']):.0f} minutes a night, from "
        f"{stats['mean_baseline'] / 60:.1f} to {stats['mean_recent'] / 60:.1f} hours."
    )
    assert reasons(evidence, text) == []


def test_the_change_must_point_the_stated_way(evidence):
    assert "does not point up" in " ".join(reasons(evidence, "Sleep went up.", direction="up"))


def test_wording_must_not_contradict_the_direction(evidence):
    found = reasons(evidence, "Your sleep increased lately.", direction="down")
    assert "wording contradicts" in " ".join(found)


def test_a_change_must_be_significant(evidence):
    found = reasons(evidence, "Your steps dropped.", ids=("steps",), metric="steps")
    assert "not significant" in " ".join(found) or "significant at" in " ".join(found)


def test_change_claims_need_a_direction(evidence):
    assert "state its direction" in " ".join(reasons(evidence, "Sleep changed.", direction=None))


def test_made_up_numbers_are_rejected(evidence):
    found = reasons(evidence, "Your sleep fell by 150 minutes.")
    assert "numbers not found" in " ".join(found) and "150" in " ".join(found)


def test_missing_and_thin_evidence_is_rejected(evidence):
    unknown = Claim(
        text="Sleep fell.",
        kind="change",
        evidence_ids=["nope"],
        metric="sleep_minutes",
        direction="down",
    )
    assert "does not exist" in check_claim(unknown, by_id(evidence))[0]
    found = reasons(evidence, "Sleep fell.", ids=("sleep", "short"))
    assert "too little data" in " ".join(found)


def test_the_change_date_and_dates_inside_the_windows_may_be_quoted(evidence):
    change = evidence["shift"].stats["change_date"]
    day = date.fromisoformat(change)
    text = f"Your sleep dropped from {day:%b} {day.day} onward ({change})."
    assert reasons(evidence, text, ids=("shift",)) == []


def test_dates_outside_the_evidence_are_rejected(evidence):
    found = reasons(evidence, "Your sleep dropped after Dec 25.", ids=("shift",))
    assert "dates outside" in " ".join(found)


def test_associations_need_a_significant_correlation_in_the_right_direction(evidence):
    ok = reasons(
        evidence,
        "Nights with a later bedtime had less sleep.",
        kind="association",
        ids=("link",),
        direction="down",
    )
    assert ok == []
    wrong = reasons(
        evidence,
        "Later bedtimes went with more sleep.",
        kind="association",
        ids=("link",),
        direction="up",
    )
    assert "does not point up" in " ".join(wrong)
    not_a_correlation = reasons(
        evidence, "Bedtime and sleep move together.", kind="association", ids=("sleep",)
    )
    assert "association evidence" in " ".join(not_a_correlation)


@pytest.mark.parametrize(
    "text, reason",
    [
        ("Your sleep dropped because of your later bedtime.", "states causation"),
        ("Your sleep dropped, which may be insomnia.", "medical language"),
        ("Your sleep dropped while you ran a calorie deficit.", "calorie balance"),
    ],
)
def test_forbidden_wording_is_rejected(evidence, text, reason):
    assert reason in " ".join(reasons(evidence, text))


def test_no_change_claims_must_match_the_evidence(evidence):
    ok = reasons(
        evidence,
        "Your steps did not change.",
        kind="no_change",
        ids=("steps",),
        metric="steps",
        direction=None,
    )
    assert ok == []
    wrong = reasons(evidence, "Your sleep stayed the same.", kind="no_change", direction=None)
    assert "shows a significant one" in " ".join(wrong)


def test_data_quality_claims_cite_coverage(evidence):
    assert (
        reasons(
            evidence,
            "Some days had little wear.",
            kind="data_quality",
            ids=("coverage",),
            metric=None,
            direction=None,
        )
        == []
    )
    found = reasons(
        evidence,
        "Some days had little wear.",
        kind="data_quality",
        ids=("sleep",),
        metric=None,
        direction=None,
    )
    assert "coverage evidence" in " ".join(found)


def test_claims_must_be_about_the_cited_metric(evidence):
    found = reasons(evidence, "Steps fell.", metric="steps")
    assert "none of the cited evidence is about steps" in " ".join(found)


def test_verify_separates_accepted_and_rejected_claims(evidence):
    good = claim("Your sleep fell.", ev=evidence)
    bad = claim("Your sleep fell by 150 minutes.", ev=evidence)
    verdict = verify([good, bad], by_id(evidence))
    assert verdict.accepted == (good,)
    assert verdict.rejected[0].claim == bad and verdict.rejected[0].reasons


def test_durations_in_hours_and_minutes_are_checked(evidence):
    from app.agent.present import duration

    stats = evidence["sleep"].stats
    recent, drop = duration(stats["mean_recent"]), duration(stats["difference"])
    good = f"You slept {recent} on average, down {drop}."
    assert reasons(evidence, good) == []
    assert "durations not found" in " ".join(
        reasons(evidence, "You slept 3 h 5 min on average, down.")
    )


@pytest.fixture(scope="module")
def bedtime():
    frame = generate(START, 60, (Step("bedtime_hour", CHANGE_DAY, 1.0),), seed=3).frame
    return compare_windows(frame, "bedtime_hour", window(30, 59), window(0, 29))


def test_clock_times_must_match_the_evidence(bedtime):
    from app.agent.present import clock

    stats = bedtime.stats
    ok = Claim(
        text=f"Your bedtime moved later, from about {clock(stats['mean_baseline'])} to "
        f"{clock(stats['mean_recent'])}.",
        kind="change",
        evidence_ids=[bedtime.id],
        metric="bedtime_hour",
        direction="up",
    )
    assert check_claim(ok, {bedtime.id: bedtime}) == []
    invented = ok.model_copy(update={"text": "Your bedtime moved later, to about 3:15 am."})
    assert "times of day" in " ".join(check_claim(invented, {bedtime.id: bedtime}))


def test_internal_metric_names_are_rejected(evidence):
    found = reasons(evidence, "Your sleep_minutes went down.")
    assert "internal metric names (sleep_minutes)" in " ".join(found)


def test_evidence_ids_in_the_text_get_their_own_reason(evidence):
    from app.agent.verifier import text_problems

    cited = list(evidence.values())
    found = text_problems(f"Your sleep got shorter (evidence {cited[0].id}).", cited)
    assert found == ["writes evidence ids in the text; list them only in evidence_ids"]
    assert text_problems("Your sleep got shorter (evidence deadbeefcafe).", cited) == []


def test_text_problems_check_any_text_against_evidence(evidence):
    from app.agent.verifier import text_problems

    cited = list(evidence.values())
    assert text_problems("Your sleep got shorter while bedtime moved later.", cited) == []
    assert text_problems("You slept 2 h less, due to stress.", cited)
