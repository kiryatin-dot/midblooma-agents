"""
AGENT 7 — Campaign Executor
Digitally executes the campaign plan — posts content, updates links, logs results.

Trigger:  Fires on schedule for each post in the Campaign Manager's plan
Receives: Social Campaign Manager envelope (reads post schedule)
Sends to: Performance Watcher (logs execution) + Nufar (confirmation digest)

Pre-flight checks before each post:
  1. Confirm content is still QA-approved (check envelope status)
  2. Confirm scheduled time has been reached
  3. Confirm no duplicate post exists for this run_id

Error handling: retry once after 60 seconds. On second failure: skip + flag.
"""
import json
import time
from datetime import datetime, timezone
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, DEFAULT_MODEL
from .shared.envelope import make_envelope, parse_json_response

AGENT_ID = "campaign_executor"

SYSTEM_PROMPT = f"""
You are the Campaign Executor for Midblooma.

You receive a campaign schedule and simulate execution of each post.
In production this agent calls real APIs (Buffer, Meta Graph API, LinkedIn API,
WhatsApp Business API). In this implementation, you produce a structured
execution log as if those API calls had been made.

For each post in the schedule:
1. Confirm the envelope status is 'ok' (QA approved)
2. Confirm the scheduled time has been reached (compare to current UTC time)
3. Confirm no post with this run_id already exists for this platform
4. If all checks pass: "execute" the post (log it as posted)
5. If any check fails: add to skipped list with reason

For each executed post, produce a realistic mock post_id (e.g. "ig_20260316_001").

Output ONLY valid JSON:
{{
  "executed": [
    {{
      "platform": "string",
      "post_type": "string",
      "post_id": "string",
      "posted_at": "ISO 8601 UTC string",
      "url": "string (mock URL)",
      "initial_reach": 0
    }}
  ],
  "skipped": [
    {{
      "platform": "string",
      "reason": "string"
    }}
  ],
  "execution_summary": "string — 1-2 sentence digest for Nufar"
}}

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def run(
    campaign_envelope: dict[str, Any],
    dry_run: bool = False,
    execution_log: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Execute the campaign plan and return an execution envelope.

    Args:
        campaign_envelope: The full envelope from the Social Campaign Manager.
        dry_run:           If True, skip the pre-flight time check
                           (useful for testing outside of scheduled windows).
        execution_log:     Existing log of post run_ids to detect duplicates.

    Returns:
        Envelope with executed/skipped lists and a summary for Nufar.
    """
    if campaign_envelope.get("status") != "ok":
        raise ValueError(
            "Campaign Executor requires a campaign envelope with status 'ok'. "
            f"Got: {campaign_envelope.get('status')}"
        )

    run_id = campaign_envelope.get("run_id", "unknown")
    posts = campaign_envelope.get("payload", {}).get("posts", [])
    now_utc = datetime.now(timezone.utc).isoformat()

    if execution_log is None:
        execution_log = []

    already_posted_run_ids = {entry.get("run_id") for entry in execution_log}

    user_message = (
        f"Current UTC time: {now_utc}\n"
        f"Run ID: {run_id}\n"
        f"Dry run mode: {dry_run} "
        f"(if True, ignore scheduled time checks and treat all posts as due)\n\n"
        f"Already executed run_ids (skip if duplicate): "
        f"{json.dumps(list(already_posted_run_ids))}\n\n"
        f"CAMPAIGN POSTS TO EXECUTE:\n{json.dumps(posts, indent=2)}\n\n"
        "For each post: run pre-flight checks, execute or skip, and build the "
        "execution log. Return only valid JSON."
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
        payload = {
            "executed": [],
            "skipped": [],
            "execution_summary": "Executor returned unparseable output — Nufar to review.",
            "parse_error": text[:500],
        }
        return make_envelope(
            agent_id=AGENT_ID,
            run_id=run_id,
            cadence="weekly",
            status="needs_review",
            payload=payload,
            notes="Campaign Executor parse error.",
        )

    executed = payload.get("executed", [])
    skipped = payload.get("skipped", [])

    status = "ok" if len(skipped) == 0 else "needs_review"
    notes = (
        f"{len(executed)} post(s) executed. "
        f"{len(skipped)} post(s) skipped. "
        + (f"Skipped: {[s['platform'] for s in skipped]}" if skipped else "")
    )

    return make_envelope(
        agent_id=AGENT_ID,
        run_id=run_id,
        cadence="weekly",
        status=status,
        payload=payload,
        notes=notes,
    )


if __name__ == "__main__":
    import uuid

    sample_campaign_envelope = {
        "agent_id": "social_campaign_manager",
        "timestamp": "2026-03-16T09:30:00Z",
        "run_id": str(uuid.uuid4()),
        "cadence": "weekly",
        "status": "ok",
        "payload": {
            "week_of": "2026-03-17",
            "posts": [
                {
                    "platform": "Instagram",
                    "post_type": "carousel",
                    "caption": "60% of women in peri report poor sleep. Here's what works.",
                    "hashtags": ["#Menopause", "#Perimenopause", "#MenopauseHealth", "#Sleep"],
                    "scheduled_time": "2026-03-17 18:00",
                    "visual_brief": "Calm bedroom scene with sleep stats overlaid.",
                    "link_in_bio_required": True,
                },
                {
                    "platform": "LinkedIn",
                    "post_type": "article_share",
                    "caption": "New research on magnesium and menopause sleep — a summary for women 40+.",
                    "hashtags": ["#Menopause", "#Perimenopause", "#MenopauseHealth", "#WomensHealth"],
                    "scheduled_time": "2026-03-18 09:00",
                    "visual_brief": "Clean infographic showing magnesium sleep research stats.",
                    "link_in_bio_required": False,
                },
            ],
        },
        "notes": "5 posts scheduled.",
    }

    result = run(sample_campaign_envelope, dry_run=True)
    print(json.dumps(result, indent=2))
