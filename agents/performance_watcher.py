"""
AGENT 2 — Performance Watcher
Tracks Midblooma's key metrics daily and flags anomalies before Nufar sees them.

Trigger:  Daily cron — 07:00, after Trend Scout completes
Receives: Midblooma platform data (via API or Zapier webhook) + previous day's log
Sends to: Nufar daily digest email (via n8n Gmail node)

Output status is always "ok" — Watcher never blocks.

Anomaly rule: flag any metric that moves more than 20% vs the 7-day average.
"""
import json
from datetime import date
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, DEFAULT_MODEL
from .shared.envelope import make_envelope, new_run_id, parse_json_response

AGENT_ID = "performance_watcher"

SYSTEM_PROMPT = f"""
You are the Performance Watcher for Midblooma.

Each day you receive yesterday's platform metrics.
Compare them to the 7-day rolling average provided.

ANOMALY RULE:
Flag any metric that moves MORE THAN 20% in either direction
vs the 7-day average. Label each anomaly as 'positive' or 'investigate'.

DIGEST SUMMARY:
Write a 3-sentence digest_summary in Midblooma voice for Nufar to read in 30 seconds.
- Lead with the most important number.
- Be direct. No filler.
- Flag any anomalies clearly.

Output ONLY valid JSON:
{{
  "date": "ISO date string",
  "metrics": {{
    "checker_uses": 0,
    "new_members": 0,
    "total_members": 0,
    "social_reach": 0,
    "newsletter_open_rate": 0.0
  }},
  "anomalies": [
    {{
      "metric": "string",
      "delta": "string e.g. '+35% vs 7-day avg'",
      "flag": "positive | investigate"
    }}
  ],
  "digest_summary": "string — 3 sentences, direct, Midblooma voice"
}}

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def run(
    today_metrics: dict[str, Any],
    seven_day_averages: dict[str, Any],
    run_id: str | None = None,
    cadence: str = "daily",
) -> dict[str, Any]:
    """
    Execute the Performance Watcher and return a handoff envelope.

    Args:
        today_metrics:      Dict of today's metric values.
                            Keys: checker_uses, new_members, total_members,
                                  social_reach, newsletter_open_rate
        seven_day_averages: Dict of 7-day rolling averages for the same keys.
        run_id:             UUID for this run (generated if not provided).
        cadence:            "daily" (default) or "weekly".

    Returns:
        Envelope with metrics, anomalies, and a 3-sentence digest for Nufar.
        Status is always "ok".
    """
    if run_id is None:
        run_id = new_run_id()

    today = date.today().isoformat()

    user_message = (
        f"Date: {today}\n\n"
        f"TODAY'S METRICS:\n{json.dumps(today_metrics, indent=2)}\n\n"
        f"7-DAY ROLLING AVERAGES:\n{json.dumps(seven_day_averages, indent=2)}\n\n"
        "Compare today's metrics to the averages. Flag anomalies (>20% movement). "
        "Write the 3-sentence digest. Return only valid JSON."
    )

    client = anthropic.Anthropic()

    with client.messages.stream(
        model=DEFAULT_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        response = stream.get_final_message()

    text = next(
        (block.text for block in response.content if block.type == "text"), ""
    )

    try:
        payload = parse_json_response(text)
    except json.JSONDecodeError:
        payload = {
            "date": today,
            "metrics": today_metrics,
            "anomalies": [],
            "digest_summary": "Performance data received but could not be parsed. Please review manually.",
            "parse_error": text[:500],
        }

    anomaly_count = len(payload.get("anomalies", []))
    notes = (
        f"Daily digest for {today}. "
        f"{anomaly_count} anomaly/anomalies flagged."
        if anomaly_count
        else f"Daily digest for {today}. All metrics within normal range."
    )

    # Watcher always returns "ok"
    return make_envelope(
        agent_id=AGENT_ID,
        run_id=run_id,
        cadence=cadence,
        status="ok",
        payload=payload,
        notes=notes,
    )


if __name__ == "__main__":
    today_metrics = {
        "checker_uses": 312,
        "new_members": 28,
        "total_members": 4201,
        "social_reach": 14800,
        "newsletter_open_rate": 0.47,
    }

    seven_day_averages = {
        "checker_uses": 260,
        "new_members": 15,
        "total_members": 4175,
        "social_reach": 11000,
        "newsletter_open_rate": 0.42,
    }

    result = run(today_metrics, seven_day_averages)
    print(json.dumps(result, indent=2))
