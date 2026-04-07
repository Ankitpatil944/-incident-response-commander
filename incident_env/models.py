from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from openenv.core.env_server.types import Action as OpenEnvAction
    from openenv.core.env_server.types import Observation as OpenEnvObservation
    from openenv.core.env_server.types import State as OpenEnvState
except ImportError:
    class OpenEnvAction(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class OpenEnvObservation(BaseModel):
        reward: float = 0.0
        done: bool = False
        model_config = ConfigDict(extra="forbid")

    class OpenEnvState(BaseModel):
        model_config = ConfigDict(extra="forbid")


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SeverityLevel(str, Enum):
    SEV1 = "SEV-1"
    SEV2 = "SEV-2"
    SEV3 = "SEV-3"
    SEV4 = "SEV-4"


class ResponseTeam(str, Enum):
    BACKEND = "backend"
    INFRA = "infra"
    DATABASE = "database"
    NETWORK = "network"
    SECURITY = "security"
    SRE = "sre"


class ActionType(str, Enum):
    CLASSIFY_SEVERITY = "classify_severity"
    ASSIGN_TEAM = "assign_team"
    SET_ESCALATION = "set_escalation"
    PUBLISH_STATUS = "publish_status"


class IncidentStatusUpdate(BaseModel):
    summary: str = Field(..., min_length=12, max_length=240)
    customer_impact: str = Field(..., min_length=10, max_length=240)
    next_action: str = Field(..., min_length=10, max_length=240)
    owner: str = Field(..., min_length=3, max_length=80)

    model_config = ConfigDict(extra="forbid")


class IncidentAction(OpenEnvAction):
    action_type: ActionType
    severity: Optional[SeverityLevel] = None
    team: Optional[ResponseTeam] = None
    escalate: Optional[bool] = None
    status_update: Optional[IncidentStatusUpdate] = None
    rationale: Optional[str] = Field(default=None, max_length=240)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_payload(self) -> "IncidentAction":
        if self.action_type == ActionType.CLASSIFY_SEVERITY and self.severity is None:
            raise ValueError("severity is required for classify_severity")
        if self.action_type == ActionType.ASSIGN_TEAM and self.team is None:
            raise ValueError("team is required for assign_team")
        if self.action_type == ActionType.SET_ESCALATION and self.escalate is None:
            raise ValueError("escalate is required for set_escalation")
        if self.action_type == ActionType.PUBLISH_STATUS and self.status_update is None:
            raise ValueError("status_update is required for publish_status")
        return self


class RewardBreakdown(BaseModel):
    severity_score: float = 0.0
    team_score: float = 0.0
    escalation_score: float = 0.0
    communication_score: float = 0.0
    penalty_total: float = 0.0
    final_score: float = 0.0

    model_config = ConfigDict(extra="forbid")


class IncidentScenario(BaseModel):
    incident_id: str
    title: str
    difficulty: DifficultyLevel
    alerts: list[str]
    logs: list[str]
    service_map: list[str]
    timeline: list[str]
    correct_severity: SeverityLevel
    correct_team: ResponseTeam
    escalation_required: bool
    service_keywords: list[str]
    impact_keywords: list[str]
    response_keywords: list[str]
    status_forbidden_keywords: list[str] = Field(default_factory=list)
    explanation: str

    model_config = ConfigDict(extra="forbid")


class IncidentObservation(OpenEnvObservation):
    incident_id: str
    title: str
    task_name: str
    difficulty: DifficultyLevel
    alerts: list[str]
    logs: list[str]
    service_map: list[str]
    timeline: list[str]
    severity_done: bool
    team_done: bool
    escalation_done: bool
    status_done: bool
    selected_severity: Optional[SeverityLevel] = None
    selected_team: Optional[ResponseTeam] = None
    escalation_decision: Optional[bool] = None
    status_update: Optional[IncidentStatusUpdate] = None
    allowed_actions: list[ActionType]
    last_action_error: Optional[str] = None
    reward_breakdown: RewardBreakdown
    steps_remaining: int

    model_config = ConfigDict(extra="forbid")


class IncidentState(OpenEnvState):
    episode_id: str
    task_name: str
    difficulty: DifficultyLevel
    incident_id: str
    title: str
    step_count: int
    max_steps: int
    done: bool
    alerts: list[str]
    logs: list[str]
    service_map: list[str]
    timeline: list[str]
    selected_severity: Optional[SeverityLevel] = None
    selected_team: Optional[ResponseTeam] = None
    escalation_decision: Optional[bool] = None
    status_update: Optional[IncidentStatusUpdate] = None
    severity_submitted: bool = False
    team_submitted: bool = False
    escalation_submitted: bool = False
    status_submitted: bool = False
    severity_score_awarded: float = 0.0
    team_score_awarded: float = 0.0
    escalation_score_awarded: float = 0.0
    communication_score_awarded: float = 0.0
    penalty_total: float = 0.0
    cumulative_reward: float = 0.0
    score: float = 0.0
    last_action_error: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

