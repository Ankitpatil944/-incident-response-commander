---
title: Incident Response Commander
sdk: docker
app_port: 7860
base_path: /web
tags:
  - openenv
---

# incident_env

`incident_env` is an OpenEnv benchmark for an Incident Response Commander AI. It simulates the real work humans do during production incidents: setting severity, selecting the owning team, deciding escalation, and sending a structured status update under pressure.

Each episode exposes realistic alerts, logs, service topology, and timeline clues from a hidden incident scenario. The agent must solve the incident through a standard `reset()` / `step()` / `state()` loop rather than a toy game mechanic.

## Motivation

Incident command is a high-value real-world workflow with sequential decisions, partial information, and visible failure costs. This environment is useful for:

- evaluating whether an agent can identify the true operational owner instead of chasing noisy alerts
- measuring whether models can communicate clearly while triaging live incidents
- training with partial-progress rewards instead of sparse end-of-episode success only

## Environment design

Each episode requires four incident-command outcomes:

- severity classification: `SEV-1` to `SEV-4`
- team assignment: `backend`, `infra`, `database`, `network`, `security`, `sre`
- escalation decision: `true` or `false`
- structured status update: `summary`, `customer_impact`, `next_action`, `owner`

The environment ships with 24 fixed scenarios:

- 8 easy: clear signal and obvious ownership
- 8 medium: multiple alerts and coordination ambiguity
- 8 hard: conflicting signals where the loudest alert is not the root cause

Episodes terminate when the agent completes all four dimensions correctly or reaches `max_steps=6`.

## Typed models

Action space: `IncidentAction`

- `action_type`
- `severity` for `classify_severity`
- `team` for `assign_team`
- `escalate` for `set_escalation`
- `status_update` for `publish_status`
- optional `rationale`

Observation space: `IncidentObservation`

- incident metadata: `incident_id`, `title`, `task_name`, `difficulty`
- evidence: `alerts`, `logs`, `service_map`, `timeline`
- progress flags: `severity_done`, `team_done`, `escalation_done`, `status_done`
- current submitted decisions
- `allowed_actions`
- `last_action_error`
- `reward_breakdown`
- `steps_remaining`

State space: `IncidentState`

- episode metadata and counters
- current selected severity, team, escalation, and status update
- progress flags for each decision dimension
- component scores, penalties, cumulative reward, and final score

## Reward shaping

The grader is deterministic and bounded to `[0.0, 1.0]`.

Positive components:

- `+0.30` correct severity
- `+0.30` correct team
- `+0.20` correct escalation
- `+0.20` accurate status update

Communication rubric:

- `+0.05` summary references the affected service or incident class
- `+0.05` customer impact reflects the real incident impact
- `+0.05` next action matches the mitigation direction
- `+0.05` owner matches the selected or correct response team

Penalty behavior:

- repeated decisions reduce the achievable final score
- invalid payloads reduce the achievable final score
- premature communication before basic triage reduces the achievable final score

## Tasks

### `easy_triage`
Clear incidents such as database primary loss, TLS expiry, or queue-consumer crash.

### `medium_coordination`
Multiple alerts require reasoning about root cause and escalation, such as DNS cache corruption, regional dependency slowdown, or WAF false positives.

### `hard_conflict`
Conflicting signals require prioritization, such as database saturation masked by network noise or key-rotation failures masked by unrelated database metrics.

## Project structure

```text
incident_env/
|-- client.py
|-- env.py
|-- graders.py
|-- models.py
|-- server/
|   |-- app.py
|   |-- incident_environment.py
|   `-- requirements.txt
`-- tasks/
    |-- catalog.py
    `-- scenarios.py
```

## Local setup

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install --upgrade pip
pip install -e .[dev]
Copy-Item .env.example .env
```

## Run locally

Direct Python use:

```python
from incident_env import IncidentAction, IncidentEnv, SeverityLevel

env = IncidentEnv()
obs = env.reset("easy_triage")
obs, reward, done, info = env.step(
    IncidentAction(action_type="classify_severity", severity=SeverityLevel.SEV1)
)
```

FastAPI server:

```bash
python -m server.app
```

Or via the packaged script:

```bash
server
```

The container sets `ENABLE_WEB_INTERFACE=true`, so `/web` is enabled in Docker and on Hugging Face Spaces.

## Validation

```bash
pytest
openenv validate
python inference.py
docker build -t incident-env .
docker run --rm -p 7860:7860 incident-env
```

## Inference baseline

`inference.py` is in the repo root and follows the required stdout contract:

- `[START]`
- `[STEP]`
- `[END]`

Environment variables:

- `HF_TOKEN` or `OPENAI_API_KEY`
- `API_BASE_URL`
- `MODEL_NAME`
- optional `IMAGE_NAME` / `LOCAL_IMAGE_NAME`

`inference.py` loads a local `.env` file automatically before reading environment variables. Start from:

```bash
Copy-Item .env.example .env
```

Then edit `.env` and set at least:

```env
HF_TOKEN=your_token_here
API_BASE_URL=https://router.huggingface.co/v1
MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
```

The script uses the OpenAI client with deterministic temperature and falls back to a rule-based planner if the remote model output is invalid. This keeps runs reproducible and bounded while still exercising a real LLM call path.

Measured local baseline from `python inference.py`:

- `easy_triage`: `1.00`
- `medium_coordination`: `1.00`
- `hard_conflict`: `1.00`

## Docker and Hugging Face Spaces

The root `Dockerfile` is HF Space compatible and includes:

- Python 3.11 slim base image
- `ENV ENABLE_WEB_INTERFACE=true`
- `uvicorn incident_env.server.app:app --port 7860`

Deploy with:

```bash
openenv push --repo-id <your-username>/incident-env
```

Tag the Space with `openenv` and verify that `/reset` responds successfully after deployment.
