"""Correcting a run's own tests together: the arithmetic, and the properties over many people."""

from datetime import date, timedelta

import pytest

from app.agent.agent import SUBMIT, answer
from app.agent.llm import Completion, ScriptedLLM, ToolCall, Usage
from app.agent.verifier import RUN_ADJUSTED, _significant, run_adjusted
from app.analysis import tools
from app.analysis.evidence import Evidence, Window
from app.analysis.screen import benjamini_hochberg
from app.synthetic import Coupling, Step, generate

START, DAYS, CHANGE = date(2026, 7, 1), 60, 45


def window(a: int, b: int) -> Window:
    return Window(start=START + timedelta(a), end=START + timedelta(b))


def make_test(p: float, tool: str = "compare_windows", **stats) -> Evidence:
    return Evidence(
        tool=tool,
        metrics=("sleep_minutes",),
        windows=(window(0, 9),),
        n=10,
        sufficient=True,
        stats={"p_value": p, **stats},
    )


def test_copies_keep_their_id_and_raw_p_and_record_the_adjustment():
    tests = [make_test(0.01), make_test(0.04), make_test(0.5)]
    adjusted = run_adjusted(tests)
    assert [e.id for e in adjusted] == [e.id for e in tests]
    assert [e.stats["p_value"] for e in adjusted] == [0.01, 0.04, 0.5]
    assert [e.stats[RUN_ADJUSTED] for e in adjusted] == pytest.approx(
        benjamini_hochberg([0.01, 0.04, 0.5])
    )
    assert all(e.stats["tests_in_run"] == 3 for e in adjusted)
    assert _significant(adjusted[0]) and not _significant(adjusted[1])  # 0.04 alone would pass


def test_a_correlation_is_adjusted_from_its_lag_corrected_p():
    corr = make_test(0.01, tool="correlate", p_value_adjusted=0.03)
    adjusted = run_adjusted([corr, make_test(0.5)])
    assert adjusted[0].stats[RUN_ADJUSTED] == pytest.approx(0.06)


def test_evidence_that_is_not_a_test_is_left_alone():
    described = Evidence(
        tool="describe",
        metrics=("steps",),
        windows=(window(0, 9),),
        n=10,
        sufficient=True,
        stats={"mean": 9000.0},
    )
    assert run_adjusted([described]) == [described]


def battery(frame) -> list[Evidence]:
    """What an agent asked about sleep typically tests (change points left out for speed)."""
    recent, baseline, whole = window(CHANGE, DAYS - 1), window(0, CHANGE - 1), window(0, DAYS - 1)
    metrics = (
        "sleep_minutes",
        "bedtime_hour",
        "time_in_bed",
        "sleep_efficiency",
        "deep_sleep_minutes",
        "awake_in_bed_minutes",
    )
    found = [tools.compare_windows(frame, m, recent, baseline) for m in metrics]
    for driver in (
        "bedtime_hour",
        "steps",
        "active_zone_minutes",
        "resting_hr",
        "very_active_minutes",
    ):
        found.append(tools.correlate(frame, driver, "sleep_minutes", whole, 2))
    found += [tools.weekday_split(frame, m, whole) for m in ("sleep_minutes", "bedtime_hour")]
    return found


def test_runs_on_people_where_nothing_changed_rarely_report_anything():
    seeds = range(60)
    raw = adjusted = 0
    for seed in seeds:
        tests = battery(generate(START, DAYS, seed=2000 + seed).frame)
        raw += any(_significant(e) for e in tests)
        adjusted += any(_significant(e) for e in run_adjusted(tests))
    assert raw / len(seeds) > 0.3  # without the correction, most runs found something
    assert adjusted / len(seeds) <= 0.15  # with it, near the 5% aimed for


def test_planted_changes_are_still_found():
    planted = (
        Step("bedtime_hour", START + timedelta(CHANGE), 1.0),
        Coupling("bedtime_hour", "sleep_minutes", lag_days=0, strength=-0.6),
        Step("sleep_minutes", START + timedelta(CHANGE), -30),
    )
    seeds = range(40)
    hits = 0
    for seed in seeds:
        tests = run_adjusted(battery(generate(START, DAYS, planted, seed=seed).frame))
        hits += any(_significant(e) and e.metrics == ("sleep_minutes",) for e in tests)
    assert hits / len(seeds) >= 0.85


def test_a_run_judges_its_own_tests_together_and_cites_the_adjusted_evidence():
    frame = generate(START, DAYS, seed=7).frame

    def submit(messages):
        import json

        ids = [
            json.loads(m["content"])["evidence_id"]
            for m in messages
            if m["role"] == "tool" and "evidence_id" in m["content"]
        ]
        claim = {
            "text": "Your time asleep held steady.",
            "kind": "no_change",
            "evidence_ids": ids[:1],
            "metric": "sleep_minutes",
        }
        call = ToolCall("s", SUBMIT, {"summary": "Steady.", "claims": [claim]})
        return Completion(None, (call,), "scripted", Usage(), 0.0, 0.0)

    compare = {
        "recent_start": str(START + timedelta(CHANGE)),
        "recent_end": str(START + timedelta(59)),
        "baseline_start": str(START),
        "baseline_end": str(START + timedelta(CHANGE - 1)),
    }
    llm = ScriptedLLM(
        [
            ScriptedLLM.call("compare_windows", "a", metric="sleep_minutes", **compare),
            ScriptedLLM.call("compare_windows", "b", metric="steps", **compare),
            ScriptedLLM.call(
                "describe", "c", metric="steps", start=str(START), end=str(START + timedelta(59))
            ),
            submit,
        ]
    )
    result = answer(llm, frame, "How is my sleep?")
    cited = next(iter(result.cited_evidence.values()))
    assert cited.stats["tests_in_run"] == 2  # two tests; the description is not one
    assert RUN_ADJUSTED in cited.stats


def test_a_change_lost_only_to_the_correction_says_how_to_confirm_it():
    from app.agent.verifier import Claim, check_claim

    point = make_test(0.04, tool="change_point", difference=-30.0, change_date="2026-08-15")
    adjusted = run_adjusted([point, make_test(0.5), make_test(0.6)])[0]
    claim = Claim(
        text="Your time asleep went down.",
        kind="change",
        evidence_ids=[adjusted.id],
        metric="sleep_minutes",
        direction="down",
    )
    reasons = " ".join(check_claim(claim, {adjusted.id: adjusted}))
    assert "after correcting for the 3 tests" in reasons and "compare_windows" in reasons
    weak = run_adjusted([make_test(0.2, tool="change_point", difference=-5.0)])[0]
    weak_claim = claim.model_copy(update={"evidence_ids": [weak.id]})
    assert "compare_windows" not in " ".join(check_claim(weak_claim, {weak.id: weak}))
