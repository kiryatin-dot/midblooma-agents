"""
AGENT 1 — Trend Scout
Scans the internet daily and surfaces the top 5 signals relevant to
Midblooma's audience.

Trigger:  Daily cron — 06:00 every morning
Receives: n8n scheduler (no upstream agent)
Sends to: Content Strategist (weekly accumulation) + Performance Watcher (daily digest)

Output status is always "ok" — Scout never blocks.
"""
import json
from datetime import date
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, DEFAULT_MODEL
from .shared.envelope import make_envelope, new_run_id, parse_json_response

AGENT_ID = "trend_scout"

SYSTEM_PROMPT = f"""
You are the Trend Scout for Midblooma, the modern menopause hub.

Your job: every morning, scan Reddit, PubMed, Google Trends, and social platforms
for the top 5 conversations, questions, or research items most relevant to women
aged 40–60 navigating perimenopause and menopause.

For each signal, extract:
- The raw source and URL
- The engagement score (upvotes / shares / citations — estimate if not available)
- The core pain point or question in ONE sentence
- The content angle Midblooma could take in ONE sentence

Rank them 1–5 by relevance and engagement potential.

Output ONLY valid JSON matching this exact schema — no prose, no commentary:
{{
  "signals": [
    {{
      "rank": 1,
      "source": "string (e.g. Reddit r/menopause, PubMed, Google Trends, X/Twitter)",
      "title": "string — headline or thread title",
      "url": "string — direct URL if available, else empty string",
      "engagement_score": 0,
      "pain_point": "one sentence describing the core pain point or question",
      "content_angle": "one sentence describing the angle Midblooma could take"
    }}
  ],
  "date": "ISO date string e.g. 2026-03-16"
}}

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def run(
    run_id: str | None = None,
    cadence: str = "daily",
    context_hint: str = "",
) -> dict[str, Any]:
    """
    Execute the Trend Scout and return a handoff envelope.

    Args:
        run_id:       UUID for this run (generated if not provided).
        cadence:      "daily" (default) or "weekly".
        context_hint: Optional extra context to narrow the search
                      (e.g. a breaking news topic).

    Returns:
        Handoff envelope dict with payload matching the signal schema.
    """
    if run_id is None:
        run_id = new_run_id()

    today = date.today().isoformat()

    user_message = (
        f"Today's date is {today}. "
        "Please scan Reddit (r/menopause, r/Perimenopause, r/WomensHealth), "
        "PubMed RSS (menopause filter), Google Trends, X/Twitter, "
        "and relevant public Facebook groups for the top 5 signals. "
    )
    if context_hint:
        user_message += f"\n\nAdditional context: {context_hint}"

    user_message += "\n\nReturn only valid JSON."

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
            "signals": [],
            "date": today,
            "parse_error": text[:500],
        }

    # Scout always returns "ok"
    return make_envelope(
        agent_id=AGENT_ID,
        run_id=run_id,
        cadence=cadence,
        status="ok",
        payload=payload,
        notes=f"Trend Scout completed for {today}. {len(payload.get('signals', []))} signals found.",
    )


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
