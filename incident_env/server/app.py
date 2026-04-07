from __future__ import annotations

import os

import uvicorn

try:
    from openenv.core.env_server.http_server import create_app
except ImportError as exc:
    raise ImportError("openenv-core must be installed to run the server") from exc

from incident_env.models import IncidentAction, IncidentObservation
from incident_env.server.incident_environment import IncidentEnvironment
from incident_env.server.web_ui import build_incident_gradio_ui


app = create_app(
    IncidentEnvironment,
    IncidentAction,
    IncidentObservation,
    env_name="incident_env",
    max_concurrent_envs=8,
    gradio_builder=build_incident_gradio_ui,
)


def main() -> None:
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
