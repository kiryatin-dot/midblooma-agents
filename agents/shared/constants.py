"""
Shared constants for the Midblooma AI Marketing Team.
Every agent imports from this file.
"""

# ─────────────────────────────────────────────
# Brand identity injected into every agent
# ─────────────────────────────────────────────
SHARED_BRAND_CONTEXT = """
MIDBLOOMA BRAND RULES — INJECTED INTO EVERY AGENT

Platform: Midblooma (midblooma.com) — the modern menopause hub.
Tagline: Everything Menopause. Done Smarter.
Audience: Women aged 40–60 navigating perimenopause and menopause.
Positioning: Evidence-based, community-led, free from paid placements.
Voice: Founder-confident, authoritative, warm. Never clinical, never condescending.
Trust signal: Every health claim must cite a source. No exceptions.
Founder: Nufar. All AMAs and live sessions are hosted by the founder.

EDITORIAL RULES:
- Never use the word 'cure'. Menopause is not a disease to be cured.
- Never give medical advice. Recommend consulting a qualified healthcare professional.
- Every health or ingredient claim must be backed by a named study, guideline, or body
  (NICE, The Menopause Society, NHS, ACOG, or peer-reviewed research).
- Product recommendations are never paid placements.
  Always state: evidence-based selection only.
- Tone for social: direct, useful, occasionally sharp.
  Not cheerful, not inspirational-quote style.
- Tone for long-form: authoritative and thorough.
  More like a knowledgeable friend than a textbook.
""".strip()

# ─────────────────────────────────────────────
# Handoff envelope schema (top-level fields)
# ─────────────────────────────────────────────
ENVELOPE_SCHEMA = {
    "agent_id": "string — name of the agent that produced this envelope",
    "timestamp": "ISO 8601 string — when the envelope was created",
    "run_id": "string (UUID) — unique ID for the full daily or weekly run",
    "cadence": "'daily' | 'weekly' — which schedule triggered this run",
    "status": "'ok' | 'blocked' | 'needs_review'",
    "payload": "object — the actual content (schema varies per agent)",
    "notes": "string (optional) — human-readable note from the agent for Nufar",
}

# ─────────────────────────────────────────────
# Words that must never appear in published content
# ─────────────────────────────────────────────
BANNED_WORDS = [
    "cure",
    "guaranteed",
    "proven to",       # only banned without a citation
    "eliminate",       # banned when referring to symptoms
    "reverse",         # banned when referring to menopause itself
]

# ─────────────────────────────────────────────
# Approved source types for health claims
# ─────────────────────────────────────────────
APPROVED_SOURCES = [
    "peer-reviewed journal",
    "NICE",
    "The Menopause Society",
    "NHS",
    "ACOG",
]

# ─────────────────────────────────────────────
# Model to use for all agents
# ─────────────────────────────────────────────
DEFAULT_MODEL = "claude-sonnet-4-5"

# ─────────────────────────────────────────────
# Social scheduling config
# ─────────────────────────────────────────────
SCHEDULE_CONFIG = {
    "instagram_carousel": "Tuesday 18:00",
    "linkedin_article": "Wednesday 09:00",
    "instagram_story": "Wednesday 18:00",
    "whatsapp_broadcast": "Thursday 10:00",
    "save_worthy_fact": "Friday 12:00",
}
