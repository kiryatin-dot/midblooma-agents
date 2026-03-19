"""
Tests for the Performance Watcher agent.
"""
import json
import unittest.mock as mock

import pytest

from agents.performance_watcher import run as watcher_run
from agents.shared.envelope import validate_envelope


TODAY_METRICS = {
    "checker_uses": 312,
    "new_members": 28,
    "total_members": 4201,
    "social_reach": 14800,
    "newsletter_open_rate": 0.47,
}

SEVEN_DAY_AVG = {
    "checker_uses": 260,
    "new_members": 15,
    "total_members": 4175,
    "social_reach": 11000,
    "newsletter_open_rate": 0.42,
}

SAMPLE_WATCHER_OUTPUT = {
    "date": "2026-03-16",
    "metrics": TODAY_METRICS,
    "anomalies": [
        {"metric": "new_members", "delta": "+87% vs 7-day avg", "flag": "positive"},
        {"metric": "social_reach", "delta": "+35% vs 7-day avg", "flag": "positive"},
    ],
    "digest_summary": (
        "Big day: 28 new members joined — 87% above the 7-day average. "
        "Social reach also surged to 14,800 (+35%). "
        "Both spikes look positive; no investigate flags today."
    ),
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


class TestPerformanceWatcher:
    def test_envelope_schema_valid(self):
        mock_stream = _make_mock_stream(SAMPLE_WATCHER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = watcher_run(TODAY_METRICS, SEVEN_DAY_AVG)

        errors = validate_envelope(result)
        assert errors == [], f"Envelope invalid: {errors}"

    def test_status_always_ok(self):
        """Watcher never blocks."""
        mock_stream = _make_mock_stream(SAMPLE_WATCHER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = watcher_run(TODAY_METRICS, SEVEN_DAY_AVG)

        assert result["status"] == "ok"

    def test_agent_id_correct(self):
        mock_stream = _make_mock_stream(SAMPLE_WATCHER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = watcher_run(TODAY_METRICS, SEVEN_DAY_AVG)

        assert result["agent_id"] == "performance_watcher"

    def test_payload_has_required_fields(self):
        mock_stream = _make_mock_stream(SAMPLE_WATCHER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = watcher_run(TODAY_METRICS, SEVEN_DAY_AVG)

        payload = result["payload"]
        for field in ["date", "metrics", "anomalies", "digest_summary"]:
            assert field in payload, f"Missing field: {field}"

    def test_digest_summary_non_empty(self):
        mock_stream = _make_mock_stream(SAMPLE_WATCHER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = watcher_run(TODAY_METRICS, SEVEN_DAY_AVG)

        assert len(result["payload"]["digest_summary"]) > 0

    def test_cadence_is_daily(self):
        mock_stream = _make_mock_stream(SAMPLE_WATCHER_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = watcher_run(TODAY_METRICS, SEVEN_DAY_AVG)

        assert result["cadence"] == "daily"
