from incident_env.env import IncidentCommanderEnv
from incident_env.graders import score_status_update
from incident_env.models import IncidentAction, IncidentStatusUpdate, ResponseTeam, SeverityLevel


def make_status(owner: str = "database") -> IncidentStatusUpdate:
    return IncidentStatusUpdate(
        summary="Orders checkout is failing because the database primary is unavailable.",
        customer_impact="Checkout unavailable and customers cannot place orders.",
        next_action="Promote replica and failover database traffic immediately.",
        owner=owner,
    )


def test_reset_returns_clean_state():
    env = IncidentCommanderEnv()
    observation = env.reset("easy_triage")

    assert observation.incident_id == "easy-db-primary-down"
    assert observation.reward == 0.0
    assert observation.done is False
    assert observation.severity_done is False
    assert observation.steps_remaining == 6


def test_easy_incident_can_score_perfectly():
    env = IncidentCommanderEnv()
    env.reset("easy_triage")

    _, reward, done, _ = env.step(
        IncidentAction(action_type="classify_severity", severity=SeverityLevel.SEV1)
    )
    assert reward == 0.3
    assert done is False

    env.step(IncidentAction(action_type="assign_team", team=ResponseTeam.DATABASE))
    env.step(IncidentAction(action_type="set_escalation", escalate=True))
    observation, reward, done, info = env.step(
        IncidentAction(action_type="publish_status", status_update=make_status())
    )

    assert reward == 0.2
    assert done is True
    assert observation.reward_breakdown.final_score == 0.99
    assert info["score"] == 0.99


def test_repeated_action_accumulates_penalty():
    env = IncidentCommanderEnv()
    env.reset("easy_triage")

    env.step(IncidentAction(action_type="classify_severity", severity=SeverityLevel.SEV2))
    _, reward, _, _ = env.step(
        IncidentAction(action_type="classify_severity", severity=SeverityLevel.SEV2)
    )

    assert reward == 0.0
    assert env.state().penalty_total == 0.13


def test_task_rotation_is_deterministic():
    env = IncidentCommanderEnv()
    first = env.reset("medium_coordination").incident_id
    second = env.reset("medium_coordination").incident_id

    assert first != second
    assert first == "medium-api-db-network-split"
    assert second == "medium-memory-leak-after-deploy"


def test_partial_score_stays_bounded():
    env = IncidentCommanderEnv()
    env.reset("hard_conflict")

    env.step(IncidentAction(action_type="assign_team", team=ResponseTeam.NETWORK))
    env.step(IncidentAction(action_type="set_escalation", escalate=True))
    observation, _, _, info = env.step(
        IncidentAction(
            action_type="publish_status",
            status_update=IncidentStatusUpdate(
                summary="Checkout has a network outage in the database path.",
                customer_impact="Customers see checkout impact globally.",
                next_action="Stabilize the network path while triaging the database.",
                owner="network commander",
            ),
        )
    )

    assert 0.0 <= info["score"] <= 1.0
    assert 0.0 <= observation.reward_breakdown.final_score <= 1.0


def test_wrong_decisions_accumulate_dependency_penalties():
    env = IncidentCommanderEnv()
    env.reset("easy_triage")

    env.step(IncidentAction(action_type="classify_severity", severity=SeverityLevel.SEV2))
    env.step(IncidentAction(action_type="assign_team", team=ResponseTeam.DATABASE))
    env.step(IncidentAction(action_type="set_escalation", escalate=True))

    state = env.state()
    assert state.penalty_total == 0.17
    assert state.team_score_awarded == 0.3
    assert state.escalation_score_awarded == 0.2


def test_status_scoring_rejects_duplicate_or_contradictory_impact():
    env = IncidentCommanderEnv()
    observation = env.reset("easy_triage")
    scenario = env._require_scenario()

    duplicate_status = IncidentStatusUpdate(
        summary="The observability and metrics pipeline is delayed because the metrics ingest path is backed up.",
        customer_impact="The observability and metrics pipeline is delayed because the metrics ingest path is backed up.",
        next_action="Restore the metrics pipeline and clear the ingest backlog to recover observability.",
        owner="infra commander",
    )
    contradictory_status = IncidentStatusUpdate(
        summary="The observability and metrics pipeline is delayed because the metrics ingest path is backed up.",
        customer_impact="Customers are blocked by a major outage across the platform.",
        next_action="Restore the metrics pipeline and clear the ingest backlog to recover observability.",
        owner="infra commander",
    )

    assert observation.incident_id == "easy-db-primary-down"
    observability_scenario = env.reset("easy_triage")
    while observability_scenario.incident_id != "easy-observability-noise":
        observability_scenario = env.reset("easy_triage")
    scenario = env._require_scenario()

    assert score_status_update(duplicate_status, scenario, "infra") == 0.15
    assert score_status_update(contradictory_status, scenario, "infra") == 0.1
