"""
AGENT 3 — Content Strategist
Picks one topic per week and produces a full research brief with sources and angle.

Trigger:  Weekly cron — Monday 08:00, consuming Trend Scout's last 7 days of output
Receives: Trend Scout envelope (7-day accumulation from Google Sheet)
Sends to: Writer agent

Output status: "ok" if 3+ sources found, "needs_review" if fewer than 2 sources.
"""
import json
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, DEFAULT_MODEL
from .shared.envelope import make_envelope, parse_json_response

AGENT_ID = "content_strategist"

SYSTEM_PROMPT = f"""
You are the Content Strategist for Midblooma, the modern menopause hub.

Every Monday you receive 7 days of trend signals. Your job:
1. Score each signal on: SEO potential (1–5), audience relevance (1–5),
   evidence availability (1–5). Multiply the three scores for a total.
2. Select the highest-scoring topic NOT covered in the past 4 weeks
   (the content log is provided in the user message).
3. Research PubMed for the 3 most current supporting studies on that topic.
4. Produce a complete content brief for the Writer agent.

RESEARCH RULES:
- Only cite peer-reviewed research, NICE, The Menopause Society, NHS, or ACOG.
- Verify the study applies to women aged 40–60.
- Never cite studies older than 10 years unless they are landmark studies.
- If you cannot find 3 sources, include as many as you can and flag the shortfall.

CONTENT TYPE SELECTION:
- "article"    — in-depth explanatory piece
- "FAQ"        — question-and-answer format for high search-intent topics
- "comparison" — head-to-head comparison of two approaches or products

Output ONLY valid JSON, no prose outside the JSON:
{{
  "topic": "string",
  "headline_draft": "string",
  "audience_pain_point": "one sentence",
  "midblooma_angle": "one sentence",
  "supporting_studies": [
    {{
      "title": "string",
      "authors": "string",
      "year": 2024,
      "journal": "string",
      "key_finding": "one sentence",
      "url": "string"
    }}
  ],
  "content_type": "article | FAQ | comparison",
  "word_count_target": 1200,
  "cta": "string — call to action for the end of the article"
}}

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def run(
    trend_envelopes: list[dict[str, Any]],
    content_log: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute the Content Strategist and return a handoff envelope.

    Args:
        trend_envelopes: List of Trend Scout envelopes from the past 7 days.
        content_log:     List of topic strings published in the last 4 weeks.
        run_id:          UUID for this run (taken from first envelope if not provided).

    Returns:
        Handoff envelope dict with the content brief as payload.
    """
    if not trend_envelopes:
        raise ValueError("content_strategist.run() requires at least one trend envelope")

    if run_id is None:
        run_id = trend_envelopes[0].get("run_id", "unknown")

    if content_log is None:
        content_log = []

    # Aggregate all signals from the 7-day window
    all_signals = []
    for envelope in trend_envelopes:
        signals = envelope.get("payload", {}).get("signals", [])
        all_signals.extend(signals)

    user_message = (
        "Here are the trend signals from the past 7 days:\n\n"
        f"{json.dumps(all_signals, indent=2)}\n\n"
        "Content covered in the last 4 weeks (do NOT repeat these topics):\n"
        f"{json.dumps(content_log, indent=2)}\n\n"
        "Score each signal, select the best topic, research PubMed for supporting "
        "studies, and return the complete content brief as valid JSON."
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
            notes="Content Strategist returned unparseable JSON — Nufar to review.",
        )

    # Determine status based on source count
    study_count = len(payload.get("supporting_studies", []))
    if study_count >= 3:
        status = "ok"
        notes = f"Topic selected: '{payload.get('topic', '')}'. {study_count} studies found."
    elif study_count >= 2:
        status = "needs_review"
        notes = (
            f"Topic selected: '{payload.get('topic', '')}'. "
            f"Only {study_count} sources found (target: 3). Nufar to decide whether to proceed."
        )
    else:
        status = "needs_review"
        notes = (
            f"Topic selected: '{payload.get('topic', '')}'. "
            f"Fewer than 2 sources found. Nufar must decide whether to proceed."
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

    # Smoke-test with a synthetic 7-day trend batch
    sample_signals = [
        {
            "rank": 1,
            "source": "Reddit r/menopause",
            "title": "Anyone tried magnesium glycinate for sleep?",
            "url": "https://reddit.com/r/menopause/example",
            "engagement_score": 842,
            "pain_point": "Women are struggling with menopause-related insomnia.",
            "content_angle": "Midblooma could publish an evidence-based guide to magnesium and sleep.",
        }
    ]
    sample_envelope = {
        "agent_id": "trend_scout",
        "timestamp": "2026-03-16T06:00:00Z",
        "run_id": str(uuid.uuid4()),
        "cadence": "daily",
        "status": "ok",
        "payload": {"signals": sample_signals, "date": "2026-03-16"},
        "notes": "",
    }

    result = run([sample_envelope], content_log=["HRT and bone density"])
    print(json.dumps(result, indent=2))
