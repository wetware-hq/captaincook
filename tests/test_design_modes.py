"""Unit tests for dual-mode /design (ligand · binder) and /bind stub."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src import bindcraft as bindcraft_mod
from src.bot import (
    COPY_BIND_STUB,
    COPY_BINDCRAFT_NOT_CONFIGURED,
    COPY_DESIGN_MODE_PROMPT,
    HELP_TEXT,
    PENDING_DESIGN_KEY,
    cmd_bind,
    cmd_design,
)


def _ctx(args: list[str] | None = None, user_data: dict | None = None):
    update = MagicMock()
    message = MagicMock()
    message.reply_text = AsyncMock()
    update.effective_message = message
    update.effective_user = MagicMock(id=1)
    context = MagicMock()
    context.args = args or []
    context.user_data = user_data if user_data is not None else {}
    context.application.bot_data = {"settings": MagicMock(
        bindcraft_home="",
        modal_token_id="",
        modal_token_secret="",
        telegram_allowed_user_id=None,
        max_sequence_length=800,
        commec_bin="commec",
        commec_timeout_sec=60,
    )}
    return update, context, message


class TestDesignModes(unittest.IsolatedAsyncioTestCase):
    async def test_bare_design_mode_prompt(self):
        update, context, message = _ctx([])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_design(update, context)
        message.reply_text.assert_awaited_once_with(COPY_DESIGN_MODE_PROMPT)
        self.assertNotIn(PENDING_DESIGN_KEY, context.user_data)

    async def test_binder_without_bindcraft_or_modal_fail_closed(self):
        update, context, message = _ctx(["binder"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_design(update, context)
        message.reply_text.assert_awaited_once_with(COPY_BINDCRAFT_NOT_CONFIGURED)
        self.assertNotIn(PENDING_DESIGN_KEY, context.user_data)

    async def test_bind_stub(self):
        update, context, message = _ctx([])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_bind(update, context)
        message.reply_text.assert_awaited_once_with(COPY_BIND_STUB)

    def test_help_contains_ligand_binder(self):
        self.assertIn(
            "/design ligand [n] — Queue Boltz small-molecule design (confirm required).",
            HELP_TEXT,
        )
        self.assertIn(
            "/design binder [n] — Queue BindCraft protein-binder design (confirm required).",
            HELP_TEXT,
        )
        self.assertIn(
            "/design — Ask which mode: ligand or binder.",
            HELP_TEXT,
        )

    def test_binder_compute_ready_modal_or_home(self):
        self.assertFalse(bindcraft_mod.binder_compute_ready(""))
        self.assertFalse(
            bindcraft_mod.binder_compute_ready(
                "", modal_token_id="x", modal_token_secret=""
            )
        )
        self.assertTrue(
            bindcraft_mod.binder_compute_ready(
                "", modal_token_id="id", modal_token_secret="sec"
            )
        )

    async def test_non_mode_non_sequence_prompts(self):
        update, context, message = _ctx(["not-a-mode"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_design(update, context)
        message.reply_text.assert_awaited_once_with(COPY_DESIGN_MODE_PROMPT)


if __name__ == "__main__":
    unittest.main()
