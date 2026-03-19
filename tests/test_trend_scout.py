"""
Tests for the Trend Scout agent.
"""
import json
import unittest.mock as mock
import uuid

import pytest

from agents.trend_scout import run as scout_run
from agents.shared.envelope import validate_envelope


def _make_mock_stream(signals: list) -> mock.MagicMock:
    response_text = json.dumps({
        "signals": signals,
        "date": "2026-03-16",
    })
    mock_block = mock.MagicMock()
    mock_block.type = "text"
    mock_block.text = response_text

    mock_final = mock.MagicMock()
    mock_final.content = [mock_block]

    mock_stream = mock.MagicMock()
    mock_stream.__enter__ = mock.MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = mock.MagicMock(return_value=False)
    mock_stream.get_final_message = mock.MagicMock(return_value=mock_final)
    return mock_stream


class TestTrendScout:
    def test_envelope_schema_valid(self):
        mock_signals = [
            {
                "rank": 1,
                "source": "Reddit r/menopause",
                "title": "Magnesium for sleep?",
                "url": "https://reddit.com/example",
                "engagement_score": 500,
                "pain_point": "Women struggle with menopause insomnia.",
                "content_angle": "Evidence-based magnesium guide.",
            }
        ]
        mock_stream = _make_mock_stream(mock_signals)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = scout_run(run_id=str(uuid.uuid4()))

        errors = validate_envelope(result)
        assert errors == [], f"Envelope invalid: {errors}"

    def test_status_always_ok(self):
        """Scout never blocks."""
        mock_stream = _make_mock_stream([])  # Even with zero signals

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = scout_run()

        assert result["status"] == "ok"

    def test_agent_id_correct(self):
        mock_stream = _make_mock_stream([])

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = scout_run()

        assert result["agent_id"] == "trend_scout"

    def test_run_id_preserved(self):
        run_id = str(uuid.uuid4())
        mock_stream = _make_mock_stream([])

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = scout_run(run_id=run_id)

        assert result["run_id"] == run_id

    def test_signals_in_payload(self):
        signals = [
            {
                "rank": i,
                "source": f"Source {i}",
                "title": f"Title {i}",
                "url": "",
                "engagement_score": i * 100,
                "pain_point": f"Pain point {i}.",
                "content_angle": f"Angle {i}.",
            }
            for i in range(1, 6)
        ]
        mock_stream = _make_mock_stream(signals)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = scout_run()

        assert len(result["payload"]["signals"]) == 5

    def test_cadence_passed_through(self):
        mock_stream = _make_mock_stream([])

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = scout_run(cadence="weekly")

        assert result["cadence"] == "weekly"


@pytest.mark.integration
def test_trend_scout_integration():
    """Integration: calls real API and returns valid envelope with 5 signals."""
    result = scout_run()
    errors = validate_envelope(result)
    assert errors == []
    assert result["status"] == "ok"
    assert result["agent_id"] == "trend_scout"
    signals = result["payload"].get("signals", [])
    assert 1 <= len(signals) <= 5, f"Expected 1-5 signals, got {len(signals)}"
    for s in signals:
        assert "pain_point" in s
        assert "content_angle" in s
