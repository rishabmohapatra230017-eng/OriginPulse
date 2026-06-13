"""Automate post-meeting extraction, Jira ticket creation, and Slack summary posting.

Usage:
    python automate_meeting.py --transcript transcripts/mock_meeting_transcript.md --dry-run

Environment:
    Copy .env.example to .env and fill in the credentials for Groq, Jira, and Slack.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from groq import Groq
from requests.auth import HTTPBasicAuth
# pyrefly: ignore [missing-import]
from slack_sdk import WebClient
# pyrefly: ignore [missing-import]
from slack_sdk.errors import SlackApiError


LOGGER = logging.getLogger("meeting_automation")


ACTION_ITEM_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "meeting_action_items",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "A concise executive summary of the meeting.",
                },
                "action_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "assignee": {
                                "type": "string",
                                "description": "Named owner, or Unassigned if unclear.",
                            },
                            "task": {
                                "type": "string",
                                "description": "Concrete task to be completed.",
                            },
                            "due_date": {
                                "type": "string",
                                "description": "ISO date if explicit/inferable, otherwise TBD.",
                            },
                        },
                        "required": ["assignee", "task", "due_date"],
                    },
                },
            },
            "required": ["summary", "action_items"],
        },
    },
}


SYSTEM_PROMPT = """You extract operational follow-ups from meeting transcripts.

Return only a JSON object with this exact shape:
{"summary":"...","action_items":[{"assignee":"...","task":"...","due_date":"..."}]}

Rules:
- Capture concrete action items only; do not invent tasks.
- Combine closely related work into one action item when the same owner, due date,
  and discussion context indicate it belongs in one Jira ticket or acceptance criteria.
- Preserve the natural assignee name when clear, such as Sarah, Alex, or Jamie.
- If no assignee is explicit or strongly implied, use "Unassigned".
- Use the provided MEETING_DATE to resolve relative dates like today, tomorrow,
  end of day tomorrow, by Friday, by Monday, and next Wednesday.
- If a due date is explicit or can be inferred from a relative phrase, use ISO format YYYY-MM-DD.
- If the due date is unclear or missing, use "TBD".
- Write tasks as clear Jira-ready summaries.
- Do not include Markdown, commentary, or keys outside the schema.
"""


class AutomationError(RuntimeError):
    """Raised when a required workflow stage cannot complete safely."""


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    project_key: str
    issue_type: str
    assignee_map: dict[str, str]


@dataclass(frozen=True)
class SlackConfig:
    bot_token: str | None
    channel_id: str | None
    webhook_url: str | None


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Transcript file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_jira_config() -> JiraConfig:
    assignee_map_raw = os.getenv("JIRA_ASSIGNEE_MAP_JSON", "{}")
    try:
        assignee_map = json.loads(assignee_map_raw)
    except json.JSONDecodeError as exc:
        raise AutomationError("JIRA_ASSIGNEE_MAP_JSON must be valid JSON.") from exc

    return JiraConfig(
        base_url=os.environ["JIRA_BASE_URL"].rstrip("/"),
        email=os.environ["JIRA_EMAIL"],
        api_token=os.environ["JIRA_API_TOKEN"],
        project_key=os.environ["JIRA_PROJECT_KEY"],
        issue_type=os.getenv("JIRA_ISSUE_TYPE", "Task"),
        assignee_map=assignee_map,
    )


def load_slack_config() -> SlackConfig:
    return SlackConfig(
        bot_token=os.getenv("SLACK_BOT_TOKEN") or None,
        channel_id=os.getenv("SLACK_CHANNEL_ID") or None,
        webhook_url=os.getenv("SLACK_WEBHOOK_URL") or None,
    )


def is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.lower()
    return any(token in lowered for token in ("your-", "example", "c0123456789"))


def validate_live_config(jira_config: JiraConfig, slack_config: SlackConfig) -> None:
    """Fail fast before creating Jira tickets if live credentials are incomplete."""
    missing = []
    if is_placeholder(jira_config.base_url) or "atlassian.net" not in jira_config.base_url:
        missing.append("JIRA_BASE_URL")
    if is_placeholder(jira_config.email):
        missing.append("JIRA_EMAIL")
    if is_placeholder(jira_config.api_token):
        missing.append("JIRA_API_TOKEN")
    if is_placeholder(jira_config.project_key):
        missing.append("JIRA_PROJECT_KEY")

    has_bot_config = not is_placeholder(slack_config.bot_token) and not is_placeholder(
        slack_config.channel_id
    )
    has_webhook_config = not is_placeholder(slack_config.webhook_url)
    if not has_bot_config and not has_webhook_config:
        missing.append("SLACK_BOT_TOKEN + SLACK_CHANNEL_ID or SLACK_WEBHOOK_URL")

    if missing:
        raise AutomationError(
            "Live run blocked. Fill these values in .env first: " + ", ".join(missing)
        )


def normalize_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure downstream steps always receive safe string defaults."""
    summary = str(payload.get("summary") or "No summary generated.").strip()
    normalized_items: list[dict[str, str]] = []

    for raw_item in payload.get("action_items", []):
        if not isinstance(raw_item, dict):
            LOGGER.warning("Skipping malformed action item: %s", raw_item)
            continue

        assignee = str(raw_item.get("assignee") or "Unassigned").strip() or "Unassigned"
        task = str(raw_item.get("task") or "").strip()
        due_date = str(raw_item.get("due_date") or "TBD").strip() or "TBD"

        if not task:
            LOGGER.warning("Skipping action item with empty task: %s", raw_item)
            continue

        normalized_items.append(
            {"assignee": assignee, "task": task, "due_date": due_date}
        )

    return {"summary": summary, "action_items": normalized_items}


