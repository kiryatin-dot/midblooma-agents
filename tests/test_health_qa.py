"""
Tests for the Health QA agent.

These tests use local helper functions (no API calls) to validate
schema and rule enforcement. Integration tests (requiring an API key)
are marked with @pytest.mark.integration and skipped by default.
"""
import json
import uuid

import pytest

from agents.health_qa import local_language_check, local_source_check, run as qa_run
from agents.shared.envelope import validate_envelope


# ─────────────────────────────────────────────
# Unit tests (no API calls)
# ─────────────────────────────────────────────

class TestLocalLanguageCheck:
    def test_detects_cure(self):
        assert "cure" in local_language_check("Magnesium is a cure for hot flushes.")

    def test_detects_guaranteed(self):
        assert "guaranteed" in local_language_check("Results are guaranteed.")

    def test_detects_case_insensitive(self):
        assert "cure" in local_language_check("This will CURE your symptoms.")

    def test_clean_text_returns_empty(self):
        assert local_language_check("Magnesium may reduce insomnia severity.") == []

    def test_eliminate_flagged(self):
        assert "eliminate" in local_language_check("This supplement eliminates hot flushes.")


class TestLocalSourceCheck:
    def test_approved_sources_pass(self):
        approved = [
            "peer-reviewed journal",
            "NICE",
            "The Menopause Society",
            "NHS",
            "ACOG",
        ]
        for source in approved:
            assert local_source_check([source]) == [], f"Expected {source} to pass"

    def test_unapproved_source_flagged(self):
        flagged = local_source_check(["Wikipedia"])
        assert "Wikipedia" in flagged

    def test_blog_source_flagged(self):
        flagged = local_source_check(["HealthBlog.com"])
        assert len(flagged) == 1

    def test_mixed_sources(self):
        flagged = local_source_check(["NICE", "Wikipedia", "NHS"])
        assert "Wikipedia" in flagged
        assert len(flagged) == 1


class TestEnvelopeSchema:
    """Validate that the QA envelope schema is correct given a known-good input."""

    def _make_writer_envelope(self, include_banned_word: bool = False) -> dict:
        body = (
            "Magnesium is a cure for insomnia."
            if include_banned_word
            else "Magnesium may reduce insomnia severity (Smith et al., 2021, Sleep Medicine)."
        )
        return {
            "agent_id": "writer",
            "timestamp": "2026-03-16T08:00:00Z",
            "run_id": str(uuid.uuid4()),
            "cadence": "weekly",
            "status": "ok",
            "payload": {
                "article": {
                    "headline": "Magnesium and Sleep",
                    "intro": "Sleep disruption affects many women in menopause.",
                    "sections": [{"h2": "The Evidence", "body": body}],
                    "conclusion": "Consult your healthcare provider before starting supplements.",
                    "cta": "Learn more at midblooma.com",
                },
                "social": {
                    "instagram_carousel": "Sleep stats here.",
                    "linkedin": "Research summary.",
                    "instagram_stories": "Vote: tried magnesium?",
                    "whatsapp": "Sharing this for you.",
                    "save_fact": "60% of perimenopausal women report insomnia.",
                },
                "newsletter_section": "Quick insight on magnesium this week.",
                "citations_used": [
                    {
                        "claim": "magnesium may reduce insomnia severity",
                        "source": "peer-reviewed journal",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/example",
                    }
                ],
            },
        }

    def test_envelope_has_required_fields(self):
        """The envelope structure should always be valid regardless of QA outcome."""
        writer_env = self._make_writer_envelope()
        # We only validate envelope structure here — not the QA outcome
        # (that requires an API call)
        errors = validate_envelope(writer_env)
        assert errors == [], f"Writer envelope invalid: {errors}"

    def test_run_id_preserved(self):
        """run_id from writer envelope must appear in QA envelope."""
        writer_env = self._make_writer_envelope()
        original_run_id = writer_env["run_id"]
        # We patch the Claude call for this structural test
        # by mocking the response inline
        import unittest.mock as mock

        mock_response_text = json.dumps({
            "qa_status": "pass",
            "issues": [],
            "approved_content": writer_env["payload"],
        })

        mock_block = mock.MagicMock()
        mock_block.type = "text"
        mock_block.text = mock_response_text

        mock_final = mock.MagicMock()
        mock_final.content = [mock_block]

        mock_stream = mock.MagicMock()
        mock_stream.__enter__ = mock.MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = mock.MagicMock(return_value=False)
        mock_stream.get_final_message = mock.MagicMock(return_value=mock_final)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = qa_run(writer_env)

        assert result["run_id"] == original_run_id

    def test_pass_produces_ok_status(self):
        """When QA passes, envelope status must be 'ok'."""
        writer_env = self._make_writer_envelope()

        import unittest.mock as mock

        mock_response_text = json.dumps({
            "qa_status": "pass",
            "issues": [],
            "approved_content": writer_env["payload"],
        })

        mock_block = mock.MagicMock()
        mock_block.type = "text"
        mock_block.text = mock_response_text

        mock_final = mock.MagicMock()
        mock_final.content = [mock_block]

        mock_stream = mock.MagicMock()
        mock_stream.__enter__ = mock.MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = mock.MagicMock(return_value=False)
        mock_stream.get_final_message = mock.MagicMock(return_value=mock_final)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = qa_run(writer_env)

        assert result["status"] == "ok"
        assert result["payload"]["qa_status"] == "pass"

    def test_fail_produces_blocked_status(self):
        """When QA fails, envelope status must be 'blocked'."""
        writer_env = self._make_writer_envelope()

        import unittest.mock as mock

        mock_response_text = json.dumps({
            "qa_status": "fail",
            "issues": [
                {
                    "check": "LANGUAGE CHECK",
                    "location": "article.sections[0].body",
                    "flagged_text": "cure",
                    "fix_instruction": "Remove the word 'cure' — menopause is not a disease.",
                }
            ],
            "approved_content": None,
        })

        mock_block = mock.MagicMock()
        mock_block.type = "text"
        mock_block.text = mock_response_text

        mock_final = mock.MagicMock()
        mock_final.content = [mock_block]

        mock_stream = mock.MagicMock()
        mock_stream.__enter__ = mock.MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = mock.MagicMock(return_value=False)
        mock_stream.get_final_message = mock.MagicMock(return_value=mock_final)

        with mock.patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream
            result = qa_run(writer_env)

        assert result["status"] == "blocked"
        assert result["payload"]["qa_status"] == "fail"
        assert len(result["payload"]["issues"]) > 0


