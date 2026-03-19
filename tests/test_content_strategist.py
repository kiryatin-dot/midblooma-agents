"""
Tests for the Content Strategist agent.
"""
import json
import unittest.mock as mock
import uuid

import pytest

from agents.content_strategist import run as strategist_run
from agents.shared.envelope import validate_envelope


def _make_trend_envelope(signals: list, run_id: str | None = None) -> dict:
    return {
        "agent_id": "trend_scout",
        "timestamp": "2026-03-16T06:00:00Z",
        "run_id": run_id or str(uuid.uuid4()),
        "cadence": "daily",
        "status": "ok",
        "payload": {"signals": signals, "date": "2026-03-16"},
        "notes": "",
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


SAMPLE_BRIEF = {
    "topic": "Magnesium and sleep in menopause",
    "headline_draft": "Can Magnesium Help You Sleep Better Through Menopause?",
    "audience_pain_point": "Women in perimenopause experience worsening insomnia.",
    "midblooma_angle": "We review the best evidence on magnesium for sleep.",
    "supporting_studies": [
        {"title": "Study A", "authors": "Smith et al.", "year": 2021, "journal": "Sleep Medicine", "key_finding": "30% reduction in insomnia.", "url": "https://pubmed.example/1"},
        {"title": "Study B", "authors": "Jones et al.", "year": 2022, "journal": "Nutrients", "key_finding": "Higher Mg linked to better sleep.", "url": "https://pubmed.example/2"},
        {"title": "NICE NG23", "authors": "NICE", "year": 2023, "journal": "NICE", "key_finding": "Sleep is a key menopause symptom.", "url": "https://www.nice.org.uk/ng23"},
    ],
    "content_type": "article",
    "word_count_target": 1200,
    "cta": "Explore midblooma.com/supplements",
}


class TestContentStrategist:
    def _sample_envelopes(self, run_id: str | None = None) -> list:
        run_id = run_id or str(uuid.uuid4())
        signals = [
            {
                "rank": 1,
                "source": "Reddit r/menopause",
                "title": "Magnesium for sleep?",
                "url": "",
                "engagement_score": 842,
                "pain_point": "Women struggle with menopause insomnia.",
                "content_angle": "Evidence-based magnesium guide.",
            }
        ]
        return [_make_trend_envelope(signals, run_id) for _ in range(7)]

    def test_envelope_schema_valid(self):
        envelopes = self._sample_envelopes()
        mock_stream = _make_mock_stream(SAMPLE_BRIEF)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = strategist_run(envelopes)

        errors = validate_envelope(result)
        assert errors == [], f"Envelope invalid: {errors}"

    def test_three_studies_produces_ok(self):
        envelopes = self._sample_envelopes()
        mock_stream = _make_mock_stream(SAMPLE_BRIEF)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = strategist_run(envelopes)

        assert result["status"] == "ok"

    def test_one_study_produces_needs_review(self):
        brief_one_study = {**SAMPLE_BRIEF, "supporting_studies": [SAMPLE_BRIEF["supporting_studies"][0]]}
        envelopes = self._sample_envelopes()
        mock_stream = _make_mock_stream(brief_one_study)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = strategist_run(envelopes)

        assert result["status"] == "needs_review"

    def test_agent_id_correct(self):
        envelopes = self._sample_envelopes()
        mock_stream = _make_mock_stream(SAMPLE_BRIEF)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = strategist_run(envelopes)

        assert result["agent_id"] == "content_strategist"

    def test_requires_at_least_one_envelope(self):
        with pytest.raises(ValueError):
            strategist_run([])

    def test_run_id_from_first_envelope(self):
        run_id = str(uuid.uuid4())
        envelopes = self._sample_envelopes(run_id=run_id)
        mock_stream = _make_mock_stream(SAMPLE_BRIEF)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = strategist_run(envelopes)

        assert result["run_id"] == run_id

    def test_payload_has_required_brief_fields(self):
        envelopes = self._sample_envelopes()
        mock_stream = _make_mock_stream(SAMPLE_BRIEF)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = strategist_run(envelopes)

        payload = result["payload"]
        for field in ["topic", "headline_draft", "supporting_studies", "content_type", "word_count_target", "cta"]:
            assert field in payload, f"Missing field: {field}"
