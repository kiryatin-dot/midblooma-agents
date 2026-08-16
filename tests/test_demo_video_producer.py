"""
Tests for the Demo Video Producer agent.

Every real external dependency (headless browser, ElevenLabs, ffmpeg) is
mocked at its seam (`_capture_site`, `_synthesize_narration`, `_render_video`)
so this suite runs anywhere pytest runs, with no browser/ffmpeg/API keys
required. Script generation goes through the real `_generate_script` code
path with only the Anthropic client mocked, so the JSON parsing / visual
label clamping logic is genuinely exercised.
"""
import json
import unittest.mock as mock
import uuid

import pytest

from agents.demo_video_producer import run as producer_run
from agents.shared.envelope import validate_envelope

FAKE_CAPTURE = {
    "site_title": "Acme Events",
    "page_text": "Acme Events — book amazing venues in seconds. 10,000+ venues worldwide.",
    "screenshots": [
        {"label": "hero", "path": "/tmp/fake_hero.png", "page_url": "https://acme.example"},
        {"label": "section_1", "path": "/tmp/fake_s1.png", "page_url": "https://acme.example"},
    ],
}

SAMPLE_SCRIPT = {
    "video_title": "Acme Events Demo",
    "voice_style": "confident",
    "scenes": [
        {
            "scene_id": 1, "role": "intro", "visual": "title_card",
            "narration": "Meet Acme Events, the fastest way to book venues.",
            "caption": "Book venues instantly",
        },
        {
            "scene_id": 2, "role": "feature", "visual": "hero",
            "narration": "Search and compare ten thousand venues in seconds.",
            "caption": "10,000+ venues",
        },
        {
            "scene_id": 3, "role": "outro", "visual": "title_card",
            "narration": "Get started free today at acme events dot example.",
            "caption": "Start free",
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


def _with_fake_narration(scenes, *_args, **_kwargs):
    for i, scene in enumerate(scenes):
        scene["audio_path"] = f"/tmp/fake_narration_{scene['scene_id']}.mp3"
        scene["duration_seconds"] = 5.0 + i
    return scenes


class TestDemoVideoProducer:
    def _run_happy_path(self, **overrides):
        mock_stream = _make_mock_stream(SAMPLE_SCRIPT)
        kwargs = dict(
            url="https://acme.example",
            company_name="Acme Events",
            company_info="Venue booking marketplace.",
        )
        kwargs.update(overrides)

        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient, mock.patch(
            "agents.demo_video_producer._synthesize_narration",
            side_effect=_with_fake_narration,
        ), mock.patch(
            "agents.demo_video_producer._render_video", return_value=15.0
        ):
            MockClient.return_value.messages.stream.return_value = mock_stream
            return producer_run(**kwargs)

    def test_envelope_schema_valid(self):
        result = self._run_happy_path()
        errors = validate_envelope(result)
        assert errors == [], f"Envelope invalid: {errors}"

    def test_status_ok(self):
        result = self._run_happy_path()
        assert result["status"] == "ok"

    def test_agent_id_correct(self):
        result = self._run_happy_path()
        assert result["agent_id"] == "demo_video_producer"

    def test_payload_has_required_fields(self):
        result = self._run_happy_path()
        payload = result["payload"]
        for field in [
            "video_path", "duration_seconds", "scene_count",
            "screenshots_captured", "source_url", "script",
        ]:
            assert field in payload, f"Missing field: {field}"
        assert payload["scene_count"] == 3
        assert payload["screenshots_captured"] == 2
        assert payload["duration_seconds"] == 15.0

    def test_run_id_generated_when_not_given(self):
        result = self._run_happy_path()
        assert result["run_id"]

    def test_run_id_preserved_when_given(self):
        run_id = str(uuid.uuid4())
        result = self._run_happy_path(run_id=run_id)
        assert result["run_id"] == run_id

    def test_requires_url(self):
        with pytest.raises(ValueError):
            producer_run(url="", company_name="Acme")

    def test_requires_company_name(self):
        with pytest.raises(ValueError):
            producer_run(url="https://acme.example", company_name="")

    def test_duration_clamped_below_minimum(self):
        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient, mock.patch(
            "agents.demo_video_producer._generate_script"
        ) as mock_gen, mock.patch(
            "agents.demo_video_producer._synthesize_narration",
            side_effect=_with_fake_narration,
        ), mock.patch(
            "agents.demo_video_producer._render_video", return_value=15.0
        ):
            MockClient.return_value.messages.stream.return_value = _make_mock_stream(SAMPLE_SCRIPT)
            mock_gen.return_value = SAMPLE_SCRIPT
            producer_run(
                url="https://acme.example", company_name="Acme",
                target_duration_seconds=5,
            )
            _, kwargs = mock_gen.call_args
            assert kwargs["target_duration_seconds"] == 30

    def test_duration_clamped_above_maximum(self):
        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient, mock.patch(
            "agents.demo_video_producer._generate_script"
        ) as mock_gen, mock.patch(
            "agents.demo_video_producer._synthesize_narration",
            side_effect=_with_fake_narration,
        ), mock.patch(
            "agents.demo_video_producer._render_video", return_value=15.0
        ):
            MockClient.return_value.messages.stream.return_value = _make_mock_stream(SAMPLE_SCRIPT)
            mock_gen.return_value = SAMPLE_SCRIPT
            producer_run(
                url="https://acme.example", company_name="Acme",
                target_duration_seconds=500,
            )
            _, kwargs = mock_gen.call_args
            assert kwargs["target_duration_seconds"] == 90

    def test_capture_failure_returns_blocked(self):
        with mock.patch(
            "agents.demo_video_producer._capture_site",
            side_effect=RuntimeError("net::ERR_NAME_NOT_RESOLVED"),
        ):
            result = producer_run(url="https://nope.example", company_name="Nope Inc")

        assert result["status"] == "blocked"
        assert result["payload"]["stage_failed"] == "capture"

    def test_no_screenshots_returns_blocked(self):
        empty_capture = {**FAKE_CAPTURE, "screenshots": []}
        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=empty_capture
        ):
            result = producer_run(url="https://acme.example", company_name="Acme")

        assert result["status"] == "blocked"
        assert result["payload"]["stage_failed"] == "capture"

    def test_script_unparseable_returns_needs_review(self):
        bad_block = mock.MagicMock()
        bad_block.type = "text"
        bad_block.text = "not json at all"
        bad_final = mock.MagicMock()
        bad_final.content = [bad_block]
        bad_stream = mock.MagicMock()
        bad_stream.__enter__ = mock.MagicMock(return_value=bad_stream)
        bad_stream.__exit__ = mock.MagicMock(return_value=False)
        bad_stream.get_final_message = mock.MagicMock(return_value=bad_final)

        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = bad_stream
            result = producer_run(url="https://acme.example", company_name="Acme")

        assert result["status"] == "needs_review"
        assert result["payload"]["stage_failed"] == "script"

    def test_script_empty_scenes_returns_needs_review(self):
        empty_script = {**SAMPLE_SCRIPT, "scenes": []}
        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = _make_mock_stream(empty_script)
            result = producer_run(url="https://acme.example", company_name="Acme")

        assert result["status"] == "needs_review"
        assert result["payload"]["stage_failed"] == "script"

    def test_invalid_visual_label_is_clamped_to_a_captured_screenshot(self):
        script_with_bad_visual = json.loads(json.dumps(SAMPLE_SCRIPT))
        script_with_bad_visual["scenes"][1]["visual"] = "some_label_that_was_never_captured"

        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient, mock.patch(
            "agents.demo_video_producer._synthesize_narration",
            side_effect=_with_fake_narration,
        ), mock.patch(
            "agents.demo_video_producer._render_video", return_value=15.0
        ) as mock_render:
            MockClient.return_value.messages.stream.return_value = _make_mock_stream(script_with_bad_visual)
            producer_run(url="https://acme.example", company_name="Acme")

        rendered_scenes = mock_render.call_args[0][0]
        feature_scene = next(s for s in rendered_scenes if s["scene_id"] == 2)
        assert feature_scene["visual"] in {"hero", "section_1"}

    def test_voice_failure_returns_needs_review_and_preserves_script(self):
        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient, mock.patch(
            "agents.demo_video_producer._synthesize_narration",
            side_effect=RuntimeError("ELEVENLABS_API_KEY is not set"),
        ):
            MockClient.return_value.messages.stream.return_value = _make_mock_stream(SAMPLE_SCRIPT)
            result = producer_run(url="https://acme.example", company_name="Acme")

        assert result["status"] == "needs_review"
        assert result["payload"]["stage_failed"] == "voice"
        assert "script" in result["payload"]

    def test_render_failure_returns_needs_review_and_preserves_narration(self):
        with mock.patch(
            "agents.demo_video_producer._capture_site", return_value=FAKE_CAPTURE
        ), mock.patch("anthropic.Anthropic") as MockClient, mock.patch(
            "agents.demo_video_producer._synthesize_narration",
            side_effect=_with_fake_narration,
        ), mock.patch(
            "agents.demo_video_producer._render_video",
            side_effect=RuntimeError("ffmpeg failed: some codec error"),
        ):
            MockClient.return_value.messages.stream.return_value = _make_mock_stream(SAMPLE_SCRIPT)
            result = producer_run(url="https://acme.example", company_name="Acme")

        assert result["status"] == "needs_review"
        assert result["payload"]["stage_failed"] == "render"
        assert len(result["payload"]["narration_audio"]) == 3
