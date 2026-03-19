"""
Utility helpers for building and validating handoff envelopes.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal


def make_envelope(
    agent_id: str,
    run_id: str,
    cadence: Literal["daily", "weekly"],
    status: Literal["ok", "blocked", "needs_review"],
    payload: dict[str, Any],
    notes: str = "",
) -> dict[str, Any]:
    """Return a fully-formed handoff envelope."""
    return {
        "agent_id": agent_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "cadence": cadence,
        "status": status,
        "payload": payload,
        "notes": notes,
    }


def new_run_id() -> str:
    return str(uuid.uuid4())


def validate_envelope(envelope: dict[str, Any]) -> list[str]:
    """
    Returns a list of validation errors.
    An empty list means the envelope is valid.
    """
    errors = []
    required = ["agent_id", "timestamp", "run_id", "cadence", "status", "payload"]
    for field in required:
        if field not in envelope:
            errors.append(f"Missing required field: {field}")

    if envelope.get("cadence") not in ("daily", "weekly"):
        errors.append("cadence must be 'daily' or 'weekly'")

    if envelope.get("status") not in ("ok", "blocked", "needs_review"):
        errors.append("status must be 'ok', 'blocked', or 'needs_review'")

    if not isinstance(envelope.get("payload"), dict):
        errors.append("payload must be a dict")

    return errors


def parse_json_response(text: str) -> dict[str, Any]:
    """
    Extract and parse the first JSON object found in a Claude response string.
    Strips markdown code fences if present.
    """
    # Strip markdown fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Drop the first and last fence lines
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(cleaned)
