"""Unit tests for /trials (FEATURE-trials + TEMPLATE-trials)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src import trials_md
from src.trials_client import (
    MAX_CAP,
    TrialStudy,
    TrialsServiceError,
    parse_search_body,
)


def _sample_study(
    *,
    nct: str = "NCT01234567",
    title: str = "KRAS G12C inhibitor study in solid tumours",
    status: str = "RECRUITING",
    phase: str | None = "Phase 2",
) -> TrialStudy:
    return TrialStudy(
        nct_id=nct,
        title=title,
        status=status,
        phase=phase,
        conditions=("Non-small cell lung cancer", "KRAS G12C"),
        eligibility_raw=(
            "Inclusion Criteria:\n"
            "* Age 18 years or older\n"
            "* Documented KRAS G12C mutation\n"
            "Exclusion Criteria:\n"
            "* Prior KRAS G12C inhibitor\n"
            "* Active untreated CNS metastases\n"
        ),
        inclusion_themes=("Age 18 years or older", "Documented KRAS G12C mutation"),
        exclusion_themes=("Prior KRAS G12C inhibitor", "Active untreated CNS metastases"),
    )


class TestParseTrialsArgs(unittest.TestCase):
    def test_structured_kras_g12c(self):
        p = trials_md.parse_trials_args(["KRAS", "G12C"])
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "KRAS")
        self.assertEqual(p.variant, "G12C")
        self.assertIn("KRAS", p.term)
        self.assertIn("G12C", p.term)

    def test_nl_condition(self):
        p = trials_md.parse_trials_args(["non-small", "cell", "lung", "cancer"])
        self.assertIsNotNone(p)
        assert p is not None
        self.assertTrue(p.term)

    def test_bare_uses_card(self):
        p = trials_md.parse_trials_args([], card_gene="KRAS", card_variant="G12C")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "KRAS")
        self.assertEqual(p.variant, "G12C")

    def test_bare_gene_only_ok(self):
        p = trials_md.parse_trials_args([], card_gene="EGFR")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "EGFR")

    def test_bare_missing_context(self):
        self.assertIsNone(trials_md.parse_trials_args([]))
        self.assertIsNone(
            trials_md.parse_trials_args(
                [], card_gene=None, card_variant=None, card_condition=None
            )
        )

    def test_missing_message_locked(self):
        self.assertEqual(
            trials_md.MSG_MISSING,
            "Please name a condition, gene, or variant, or /load a card first. "
            "Example: /trials KRAS G12C",
        )


class TestRenderTrials(unittest.TestCase):
    def test_empty_hits_honest(self):
        q = trials_md.parse_trials_args(["KRAS", "G12C"])
        assert q is not None
        body = trials_md.render_trials_md(q, [])
        self.assertIn("# Trials shortlist", body)
        self.assertIn(trials_md.STUDIES_ZERO, body)
        self.assertIn(trials_md.SCOPE_DISCLAIMER, body)
        self.assertIn(trials_md.SOURCE_NOTE, body)
        self.assertNotIn("NCT0", body)
        self.assertNotIn("you are eligible", body.lower())
        self.assertNotIn("enroll now", body.lower())

    def test_hits_locked_fields_no_enroll(self):
        q = trials_md.parse_trials_args(["KRAS", "G12C"])
        assert q is not None
        body = trials_md.render_trials_md(q, [_sample_study()])
        self.assertIn("NCT01234567", body)
        self.assertIn("KRAS G12C inhibitor study", body)
        self.assertIn("RECRUITING", body)
        self.assertIn("Phase 2", body)
        lower = body.lower()
        self.assertIn("why it matched", lower)
        self.assertIn("eligibility themes", lower)
        self.assertIn("clinicaltrials.gov/study/NCT01234567".lower(), lower)
        self.assertNotIn("you are eligible", lower)
        self.assertNotIn("you qualify", lower)
        self.assertNotIn("enroll now", lower)
        self.assertNotIn("we will enroll", lower)
        self.assertIn("does not enroll", lower)
        self.assertIn("research use only", lower)
        self.assertFalse(trials_md.has_enroll_language(body))

    def test_cap_at_most_ten(self):
        q = trials_md.parse_trials_args(["KRAS", "G12C"])
        assert q is not None
        studies = [
            _sample_study(nct=f"NCT{i:08d}", title=f"Study {i}") for i in range(15)
        ]
        body = trials_md.render_trials_md(q, studies)
        nct_count = sum(1 for i in range(15) if f"NCT{i:08d}" in body)
        self.assertLessEqual(nct_count, MAX_CAP)
        self.assertEqual(nct_count, MAX_CAP)
        self.assertEqual(trials_md.clamp_limit(99), MAX_CAP)
        self.assertEqual(trials_md.clamp_limit(None), trials_md.DEFAULT_CAP)

    def test_caption_locked(self):
        self.assertEqual(
            trials_md.caption_for(3),
            trials_md.CAPTION_HITS.format(n=3),
        )
        self.assertEqual(trials_md.caption_for(0), trials_md.CAPTION_ZERO)

    def test_help_line_in_bot(self):
        from src import bot as bot_mod

        help_text = getattr(bot_mod, "HELP_TEXT", None) or getattr(bot_mod, "HELP_TEXT", "")
        self.assertIn("/trials", help_text)
        self.assertIn(trials_md.HELP_LINE, help_text)
        self.assertIn("/board", help_text)
        self.assertIn("/variant", help_text)
        self.assertIn("does not enroll", help_text.lower())


class TestTrialsClientParse(unittest.TestCase):
    def test_parse_empty_studies(self):
        raw = json.dumps({"studies": []})
        self.assertEqual(parse_search_body(raw), [])

    def test_parse_malformed_fail_closed(self):
        with self.assertRaises(TrialsServiceError):
            parse_search_body("{not-json")
        with self.assertRaises(TrialsServiceError):
            parse_search_body(json.dumps({"no_studies": True}))

    def test_parse_one_study(self):
        payload = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT09999999",
                            "briefTitle": "Example KRAS study",
                        },
                        "statusModule": {"overallStatus": "RECRUITING"},
                        "designModule": {"phases": ["PHASE2"]},
                        "conditionsModule": {"conditions": ["NSCLC"]},
                        "eligibilityModule": {
                            "eligibilityCriteria": (
                                "Inclusion Criteria:\n* Adults\n"
                                "Exclusion Criteria:\n* Pregnancy"
                            )
                        },
                    }
                }
            ]
        }
        studies = parse_search_body(json.dumps(payload), limit=5)
        self.assertEqual(len(studies), 1)
        self.assertEqual(studies[0].nct_id, "NCT09999999")
        self.assertEqual(studies[0].title, "Example KRAS study")
        self.assertEqual(studies[0].status, "RECRUITING")
        self.assertEqual(studies[0].phase, "Phase 2")
        self.assertTrue(studies[0].inclusion_themes)


class TestCmdTrialsHandler(unittest.IsolatedAsyncioTestCase):
    async def test_missing_args_refuse(self):
        from src.bot import cmd_trials

        update = MagicMock()
        message = AsyncMock()
        update.effective_message = message
        update.effective_user = MagicMock(id=1)
        context = MagicMock()
        context.args = []
        context.user_data = {}
        context.bot_data = {"settings": MagicMock(allowed_user_ids=None)}

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_trials(update, context)
        message.reply_text.assert_awaited()
        self.assertEqual(
            message.reply_text.await_args.args[0], trials_md.MSG_MISSING
        )

    async def test_fail_closed_on_service_error(self):
        from src.bot import cmd_trials

        update = MagicMock()
        message = AsyncMock()
        update.effective_message = message
        update.effective_user = MagicMock(id=1)
        context = MagicMock()
        context.args = ["KRAS", "G12C"]
        context.user_data = {}
        context.bot_data = {"settings": MagicMock(allowed_user_ids=None)}

        with (
            patch("src.bot._authorized", new=AsyncMock(return_value=True)),
            patch(
                "src.bot.search_trials",
                side_effect=TrialsServiceError("down"),
            ),
        ):
            await cmd_trials(update, context)
        message.reply_text.assert_awaited_with(trials_md.MSG_FAIL_CLOSED)

    async def test_empty_hits_short_text(self):
        from src.bot import cmd_trials

        update = MagicMock()
        message = AsyncMock()
        update.effective_message = message
        update.effective_user = MagicMock(id=1)
        context = MagicMock()
        context.args = ["KRAS", "G12C"]
        context.user_data = {}
        context.bot_data = {"settings": MagicMock(allowed_user_ids=None)}

        with (
            patch("src.bot._authorized", new=AsyncMock(return_value=True)),
            patch("src.bot.search_trials", return_value=[]),
        ):
            await cmd_trials(update, context)
        message.reply_text.assert_awaited()
        body = message.reply_text.await_args.args[0]
        self.assertIn(trials_md.STUDIES_ZERO, body)
        message.reply_document.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
