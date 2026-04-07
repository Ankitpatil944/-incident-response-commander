from __future__ import annotations

from dataclasses import dataclass

from incident_env.models import DifficultyLevel
from incident_env.tasks.scenarios import INCIDENT_SCENARIOS


@dataclass(frozen=True)
class TaskSpec:
    name: str
    difficulty: DifficultyLevel
    description: str
    max_steps: int


TASK_ORDER = ["easy_triage", "medium_coordination", "hard_conflict"]

TASK_SPECS = {
    "easy_triage": TaskSpec(
        name="easy_triage",
        difficulty=DifficultyLevel.EASY,
        description="Clear-signal incidents with an obvious owner and severity.",
        max_steps=6,
    ),
    "medium_coordination": TaskSpec(
        name="medium_coordination",
        difficulty=DifficultyLevel.MEDIUM,
        description="Incidents with multiple alerts requiring owner and escalation reasoning.",
        max_steps=6,
    ),
    "hard_conflict": TaskSpec(
        name="hard_conflict",
        difficulty=DifficultyLevel.HARD,
        description="Conflicting signals that reward prioritization over alert chasing.",
        max_steps=6,
    ),
}


def get_task_spec(task_name: str) -> TaskSpec:
    if task_name not in TASK_SPECS:
        raise KeyError(f"Unknown task: {task_name}")
    return TASK_SPECS[task_name]


def get_scenarios_for_task(task_name: str):
    task = get_task_spec(task_name)
    return [scenario for scenario in INCIDENT_SCENARIOS if scenario.difficulty == task.difficulty]

