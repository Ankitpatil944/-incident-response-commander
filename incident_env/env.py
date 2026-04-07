from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import uuid4

from incident_env.graders import grade_state, score_status_update
from incident_env.models import (
    ActionType,
    IncidentAction,
    IncidentObservation,
    IncidentScenario,
    IncidentState,
    RewardBreakdown,
)
from incident_env.tasks.catalog import TASK_ORDER, get_scenarios_for_task, get_task_spec


class IncidentCommanderEnv:
    def __init__(self, max_steps: int | None = None):
        self._task_counters: dict[str, int] = defaultdict(int)
        self._scenario: IncidentScenario | None = None
        self._state: IncidentState | None = None
        self._max_steps_override = max_steps

    def reset(self, task_name: str | None = None) -> IncidentObservation:
        task_name = task_name or TASK_ORDER[0]
        task_spec = get_task_spec(task_name)
        scenarios = get_scenarios_for_task(task_name)
        if not scenarios:
            raise RuntimeError(f"No scenarios configured for task {task_name}")

        idx = self._task_counters[task_name] % len(scenarios)
        self._task_counters[task_name] += 1
        self._scenario = scenarios[idx]
        max_steps = self._max_steps_override or task_spec.max_steps

        self._state = IncidentState(
            episode_id=str(uuid4()),
            task_name=task_name,
            difficulty=self._scenario.difficulty,
            incident_id=self._scenario.incident_id,
            title=self._scenario.title,
            step_count=0,
            max_steps=max_steps,
            done=False,
            alerts=list(self._scenario.alerts),
            logs=list(self._scenario.logs),
            service_map=list(self._scenario.service_map),
            timeline=list(self._scenario.timeline),
        )
        self._state.score = grade_state(self._state, self._scenario)
        return self._build_observation(reward=0.0, done=False)

    def step(self, action: IncidentAction) -> tuple[IncidentObservation, float, bool, dict[str, Any]]:
        state = self._require_state()
        scenario = self._require_scenario()
        if state.done:
            state.last_action_error = "Episode already completed"
            observation = self._build_observation(reward=0.0, done=True)
            return observation, 0.0, True, self._info()

        progress_reward = 0.0
        penalty = 0.0
        error: str | None = None

        state.step_count += 1

        if action.action_type == ActionType.CLASSIFY_SEVERITY:
            error, progress_reward, penalty = self._handle_severity(action, scenario)
        elif action.action_type == ActionType.ASSIGN_TEAM:
            error, progress_reward, penalty = self._handle_team(action, scenario)
        elif action.action_type == ActionType.SET_ESCALATION:
            error, progress_reward, penalty = self._handle_escalation(action, scenario)
        elif action.action_type == ActionType.PUBLISH_STATUS:
            error, progress_reward, penalty = self._handle_status(action, scenario)
        else:
            error = f"Unsupported action type: {action.action_type}"
            penalty = 0.05

        state.last_action_error = error
        state.penalty_total = round(min(1.0, state.penalty_total + penalty), 2)
        step_reward = round(min(1.0, max(0.0, progress_reward - penalty)), 2)
        state.cumulative_reward = round(min(1.0, state.cumulative_reward + step_reward), 2)
        state.done = self._is_episode_complete()
        if state.step_count >= state.max_steps:
            state.done = True
        state.score = grade_state(state, scenario)

        observation = self._build_observation(reward=step_reward, done=state.done)
        return observation, step_reward, state.done, self._info()

    def state(self) -> IncidentState:
        return self._require_state().model_copy(deep=True)

    def close(self) -> None:
        return None

    def _handle_severity(
        self, action: IncidentAction, scenario: IncidentScenario
    ) -> tuple[str | None, float, float]:
        state = self._require_state()
        if action.severity is None:
            return "severity is required", 0.0, 0.05
        if state.selected_severity == action.severity:
            return "Repeated severity decision", 0.0, 0.03
        if state.severity_score_awarded == 0.3 and state.selected_severity is not None:
            return "Severity already correctly resolved", 0.0, 0.01

        state.selected_severity = action.severity
        state.severity_submitted = True
        if action.severity == scenario.correct_severity and state.severity_score_awarded < 0.3:
            state.severity_score_awarded = 0.3
            return None, 0.3, 0.0
        return None, 0.0, 0.1

    def _handle_team(self, action: IncidentAction, scenario: IncidentScenario) -> tuple[str | None, float, float]:
        state = self._require_state()
        if action.team is None:
            return "team is required", 0.0, 0.05
        if state.selected_team == action.team:
            return "Repeated team decision", 0.0, 0.03
        if state.team_score_awarded == 0.3 and state.selected_team is not None:
            return "Team already correctly resolved", 0.0, 0.01

        state.selected_team = action.team
        state.team_submitted = True
        penalty = 0.0
        if state.severity_submitted and state.selected_severity != scenario.correct_severity:
            penalty += 0.05
        if action.team == scenario.correct_team and state.team_score_awarded < 0.3:
            state.team_score_awarded = 0.3
            return None, 0.3, round(penalty, 2)
        penalty += 0.05
        return None, 0.0, round(penalty, 2)

    def _handle_escalation(
        self, action: IncidentAction, scenario: IncidentScenario
    ) -> tuple[str | None, float, float]:
        state = self._require_state()
        if action.escalate is None:
            return "escalate is required", 0.0, 0.05
        if state.escalation_decision == action.escalate and state.escalation_submitted:
            return "Repeated escalation decision", 0.0, 0.03
        if state.escalation_score_awarded == 0.2 and state.escalation_submitted:
            return "Escalation already correctly resolved", 0.0, 0.01

        state.escalation_decision = action.escalate
        state.escalation_submitted = True
        penalty = 0.0
        if state.severity_submitted and state.selected_severity != scenario.correct_severity:
            penalty += 0.02
        if action.escalate == scenario.escalation_required and state.escalation_score_awarded < 0.2:
            state.escalation_score_awarded = 0.2
            return None, 0.2, round(penalty, 2)
        penalty += 0.03
        return None, 0.0, round(penalty, 2)

    def _handle_status(
        self, action: IncidentAction, scenario: IncidentScenario
    ) -> tuple[str | None, float, float]:
        state = self._require_state()
        if action.status_update is None:
            return "status_update is required", 0.0, 0.05

        penalty = 0.0
        if not state.severity_submitted and not state.team_submitted:
            penalty += 0.02

        previous_score = state.communication_score_awarded
        current_score = score_status_update(
            action.status_update,
            scenario,
            state.selected_team.value if state.selected_team is not None else None,
            severity_correct=state.selected_severity == scenario.correct_severity,
            team_correct=state.selected_team == scenario.correct_team,
        )
        if state.severity_submitted and state.selected_severity != scenario.correct_severity:
            penalty += 0.03
        if state.team_submitted and state.selected_team != scenario.correct_team:
            penalty += 0.05
        if state.status_submitted and current_score <= previous_score:
            penalty += 0.03

        state.status_update = action.status_update
        state.status_submitted = True
        state.communication_score_awarded = max(previous_score, current_score)
        progress_reward = round(max(0.0, state.communication_score_awarded - previous_score), 2)
        return None, progress_reward, round(penalty, 2)

    def _is_episode_complete(self) -> bool:
        state = self._require_state()
        return (
            state.severity_score_awarded >= 0.3
            and state.team_score_awarded >= 0.3
            and state.escalation_score_awarded >= 0.2
            and state.communication_score_awarded >= 0.2
        )

    def _reward_breakdown(self) -> RewardBreakdown:
        state = self._require_state()
        return RewardBreakdown(
            severity_score=state.severity_score_awarded,
            team_score=state.team_score_awarded,
            escalation_score=state.escalation_score_awarded,
            communication_score=state.communication_score_awarded,
            penalty_total=state.penalty_total,
            final_score=state.score,
        )

    def _build_observation(self, reward: float, done: bool) -> IncidentObservation:
        state = self._require_state()
        scenario = self._require_scenario()
        return IncidentObservation(
            incident_id=scenario.incident_id,
            title=scenario.title,
            task_name=state.task_name,
            difficulty=scenario.difficulty,
            alerts=list(scenario.alerts),
            logs=list(scenario.logs),
            service_map=list(scenario.service_map),
            timeline=list(scenario.timeline),
            severity_done=state.severity_submitted,
            team_done=state.team_submitted,
            escalation_done=state.escalation_submitted,
            status_done=state.status_submitted,
            selected_severity=state.selected_severity,
            selected_team=state.selected_team,
            escalation_decision=state.escalation_decision,
            status_update=state.status_update,
            allowed_actions=list(ActionType),
            last_action_error=state.last_action_error,
            reward_breakdown=self._reward_breakdown(),
            steps_remaining=max(0, state.max_steps - state.step_count),
            reward=reward,
            done=done,
        )

    def _info(self) -> dict[str, Any]:
        state = self._require_state()
        return {
            "task_name": state.task_name,
            "incident_id": state.incident_id,
            "score": state.score,
            "penalty_total": state.penalty_total,
            "completed_progress": {
                "severity": state.severity_score_awarded > 0.0,
                "team": state.team_score_awarded > 0.0,
                "escalation": state.escalation_score_awarded > 0.0,
                "communication": state.communication_score_awarded > 0.0,
            },
        }

    def _require_state(self) -> IncidentState:
        if self._state is None:
            raise RuntimeError("Call reset() before step() or state()")
        return self._state

    def _require_scenario(self) -> IncidentScenario:
        if self._scenario is None:
            raise RuntimeError("Scenario not loaded; call reset() first")
        return self._scenario
