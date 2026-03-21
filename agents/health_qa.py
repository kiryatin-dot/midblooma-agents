"""
AGENT 5 — Health QA Agent
Blocks any content that makes unsourced health claims or violates
Midblooma's editorial rules.

Built first because it has no upstream agent dependencies and is the
easiest to unit-test in isolation.

Input:  Writer agent envelope  (status "ok")
Output: QA envelope            (status "ok" | "blocked")
"""
import json
import re
from typing import Any

import anthropic

from .shared.constants import SHARED_BRAND_CONTEXT, BANNED_WORDS, APPROVED_SOURCES, DEFAULT_MODEL
from .shared.envelope import make_envelope, parse_json_response

AGENT_ID = "health_qa"

SYSTEM_PROMPT = f"""
You are the Health QA Agent for Midblooma.
You review every piece of content before it is published. You are the final
guardian of Midblooma's promise to be evidence-based and trustworthy.

Run these four checks IN ORDER:

1. CLAIMS CHECK
   Every sentence that makes a health claim must have a corresponding entry
   in citations_used. A "health claim" is any statement about what a
   substance, behaviour, or intervention does to the body or symptoms.
   Flag any health claim whose cited source does not appear in citations_used.

2. LANGUAGE CHECK
   Scan for these banned phrases (case-insensitive):
   {json.dumps(BANNED_WORDS)}
   Flag any match with the exact text and its location.

3. MEDICAL ADVICE CHECK
   Flag ONLY sentences that do ONE of the following WITHOUT a consultation
   qualifier anywhere in the same paragraph or section:
   a) Instruct a reader to START, STOP, or CHANGE a prescription medication,
      hormone therapy, or specific supplement dose.
   b) Instruct a reader to DEMAND or REQUEST a specific medical test using
      direct imperative language (e.g. "Request X test", "Get X tested").
   DO NOT flag:
   - General lifestyle advice (sleep, diet, exercise, stress) that has a
     "work with your healthcare provider" qualifier anywhere in the same
     section or paragraph.
   - Screening or test SUGGESTIONS framed as "ask your provider about",
     "discuss with your healthcare provider whether", or "it may be worth
     discussing".
   - Advocacy language like "it's reasonable to ask" or "you can request
     a referral" that is framed as a suggestion, not a command.
   A "consultation qualifier" is any of: "consult your healthcare provider",
   "discuss with your healthcare provider", "work with your healthcare
   provider", "ask your doctor", "speak with your GP", or similar.

4. SOURCE CHECK
   Every source in citations_used must be one of:
   {json.dumps(APPROVED_SOURCES)}
   Flag any source that does not match these types.

RESPONSE FORMAT — output ONLY valid JSON, no prose:
{{
  "qa_status": "pass" | "fail",
  "issues": [
    {{
      "check": "CLAIMS CHECK | LANGUAGE CHECK | MEDICAL ADVICE CHECK | SOURCE CHECK",
      "location": "article.sections[1].body | social.linkedin | newsletter_section | etc.",
      "flagged_text": "exact sentence or phrase",
      "fix_instruction": "specific instruction for the Writer to fix this"
    }}
  ],
  "approved_content": <original Writer payload if qa_status is pass, null if fail>
}}

Zero tolerance for ambiguity. If ANY check fails, qa_status is "fail".

Brand context:
{SHARED_BRAND_CONTEXT}
""".strip()


