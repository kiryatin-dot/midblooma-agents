"""
Tests for the Social Campaign Manager agent.
"""
import json
import unittest.mock as mock
import uuid

import pytest

from agents.social_campaign_manager import run as manager_run
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
                "social": {
                    "instagram_carousel": "60% of women in peri report poor sleep.",
                    "linkedin": "Magnesium and sleep research summary.",
                    "instagram_stories": "Have you tried magnesium for sleep?",
                    "whatsapp": "Sharing this sleep research with you.",
                    "save_fact": "60% of perimenopausal women experience insomnia.",
                },
            },
        },
        "notes": "",
    }


SAMPLE_CAMPAIGN_OUTPUT = {
    "week_of": "2026-03-17",
    "posts": [
        {
            "platform": "Instagram",
            "post_type": "carousel",
            "caption": "60% of women in peri report poor sleep.",
            "hashtags": ["#Menopause", "#Perimenopause", "#MenopauseHealth", "#Sleep"],
            "scheduled_time": "2026-03-18 18:00",
            "visual_brief": "Calm bedroom with sleep stats overlaid.",
            "link_in_bio_required": True,
        },
        {
            "platform": "LinkedIn",
            "post_type": "article_share",
            "caption": "Magnesium and sleep research summary.",
            "hashtags": ["#Menopause", "#Perimenopause", "#MenopauseHealth", "#WomensHealth"],
            "scheduled_time": "2026-03-19 09:00",
            "visual_brief": "Clean infographic with research stats.",
            "link_in_bio_required": False,
        },
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


class TestSocialCampaignManager:
    def test_envelope_schema_valid(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_CAMPAIGN_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = manager_run(env)

        errors = validate_envelope(result)
        assert errors == [], f"Envelope invalid: {errors}"

    def test_status_ok(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_CAMPAIGN_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = manager_run(env)

        assert result["status"] == "ok"

    def test_agent_id_correct(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_CAMPAIGN_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = manager_run(env)

        assert result["agent_id"] == "social_campaign_manager"

    def test_raises_on_non_ok_input(self):
        env = _make_qa_envelope()
        env["status"] = "blocked"

        with pytest.raises(ValueError):
            manager_run(env)

    def test_run_id_preserved(self):
        run_id = str(uuid.uuid4())
        env = _make_qa_envelope(run_id=run_id)
        mock_stream = _make_mock_stream(SAMPLE_CAMPAIGN_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = manager_run(env)

        assert result["run_id"] == run_id

    def test_payload_has_posts(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_CAMPAIGN_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = manager_run(env)

        assert "posts" in result["payload"]
        assert len(result["payload"]["posts"]) > 0

    def test_posts_have_required_fields(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_CAMPAIGN_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = manager_run(env)

        for post in result["payload"]["posts"]:
            for field in ["platform", "post_type", "caption", "hashtags", "scheduled_time", "visual_brief", "link_in_bio_required"]:
                assert field in post, f"Post missing field: {field}"

    def test_hashtags_include_required_tags(self):
        env = _make_qa_envelope()
        mock_stream = _make_mock_stream(SAMPLE_CAMPAIGN_OUTPUT)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = manager_run(env)

        required_tags = {"#Menopause", "#Perimenopause", "#MenopauseHealth"}
        for post in result["payload"]["posts"]:
            tag_set = set(post.get("hashtags", []))
            for tag in required_tags:
                assert tag in tag_set, f"Post missing required hashtag {tag}: {post}"
