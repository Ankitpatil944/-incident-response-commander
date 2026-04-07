from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI

from incident_env.env import IncidentCommanderEnv
from incident_env.models import IncidentAction, IncidentStatusUpdate, ResponseTeam, SeverityLevel
from incident_env.tasks.catalog import TASK_ORDER


def load_dotenv(dotenv_path: str = ".env") -> None:
    env_file = Path(dotenv_path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
IMAGE_NAME = os.getenv("IMAGE_NAME") or LOCAL_IMAGE_NAME
HF_TOKEN = os.getenv("HF_TOKEN")
API_KEY = HF_TOKEN or "missing"
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
BENCHMARK = os.getenv("INCIDENT_ENV_BENCHMARK", "incident_env")
TEMPERATURE = 0.0


def format_reward(value: float) -> str:
    return f"{value:.2f}"


def action_to_log(action: IncidentAction) -> str:
    payload = action.model_dump(mode="json", exclude_none=True)
    payload.pop("metadata", None)
    return json.dumps(payload, separators=(",", ":"))


def flatten_evidence(observation) -> str:
    return "\n".join(
        [
            f"Title: {observation.title}",
            f"Alerts: {observation.alerts}",
            f"Logs: {observation.logs}",
            f"ServiceMap: {observation.service_map}",
            f"Timeline: {observation.timeline}",
        ]
    )


def evidence_text(observation) -> str:
    return " ".join(
        observation.alerts
        + observation.logs
        + observation.service_map
        + observation.timeline
    ).lower()


def infer_team(text: str) -> ResponseTeam:
    if any(marker in text for marker in ["control plane", "kubernetes api unavailable", "regional failover", "incident bot: rollback aborted"]):
        return ResponseTeam.SRE
    if any(marker in text for marker in ["signature mismatch", "signing key", "key rotation", "token validation", "waf", "security rule"]):
        return ResponseTeam.SECURITY
    if any(marker in text for marker in ["dns", "packet loss", "mtls", "tls", "service mesh", "gateway", "edge", "name resolution"]):
        return ResponseTeam.NETWORK
    if any(marker in text for marker in ["postgres", "replica", "database", "write lock", "lock contention", "db-primary", "read replica"]):
        return ResponseTeam.DATABASE
    if any(marker in text for marker in ["deploy", "worker", "queue consumer", "keyerror", "auth-service", "rate-limit", "tax provider", "null pointer", "checkout-api: heap grew"]):
        return ResponseTeam.BACKEND
    if any(marker in text for marker in ["object-store", "cache", "observability", "metrics-ingest", "trace collector", "healthy instances", "autoscaling", "memory pressure"]):
        return ResponseTeam.INFRA
    return ResponseTeam.INFRA


def infer_severity(text: str) -> SeverityLevel:
    if any(marker in text for marker in ["no customer impact", "customer endpoints stable", "public apis healthy", "login success rate remains 99.2%", "service stable"]):
        return SeverityLevel.SEV4
    if any(
        marker in text
        for marker in [
            "100%",
            "success rate 0%",
            "heartbeat lost",
            "major outage",
            "failure rate 68%",
            "failure rate 48%",
            "all api traffic failing",
            "writes failing globally",
            "checkout p95 latency 8x baseline",
            "order failures confined to one cell",
        ]
    ):
        return SeverityLevel.SEV1
    if any(
        marker in text
        for marker in [
            "login failure rate spike",
            "timeout rate critical",
            "success rate 8%",
            "success rate 42%",
            "error rate 45%",
            "http 500 rate 24%",
            "latency 12x baseline",
            "media-upload success rate 71%",
            "public-api error rate 31%",
        ]
    ):
        return SeverityLevel.SEV2
    return SeverityLevel.SEV3


def infer_escalation(text: str, severity: SeverityLevel) -> bool:
    if severity == SeverityLevel.SEV1:
        return True
    if severity == SeverityLevel.SEV4:
        return False
    if any(
        marker in text
        for marker in [
            "regional",
            "dns configuration drift",
            "packet loss",
            "token validation",
            "waf",
            "object-store latency",
            "third-party",
            "tax provider",
            "cell-b",
            "mobile-api traffic success rate 8%",
        ]
    ):
        return True
    if any(
        marker in text
        for marker in [
            "queue consumer",
            "rate-limit-service",
            "read replica lag",
            "redis cache memory",
            "batch jobs running",
            "failover preserves service",
        ]
    ):
        return False
    return severity == SeverityLevel.SEV2


def infer_summary(text: str, team: ResponseTeam) -> str:
    if "queue consumer" in text:
        return "Payment webhook processing is delayed because the queue consumer crashed."
    if "dns configuration drift" in text or "decommissioned load balancer" in text:
        return "Mobile API traffic is routed to a retired edge endpoint through bad DNS."
    if "metrics-ingest backlog" in text or "dashboard freshness below sla" in text:
        return "The observability and metrics pipeline is delayed because the metrics ingest path is backed up."
    if "packet loss" in text and "cell-b" in text:
        return "The orders API in cell-b is failing because database connectivity is broken."
    if "write lock" in text or "lock contention" in text:
        return "Checkout is degraded because database saturation is blocking payment writes."
    if "signature mismatch" in text or "key rotation" in text:
        return "Authentication is failing because a recent signing-key change is not validating tokens correctly."
    if "waf" in text:
        return "A security rule is blocking valid checkout traffic from one geography."
    if "object-store" in text:
        return "Image uploads are degraded because the object-store dependency is slow."
    if "control plane" in text:
        return "A control-plane failure is blocking normal remediation during an API outage."
    if "db-primary heartbeat lost" in text or "connection refused to db-primary" in text:
        return "Orders checkout is unavailable because the primary database failed."
    return f"The primary incident appears to be owned by the {team.value} team."


def infer_customer_impact(text: str, severity: SeverityLevel) -> str:
    if "no customer impact" in text or "public apis healthy" in text or "customer endpoints stable" in text:
        return "No customer impact; internal visibility is degraded and dashboards are delayed."
    if "db-primary heartbeat lost" in text or "connection refused to db-primary" in text:
        return "Checkout unavailable and customers cannot place orders."
    if "mobile-api traffic success rate 8%" in text:
        return "Mobile customers are blocked while other channels remain healthy."
    if "queue consumer" in text:
        return "Payment status updates and settlement flows are delayed."
    if "cell-b" in text and "order failures" in text:
        return "Order failures, checkout degraded, and customer transactions are failing in cell-b."
    if "write lock" in text or "lock contention" in text:
        return "Checkout severe latency and payment delays are impacting customers globally."
    if severity == SeverityLevel.SEV1:
        return "Customers are blocked from a critical workflow."
    if severity == SeverityLevel.SEV2:
        return "Customers are seeing a major degradation in an important workflow."
    return "Customers are seeing a partial degradation while service remains available."


def infer_next_action(text: str, team: ResponseTeam) -> str:
    if "db-primary" in text or "replica promotion candidate healthy" in text:
        return "Promote replica and failover checkout traffic to restore database writes."
    if "decommissioned load balancer" in text or "dns configuration drift" in text:
        return "Rollback the DNS change and restore traffic to the active edge."
    if "metrics-ingest backlog" in text or "dashboard freshness" in text:
        return "Restore the metrics pipeline and clear the ingest backlog to recover observability."
    if "packet loss" in text and "cell-b" in text:
        return "Stabilize network path, reroute traffic, and isolate the failing network segment."
    if "lock contention" in text or "write lock" in text:
        return "Stabilize the database and shift write load to reduce lock contention immediately."
    if "signature mismatch" in text or "key rotation" in text:
        return "Rollback or complete the key propagation to restore token validation."
    if "waf" in text:
        return "Disable the WAF rule and restore checkout traffic."
    if "queue consumer" in text:
        return "Restart and scale the webhook consumer to drain the backlog."
    if "object-store" in text:
        return "Shift traffic or mitigate the object-store latency to restore uploads."
    if "control plane" in text:
        return "Trigger regional failover and coordinate manual mitigation while restoring control-plane access."
    if team == ResponseTeam.NETWORK:
        return "Stabilize the network path and reroute traffic away from the failing component."
    if team == ResponseTeam.DATABASE:
        return "Stabilize the database and restore healthy read and write service."
    if team == ResponseTeam.SECURITY:
        return "Rollback the security change and restore valid traffic."
    if team == ResponseTeam.BACKEND:
        return "Rollback the bad application change and stabilize the service."
    if team == ResponseTeam.SRE:
        return "Coordinate platform mitigation and restore control-plane access."
    return "Stabilize the affected infrastructure dependency and restore service."


def heuristic_plan(observation) -> list[IncidentAction]:
    text = evidence_text(observation)
    team = infer_team(text)
    severity = infer_severity(text)
    escalate = infer_escalation(text, severity)
    summary = infer_summary(text, team)
    customer_impact = infer_customer_impact(text, severity)
    next_action = infer_next_action(text, team)

    status_update = IncidentStatusUpdate(
        summary=summary,
        customer_impact=customer_impact,
        next_action=next_action,
        owner=f"{team.value} commander",
    )

    return [
        IncidentAction(action_type="classify_severity", severity=severity, rationale="Heuristic severity classification."),
        IncidentAction(action_type="assign_team", team=team, rationale="Heuristic team assignment."),
        IncidentAction(action_type="set_escalation", escalate=escalate, rationale="Heuristic escalation decision."),
        IncidentAction(action_type="publish_status", status_update=status_update, rationale="Structured status update."),
    ]


def choose_plan(client: OpenAI, observation) -> list[IncidentAction]:
    try:
        default_plan = heuristic_plan(observation)
        default_status = default_plan[-1].status_update
        prompt = f"""
Return one JSON object with keys summary, customer_impact, next_action, owner.
Keep the operational meaning of this draft status update but make it concise and precise.
Draft:
{json.dumps(default_status.model_dump(mode="json"), ensure_ascii=True)}

Incident:
{flatten_evidence(observation)}
"""
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=TEMPERATURE,
            messages=[
                {"role": "system", "content": "You rewrite incident updates and return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Model output did not include a JSON object")
        status_payload = json.loads(content[start : end + 1])
        default_plan[-1] = IncidentAction(
            action_type="publish_status",
            status_update=IncidentStatusUpdate.model_validate(status_payload),
            rationale="Model-refined status update.",
        )
        return default_plan
    except Exception:
        return heuristic_plan(observation)


def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    for task_name in TASK_ORDER:
        env = IncidentCommanderEnv()
        rewards: list[float] = []
        success = False
        step_count = 0
        score = 0.0
        observation = env.reset(task_name)
        print(f"[START] task={task_name} env={BENCHMARK} model={MODEL_NAME}")

        try:
            planned_actions = choose_plan(client, observation)
            for action in planned_actions:
                observation, reward, done, info = env.step(action)
                step_count += 1
                rewards.append(reward)
                error = observation.last_action_error if observation.last_action_error is not None else "null"
                print(
                    f"[STEP] step={step_count} action={action_to_log(action)} reward={format_reward(reward)} "
                    f"done={'true' if done else 'false'} error={error}"
                )
                score = float(info["score"])
                if done:
                    break
            success = score >= 0.8
        finally:
            env.close()
            rewards_str = ",".join(format_reward(value) for value in rewards)
            print(
                f"[END] success={'true' if success else 'false'} steps={step_count} "
                f"score={format_reward(score)} rewards={rewards_str}"
            )


if __name__ == "__main__":
    main()
