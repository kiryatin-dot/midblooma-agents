"""
AGENT 8 — Newsletter Editor
Compiles and formats the Midblooma Weekly Edit for Nufar's approval.

Trigger:  Weekly cron — Thursday 12:00
Receives: Health QA agent (approved newsletter_section from Writer)
          + Performance Watcher (week summary)
          + Trend Scout (top signal of the week)
Sends to: Nufar review link (Google Doc or MailerLite draft)

IMPORTANT: Status is ALWAYS "needs_review".
           This agent NEVER auto-sends. Nufar must explicitly approve.
"""
import json
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, DEFAULT_MODEL
from .shared.envelope import make_envelope, parse_json_response

AGENT_ID = "newsletter_editor"

SYSTEM_PROMPT = f"""
You are the Newsletter Editor for Midblooma.

Every Thursday you compile the Midblooma Weekly Edit from that week's content.

EMAIL STRUCTURE — always in this exact order:
1. Subject line: produce 3 options
   - Option A: curiosity-driven (makes reader wonder)
   - Option B: benefit-driven (clear value)
   - Option C: direct (plain statement)
   All under 50 characters. No clickbait. No ALL-CAPS.

2. Opening line: one sentence in Nufar's voice, referencing the week's big insight.
   Warm but authoritative. Founder-to-member.

3. Feature article section: use the approved newsletter_section from the Writer.
   Do not paraphrase — include it as-is, with the article link as a placeholder
   [ARTICLE_URL] if not provided.

4. Product spotlight: choose one relevant product from the marketplace data provided
   (or use placeholder [MARKETPLACE_PRODUCT_NAME] and [MARKETPLACE_PRODUCT_URL]
   if no data is provided). One sentence on why it's evidence-based and relevant.

5. Community moment: reference any events provided, or use placeholder
   [UPCOMING_EVENT]. Keep to 1–2 sentences.

6. Closing: 2–3 sentences written as if Nufar is writing directly to a member.
   Personal, warm. Sign off as "Nufar x".

7. Footer: include unsubscribe placeholder [UNSUBSCRIBE_LINK].

VOICE: warm but authoritative. Founder-to-member, not brand-to-subscriber.

Output ONLY valid JSON:
{{
  "subject_options": [
    "Option A: curiosity-driven (under 50 chars)",
    "Option B: benefit-driven (under 50 chars)",
    "Option C: direct (under 50 chars)"
  ],
  "email_html": "string — full HTML email body",
  "email_plain_text": "string — plain text version",
  "word_count": 0,
  "estimated_read_time": "X min read",
  "product_featured": {{
    "name": "string",
    "url": "string",
    "reason": "one sentence on why this product is evidence-based and relevant"
  }}
}}

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def run(
    qa_envelope: dict[str, Any],
    watcher_envelope: dict[str, Any] | None = None,
    top_signal: dict[str, Any] | None = None,
    marketplace_data: list[dict] | None = None,
    events_data: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Compile the weekly newsletter draft for Nufar's approval.

    Args:
        qa_envelope:      Health QA envelope with approved Writer output.
        watcher_envelope: Performance Watcher envelope (week summary). Optional.
        top_signal:       The top Trend Scout signal of the week. Optional.
        marketplace_data: List of marketplace products to feature. Optional.
        events_data:      List of upcoming community events. Optional.

    Returns:
        Envelope with status ALWAYS "needs_review".
        Nufar must approve before Campaign Executor sends.
    """
    run_id = qa_envelope.get("run_id", "unknown")
    approved_content = qa_envelope.get("payload", {}).get("approved_content", {})
    newsletter_section = approved_content.get("newsletter_section", "")

    # Build context for the newsletter
    watcher_summary = ""
    if watcher_envelope:
        watcher_summary = watcher_envelope.get("payload", {}).get("digest_summary", "")

    user_message = (
        "Compile the Midblooma Weekly Edit newsletter. "
        "Return only valid JSON.\n\n"
        f"APPROVED NEWSLETTER SECTION:\n{newsletter_section}\n\n"
        f"WEEK PERFORMANCE SUMMARY:\n{watcher_summary or '(not provided)'}\n\n"
        f"TOP TREND SIGNAL OF THE WEEK:\n"
        f"{json.dumps(top_signal, indent=2) if top_signal else '(not provided)'}\n\n"
        f"MARKETPLACE PRODUCTS:\n"
        f"{json.dumps(marketplace_data, indent=2) if marketplace_data else '(not provided — use placeholder)'}\n\n"
        f"UPCOMING EVENTS:\n"
        f"{json.dumps(events_data, indent=2) if events_data else '(not provided — use placeholder)'}"
    )

    client = anthropic.Anthropic()

    with client.messages.stream(
        model=DEFAULT_MODEL,
        max_tokens=8192,
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
            notes="Newsletter Editor returned unparseable JSON. Nufar must review and rebuild.",
        )

    # Status is ALWAYS needs_review — this agent never auto-sends
    return make_envelope(
        agent_id=AGENT_ID,
        run_id=run_id,
        cadence="weekly",
        status="needs_review",
        payload=payload,
        notes=(
            "Newsletter draft ready for Nufar's review. "
            f"Estimated read time: {payload.get('estimated_read_time', 'unknown')}. "
            f"Word count: {payload.get('word_count', 0)}. "
            "IMPORTANT: This newsletter will NOT be sent until Nufar approves."
        ),
    )


if __name__ == "__main__":
    import uuid

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
                "newsletter_section": (
                    "This week we looked at magnesium and sleep during menopause. "
                    "A 2021 trial in Sleep Medicine found a 30% reduction in insomnia "
                    "severity with magnesium supplementation. Read the full evidence "
                    "review at [ARTICLE_URL]. Always consult your healthcare provider "
                    "before starting supplements."
                ),
            },
        },
        "notes": "",
    }

    sample_top_signal = {
        "rank": 1,
        "source": "Reddit r/menopause",
        "title": "Anyone tried magnesium glycinate for sleep?",
        "pain_point": "Women struggling with menopause-related insomnia.",
        "content_angle": "Evidence-based magnesium guide for sleep.",
    }

    result = run(
        qa_envelope=sample_qa_envelope,
        top_signal=sample_top_signal,
    )
    print(json.dumps(result, indent=2))