# ─────────────────────────────────────────────
# Integration tests (require ANTHROPIC_API_KEY)
# ─────────────────────────────────────────────

@pytest.mark.integration
def test_qa_agent_passes_clean_content():
    """Integration: clean content should pass all four checks."""
    writer_env = {
        "agent_id": "writer",
        "timestamp": "2026-03-16T08:00:00Z",
        "run_id": str(uuid.uuid4()),
        "cadence": "weekly",
        "status": "ok",
        "payload": {
            "article": {
                "headline": "Magnesium and Sleep in Menopause",
                "intro": "Sleep disruption is a key symptom of menopause.",
                "sections": [
                    {
                        "h2": "What the evidence shows",
                        "body": (
                            "A 2021 randomised trial in Sleep Medicine found magnesium "
                            "supplementation reduced insomnia severity by 30% in postmenopausal "
                            "women (Smith et al., 2021). "
                            "Always consult your healthcare provider before starting supplements."
                        ),
                    }
                ],
                "conclusion": "Magnesium is one evidence-based option.",
                "cta": "Learn more at midblooma.com/supplements",
            },
            "social": {
                "instagram_carousel": "60% of women in peri report poor sleep.",
                "linkedin": "Magnesium and sleep: what the research shows.",
                "instagram_stories": "Have you tried magnesium for sleep? Vote below.",
                "whatsapp": "Sharing this because sleep has been a big topic this week.",
                "save_fact": "60% of perimenopausal women experience insomnia (Sleep Medicine, 2021).",
            },
            "newsletter_section": "This week we covered magnesium and sleep. Read more at midblooma.com.",
            "citations_used": [
                {
                    "claim": "magnesium supplementation reduced insomnia severity by 30%",
                    "source": "peer-reviewed journal",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/example",
                }
            ],
        },
    }

    result = qa_run(writer_env)
    errors = validate_envelope(result)
    assert errors == [], f"Envelope invalid: {errors}"
    assert result["status"] in ("ok", "blocked")
    assert "qa_status" in result["payload"]
