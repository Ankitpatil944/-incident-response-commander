from __future__ import annotations

try:
    from openenv.core.env_server.interfaces import Environment
except ImportError:
    class Environment:
        pass

from incident_env.env import IncidentCommanderEnv
from incident_env.models import IncidentAction, IncidentObservation, IncidentState


class IncidentEnvironment(IncidentCommanderEnv, Environment):
    """OpenEnv-compatible server adapter."""

    SUPPORTS_CONCURRENT_SESSIONS = True

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        task_name: str | None = None,
        **kwargs,
    ) -> IncidentObservation:
        return super().reset(task_name=task_name)

    def step(
        self,
        action: IncidentAction,
        timeout_s: float | None = None,
        **kwargs,
    ) -> IncidentObservation:
        observation, _, _, _ = super().step(action)
        return observation

    @property
    def state(self) -> IncidentState:
        return super().state()