def build_relative_date_context(meeting_date: str) -> str:
    """Provide the LLM with deterministic anchors for common meeting due dates."""
    anchor = date.fromisoformat(meeting_date)
    next_days = []
    for offset in range(0, 10):
        day = anchor + timedelta(days=offset)
        next_days.append(f"- {day.strftime('%A')}: {day.isoformat()}")

    tomorrow = anchor + timedelta(days=1)
    return (
        "DATE_CONTEXT:\n"
        f"- Meeting date / today: {anchor.isoformat()} ({anchor.strftime('%A')})\n"
        f"- Tomorrow: {tomorrow.isoformat()} ({tomorrow.strftime('%A')})\n"
        "- Upcoming calendar days:\n"
        + "\n".join(next_days)
        + "\n\n"
        "Use this DATE_CONTEXT when resolving due dates. For example, if the "
        "transcript says 'by Friday', use the upcoming Friday shown above."
    )


def extract_meeting_data(
    transcript_text: str,
    model: str,
    meeting_date: str,
) -> dict[str, Any]:
    """Use Groq to extract a summary and Jira-ready action items."""
    LOGGER.info("Extracting meeting summary and action items with Groq model %s", model)
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    extraction_request = (
        f"MEETING_DATE: {meeting_date}\n\n"
        f"{build_relative_date_context(meeting_date)}\n\n"
        "TRANSCRIPT:\n"
        f"{transcript_text}"
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format=ACTION_ITEM_SCHEMA,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": extraction_request},
            ],
            timeout=60,
        )
    except Exception as exc:
        raise AutomationError("Groq extraction request failed.") from exc

    content = completion.choices[0].message.content
    if not content:
        raise AutomationError("Groq returned an empty extraction response.")

    try:
        return normalize_extraction(json.loads(content))
    except json.JSONDecodeError as exc:
        raise AutomationError(f"Groq returned malformed JSON: {content[:500]}") from exc


def jira_adf_document(text: str) -> dict[str, Any]:
    """Build Atlassian Document Format for Jira Cloud multiline descriptions."""
    paragraphs = []
    for line in text.splitlines():
        paragraphs.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}] if line else [],
            }
        )

    return {"type": "doc", "version": 1, "content": paragraphs}


def as_jira_due_date(value: str) -> str | None:
    """Jira accepts due dates as YYYY-MM-DD. Relative or TBD dates are omitted."""
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    return None


def create_jira_tickets(
    action_items: list[dict[str, str]],
    config: JiraConfig,
    dry_run: bool = False,
) -> list[dict[str, str]]:
    """Create one Jira issue per action item and return issue metadata."""
    created: list[dict[str, str]] = []
    endpoint = f"{config.base_url}/rest/api/3/issue"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    for item in action_items:
        summary = item["task"][:255]
        description = (
            f"Meeting action item\n\n"
            f"Assignee from transcript: {item['assignee']}\n"
            f"Due date from transcript: {item['due_date']}\n\n"
            f"Task:\n{item['task']}"
        )
        fields: dict[str, Any] = {
            "project": {"key": config.project_key},
            "summary": summary,
            "description": jira_adf_document(description),
            "issuetype": {"name": config.issue_type},
            "labels": ["meeting-action-item"],
        }

        due_date = as_jira_due_date(item["due_date"])
        if due_date:
            fields["duedate"] = due_date

        account_id = config.assignee_map.get(item["assignee"])
        if account_id:
            fields["assignee"] = {"id": account_id}
        elif item["assignee"] in {"Unassigned", "TBD"}:
            fields["labels"].append("needs-triage")

        payload = {"fields": fields}

        if dry_run:
            fake_key = f"{config.project_key}-DRYRUN-{len(created) + 1}"
            fake_url = f"{config.base_url}/browse/{fake_key}"
            LOGGER.info("DRY RUN: would create Jira issue %s for %s", fake_key, summary)
            created.append({"key": fake_key, "url": fake_url, **item})
            continue

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                auth=auth,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            issue = response.json()
            key = issue["key"]
            url = f"{config.base_url}/browse/{key}"
            LOGGER.info("Created Jira issue %s", key)
            created.append({"key": key, "url": url, **item})
        except requests.RequestException as exc:
            LOGGER.exception("Failed to create Jira issue for action item: %s", item)
            continue
        except (KeyError, json.JSONDecodeError) as exc:
            LOGGER.exception("Jira returned an unexpected response for item: %s", item)
            continue

    return created


