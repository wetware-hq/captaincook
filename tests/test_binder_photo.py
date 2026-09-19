"""Binder result image: N=1 single complex / N>1 grid; text fallback; locked COPY."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.bindcraft import BinderDesignResult
from src.bot import (
    COPY_BINDER_RESULT_PHOTO_GRID,
    COPY_BINDER_RESULT_PHOTO_N1,
    COPY_BINDER_RESULT_TEXT_FALLBACK,
    PENDING_DESIGN_KEY,
    cmd_confirm,
)
from src.photo import list_binder_cifs, render_binder_png, send_binder_photo

CIF_A = Path("/tmp/binder_modal_1_qnat1o/binder_e25e85bbfe10_0.cif")
CIF_B = Path("/tmp/binder_modal_1_qnat1o/binder_e25e85bbfe10_1.cif")


def _confirm_ctx(*, artifacts: list[str] | None = None):
    update = MagicMock()
    message = MagicMock()
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    update.effective_message = message
    update.effective_user = MagicMock(id=1)
    update.effective_chat = MagicMock(id=42)
    context = MagicMock()
    context.args = []
    context.user_data = {
        PENDING_DESIGN_KEY: {
            "mode": "binder",
            "n_designs": 1,
            "structure_path": str(CIF_A) if CIF_A.is_file() else None,
            "hotspot_residues": None,
            "sequence": "M" * 50,
            "hotspot_provenance": "none",
        }
    }
    context.application.bot_data = {
        "settings": MagicMock(
            bindcraft_home="",
            bindcraft_timeout_sec=60,
            modal_token_id="id",
            modal_token_secret="sec",
            modal_bindcraft_app="app",
            telegram_allowed_user_id=None,
            max_sequence_length=800,
            commec_bin="commec",
            commec_timeout_sec=60,
        )
    }
    return update, context, message


class TestBinderCopyLocked(unittest.TestCase):
    def test_photo_n1_caption(self):
        self.assertIn("one ranked in-silico protein binder", COPY_BINDER_RESULT_PHOTO_N1)
        self.assertIn("This image shows the loaded target", COPY_BINDER_RESULT_PHOTO_N1)
        self.assertIn("Research use only", COPY_BINDER_RESULT_PHOTO_N1)

    def test_photo_grid_caption(self):
        self.assertIn("grid of ranked in-silico protein binders", COPY_BINDER_RESULT_PHOTO_GRID)
        self.assertIn("Each cell is a computational complex view", COPY_BINDER_RESULT_PHOTO_GRID)

    def test_text_fallback_points_download_no_image_claim(self):
        self.assertIn("/download", COPY_BINDER_RESULT_TEXT_FALLBACK)
        self.assertNotIn("This image shows", COPY_BINDER_RESULT_TEXT_FALLBACK)
        self.assertNotIn("This image is a grid", COPY_BINDER_RESULT_TEXT_FALLBACK)


class TestListBinderCifs(unittest.TestCase):
    def test_filters_existing_cifs_only(self):
        paths = list_binder_cifs(
            [
                str(CIF_A) if CIF_A.is_file() else "/nope.cif",
                "/tmp/does-not-exist-binder.cif",
                "/tmp/binder_modal_1_qnat1o/binder_e25e85bbfe10.fasta",
            ]
        )
        if CIF_A.is_file():
            self.assertEqual(paths, [CIF_A.resolve()])
        else:
            self.assertEqual(paths, [])


class TestRenderBinderPng(unittest.TestCase):
    def test_n1_single_complex(self):
        if not CIF_A.is_file():
            self.skipTest("binder CIF missing")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "n1.png"
            path, n = render_binder_png([CIF_A], out_path=out)
            self.assertEqual(n, 1)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 64)

    def test_n_gt1_grid(self):
        if not (CIF_A.is_file() and CIF_B.is_file()):
            self.skipTest("need two binder CIFs")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "grid.png"
            path, n = render_binder_png([CIF_A, CIF_B], out_path=out)
            self.assertEqual(n, 2)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 64)


class TestSendBinderPhoto(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_photo_n1_caption(self):
        if not CIF_A.is_file():
            self.skipTest("binder CIF missing")
        message = MagicMock()
        message.reply_photo = AsyncMock()
        caption = await send_binder_photo(
            message,
            [CIF_A],
            caption_n1=COPY_BINDER_RESULT_PHOTO_N1,
            caption_grid=COPY_BINDER_RESULT_PHOTO_GRID,
        )
        self.assertEqual(caption, COPY_BINDER_RESULT_PHOTO_N1)
        message.reply_photo.assert_awaited_once()
        self.assertEqual(
            message.reply_photo.await_args.kwargs["caption"],
            COPY_BINDER_RESULT_PHOTO_N1,
        )

    async def test_grid_caption_when_two_cells(self):
        if not (CIF_A.is_file() and CIF_B.is_file()):
            self.skipTest("need two binder CIFs")
        message = MagicMock()
        message.reply_photo = AsyncMock()
        caption = await send_binder_photo(
            message,
            [CIF_A, CIF_B],
            caption_n1=COPY_BINDER_RESULT_PHOTO_N1,
            caption_grid=COPY_BINDER_RESULT_PHOTO_GRID,
        )
        self.assertEqual(caption, COPY_BINDER_RESULT_PHOTO_GRID)
        message.reply_photo.assert_awaited_once()

    async def test_render_fail_returns_none_no_photo(self):
        message = MagicMock()
        message.reply_photo = AsyncMock()
        with patch("src.photo.render_binder_png", side_effect=RuntimeError("boom")):
            caption = await send_binder_photo(
                message,
                [CIF_A] if CIF_A.is_file() else [Path("/tmp/x.cif")],
                caption_n1=COPY_BINDER_RESULT_PHOTO_N1,
                caption_grid=COPY_BINDER_RESULT_PHOTO_GRID,
            )
        self.assertIsNone(caption)
        message.reply_photo.assert_not_awaited()


class TestConfirmBinderPhotoPath(unittest.IsolatedAsyncioTestCase):
    async def test_success_prefers_photo(self):
        if not CIF_A.is_file():
            self.skipTest("binder CIF missing")
        update, context, message = _confirm_ctx()
        result = BinderDesignResult(
            designs=[{"id": "d0"}],
            run_id="testphoto",
            artifact_paths=[str(CIF_A)],
            source="modal",
        )
        with (
            patch("src.bot._authorized", new=AsyncMock(return_value=True)),
            patch("src.bot._refuse_if_blocked", new=AsyncMock(return_value=False)),
            patch("src.bot.bindcraft_mod.run_binder_design", return_value=result),
            patch(
                "src.bot.send_binder_photo",
                new=AsyncMock(return_value=COPY_BINDER_RESULT_PHOTO_N1),
            ) as send_mock,
            patch("src.bot._persist_interpretation", new=AsyncMock()),
            patch("src.bot._safe_emit"),
            patch("src.bot.load_card", return_value=None),
        ):
            await cmd_confirm(update, context)
        send_mock.assert_awaited()
        message.reply_photo.assert_not_awaited()  # send_binder_photo mocked
        message.reply_text.assert_not_awaited()

    async def test_render_fail_uses_text_fallback(self):
        if not CIF_A.is_file():
            self.skipTest("binder CIF missing")
        update, context, message = _confirm_ctx()
        result = BinderDesignResult(
            designs=[{"id": "d0"}],
            run_id="testfail",
            artifact_paths=[str(CIF_A)],
            source="modal",
        )
        with (
            patch("src.bot._authorized", new=AsyncMock(return_value=True)),
            patch("src.bot._refuse_if_blocked", new=AsyncMock(return_value=False)),
            patch("src.bot.bindcraft_mod.run_binder_design", return_value=result),
            patch("src.bot.send_binder_photo", new=AsyncMock(return_value=None)),
            patch("src.bot._persist_interpretation", new=AsyncMock()),
            patch("src.bot._safe_emit"),
            patch("src.bot.load_card", return_value=None),
        ):
            await cmd_confirm(update, context)
        message.reply_text.assert_awaited_once_with(COPY_BINDER_RESULT_TEXT_FALLBACK)
        self.assertIn("/download", message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
