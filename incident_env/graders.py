from __future__ import annotations

from incident_env.models import IncidentScenario, IncidentState, IncidentStatusUpdate


def clamp_task_score(value: float) -> float:
    return round(max(0.01, min(0.99, value)), 2)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _contains_any(text: str, keywords: list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(keyword.lower() in normalized for keyword in keywords)


def _is_distinct(text: str, other_text: str) -> bool:
    return _normalize_text(text) != _normalize_text(other_text)


def _is_low_impact_scenario(scenario: IncidentScenario) -> bool:
    low_impact_markers = [
        "no customer impact",
        "minimal customer impact",
        "internal visibility degraded",
        "service stable",
    ]
    return any(_contains_any(keyword, scenario.impact_keywords) for keyword in low_impact_markers)


def _has_impact_contradiction(status_update: IncidentStatusUpdate, scenario: IncidentScenario) -> bool:
    normalized = _normalize_text(status_update.customer_impact)
    low_impact_claims = ["no customer impact", "minimal customer impact", "healthy"]
    high_impact_claims = ["customers blocked", "outage", "unavailable", "requests failing", "major outage"]

    if _is_low_impact_scenario(scenario):
        return any(marker in normalized for marker in high_impact_claims)
    return any(marker in normalized for marker in low_impact_claims)


def score_status_update(
    status_update: IncidentStatusUpdate | None,
    scenario: IncidentScenario,
    selected_team: str | None,
    *,
    severity_correct: bool = True,
    team_correct: bool = True,
) -> float:
    if status_update is None:
        return 0.0

    score = 0.0
    if len(status_update.summary.strip()) >= 20 and _contains_any(status_update.summary, scenario.service_keywords):
        score += 0.05
    if (
        len(status_update.customer_impact.strip()) >= 20
        and _contains_any(status_update.customer_impact, scenario.impact_keywords)
        and _is_distinct(status_update.customer_impact, status_update.summary)
    ):
        score += 0.05
    if (
        len(status_update.next_action.strip()) >= 15
        and _contains_any(status_update.next_action, scenario.response_keywords)
        and _is_distinct(status_update.next_action, status_update.summary)
    ):
        score += 0.05

    owner = _normalize_text(status_update.owner)
    allowed_owner_markers = {scenario.correct_team.value}
    if selected_team:
        allowed_owner_markers.add(selected_team.lower())
    if any(marker in owner for marker in allowed_owner_markers):
        score += 0.05

    status_blob = _normalize_text(
        " ".join(
            [
                status_update.summary,
                status_update.customer_impact,
                status_update.next_action,
                status_update.owner,
            ]
        )
    )
    if any(keyword.lower() in status_blob for keyword in scenario.status_forbidden_keywords):
        score = max(0.0, score - 0.05)
    if _has_impact_contradiction(status_update, scenario):
        score = max(0.0, score - 0.05)
    if not severity_correct:
        score = max(0.0, score - 0.05)
    if not team_correct:
        score = min(score, 0.1)

    return round(min(score, 0.2), 2)


def grade_state(state: IncidentState, scenario: IncidentScenario) -> float:
    severity_correct = state.selected_severity == scenario.correct_severity
    team_correct = state.selected_team == scenario.correct_team
    escalation_correct = state.escalation_decision == scenario.escalation_required

    severity_score = 0.3 if severity_correct else 0.0
    team_score = 0.3 if team_correct else 0.0
    escalation_score = 0.2 if escalation_correct else 0.0
    communication_score = score_status_update(
        state.status_update,
        scenario,
        state.selected_team.value if state.selected_team is not None else None,
        severity_correct=severity_correct,
        team_correct=team_correct,
    )
    final_score = severity_score + team_score + escalation_score + communication_score - state.penalty_total
    return clamp_task_score(final_score)
