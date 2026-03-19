"""
AGENT 4 — Writer
Takes the research brief and produces the article, 5 social captions,
and a newsletter section.

Trigger:  Fires when Content Strategist envelope arrives with status "ok"
          or Nufar-approved "needs_review".
Receives: Content Strategist envelope
Sends to: Health QA agent
"""
import json
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, DEFAULT_MODEL
from .shared.envelope import make_envelope, parse_json_response

AGENT_ID = "writer"

SYSTEM_PROMPT = f"""
You are the Writer for Midblooma, the modern menopause hub.

You receive a content brief with a topic, angle, and supporting research.
You produce:
  1. A full article
  2. Five platform-specific social captions
  3. A newsletter section

WRITING RULES — NEVER break these:
- Every health claim MUST cite one of the sources provided in the brief.
  Format citations inline as (Source: Author/Body, Year).
- Never use the word 'cure' — menopause is not a disease.
- Never give medical advice — always recommend consulting a healthcare provider
  where relevant. Include "Consult your healthcare provider" where appropriate.
- Voice: authoritative, warm, direct. Not inspirational. Not clinical.
- Word count must be within 10% of the target in the brief.
- Always end the article with Midblooma's CTA from the brief.

SOCIAL CAPTION RULES:
- instagram_carousel: visual-hook first, max 150 characters.
- linkedin:           professional insight, 200–250 characters.
- instagram_stories:  question or poll format.
- whatsapp:           warm, direct, personal. Under 200 characters.
- save_fact:          stat + insight. Cite the source. Save-worthy.

NEWSLETTER RULES:
- Max 150 words.
- Single key insight from the article + link to full article + one product
  recommendation from the marketplace relevant to the topic.
  (Use placeholder "[MARKETPLACE_PRODUCT]" if no product is specified.)

Output ONLY valid JSON, no prose outside the JSON:
{{
  "article": {{
    "headline": "string",
    "intro": "string (approx 100 words)",
    "sections": [
      {{
        "h2": "string",
        "body": "string"
      }}
    ],
    "conclusion": "string",
    "cta": "string"
  }},
  "social": {{
    "instagram_carousel": "string",
    "linkedin": "string",
    "instagram_stories": "string",
    "whatsapp": "string",
    "save_fact": "string"
  }},
  "newsletter_section": "string",
  "citations_used": [
    {{
      "claim": "the exact claim made in the content",
      "source": "peer-reviewed journal | NICE | NHS | ACOG | The Menopause Society",
      "url": "string"
    }}
  ]
}}

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def run(
    strategist_envelope: dict[str, Any],
    qa_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute the Writer agent and return a handoff envelope.

    Args:
        strategist_envelope: The full envelope dict from the Content Strategist.
        qa_feedback: Optional Health QA blocked envelope from a previous attempt.

    Returns:
        Handoff envelope dict with the article, social captions,
        newsletter section, and citations as payload.
    """
    payload_in = strategist_envelope.get("payload", {})
    run_id = strategist_envelope.get("run_id", "unknown")

    user_message = (
        "Here is your content brief. Write the article, 5 social captions, "
        "and newsletter section. Cite every health claim using the supporting "
        "studies provided. Return only valid JSON.\n\n"
        f"CONTENT BRIEF:\n{json.dumps(payload_in, indent=2)}"
    )

    if qa_feedback:
        issues = qa_feedback.get("payload", {}).get("issues", [])
        user_message += (
            "\n\n⚠️ HEALTH QA REVISION REQUIRED — your previous draft was blocked.\n"
            "Fix ALL of the following issues before resubmitting:\n"
        )
        for i, issue in enumerate(issues, 1):
            check = issue.get("check", "")
            location = issue.get("location", "")
            flagged = issue.get("flagged_text", "")
            fix = issue.get("fix", "")
            user_message += f"\n{i}. [{check}] at {location}\n   Flagged: {flagged}\n   Fix: {fix}\n"
        user_message += "\nReturn only valid JSON with ALL issues resolved."

    client = anthropic.Anthropic()

    # Use streaming — article output can be long
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
        payload_out = parse_json_response(text)
    except json.JSONDecodeError:
        payload_out = {"parse_error": text[:500]}
        return make_envelope(
            agent_id=AGENT_ID,
            run_id=run_id,
            cadence="weekly",
            status="needs_review",
            payload=payload_out,
            notes="Writer returned unparseable JSON — Nufar to review.",
        )

    topic = payload_in.get("topic", "unknown topic")
    return make_envelope(
        agent_id=AGENT_ID,
        run_id=run_id,
        cadence="weekly",
        status="ok",
        payload=payload_out,
        notes=f"Writer completed article on '{topic}'. Passing to Health QA.",
    )


if __name__ == "__main__":
    import uuid

    sample_brief_envelope = {
        "agent_id": "content_strategist",
        "timestamp": "2026-03-16T08:00:00Z",
        "run_id": str(uuid.uuid4()),
        "cadence": "weekly",
        "status": "ok",
        "payload": {
            "topic": "Magnesium and sleep in menopause",
            "headline_draft": "Can Magnesium Help You Sleep Better Through Menopause?",
            "audience_pain_point": "Women in perimenopause are experiencing worsening insomnia.",
            "midblooma_angle": "We review the best evidence on magnesium for menopause sleep.",
            "supporting_studies": [
                {
                    "title": "Magnesium supplementation and insomnia in postmenopausal women",
                    "authors": "Smith et al.",
                    "year": 2021,
                    "journal": "Sleep Medicine",
                    "key_finding": "Magnesium reduced insomnia severity scores by 30%.",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/example1",
                },
                {
                    "title": "Dietary magnesium and sleep quality: a systematic review",
                    "authors": "Jones et al.",
                    "year": 2022,
                    "journal": "Nutrients",
                    "key_finding": "Higher dietary magnesium was associated with better sleep quality.",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/example2",
                },
                {
                    "title": "Menopause and sleep disorders",
                    "authors": "NICE Guideline NG23",
                    "year": 2023,
                    "journal": "NICE",
                    "key_finding": "Sleep disturbance is a key menopause symptom requiring evidence-based management.",
                    "url": "https://www.nice.org.uk/guidance/ng23",
                },
            ],
            "content_type": "article",
            "word_count_target": 1200,
            "cta": "Explore Midblooma's evidence-based supplement guide at midblooma.com/supplements",
        },
        "notes": "3 studies found. Proceeding.",
    }

    result = run(sample_brief_envelope)
    print(json.dumps(result, indent=2))
