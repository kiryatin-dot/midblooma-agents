"""
AGENT 6 — Social Campaign Manager
Builds the weekly social campaign plan from QA-approved captions.

Trigger:  Fires when Health QA envelope arrives with status "ok"
Receives: Health QA agent (approved Writer output)
Sends to: Campaign Executor agent

Output status is always "ok".
"""
import json
from datetime import date, timedelta
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, DEFAULT_MODEL, SCHEDULE_CONFIG
from .shared.envelope import make_envelope, parse_json_response

AGENT_ID = "social_campaign_manager"

SYSTEM_PROMPT = f"""
You are the Social Campaign Manager for Midblooma.

You receive QA-approved content and build the weekly posting schedule.

SCHEDULE (always use these exact days/times):
{json.dumps(SCHEDULE_CONFIG, indent=2)}

For each post produce:
- platform:              "Instagram" | "LinkedIn" | "WhatsApp" | "Instagram Stories"
- post_type:             "carousel" | "article_share" | "story" | "broadcast" | "fact_post"
- caption:               The APPROVED caption text — do NOT edit or paraphrase it.
                         Preserve it character-for-character.
- hashtags:              List of 5–10 tags. ALWAYS include:
                           #Menopause #Perimenopause #MenopauseHealth
                         Plus 2–7 topic-specific tags.
                         NEVER use vague lifestyle tags (#wellness, #selfcare)
                         without a specific pair tag alongside them.
- scheduled_time:        Exact datetime string in the format "YYYY-MM-DD HH:MM"
                         calculated from the week_of date.
- visual_brief:          ONE sentence describing what Canva should show for this post.
- link_in_bio_required:  true | false

Output ONLY valid JSON, no prose:
{{
  "week_of": "YYYY-MM-DD (Monday of the campaign week)",
  "posts": [
    {{
      "platform": "string",
      "post_type": "string",
      "caption": "string — exact approved text, unchanged",
      "hashtags": ["#Menopause", "..."],
      "scheduled_time": "YYYY-MM-DD HH:MM",
      "visual_brief": "string",
      "link_in_bio_required": true
    }}
  ]
}}

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def _next_monday(from_date: date | None = None) -> date:
    """Return the next Monday on or after from_date (defaults to today)."""
    d = from_date or date.today()
    days_ahead = (7 - d.weekday()) % 7  # 0 = Monday
    if days_ahead == 0:
        return d
    return d + timedelta(days=days_ahead)


def run(
    qa_envelope: dict[str, Any],
    week_of: str | None = None,
) -> dict[str, Any]:
    """
    Execute the Social Campaign Manager and return a handoff envelope.

    Args:
        qa_envelope: The full envelope dict from the Health QA agent (status "ok").
        week_of:     ISO date string for the Monday of the campaign week.
                     Defaults to the next Monday from today.

    Returns:
        Handoff envelope with the campaign schedule as payload.
    """
    if qa_envelope.get("status") != "ok":
        raise ValueError(
            "Social Campaign Manager requires a QA envelope with status 'ok'. "
            f"Got: {qa_envelope.get('status')}"
        )

    run_id = qa_envelope.get("run_id", "unknown")
    approved_content = qa_envelope.get("payload", {}).get("approved_content", {})

    if week_of is None:
        week_of = _next_monday().isoformat()

    user_message = (
        f"The campaign week starts on Monday {week_of}. "
        "Build the posting schedule from the approved content below. "
        "Use exact scheduled datetimes based on the week_of date. "
        "Return only valid JSON.\n\n"
        f"APPROVED CONTENT:\n{json.dumps(approved_content, indent=2)}"
    )

    client = anthropic.Anthropic()

    with client.messages.stream(
        model=DEFAULT_MODEL,
        max_tokens=4096,
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
        payload = {"parse_error": text[:500]}
        return make_envelope(
            agent_id=AGENT_ID,
            run_id=run_id,
            cadence="weekly",
            status="needs_review",
            payload=payload,
            notes="Campaign Manager returned unparseable JSON — Nufar to review.",
        )

    post_count = len(payload.get("posts", []))
    return make_envelope(
        agent_id=AGENT_ID,
        run_id=run_id,
        cadence="weekly",
        status="ok",
        payload=payload,
        notes=f"Campaign plan built for week of {week_of}. {post_count} posts scheduled.",
    )


if __name__ == "__main__":
    import uuid

    # Smoke-test with a minimal QA-passed envelope
    sample_qa_envelope = {
        "agent_id": "health_qa",
        "timestamp": "2026-03-16T09:00:00Z",
        "run_id": str(uuid.uuid4()),
        "cadence": "weekly",
        "status": "ok",
        "payload": {
            "qa_status": "pass",
            "issues": [],
            "approved_content": {
                "article": {
                    "headline": "Can Magnesium Help You Sleep Better Through Menopause?",
                    "intro": "Sleep disruption is one of the most common symptoms...",
                    "sections": [],
                    "conclusion": "Magnesium is a well-studied option — not a cure.",
                    "cta": "Explore Midblooma's supplement guide at midblooma.com/supplements",
                },
                "social": {
                    "instagram_carousel": "60% of women in peri report poor sleep. Here's what works.",
                    "linkedin": "New research on magnesium and menopause sleep — a summary for women 40+.",
                    "instagram_stories": "Is magnesium your missing sleep ingredient? Vote below 👇",
                    "whatsapp": "Hey — sharing this because sleep has been a game-changer topic this week.",
                    "save_fact": "Stat: 60% of perimenopausal women experience insomnia (Sleep Medicine, 2021). Save this.",
                },
                "newsletter_section": "This week we look at magnesium and sleep...",
                "citations_used": [],
            },
        },
        "notes": "",
    }

    result = run(sample_qa_envelope, week_of="2026-03-17")
    print(json.dumps(result, indent=2))
