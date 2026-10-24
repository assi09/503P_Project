"""Validated log payloads, with explicit units and timezone-aware times."""

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from pydantic.alias_generators import to_camel

from app.agent.sanitize import clean, reads_like_instruction

Number = Annotated[float, Field(ge=0, le=100000, strict=True)]


class LogModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        allow_inf_nan=False,
    )


class FoodLog(LogModel):
    kind: Literal["food"] = "food"
    food_name: str = Field(min_length=1, max_length=160)
    consumed_at: AwareDatetime
    meal_type: Literal["BREAKFAST", "LUNCH", "DINNER", "SNACK"]
    energy_kcal: Number | None = None
    protein_g: Number | None = None
    carbohydrate_g: Number | None = None
    fat_g: Number | None = None
    # This first tool accepts supplied values only. Estimates need a separate provenance path.
    provenance: Literal["user_entered"] = "user_entered"

    @model_validator(mode="after")
    def valid_food(self) -> Self:
        name = clean(self.food_name, 160)
        if not name or reads_like_instruction(name):
            raise ValueError("Use a food name, without instructions.")
        self.food_name = name
        if all(
            v is None for v in (self.energy_kcal, self.protein_g, self.carbohydrate_g, self.fat_g)
        ):
            raise ValueError("Supply at least one energy or macronutrient value.")
        return self

    def google_payload(self) -> dict:
        log = {
            "foodDisplayName": self.food_name,
            "interval": interval(self.consumed_at, self.consumed_at + timedelta(seconds=1)),
            "mealType": self.meal_type,
            "serving": {"amount": 1.0},
        }
        for field, value, unit in (
            ("energy", self.energy_kcal, "kcal"),
            ("totalCarbohydrate", self.carbohydrate_g, "grams"),
            ("totalFat", self.fat_g, "grams"),
        ):
            if value is not None:
                log[field] = {unit: value}
        if self.protein_g is not None:
            log["nutrients"] = [{"nutrient": "PROTEIN", "quantity": {"grams": self.protein_g}}]
        return {"nutritionLog": log}


class WorkoutLog(LogModel):
    kind: Literal["workout"] = "workout"
    exercise_type: Literal["RUNNING", "WALKING", "BIKING", "AEROBIC_WORKOUT"]
    start_time: AwareDatetime
    end_time: AwareDatetime
    active_seconds: Annotated[int, Field(gt=0, strict=True)]
    distance_km: Annotated[float, Field(ge=0, strict=True)] | None = None
    provenance: Literal["user_entered"] = "user_entered"

    @model_validator(mode="after")
    def ordered(self) -> Self:
        elapsed = (self.end_time - self.start_time).total_seconds()
        if elapsed <= 0 or self.active_seconds > elapsed:
            raise ValueError("Active time must fit within the workout interval.")
        return self

    def google_payload(self) -> dict:
        exercise = {
            "exerciseType": self.exercise_type,
            "interval": interval(self.start_time, self.end_time),
            "activeDuration": f"{self.active_seconds:g}s",
        }
        if self.distance_km is not None:
            exercise["metricsSummary"] = {"distanceMillimeters": self.distance_km * 1_000_000}
        # No fabricated HR, steps or calories, and no telemetry writes that duplicate device data.
        return {"exercise": exercise}


def interval(start: datetime, end: datetime) -> dict:
    return {
        "startTime": start.isoformat(),
        "endTime": end.isoformat(),
        "startUtcOffset": f"{start.utcoffset().total_seconds():g}s",
        "endUtcOffset": f"{end.utcoffset().total_seconds():g}s",
    }


Log = Annotated[FoodLog | WorkoutLog, Field(discriminator="kind")]
LOG = TypeAdapter(Log)
DATA_TYPES = {"food": "nutrition-log", "workout": "exercise"}
WRITE_SCOPES = {
    "food": "https://www.googleapis.com/auth/googlehealth.nutrition.writeonly",
    "workout": "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.writeonly",
}
