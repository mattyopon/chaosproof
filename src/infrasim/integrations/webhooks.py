"""Webhook integrations for notifications."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    url: str
    type: str  # "slack", "pagerduty", "generic"


async def send_slack_notification(webhook_url: str, report_summary: dict) -> bool:
    """Send simulation results to Slack."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "InfraSim Simulation Report"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Resilience Score:* {report_summary.get('resilience_score', 'N/A')}/100\n"
                    f"*Critical:* {report_summary.get('critical_count', 0)} | "
                    f"*Warning:* {report_summary.get('warning_count', 0)} | "
                    f"*Passed:* {report_summary.get('passed_count', 0)}"
                ),
            },
        },
    ]
    if report_summary.get("critical_count", 0) > 0:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":rotating_light: *Critical findings detected!* "
                        "Run `infrasim analyze` for recommendations."
                    ),
                },
            }
        )

    payload = {"blocks": blocks}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            return resp.status_code == 200
    except Exception:
        logger.warning("Slack notification failed.", exc_info=True)
        return False


async def send_pagerduty_event(routing_key: str, report_summary: dict) -> bool:
    """Send PagerDuty event for critical findings."""
    if report_summary.get("critical_count", 0) == 0:
        return False  # Only alert on critical

    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "payload": {
            "summary": (
                f"InfraSim: {report_summary['critical_count']} "
                "critical infrastructure risks detected"
            ),
            "severity": "critical",
            "source": "infrasim",
            "custom_details": report_summary,
        },
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=10,
            )
            return resp.status_code == 202
    except Exception:
        logger.warning("PagerDuty event failed.", exc_info=True)
        return False


async def send_generic_webhook(url: str, report_summary: dict) -> bool:
    """Send results to any webhook URL."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=report_summary, timeout=10)
            return resp.status_code < 400
    except Exception:
        logger.warning("Generic webhook failed.", exc_info=True)
        return False
