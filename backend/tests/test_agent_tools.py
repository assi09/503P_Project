import json
from datetime import date, timedelta

import pytest

from app.agent.llm import ToolCall
from app.agent.tools import TOOLS, Toolbox
from app.synthetic import Step, generate

START = date(2026, 1, 1)
SLEEP = ("sleep_minutes", "sleep_efficiency", "bedtime_hour")


@pytest.fixture
def frame():
    return generate(START, 60, (Step("sleep_minutes", START + timedelta(30), -45),), seed=1).frame


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(id="c1", name=name, arguments=arguments)


def day(offset: int) -> str:
    return (START + timedelta(offset)).isoformat()


def test_schemas_list_every_tool_with_the_allowed_metrics(frame):
    box = Toolbox(frame, SLEEP)
    schemas = {s["function"]["name"]: s["function"] for s in box.schemas()}
    assert set(schemas) == set(TOOLS)
    metric = schemas["trend"]["parameters"]["properties"]["metric"]
    assert metric["enum"] == sorted(SLEEP)
    correlate = schemas["correlate"]["parameters"]["properties"]
    assert correlate["driver"]["enum"] == correlate["target"]["enum"] == sorted(SLEEP)
    assert schemas["coverage"]["parameters"]["required"] == ["start", "end"]


def test_a_valid_call_returns_evidence_the_model_can_cite(frame):
    box = Toolbox(frame, SLEEP)
    result = box.run(
        call(
            "compare_windows",
            metric="sleep_minutes",
            recent_start=day(30),
            recent_end=day(59),
            baseline_start=day(0),
            baseline_end=day(29),
        )
    )
    assert result.error is None
    payload = json.loads(result.content)
    assert payload["evidence_id"] == result.evidence.id
    assert payload["stats"]["difference"] < -30
    assert box.evidence[result.evidence.id] is result.evidence


def test_change_point_is_available_to_the_agent(frame):
    result = Toolbox(frame, SLEEP).run(
        call("change_point", metric="sleep_minutes", start=day(0), end=day(59))
    )
    assert json.loads(result.content)["stats"]["change_date"] is not None


def test_metrics_outside_the_expert_are_refused(frame):
    result = Toolbox(frame, SLEEP).run(call("trend", metric="steps", start=day(0), end=day(59)))
    assert "not available here" in result.error
    assert "sleep_minutes" in result.error  # tells the model what it may use


def test_wear_time_stays_visible_for_coverage(frame):
    box = Toolbox(frame, SLEEP)
    assert "wear_minutes" not in box.metrics
    result = box.run(call("coverage", start=day(0), end=day(59)))
    assert "low_wear_days" in json.loads(result.content)["stats"]


@pytest.mark.parametrize(
    "name, arguments, message",
    [
        ("trend", {"metric": "sleep_minutes", "start": day(0)}, "end"),
        ("trend", {"metric": "sleep_minutes", "start": "yesterday", "end": day(5)}, "start"),
        ("trend", {"metric": "sleep_minutes", "start": day(0), "end": day(5), "x": 1}, "x"),
        (
            "correlate",
            {
                "driver": "bedtime_hour",
                "target": "sleep_minutes",
                "start": day(0),
                "end": day(59),
                "max_lag": 30,
            },
            "max_lag",
        ),
    ],
)
def test_invalid_arguments_are_explained(frame, name, arguments, message):
    result = Toolbox(frame, SLEEP).run(call(name, **arguments))
    assert result.error.startswith("Invalid arguments") and message in result.error
    assert result.evidence is None


def test_dates_outside_the_data_are_refused(frame):
    result = Toolbox(frame, SLEEP).run(
        call("trend", metric="sleep_minutes", start="2025-01-01", end=day(5))
    )
    assert "Dates must be between 2026-01-01 and 2026-03-01" in result.error


def test_analysis_errors_come_back_as_messages(frame):
    overlapping = call(
        "compare_windows",
        metric="sleep_minutes",
        recent_start=day(10),
        recent_end=day(40),
        baseline_start=day(0),
        baseline_end=day(20),
    )
    assert "overlap" in Toolbox(frame, SLEEP).run(overlapping).error
    reversed_window = call("trend", metric="sleep_minutes", start=day(20), end=day(10))
    assert "after its end" in Toolbox(frame, SLEEP).run(reversed_window).error


def test_unknown_tools_and_malformed_calls_are_errors(frame):
    box = Toolbox(frame, SLEEP, tools=["describe", "trend"])
    assert "Unknown tool 'change_point'" in box.run(call("change_point")).error
    broken = ToolCall(
        id="c1", name="trend", arguments=None, error="The arguments were not valid JSON."
    )
    assert box.run(broken).error == "The arguments were not valid JSON."
    assert box.evidence == {}


def test_toolbox_can_be_limited_to_some_tools(frame):
    box = Toolbox(frame, SLEEP, tools=["describe"])
    assert [s["function"]["name"] for s in box.schemas()] == ["describe"]
