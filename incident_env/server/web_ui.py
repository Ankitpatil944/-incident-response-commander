from __future__ import annotations

import json
from typing import Any

import gradio as gr

from incident_env.models import ActionType, ResponseTeam, SeverityLevel


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("observation"), dict):
        return data["observation"]
    return data if isinstance(data, dict) else {}


def _json_block(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2)


def _render_incident_markdown(data: dict[str, Any]) -> str:
    payload = _payload(data)
    if not payload:
        return "## Current Incident\n\nReset the environment to load an incident."

    alerts = "\n".join(f"- {item}" for item in payload.get("alerts", [])) or "- none"
    logs = "\n".join(f"- {item}" for item in payload.get("logs", [])) or "- none"
    timeline = "\n".join(f"- {item}" for item in payload.get("timeline", [])) or "- none"
    service_map = "\n".join(f"- {item}" for item in payload.get("service_map", [])) or "- none"

    return (
        f"## Current Incident\n\n"
        f"**{payload.get('title', 'Unknown incident')}**\n\n"
        f"- Incident ID: `{payload.get('incident_id', 'n/a')}`\n"
        f"- Task: `{payload.get('task_name', 'n/a')}`\n"
        f"- Difficulty: `{payload.get('difficulty', 'n/a')}`\n"
        f"- Steps Remaining: `{payload.get('steps_remaining', 'n/a')}`\n\n"
        f"### Alerts\n{alerts}\n\n"
        f"### Logs\n{logs}\n\n"
        f"### Service Map\n{service_map}\n\n"
        f"### Timeline\n{timeline}"
    )


def _render_progress_markdown(data: dict[str, Any]) -> str:
    payload = _payload(data)
    breakdown = payload.get("reward_breakdown", {})
    return (
        "## Progress\n\n"
        f"- Severity submitted: `{payload.get('severity_done', False)}`\n"
        f"- Team submitted: `{payload.get('team_done', False)}`\n"
        f"- Escalation submitted: `{payload.get('escalation_done', False)}`\n"
        f"- Status submitted: `{payload.get('status_done', False)}`\n"
        f"- Selected severity: `{payload.get('selected_severity')}`\n"
        f"- Selected team: `{payload.get('selected_team')}`\n"
        f"- Escalation decision: `{payload.get('escalation_decision')}`\n"
        f"- Last action error: `{payload.get('last_action_error')}`\n\n"
        "## Scorecard\n\n"
        f"- Severity score: `{breakdown.get('severity_score', 0.0)}`\n"
        f"- Team score: `{breakdown.get('team_score', 0.0)}`\n"
        f"- Escalation score: `{breakdown.get('escalation_score', 0.0)}`\n"
        f"- Communication score: `{breakdown.get('communication_score', 0.0)}`\n"
        f"- Penalties: `{breakdown.get('penalty_total', 0.0)}`\n"
        f"- Final score: `{breakdown.get('final_score', 0.0)}`\n"
        f"- Done: `{data.get('done', payload.get('done', False))}`"
    )


def _action_help(action_type: str) -> str:
    if action_type == ActionType.CLASSIFY_SEVERITY.value:
        return "Pick only the incident severity. Other fields are ignored."
    if action_type == ActionType.ASSIGN_TEAM.value:
        return "Pick the owning team. Other fields are ignored."
    if action_type == ActionType.SET_ESCALATION.value:
        return "Choose whether escalation is required. Other fields are ignored."
    return (
        "Fill all four communication fields. Good updates mention the affected service, "
        "real customer impact, a concrete next action, and the correct owner."
    )


def _action_visibility(action_type: str):
    return (
        gr.update(visible=action_type == ActionType.CLASSIFY_SEVERITY.value),
        gr.update(visible=action_type == ActionType.ASSIGN_TEAM.value),
        gr.update(visible=action_type == ActionType.SET_ESCALATION.value),
        gr.update(visible=action_type == ActionType.PUBLISH_STATUS.value),
        _action_help(action_type),
    )


def _owner_value(team: str):
    if not team:
        return gr.update()
    return gr.update(value=f"{team} commander")


