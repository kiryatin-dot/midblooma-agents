"""
Tests for the Newsletter Editor agent.
"""
import json
import unittest.mock as mock
import uuid

import pytest

from agents.newsletter_editor import run as editor_run
from agents.shared.envelope import validate_envelope


def _make_qa_envelope(run_id: str | None = None) -> dict:
    return {
        "agent_id": "health_qa",
        "timestamp": "2026-03-16T09:00:00Z",
        "run_id": run_id or str(uuid.uuid4()),
        "cadence": "weekly",
        "status": "ok",
        "payload": {
            "qa_status": "pass",
            "issues": [],
            "approved_content": {
                "newsletter_section": (
                    "This week we covered magnesium and sleep. A 2021 trial showed "
                    "a 30% reduction in insomnia severity. Read more at [ARTICLE_URL]."
                ),
            },
        },
        "notes": "",
    }


SAMPLE_NEWSLETTER_OUTPUT = {
    "subject_options": [
        "The sleep secret hiding in your diet",
        "Magnesium: your menopause sleep ally",
        "What research says about magnesium + sleep",
    ],
    "email_html": "<html><body><p>Hello from Nufar...</p></body></html>",
    "email_plain_text": "Hello from Nufar...\n\nThis week we covered magnesium and sleep.",
    "word_count": 320,
    "estimated_read_time": "2 min read",
    "product_featured": {
        "name": "[MARKETPLACE_PRODUCT_NAME]",
        "url": "[MARKETPLACE_PRODUCT_URL]",
        "reason": "Evidence-based magnesium supplement aligned with this week's research.",
    },
}


def _make_mock_stream(payload: dict) -> mock.MagicMock:
    mock_block = mock.MagicMock()
    mock_block.type = "text"
    mock_block.text = json.dumps(payload)

    mock_final = mock.MagicMock()
    mock_final.content = [mock_block]

    mock_stream = mock.MagicMock()
    mock_stream.__enter__ = mock.MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = mock.MagicMock(return_value=False)
    mock_stream.get_final_message = mock.MagicMock(return_value=mock_final)
    return mock_stream


class TestNewsletterEditor:
    def test_envelope_schema_valid(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_NEWSLETTER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = editor_run(env)

        errors = validate_envelope(result)
        assert errors == [], f"Envelope invalid: {errors}"

    def test_status_always_needs_review(self):
        """Newsletter Editor NEVER auto-sends — always needs_review."""
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_NEWSLETTER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = editor_run(env)

        assert result["status"] == "needs_review", (
            "Newsletter Editor must NEVER auto-send. Status must always be 'needs_review'."
        )

    def test_agent_id_correct(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_NEWSLETTER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = editor_run(env)

        assert result["agent_id"] == "newsletter_editor"

    def test_run_id_preserved(self):
        run_id = str(uuid.uuid4())
        env = _make_qa_envelope(run_id=run_id)
        mock_stream = _make_mock_stream(SAMPLE_NEWSLETTER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = editor_run(env)

        assert result["run_id"] == run_id

    def test_three_subject_options(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_NEWSLETTER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = editor_run(env)

        subjects = result["payload"].get("subject_options", [])
        assert len(subjects) == 3, f"Expected 3 subject options, got {len(subjects)}"

    def test_subject_lines_under_50_chars(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_NEWSLETTER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = editor_run(env)

        for subj in result["payload"].get("subject_options", []):
            assert len(subj) <= 50, f"Subject line too long ({len(subj)} chars): '{subj}'"

    def test_payload_has_both_formats(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_NEWSLETTER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = editor_run(env)

        payload = result["payload"]
        assert "email_html" in payload
        assert "email_plain_text" in payload
        assert len(payload["email_html"]) > 0
        assert len(payload["email_plain_text"]) > 0
