"""
Tests for the Writer agent.
"""
import json
import unittest.mock as mock
import uuid

import pytest

from agents.writer import run as writer_run
from agents.shared.envelope import validate_envelope


def _make_strategist_envelope(run_id: str | None = None) -> dict:
    return {
        "agent_id": "content_strategist",
        "timestamp": "2026-03-16T08:00:00Z",
        "run_id": run_id or str(uuid.uuid4()),
        "cadence": "weekly",
        "status": "ok",
        "payload": {
            "topic": "Magnesium and sleep in menopause",
            "headline_draft": "Can Magnesium Help You Sleep Better Through Menopause?",
            "audience_pain_point": "Women in perimenopause experience worsening insomnia.",
            "midblooma_angle": "We review the best evidence on magnesium for sleep.",
            "supporting_studies": [
                {
                    "title": "Magnesium and insomnia in postmenopausal women",
                    "authors": "Smith et al.",
                    "year": 2021,
                    "journal": "Sleep Medicine",
                    "key_finding": "Reduced insomnia severity by 30%.",
                    "url": "https://pubmed.example/1",
                }
            ],
            "content_type": "article",
            "word_count_target": 1200,
            "cta": "Explore midblooma.com/supplements",
        },
        "notes": "",
    }


SAMPLE_WRITER_OUTPUT = {
    "article": {
        "headline": "Can Magnesium Help You Sleep Better Through Menopause?",
        "intro": "Sleep disruption affects up to 60% of women in perimenopause.",
        "sections": [
            {
                "h2": "What the evidence shows",
                "body": "A 2021 trial in Sleep Medicine found magnesium reduced insomnia severity by 30% (Smith et al., 2021). Consult your healthcare provider before starting any supplement.",
            }
        ],
        "conclusion": "Magnesium is one evidence-based option — not a cure.",
        "cta": "Explore midblooma.com/supplements",
    },
    "social": {
        "instagram_carousel": "60% of women in peri report poor sleep. Here's what the science says.",
        "linkedin": "New research on magnesium and menopause sleep — a summary for women 40+.",
        "instagram_stories": "Is magnesium your missing piece? Vote below 👇",
        "whatsapp": "Sharing this because sleep has been a game-changer topic this week.",
        "save_fact": "Stat: 60% of perimenopausal women experience insomnia (Sleep Medicine, 2021).",
    },
    "newsletter_section": "This week we covered magnesium and sleep. Read more at midblooma.com.",
    "citations_used": [
        {
            "claim": "magnesium reduced insomnia severity by 30%",
            "source": "peer-reviewed journal",
            "url": "https://pubmed.example/1",
        }
    ],
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


class TestWriter:
    def test_envelope_schema_valid(self):
        env = _make_strategist_envelope()
        mock_stream = _make_mock_stream(SAMPLE_WRITER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = writer_run(env)

        errors = validate_envelope(result)
        assert errors == [], f"Envelope invalid: {errors}"

    def test_agent_id_correct(self):
        env = _make_strategist_envelope()
        mock_stream = _make_mock_stream(SAMPLE_WRITER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = writer_run(env)

        assert result["agent_id"] == "writer"

    def test_run_id_preserved(self):
        run_id = str(uuid.uuid4())
        env = _make_strategist_envelope(run_id=run_id)
        mock_stream = _make_mock_stream(SAMPLE_WRITER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = writer_run(env)

        assert result["run_id"] == run_id

    def test_status_ok(self):
        env = _make_strategist_envelope()
        mock_stream = _make_mock_stream(SAMPLE_WRITER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = writer_run(env)

        assert result["status"] == "ok"

    def test_payload_has_required_fields(self):
        env = _make_strategist_envelope()
        mock_stream = _make_mock_stream(SAMPLE_WRITER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = writer_run(env)

        payload = result["payload"]
        assert "article" in payload
        assert "social" in payload
        assert "newsletter_section" in payload
        assert "citations_used" in payload

    def test_social_has_all_five_platforms(self):
        env = _make_strategist_envelope()
        mock_stream = _make_mock_stream(SAMPLE_WRITER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = writer_run(env)

        social = result["payload"]["social"]
        for key in ["instagram_carousel", "linkedin", "instagram_stories", "whatsapp", "save_fact"]:
            assert key in social, f"Missing social key: {key}"

    def test_article_has_required_fields(self):
        env = _make_strategist_envelope()
        mock_stream = _make_mock_stream(SAMPLE_WRITER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = writer_run(env)

        article = result["payload"]["article"]
        for key in ["headline", "intro", "sections", "conclusion", "cta"]:
            assert key in article, f"Missing article key: {key}"
