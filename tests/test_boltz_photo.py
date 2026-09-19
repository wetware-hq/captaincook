"""Guards for /boltz photo path: never blank media; refuse without sequence; CIF on card."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot import cmd_boltz
from src.context_card import (
    CONTEXT_CARD_KEY,
    attach_last_run,
    parse_load_text,
    store_card,
)
from src.photo import IMAGE_RENDER_FAILED, _usable_png, send_structure_photo
from src.structure_photo import _render_backbone, render_cif_to_png


CIF_SMOKE = Path(
    "/workspace/telegram-biomodel-bot/boltz-experiments/"
    "session_8820957555/run_20260919T001457Z/boltz.cif"
)


def _ctx(args: list[str] | None = None, user_data: dict | None = None):
    update = MagicMock()
    message = MagicMock()
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    update.effective_message = message
    update.effective_user = MagicMock(id=1)
    update.effective_chat = MagicMock(id=42)
    context = MagicMock()
    context.args = args or []
    context.user_data = user_data if user_data is not None else {}
    context.application.bot_data = {
        "settings": MagicMock(
            telegram_allowed_user_id=None,
            max_sequence_length=800,
            commec_bin="commec",
            commec_timeout_sec=60,
        ),
        "boltz": MagicMock(),
    }
    return update, context, message


class TestLoadBinderNLSequence(unittest.TestCase):
    def test_binder_nl_resolves_kras_g12c_sequence(self):
        card = parse_load_text("design a de novo protein binder to KRAS G12C")
        self.assertTrue(card.sequence)
        self.assertEqual(len(card.sequence), 169)
        self.assertEqual(card.sequence_source, "cached_uniprot")
        self.assertEqual(card.gene, "KRAS")
        self.assertEqual(card.variant, "G12C")

    def test_nl_without_gene_has_no_sequence(self):
        card = parse_load_text("design a de novo protein binder")
        self.assertIsNone(card.sequence)
        self.assertEqual(card.sequence_source, "missing")


class TestBoltzRefuseNoSequence(unittest.IsolatedAsyncioTestCase):
    async def test_bare_boltz_without_card_refuses_text(self):
        update, context, message = _ctx([])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_boltz(update, context)
        message.reply_text.assert_awaited()
        body = message.reply_text.await_args.args[0]
        self.assertIn("sequence is required", body.lower())
        message.reply_photo.assert_not_awaited()

    async def test_bare_boltz_after_nl_without_sequence_refuses(self):
        card = parse_load_text("design a de novo protein binder")
        user_data: dict = {}
        store_card(user_data, card)
        update, context, message = _ctx([], user_data=user_data)
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_boltz(update, context)
        message.reply_text.assert_awaited()
        body = message.reply_text.await_args.args[0]
        self.assertIn("sequence", body.lower())
        self.assertIn("does not resolve", body.lower())
        message.reply_photo.assert_not_awaited()


class TestPhotoGuards(unittest.IsolatedAsyncioTestCase):
    async def test_usable_png_rejects_none_and_empty(self):
        self.assertIsNone(_usable_png(None))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            path = Path(fh.name)
        try:
            path.write_bytes(b"tiny")
            self.assertIsNone(_usable_png(path))
        finally:
            path.unlink(missing_ok=True)

    async def test_send_structure_photo_skips_reply_when_render_returns_empty(self):
        message = MagicMock()
        message.reply_photo = AsyncMock()
        with tempfile.NamedTemporaryFile(suffix=".cif", delete=False) as fh:
            cif = Path(fh.name)
            cif.write_text("data_empty\n")
        try:
            with patch(
                "src.photo.render_structure_result",
                side_effect=lambda *a, **k: type(
                    "R",
                    (),
                    {
                        "path": Path("/tmp/does-not-exist-struct.png"),
                        "engine": "backbone_ca",
                        "simplified": True,
                    },
                )(),
            ):
                ok = await send_structure_photo(message, cif, caption="cap")
            self.assertFalse(ok)
            message.reply_photo.assert_not_awaited()
        finally:
            cif.unlink(missing_ok=True)

    async def test_backbone_render_produces_nonempty_png(self):
        if not CIF_SMOKE.is_file():
            self.skipTest("smoke CIF missing")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bb.png"
            path = _render_backbone(CIF_SMOKE, out)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 64)

    async def test_auto_render_falls_back_to_backbone(self):
        if not CIF_SMOKE.is_file():
            self.skipTest("smoke CIF missing")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "auto.png"
            path = render_cif_to_png(CIF_SMOKE, out_path=out)
            self.assertTrue(Path(path).is_file())
            self.assertGreater(Path(path).stat().st_size, 64)

    async def test_send_structure_photo_sends_bytes_not_none(self):
        if not CIF_SMOKE.is_file():
            self.skipTest("smoke CIF missing")
        message = MagicMock()
        message.reply_photo = AsyncMock()
        ok = await send_structure_photo(message, CIF_SMOKE, caption="research use only")
        self.assertTrue(ok)
        message.reply_photo.assert_awaited_once()
        kwargs = message.reply_photo.await_args.kwargs
        photo = kwargs.get("photo")
        self.assertIsInstance(photo, (bytes, bytearray))
        self.assertGreater(len(photo), 64)
        self.assertNotIn(None, message.reply_photo.await_args.args)


class TestLastRunCifOnSuccess(unittest.TestCase):
    def test_attach_last_run_keeps_cif_file_record(self):
        card = parse_load_text("design a de novo protein binder to KRAS G12C")
        cif_path = "/tmp/fake_boltz.cif"
        attach_last_run(
            card,
            kind="boltz_structure",
            interpretation="fold ok",
            files=[{"path": cif_path, "filename": "boltz.cif", "kind": "cif"}],
            result_png=None,
        )
        self.assertIsNotNone(card.last_run)
        files = card.last_run["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["kind"], "cif")
        self.assertEqual(files[0]["path"], cif_path)
        # PNG may be absent when render fails; CIF must still land.
        self.assertIsNone(card.last_run.get("result_png"))


class TestImageRenderFailedConstant(unittest.TestCase):
    def test_constant_is_clear(self):
        self.assertIn("could not be drawn", IMAGE_RENDER_FAILED.lower())


if __name__ == "__main__":
    unittest.main()


class TestRenderHonesty(unittest.IsolatedAsyncioTestCase):
    async def test_auto_prefers_pymol_when_available(self):
        if not CIF_SMOKE.is_file():
            self.skipTest("smoke CIF missing")
        from src.structure_photo import render_structure

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "auto.png"
            result = render_structure(CIF_SMOKE, out_path=out)
            self.assertTrue(result.path.is_file())
            self.assertGreater(result.path.stat().st_size, 64)
            # Host now has apt PyMOL; auto path must not be the zigzag stick.
            self.assertEqual(result.engine, "pymol")
            self.assertFalse(result.simplified)

    async def test_simplified_caption_note_appended_for_backbone(self):
        from src.photo import SIMPLIFIED_CA_CAPTION_NOTE, _caption_with_render_note

        capped = _caption_with_render_note("Fold looks compact.", simplified=True)
        self.assertIn("simplified", capped.lower())
        self.assertIn("/download", capped.lower())
        self.assertIn(SIMPLIFIED_CA_CAPTION_NOTE.split(".")[0], capped)
        plain = _caption_with_render_note("Fold looks compact.", simplified=False)
        self.assertEqual(plain, "Fold looks compact.")
        self.assertNotIn("simplified", plain.lower())

    async def test_backbone_force_still_nonempty_and_marked_simplified(self):
        if not CIF_SMOKE.is_file():
            self.skipTest("smoke CIF missing")
        from src.structure_photo import render_structure

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bb.png"
            result = render_structure(CIF_SMOKE, engine="backbone_ca", out_path=out)
            self.assertTrue(result.simplified)
            self.assertEqual(result.engine, "backbone_ca")
            self.assertGreater(result.path.stat().st_size, 64)