def build_slack_blocks(summary: str, tickets: list[dict[str, str]]) -> list[dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ticket_count = len(tickets)
    action_lines = []
    for ticket in tickets:
        action_lines.append(
            f"- :ticket: <{ticket['url']}|*{ticket['key']}*> | "
            f":bust_in_silhouette: *{ticket['assignee']}* | "
            f":calendar: *Due {ticket['due_date']}*\n"
            f"  {ticket['task']}"
        )

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "OriginPulse Meeting Follow-up",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f":robot_face: Generated by *OriginPulse* | "
                        f":clock3: {generated_at} | :white_check_mark: {ticket_count} Jira tickets"
                    ),
                }
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":memo: *Meeting Summary*\n{summary}"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":dart: *Action Items & Jira Tickets*\n"
                + ("\n".join(action_lines) or "_None found._"),
            },
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Review `Unassigned` or `TBD` items before the next clinical pilot sync.",
                }
            ],
        },
    ]


def post_slack_summary(
    summary: str,
    tickets: list[dict[str, str]],
    config: SlackConfig,
    dry_run: bool = False,
) -> None:
    """Post a Block Kit summary using either Slack bot auth or an incoming webhook."""
    blocks = build_slack_blocks(summary, tickets)

    if dry_run:
        LOGGER.info("DRY RUN: would post Slack blocks:\n%s", json.dumps(blocks, indent=2))
        return

    if config.bot_token and config.channel_id:
        try:
            client = WebClient(token=config.bot_token)
            client.chat_postMessage(
                channel=config.channel_id,
                text="Meeting summary and action items",
                blocks=blocks,
            )
            LOGGER.info("Posted Slack summary to channel %s", config.channel_id)
            return
        except SlackApiError as exc:
            raise AutomationError(f"Slack bot post failed: {exc.response['error']}") from exc

    if config.webhook_url:
        try:
            response = requests.post(
                config.webhook_url,
                json={"text": "Meeting summary and action items", "blocks": blocks},
                timeout=30,
            )
            response.raise_for_status()
            LOGGER.info("Posted Slack summary through incoming webhook")
            return
        except requests.RequestException as exc:
            raise AutomationError("Slack webhook post failed.") from exc

    raise AutomationError(
        "Slack is not configured. Set SLACK_BOT_TOKEN + SLACK_CHANNEL_ID or SLACK_WEBHOOK_URL."
    )


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate meeting follow-up workflows.")
    parser.add_argument(
        "--transcript",
        default=os.getenv("TRANSCRIPT_PATH", "transcripts/mock_meeting_transcript.md"),
        help="Path to a meeting transcript text/Markdown file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=env_bool("DRY_RUN", False),
        help="Run extraction and log Jira/Slack writes without calling Jira or Slack.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Override DRY_RUN=true and create real Jira tickets/post to Slack.",
    )
    parser.add_argument(
        "--meeting-date",
        default=os.getenv("MEETING_DATE", date.today().isoformat()),
        help="Meeting date as YYYY-MM-DD, used to resolve relative due dates.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    configure_logging()
    args = parse_args()
    if args.live:
        args.dry_run = False

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    transcript_path = Path(args.transcript)

    try:
        date.fromisoformat(args.meeting_date)
        jira_config = load_jira_config()
        slack_config = load_slack_config()
        if not args.dry_run:
            validate_live_config(jira_config, slack_config)

        transcript_text = load_text(transcript_path)
        extraction = extract_meeting_data(
            transcript_text,
            model=model,
            meeting_date=args.meeting_date,
        )
        LOGGER.info("Extracted %d action items", len(extraction["action_items"]))

        tickets = create_jira_tickets(
            extraction["action_items"],
            config=jira_config,
            dry_run=args.dry_run,
        )
        post_slack_summary(
            extraction["summary"],
            tickets,
            config=slack_config,
            dry_run=args.dry_run,
        )

        LOGGER.info("Workflow complete. Created/referenced %d Jira tickets.", len(tickets))
        return 0
    except KeyError as exc:
        LOGGER.error("Missing required environment variable: %s", exc)
        return 2
    except Exception as exc:
        LOGGER.exception("Workflow failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
