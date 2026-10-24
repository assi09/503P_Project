"""Agent proposal tools: server-bound owner and request key, and no execution capability."""

import json
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.actions import store
from app.actions.schemas import FoodLog, WorkoutLog
from app.agent.agent import ExtraTool
from app.api.errors import ApiError


def proposal_tools(
    sessions: Callable[[], AbstractContextManager[Session]],
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    now: datetime,
    prepared: list[str],
) -> dict[str, list[ExtraTool]]:
    def tool(model: type[FoodLog] | type[WorkoutLog], expert: str) -> ExtraTool:
        schema = model.model_json_schema(by_alias=True)
        schema.pop("title", None)

        def run(arguments: dict | None) -> tuple[str, dict]:
            try:
                log = model.model_validate(arguments or {})
                payload = log.model_dump(mode="json", by_alias=True, exclude_none=True)
                # Repeated identical calls in this question prepare one draft, across restarts.
                key = uuid.uuid5(question_id, payload["kind"])
                with sessions() as db:
                    row = store.propose(db, user_id, key, payload, now)
                    content = {
                        "draft_id": str(row.id),
                        "version": row.version,
                        "status": row.status,
                        "log": row.payload,
                        "note": "Draft only; review and confirm before sending to Google.",
                    }
            except ValidationError as exc:
                # Field names are safe, unlike Pydantic's input-bearing error strings.
                fields = sorted(
                    {str(e["loc"][0]) for e in exc.errors(include_input=False) if e["loc"]}
                )
                content = {
                    "error": "Ask for valid values for the required log fields.",
                    "fields": fields,
                }
                return json.dumps(content), {"error": "invalid_log"}
            except ApiError:
                return json.dumps({"error": "The draft could not be prepared."}), {
                    "error": "invalid_log"
                }
            except Exception:
                # SQL/transport exceptions may contain the log payload; never send or log them.
                return json.dumps(
                    {"error": "Could not save the draft. Check saved entries before retrying."}
                ), {"error": "draft_storage"}
            if content["draft_id"] not in prepared:
                prepared.append(content["draft_id"])
            return json.dumps(content), {k: content[k] for k in ("draft_id", "version", "status")}

        return ExtraTool(
            f"propose_{'food' if expert == 'nutrition' else 'workout'}_log",
            "Prepare one draft per message, using supplied values. Ask for missing fields "
            "first, including timezone-aware times. Never estimate nutrients, invent measurements "
            "or claim it was logged. This tool cannot confirm, execute or delete a Google record.",
            schema,
            run,
        )

    return {"nutrition": [tool(FoodLog, "nutrition")], "activity": [tool(WorkoutLog, "activity")]}