def build_incident_gradio_ui(
    web_manager,
    action_fields,
    metadata,
    is_chat_env,
    title,
    quick_start_md,
):
    del action_fields, is_chat_env

    async def do_reset(task_name: str):
        request = {"task_name": task_name} if task_name else {}
        result = await web_manager.reset_environment(request)
        return (
            _json_block(result),
            "Environment reset successfully.",
            _render_incident_markdown(result),
            _render_progress_markdown(result),
        )

    async def do_step(
        action_type: str,
        severity: str,
        team: str,
        escalate: str,
        summary: str,
        customer_impact: str,
        next_action: str,
        owner: str,
        rationale: str,
    ):
        action_data: dict[str, Any] = {"action_type": action_type}
        if rationale.strip():
            action_data["rationale"] = rationale.strip()

        if action_type == ActionType.CLASSIFY_SEVERITY.value and severity:
            action_data["severity"] = severity
        elif action_type == ActionType.ASSIGN_TEAM.value and team:
            action_data["team"] = team
        elif action_type == ActionType.SET_ESCALATION.value and escalate:
            action_data["escalate"] = escalate.lower() == "true"
        elif action_type == ActionType.PUBLISH_STATUS.value:
            action_data["status_update"] = {
                "summary": summary.strip(),
                "customer_impact": customer_impact.strip(),
                "next_action": next_action.strip(),
                "owner": owner.strip(),
            }

        try:
            result = await web_manager.step_environment(action_data)
            return (
                _json_block(result),
                "Step executed successfully.",
                _render_incident_markdown(result),
                _render_progress_markdown(result),
            )
        except Exception as exc:
            error_payload = {"error": str(exc), "action": action_data}
            rendered = _json_block(error_payload)
            return rendered, f"Error: {exc}", "", ""

    def do_get_state():
        try:
            result = web_manager.get_state()
            return (
                _json_block(result),
                "Current state loaded.",
                _render_incident_markdown(result),
                _render_progress_markdown(result),
            )
        except Exception as exc:
            rendered = _json_block({"error": str(exc)})
            return rendered, f"Error: {exc}", "", ""

    with gr.Blocks() as demo:
        gr.Markdown(
            f"# {title}\n\n"
            "Use this incident console for structured triage. Reset first, inspect the incident, "
            "then submit one action at a time."
        )

        with gr.Row():
            with gr.Column(scale=1):
                with gr.Accordion("Quick Start", open=True):
                    gr.Markdown(quick_start_md)
                with gr.Accordion("README", open=False):
                    gr.Markdown(metadata.readme_content or "")
                with gr.Accordion("Action Guide", open=True):
                    gr.Markdown(
                        "- `classify_severity`: set only severity\n"
                        "- `assign_team`: set only team\n"
                        "- `set_escalation`: set only escalate\n"
                        "- `publish_status`: fill summary, customer impact, next action, owner"
                    )

            with gr.Column(scale=2):
                with gr.Row():
                    task_name = gr.Dropdown(
                        choices=["easy_triage", "medium_coordination", "hard_conflict"],
                        value="easy_triage",
                        label="Task",
                    )
                    action_type = gr.Dropdown(
                        choices=[action.value for action in ActionType],
                        value=ActionType.CLASSIFY_SEVERITY.value,
                        label="Action Type",
                    )

                action_help = gr.Markdown(_action_help(ActionType.CLASSIFY_SEVERITY.value))

                with gr.Group() as severity_group:
                    severity = gr.Dropdown(
                        choices=[severity.value for severity in SeverityLevel],
                        value=SeverityLevel.SEV1.value,
                        label="Severity",
                    )

                with gr.Group(visible=False) as team_group:
                    team = gr.Dropdown(
                        choices=[team.value for team in ResponseTeam],
                        value=ResponseTeam.DATABASE.value,
                        label="Team",
                    )

                with gr.Group(visible=False) as escalation_group:
                    escalate = gr.Radio(
                        choices=["true", "false"],
                        value="true",
                        label="Escalate",
                    )

                with gr.Group(visible=False) as status_group:
                    summary = gr.Textbox(label="Status Summary", lines=2)
                    customer_impact = gr.Textbox(label="Customer Impact", lines=2)
                    next_action = gr.Textbox(label="Next Action", lines=2)
                    owner = gr.Textbox(label="Owner", value="database commander")

                rationale = gr.Textbox(label="Rationale", lines=2, placeholder="Optional short explanation.")

                with gr.Row():
                    reset_button = gr.Button("Reset", variant="secondary")
                    step_button = gr.Button("Step", variant="primary")
                    state_button = gr.Button("Get State")

                status = gr.Textbox(label="Status", interactive=False)

                with gr.Row():
                    incident_card = gr.Markdown("## Current Incident\n\nReset the environment to load an incident.")
                    progress_card = gr.Markdown("## Progress\n\nNo episode loaded.")

                raw_json = gr.Code(label="Raw JSON response", language="json")

        action_type.change(
            _action_visibility,
            inputs=[action_type],
            outputs=[severity_group, team_group, escalation_group, status_group, action_help],
        )
        team.change(_owner_value, inputs=[team], outputs=[owner])

        reset_button.click(
            do_reset,
            inputs=[task_name],
            outputs=[raw_json, status, incident_card, progress_card],
        )
        step_button.click(
            do_step,
            inputs=[
                action_type,
                severity,
                team,
                escalate,
                summary,
                customer_impact,
                next_action,
                owner,
                rationale,
            ],
            outputs=[raw_json, status, incident_card, progress_card],
        )
        state_button.click(
            do_get_state,
            outputs=[raw_json, status, incident_card, progress_card],
        )

    return demo