def run(writer_envelope: dict[str, Any]) -> dict[str, Any]:
    """
    Takes the Writer agent's envelope and returns a QA envelope.

    Args:
        writer_envelope: The full envelope dict from the Writer agent.

    Returns:
        A new envelope with agent_id "health_qa" and status "ok" or "blocked".
    """
    payload = writer_envelope.get("payload", {})
    run_id = writer_envelope.get("run_id", "unknown")
    cadence = writer_envelope.get("cadence", "weekly")

    # Build the user message — pass the full Writer payload for review
    user_message = (
        "Please review the following content from the Writer agent and run all "
        "four QA checks. Return only valid JSON.\n\n"
        f"WRITER PAYLOAD:\n{json.dumps(payload, indent=2)}"
    )

    client = anthropic.Anthropic()

    with client.messages.stream(
        model=DEFAULT_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        response = stream.get_final_message()

    # Extract text response
    text = next(
        (block.text for block in response.content if block.type == "text"), ""
    )

    try:
        qa_result = parse_json_response(text)
    except json.JSONDecodeError:
        # If Claude returns unparseable JSON, treat it as a blocker
        qa_result = {
            "qa_status": "fail",
            "issues": [
                {
                    "check": "CLAIMS CHECK",
                    "location": "unknown",
                    "flagged_text": text[:200],
                    "fix_instruction": "QA agent returned unparseable output — resubmit.",
                }
            ],
            "approved_content": None,
        }

    qa_status = qa_result.get("qa_status", "fail")
    envelope_status = "ok" if qa_status == "pass" else "blocked"

    notes = ""
    if envelope_status == "blocked":
        issue_count = len(qa_result.get("issues", []))
        notes = (
            f"QA FAILED — {issue_count} issue(s) found. "
            "Content returned to Writer for correction."
        )

    return make_envelope(
        agent_id=AGENT_ID,
        run_id=run_id,
        cadence=cadence,
        status=envelope_status,
        payload=qa_result,
        notes=notes,
    )


# ── Local check helpers (used by tests without hitting the API) ──────────────

def local_language_check(text: str) -> list[str]:
    """Return a list of banned words found in text (case-insensitive)."""
    found = []
    for word in BANNED_WORDS:
        if re.search(re.escape(word), text, re.IGNORECASE):
            found.append(word)
    return found


def local_source_check(sources: list[str]) -> list[str]:
    """Return any sources that are not in APPROVED_SOURCES."""
    invalid = []
    for source in sources:
        if not any(
            approved.lower() in source.lower() for approved in APPROVED_SOURCES
        ):
            invalid.append(source)
    return invalid


if __name__ == "__main__":
    import sys
    import uuid

    # Quick smoke-test with a minimal Writer envelope
    sample_writer_envelope = {
        "agent_id": "writer",
        "timestamp": "2026-03-16T08:00:00Z",
        "run_id": str(uuid.uuid4()),
        "cadence": "weekly",
        "status": "ok",
        "payload": {
            "article": {
                "headline": "How Magnesium Supports Sleep During Menopause",
                "intro": "Sleep disruption affects up to 60% of women in perimenopause.",
                "sections": [
                    {
                        "h2": "The evidence",
                        "body": (
                            "A 2021 randomised trial published in the journal Sleep Medicine "
                            "found magnesium supplementation reduced insomnia severity in "
                            "postmenopausal women. Consult your healthcare provider before "
                            "starting any supplement."
                        ),
                    }
                ],
                "conclusion": "Magnesium is one tool — not a cure — in your sleep toolkit.",
                "cta": "Explore our evidence-based supplement guide at midblooma.com",
            },
            "social": {
                "instagram_carousel": "60% of women in peri report poor sleep. Here's what the science says.",
                "linkedin": "New research on magnesium and menopause sleep — a summary for women 40+.",
                "instagram_stories": "Is magnesium your missing piece? Swipe to find out.",
                "whatsapp": "Hey — sharing this because it helped me understand my sleep patterns.",
                "save_fact": "Stat: 60% of perimenopausal women experience insomnia. Source: Sleep Medicine (2021).",
            },
            "newsletter_section": (
                "This week we're looking at magnesium and sleep. "
                "A 2021 trial (Sleep Medicine) showed real results. "
                "Read the full article at midblooma.com."
            ),
            "citations_used": [
                {
                    "claim": "magnesium supplementation reduced insomnia severity",
                    "source": "peer-reviewed journal",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/example",
                }
            ],
        },
    }

    result = run(sample_writer_envelope)
    print(json.dumps(result, indent=2))
