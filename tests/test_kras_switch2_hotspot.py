"""KRAS Switch-II curated hotspot map (FEATURE-kras-switch2-hotspot)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot import (
    COPY_BINDER_CONFIRM_SWITCH2_FIXTURE,
    COPY_BINDER_CONFIRM_TARGET_WIDE,
    PENDING_DESIGN_KEY,
    _card_hotspot,
    _queue_binder_design,
)
from src.context_card import ContextCard, parse_load_text, store_card
from src.targets import (
    HOTSPOT_SOURCE_KRAS_SWITCH_II,
    KRAS_SWITCH_II_POCKET,
    pocket_residues_to_hotspot_list,
)


class TestKrasSwitch2Hotspot(unittest.IsolatedAsyncioTestCase):
    def test_fixture_residues_60_to_76(self):
        self.assertEqual(KRAS_SWITCH_II_POCKET["A"], list(range(60, 77)))
        self.assertEqual(KRAS_SWITCH_II_POCKET["A"][0], 60)
        self.assertEqual(KRAS_SWITCH_II_POCKET["A"][-1], 76)

    def test_kras_g12c_switch_ii_sets_pocket(self):
        card = parse_load_text(
            "design a de novo protein binder to KRAS G12C at the Switch-II pocket"
        )
        self.assertEqual(card.gene, "KRAS")
        self.assertEqual(card.variant, "G12C")
        self.assertEqual(card.pocket_residues, {"A": list(range(60, 77))})
        self.assertEqual(card.hotspot_source, HOTSPOT_SOURCE_KRAS_SWITCH_II)

    def test_phrase_variants(self):
        for phrase in ("Switch-II", "switch ii", "Switch 2", "SII", "sii"):
            card = parse_load_text(f"binder for KRAS WT at the {phrase} pocket")
            self.assertEqual(
                card.pocket_residues,
                {"A": list(range(60, 77))},
                msg=phrase,
            )
            self.assertEqual(card.hotspot_source, HOTSPOT_SOURCE_KRAS_SWITCH_II)

    def test_non_kras_switch_ii_no_invented_hotspot(self):
        card = parse_load_text("design a binder to EGFR at the Switch-II pocket")
        self.assertEqual(card.gene, "EGFR")
        self.assertIsNone(card.pocket_residues)
        self.assertIsNone(card.hotspot_source)
        self.assertIsNone(_card_hotspot(card))

    def test_kras_without_switch_ii_no_auto_hotspot(self):
        card = parse_load_text("design a binder to KRAS G12C")
        self.assertEqual(card.gene, "KRAS")
        self.assertIsNone(card.pocket_residues)
        self.assertIsNone(card.hotspot_source)
        self.assertIsNone(_card_hotspot(card))

    def test_card_hotspot_from_fixture(self):
        card = parse_load_text("KRAS G12D Switch-II binder")
        hs = _card_hotspot(card)
        self.assertEqual(hs, pocket_residues_to_hotspot_list({"A": list(range(60, 77))}))
        self.assertEqual(hs[0], "A60")
        self.assertEqual(hs[-1], "A76")

    async def test_binder_confirm_mentions_fixture_map(self):
        card = parse_load_text(
            "design a de novo protein binder to KRAS G12C at the Switch-II pocket"
        )
        card.last_run = {
            "kind": "fold",
            "files": [{"kind": "cif", "filename": "/tmp/fake.cif", "path": "/tmp/fake.cif"}],
        }
        # file_of_kind expects path-like entries — mirror store shape used in bot
        user_data: dict = {}
        store_card(user_data, card)
        # Ensure last_run survives store (store uses to_dict)
        user_data["context_card"]["last_run"] = {
            "kind": "fold",
            "files": [{"kind": "cif", "path": "/tmp/fake.cif"}],
        }

        update = MagicMock()
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.effective_message = message
        context = MagicMock()
        context.user_data = user_data
        context.application.bot_data = {
            "settings": MagicMock(
                bindcraft_home="",
                modal_token_id="id",
                modal_token_secret="sec",
                telegram_allowed_user_id=None,
                max_sequence_length=800,
                commec_bin="commec",
                commec_timeout_sec=60,
            )
        }

        with patch("src.bot.file_of_kind", return_value="/tmp/fake.cif"):
            with patch("src.bot.bindcraft_mod.binder_compute_ready", return_value=True):
                await _queue_binder_design(update, context, n=1)

        message.reply_text.assert_awaited_once_with(
            COPY_BINDER_CONFIRM_SWITCH2_FIXTURE.format(n=1)
        )
        pending = context.user_data[PENDING_DESIGN_KEY]
        self.assertEqual(pending["hotspot_source"], HOTSPOT_SOURCE_KRAS_SWITCH_II)
        self.assertEqual(pending["hotspot_residues"][0], "A60")
        self.assertEqual(pending["hotspot_residues"][-1], "A76")

    async def test_binder_confirm_target_wide_for_non_kras_switch_ii(self):
        # Non-KRAS + Switch-II: no curated sequence; build a card with pasted seq + EGFR label
        card = ContextCard(
            gene="EGFR",
            sequence="M" * 50,
            sequence_source="user_paste",
            raw_text="EGFR Switch-II",
            pocket_residues=None,
            hotspot_source=None,
            last_run={
                "kind": "fold",
                "files": [{"kind": "cif", "path": "/tmp/fake.cif"}],
            },
        )
        user_data: dict = {}
        store_card(user_data, card)
        user_data["context_card"]["last_run"] = card.last_run

        update = MagicMock()
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.effective_message = message
        context = MagicMock()
        context.user_data = user_data
        context.application.bot_data = {
            "settings": MagicMock(
                bindcraft_home="/fake",
                modal_token_id="",
                modal_token_secret="",
                telegram_allowed_user_id=None,
                max_sequence_length=800,
                commec_bin="commec",
                commec_timeout_sec=60,
            )
        }

        with patch("src.bot.file_of_kind", return_value="/tmp/fake.cif"):
            with patch("src.bot.bindcraft_mod.binder_compute_ready", return_value=True):
                await _queue_binder_design(update, context, n=5)

        message.reply_text.assert_awaited_once_with(
            COPY_BINDER_CONFIRM_TARGET_WIDE.format(n=5)
        )
        self.assertIsNone(context.user_data[PENDING_DESIGN_KEY]["hotspot_residues"])


if __name__ == "__main__":
    unittest.main()
