"""Unit tests for /variant (FEATURE-variant + TEMPLATE-variant)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.research_client import Author, Record
from src import variant_md


def _sample_rec(*, doi: str = "10.1000/variant.1", year: str = "2024") -> Record:
    return Record(
        authors=(Author("Smith", "J.A"), Author("Lee", "K"), Author("Patel", "R")),
        year=year,
        title="KRAS G12C inhibitors in NSCLC",
        server="Nature Medicine",
        doi=doi,
        url=f"https://doi.org/{doi}",
        date=f"{year}-01-15",
        abstract=(
            "KRAS G12C is a recurrent substitution studied in peer-reviewed trials "
            "of covalent inhibitors."
        ),
        relevance=0,
    )


class TestParseGeneChange(unittest.TestCase):
    def test_structured_kras_g12c(self):
        p = variant_md.parse_variant_args(["KRAS", "G12C"])
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "KRAS")
        self.assertEqual(p.change, "G12C")

    def test_structured_egfr_l858r(self):
        p = variant_md.parse_variant_args(["EGFR", "L858R"])
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "EGFR")
        self.assertEqual(p.change, "L858R")

    def test_nl_mentions_gene_and_change(self):
        p = variant_md.parse_variant_args(
            ["what", "about", "the", "BRAF", "V600E", "mutation"]
        )
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "BRAF")
        self.assertEqual(p.change, "V600E")

    def test_p_dot_and_three_letter(self):
        p = variant_md.parse_variant_args(["TP53", "p.R175H"])
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "TP53")
        self.assertEqual(p.change, "p.R175H")

        p2 = variant_md.parse_variant_args(["KRAS", "Gly12Cys"])
        self.assertIsNotNone(p2)
        assert p2 is not None
        self.assertEqual(p2.gene, "KRAS")
        self.assertEqual(p2.change, "Gly12Cys")

    def test_bare_uses_card(self):
        p = variant_md.parse_variant_args(
            [], card_gene="KRAS", card_variant="G12C"
        )
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.gene, "KRAS")
        self.assertEqual(p.change, "G12C")

    def test_bare_missing_card_fields(self):
        self.assertIsNone(variant_md.parse_variant_args([]))
        self.assertIsNone(
            variant_md.parse_variant_args([], card_gene="KRAS", card_variant=None)
        )
        self.assertIsNone(variant_md.parse_variant_args(["onlygene"]))

    def test_missing_message_locked(self):
        self.assertEqual(
            variant_md.MSG_MISSING,
            "Please name a gene and a variant. Example: /variant KRAS G12C",
        )


class TestRenderNoScoreEmpty(unittest.TestCase):
    def test_empty_hits_honest(self):
        body = variant_md.render_variant_md("KRAS", "G12C", [])
        self.assertIn("# Variant brief: KRAS G12C", body)
        self.assertIn(variant_md.FINDINGS_ZERO, body)
        self.assertIn("## References", body)
        self.assertIn(variant_md.REFERENCES_ZERO, body)
        self.assertNotIn("https://doi.org/", body)
        self.assertFalse(variant_md.has_score_block(body))

    def test_hits_papers_first_no_score(self):
        body = variant_md.render_variant_md("KRAS", "G12C", [_sample_rec()])
        self.assertIn("## What this variant is", body)
        self.assertIn("## What the papers report", body)
        self.assertIn("## What the papers do not prove", body)
        self.assertIn(variant_md.WHAT_NOT_PROVE, body)
        self.assertIn("## References", body)
        self.assertIn("https://doi.org/10.1000/variant.1", body)
        self.assertIn("(Smith et al., 2024)", body)
        # No diagnosis / dose / score block
        self.assertFalse(variant_md.has_score_block(body))
        lower = body.lower()
        self.assertNotIn("alphamissense", lower)
        self.assertNotIn("clinvar", lower)
        self.assertNotIn("## computational estimate", lower)
        # Research-use disclaimer present; no dose language as advice
        self.assertIn("research use only", lower)
        self.assertIn("not a diagnosis", lower)
        self.assertNotIn("take mg", lower)
        self.assertNotIn("prescribe", lower)

    def test_caption_locked(self):
        self.assertEqual(
            variant_md.caption_for("KRAS", "G12C"),
            "Variant brief for KRAS G12C: peer-reviewed literature only. "
            "Research use only; not a diagnosis.",
        )

    def test_drop_no_doi_like_evidence(self):
        bare = Record(
            authors=(Author("Anon", "A"),),
            year="2020",
            title="No DOI paper",
            server="Journal",
            doi=None,
            url="https://europepmc.org/article/MED/1",
            date="2020-01-01",
            abstract=None,
            relevance=0,
        )
        body = variant_md.render_variant_md("KRAS", "G12C", [bare])
        self.assertIn(variant_md.FINDINGS_ZERO, body)

    def test_help_line_specialty_agnostic(self):
        # Import HELP from bot without starting the poller.
        from src import bot as bot_mod

        self.assertIn("/variant", bot_mod.HELP_TEXT)
        lower = bot_mod.HELP_TEXT.lower()
        self.assertIn("specialty-agnostic", lower)
        self.assertNotIn("oncology-only", lower)
        self.assertIn("not a diagnosis", lower)


class TestCmdVariantHandler(unittest.IsolatedAsyncioTestCase):
    async def test_missing_args_refuse(self):
        from src.bot import cmd_variant

        update = MagicMock()
        message = AsyncMock()
        update.effective_message = message
        update.effective_user = MagicMock(id=1)
        context = MagicMock()
        context.args = []
        context.user_data = {}
        context.bot_data = {"settings": MagicMock(allowed_user_ids=None)}

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_variant(update, context)
        message.reply_text.assert_awaited()
        self.assertEqual(
            message.reply_text.await_args.args[0], variant_md.MSG_MISSING
        )

    async def test_fail_closed_on_lit_error(self):
        from src.bot import cmd_variant
        from src.evidence_client import EvidenceServiceError

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
                "src.bot.search_peer_reviewed",
                side_effect=EvidenceServiceError("down"),
            ),
        ):
            await cmd_variant(update, context)
        message.reply_text.assert_awaited_with(variant_md.MSG_FAIL_CLOSED)

    async def test_empty_hits_short_text(self):
        from src.bot import cmd_variant

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
            patch("src.bot.search_peer_reviewed", return_value=[]),
            patch("src.bot._safe_emit"),
        ):
            await cmd_variant(update, context)
        message.reply_text.assert_awaited()
        body = message.reply_text.await_args.args[0]
        self.assertIn(variant_md.FINDINGS_ZERO, body)
        message.reply_document.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
