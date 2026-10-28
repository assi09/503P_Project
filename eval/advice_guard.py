"""How many medical sentences the word check and the Jev guard catch, and how many coaching and
pattern sentences (which must pass) they wrongly flag. Run from the repository root:
`PYTHONPATH=backend python eval/advice_guard.py`. Calls Jev (about $0.0003); prints aggregates and
the sentences each check got wrong."""

import json
from pathlib import Path

from app.agent.guard import MAX_TEXTS, JevGuard
from app.agent.jev import JevClient
from app.agent.verifier import MEDICAL
from app.config import settings

data = json.loads((Path(__file__).parent / "advice_sentences.json").read_text())
labeled = (
    [(t, True) for t in data["medical"]]
    + [(t, False) for t in data["coaching"]]
    + [(t, False) for t in data["pattern"]]
)

guard = JevGuard(JevClient.from_settings(settings))
jev_flags, cost = [], 0.0
for i in range(0, len(labeled), MAX_TEXTS):
    batch = [t for t, _ in labeled[i : i + MAX_TEXTS]]
    judgement = guard.judge(batch)
    jev_flags += judgement.flagged
    cost += judgement.cost_usd

checks = {"word check": [bool(MEDICAL.search(t)) for t, _ in labeled], "Jev guard": jev_flags}
checks["both"] = [w or j for w, j in zip(checks["word check"], jev_flags, strict=True)]
medical, sound = len(data["medical"]), len(data["coaching"]) + len(data["pattern"])
for name, flags in checks.items():
    caught = sum(f for f, (_, bad) in zip(flags, labeled, strict=True) if bad)
    wrong = sum(f for f, (_, bad) in zip(flags, labeled, strict=True) if not bad)
    print(f"{name}: caught {caught}/{medical} medical, wrongly flagged {wrong}/{sound} sound")
    for flag, (text, bad) in zip(flags, labeled, strict=True):
        if flag != bad:
            print(f"   {'missed' if bad else 'false alarm'}: {text}")
print(f"Jev cost: ${cost:.6f}")
