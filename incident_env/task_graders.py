from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from incident_env.graders import clamp_task_score, grade_state
from incident_env.models import IncidentObservation, IncidentScenario, IncidentState
from incident_env.tasks.scenarios import INCIDENT_SCENARIOS


SCENARIO_BY_ID = {scenario.incident_id: scenario for scenario in INCIDENT_SCENARIOS}


def _clamp_score(value: float) -> float:
    return clamp_task_score(value)


def _scenario_from_payload(
    state: IncidentState | None = None,
    observation: IncidentObservation | None = None,
    incident_id: str | None = None,
) -> IncidentScenario | None:
    if incident_id:
        return SCENARIO_BY_ID.get(incident_id)
    if state is not None:
        return SCENARIO_BY_ID.get(state.incident_id)
    if observation is not None:
        return SCENARIO_BY_ID.get(observation.incident_id)
    return None


def _state_from_kwargs(**kwargs: Any) -> IncidentState | None:
    candidates = (
        kwargs.get("state"),
        kwargs.get("env_state"),
        kwargs.get("final_state"),
    )
    for candidate in candidates:
        if isinstance(candidate, IncidentState):
            return candidate
        if isinstance(candidate, dict):
            try:
                return IncidentState.model_validate(candidate)
            except Exception:
                continue
    return None


def _observation_from_kwargs(**kwargs: Any) -> IncidentObservation | None:
    candidates = (
        kwargs.get("observation"),
        kwargs.get("final_observation"),
        kwargs.get("result"),
    )
    for candidate in candidates:
        if isinstance(candidate, IncidentObservation):
            return candidate
        if isinstance(candidate, dict):
            if "observation" in candidate and isinstance(candidate["observation"], dict):
                candidate = candidate["observation"]
            try:
                return IncidentObservation.model_validate(candidate)
            except Exception:
                continue
    return None


@dataclass
class BaseIncidentGrader:
    task_id: str

    def grade(self, **kwargs: Any) -> float:
        state = _state_from_kwargs(**kwargs)
        observation = _observation_from_kwargs(**kwargs)

        if state is not None:
            scenario = _scenario_from_payload(state=state)
            if scenario is None:
                return 0.0
            return _clamp_score(grade_state(state, scenario))

        if observation is not None:
            return _clamp_score(observation.reward_breakdown.final_score)

        score = kwargs.get("score")
        if isinstance(score, (int, float)):
            return _clamp_score(float(score))

        return 0.0

    def __call__(self, **kwargs: Any) -> float:
        return self.grade(**kwargs)


class EasyGrader(BaseIncidentGrader):
    def __init__(self) -> None:
        super().__init__(task_id="easy_triage")


class MediumGrader(BaseIncidentGrader):
    def __init__(self) -> None:
        super().__init__(task_id="medium_coordination")


class HardGrader(BaseIncidentGrader):
    def __init__(self) -> None:
        super().__init__(task_id="hard_conflict")
