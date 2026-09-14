"""Unit tests for locked /scribe (unlinked meeting minutes)."""

from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import URLError

from src.scribe_client import (
    ScribeNotConfiguredError,
    ScribeServiceError,
    organise_minutes,
    resolve_endpoint,
)
from src.scribe_md import (
    CAPTION,
    DISCLAIMER,
    MSG_ARMED,
    MSG_CANCELLED,
    MSG_EMPTY,
    MSG_FAIL_CLOSED,
    MSG_NOT_CONFIGURED,
    MSG_TOO_LONG,
    SOURCE_MAX_CHARS,
    SOURCE_NOTE,
    arm_scribe,
    end_scribe,
    ensure_skeleton,
    is_armed,
    source_error,
)


SAMPLE_LLM = """\
# Meeting minutes

Disclaimer placeholder.

## Summary
The team reviewed the KRAS G12C binder series and agreed next steps for docking.

## Decisions
- Proceed with the top three docking poses for further analysis.

## Action items
- Alice to share docking outputs by Friday.

## Discussion
Binding scores for compound 12 were discussed. Uncertainty was noted for pose 2.

## Open questions
- Whether covalent warhead geometry needs revision.

## Source note
Organised from user-supplied text; items not stated in the source were not added.
"""


class FakeHTTP:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeHTTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _completion(content: str) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode("utf-8")



class TestTemplateVerbatim(unittest.TestCase):
    """Constants must match docs/TEMPLATE-scribe.md exactly."""

    def test_locked_strings(self):
        self.assertEqual(
            DISCLAIMER,
            "This document organises user-supplied meeting text for research and "
            "documentation use only. It is not a legal medical record and is not clinical advice.",
        )
        self.assertEqual(
            SOURCE_NOTE,
            "Organised from user-supplied text; items not stated in the source were not added.",
        )
        self.assertEqual(
            CAPTION,
            "Meeting minutes organised from your text. Research use only; not a clinical record.",
        )
        self.assertEqual(
            MSG_ARMED,
            "Send the meeting notes or transcript in your next message. /scribe does not use "
            "the context card, biometric secrets, or patient files.",
        )
        self.assertEqual(MSG_CANCELLED, "Scribe cancelled. No minutes were written.")
        self.assertEqual(
            MSG_EMPTY,
            "Please provide meeting notes or a transcript. Example: /scribe then paste the text, "
            "or /scribe followed by a short note.",
        )
        self.assertEqual(
            MSG_TOO_LONG,
            "This text is too long for one pass. Please shorten it to 12000 characters or fewer "
            "and try again.",
        )
        self.assertEqual(
            MSG_FAIL_CLOSED,
            "This request cannot proceed. The scribe service is not configured or did not "
            "respond safely, so no minutes were written. Please try again shortly or contact "
            "the operator.",
        )
        self.assertEqual(MSG_NOT_CONFIGURED, MSG_FAIL_CLOSED)

    def test_template_file_present_and_contains_locks(self):
        from pathlib import Path
        from src.scribe_md import SYSTEM_PROMPT_CORE, load_biolang_override

        docs = Path(__file__).resolve().parents[1] / "docs" / "TEMPLATE-scribe.md"
        self.assertTrue(docs.is_file(), "docs/TEMPLATE-scribe.md missing")
        body = docs.read_text(encoding="utf-8")
        self.assertIn(DISCLAIMER, body)
        self.assertIn(SOURCE_NOTE, body)
        self.assertIn(CAPTION, body)
        self.assertIn(MSG_ARMED, body)
        self.assertIn(MSG_CANCELLED, body)
        self.assertIn(MSG_EMPTY, body)
        self.assertIn(MSG_TOO_LONG, body)
        self.assertIn(MSG_FAIL_CLOSED, body)
        self.assertIn(SYSTEM_PROMPT_CORE, body)
        self.assertIn("## Summary", body)
        self.assertIn("## Decisions", body)
        self.assertIn("## Action items", body)
        self.assertIn("## Discussion", body)
        self.assertIn("## Open questions", body)
        self.assertIn("## Source note", body)
        override = load_biolang_override()
        self.assertIsNotNone(override)
        self.assertIn(DISCLAIMER, override or "")


class TestSourceGates(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(source_error(""), MSG_EMPTY)
        self.assertEqual(source_error("   "), MSG_EMPTY)

    def test_oversize(self):
        self.assertEqual(source_error("x" * (SOURCE_MAX_CHARS + 1)), MSG_TOO_LONG)

    def test_ok(self):
        self.assertIsNone(source_error("Short meeting notes about docking."))


class TestSkeleton(unittest.TestCase):
    def test_required_sections_present(self):
        body = ensure_skeleton(SAMPLE_LLM)
        self.assertIn("# Meeting minutes", body)
        self.assertIn(DISCLAIMER, body)
        self.assertIn("## Summary", body)
        self.assertIn("## Source note", body)
        self.assertIn(SOURCE_NOTE, body)
        self.assertLess(body.find("## Summary"), body.find("## Decisions"))
        self.assertLess(body.find("## Decisions"), body.find("## Action items"))
        self.assertIn("## Open questions", body)

    def test_omits_empty_optional(self):
        sparse = """\
## Summary
Docking was discussed.

## Decisions
None.

## Source note
Organised from user-supplied text; items not stated in the source were not added.
"""
        body = ensure_skeleton(sparse)
        self.assertIn("## Summary", body)
        self.assertNotIn("## Decisions", body)
        self.assertIn("## Source note", body)

    def test_does_not_invent_when_no_sections(self):
        body = ensure_skeleton("We talked about timeline only.")
        self.assertIn("## Summary", body)
        self.assertIn("We talked about timeline only.", body)
        self.assertNotIn("## Decisions", body)
        self.assertIn("## Source note", body)


class TestArmCancel(unittest.TestCase):
    def test_arm_and_cancel(self):
        user_data: dict = {}
        arm_scribe(user_data)
        self.assertTrue(is_armed(user_data))
        self.assertTrue(end_scribe(user_data))
        self.assertFalse(is_armed(user_data))
        self.assertFalse(end_scribe(user_data))


class TestClientFailClosed(unittest.TestCase):
    def test_missing_url_raises(self):
        with patch.dict(os.environ, {"SCRIBE_LLM_URL": ""}, clear=False):
            os.environ.pop("SCRIBE_LLM_URL", None)
            with self.assertRaises(ScribeNotConfiguredError):
                resolve_endpoint("")
            with self.assertRaises(ScribeNotConfiguredError):
                organise_minutes("notes", url="")

    def test_down_raises(self):
        with patch(
            "src.scribe_client.urlopen",
            side_effect=URLError("down"),
        ):
            with self.assertRaises(ScribeServiceError):
                organise_minutes("notes", url="http://127.0.0.1:9/v1")

    def test_mock_llm_returns_content(self):
        fake = FakeHTTP(_completion(SAMPLE_LLM))
        with patch("src.scribe_client.urlopen", return_value=fake) as opener:
            out = organise_minutes(
                "Team discussed docking.",
                url="http://example.test/v1",
                api_key="k",
                model="m",
            )
        self.assertIn("## Summary", out)
        opener.assert_called_once()
        req = opener.call_args.args[0]
        self.assertTrue(str(req.full_url).endswith("/chat/completions"))
        sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(sent["model"], "m")
        self.assertEqual(sent["messages"][1]["content"], "Team discussed docking.")
        # Must not log full source at INFO — check call used length only via logger
        # (behavioural: organise accepts and returns; logging asserted separately below)

    def test_info_log_does_not_include_full_source(self):
        secret = "SECRET_MEETING_BODY_DO_NOT_LOG_FULLY"
        fake = FakeHTTP(_completion(SAMPLE_LLM))
        with patch("src.scribe_client.urlopen", return_value=fake):
            with self.assertLogs("src.scribe_client", level="INFO") as cm:
                organise_minutes(secret, url="http://example.test/v1/chat/completions")
        joined = "\n".join(cm.output)
        self.assertNotIn(secret, joined)
        self.assertIn(f"chars={len(secret)}", joined)


class TestCmdScribe(unittest.IsolatedAsyncioTestCase):
    def _ctx(self, args: list[str], user_data: dict | None = None):
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.reply_document = AsyncMock()
        message.text = " ".join(args) if args else ""
        update = MagicMock()
        update.effective_message = message
        context = MagicMock()
        context.args = args
        context.user_data = user_data if user_data is not None else {}
        settings = MagicMock()
        settings.scribe_llm_url = "http://example.test/v1"
        settings.scribe_llm_key = "k"
        settings.scribe_llm_model = "m"
        context.application.bot_data = {"settings": settings}
        return update, context, message

    async def test_bare_arms(self):
        from src.bot import cmd_scribe

        update, context, message = self._ctx([])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_scribe(update, context)
        self.assertTrue(is_armed(context.user_data))
        message.reply_text.assert_awaited_once_with(MSG_ARMED)
        message.reply_document.assert_not_called()

    async def test_oversize_refuses(self):
        from src.bot import cmd_scribe

        update, context, message = self._ctx(["x" * (SOURCE_MAX_CHARS + 1)])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch("src.bot.organise_minutes") as org:
                await cmd_scribe(update, context)
        org.assert_not_called()
        message.reply_text.assert_awaited_once_with(MSG_TOO_LONG)

    async def test_missing_config_fail_closed(self):
        from src.bot import cmd_scribe

        update, context, message = self._ctx(["Docking", "review"])
        context.application.bot_data = {"settings": MagicMock(
            scribe_llm_url="", scribe_llm_key="", scribe_llm_model=""
        )}
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.organise_minutes",
                side_effect=ScribeNotConfiguredError("unset"),
            ):
                await cmd_scribe(update, context)
        message.reply_text.assert_awaited_once_with(MSG_NOT_CONFIGURED)
        message.reply_document.assert_not_called()

    async def test_down_fail_closed(self):
        from src.bot import cmd_scribe

        update, context, message = self._ctx(["Docking", "review"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.organise_minutes",
                side_effect=ScribeServiceError("down"),
            ):
                await cmd_scribe(update, context)
        message.reply_text.assert_awaited_once_with(MSG_FAIL_CLOSED)
        message.reply_document.assert_not_called()

    async def test_sends_markdown_document(self):
        from src.bot import cmd_scribe

        update, context, message = self._ctx(["Team", "discussed", "docking."])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.asyncio.to_thread",
                new=AsyncMock(return_value=SAMPLE_LLM),
            ):
                await cmd_scribe(update, context)
        message.reply_document.assert_awaited()
        kwargs = message.reply_document.await_args.kwargs
        self.assertEqual(kwargs["filename"], "meeting-minutes.md")
        self.assertEqual(kwargs["caption"], CAPTION)
        body = kwargs["document"].getvalue().decode("utf-8")
        self.assertIn("## Summary", body)
        self.assertIn("## Source note", body)
        self.assertIsInstance(kwargs["document"], BytesIO)

    async def test_unlinked_card_patient_unchanged(self):
        from src.bot import cmd_scribe
        from src.context_card import CONTEXT_CARD_KEY

        user_data = {
            CONTEXT_CARD_KEY: {
                "intent": "fold",
                "sequence": "MTEYKLVVVG",
                "patient": {"age_years": 55, "complete": True},
                "patient_files": [{"text": "private note", "id": "1"}],
            }
        }
        before = deepcopy(user_data[CONTEXT_CARD_KEY])
        update, context, message = self._ctx(["Brief", "standup"], user_data=user_data)
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.asyncio.to_thread",
                new=AsyncMock(return_value=SAMPLE_LLM),
            ):
                with patch("src.onboard.get_patient") as get_patient:
                    with patch("src.patient_files.get_patient_files") as get_files:
                        with patch("src.context_card.load_card") as load_card:
                            with patch("src.context_card.store_card") as store_card:
                                await cmd_scribe(update, context)
        get_patient.assert_not_called()
        get_files.assert_not_called()
        load_card.assert_not_called()
        store_card.assert_not_called()
        self.assertEqual(user_data[CONTEXT_CARD_KEY], before)
        body = message.reply_document.await_args.kwargs["document"].getvalue().decode()
        self.assertNotIn("private note", body)
        self.assertNotIn("age_years", body)
        self.assertNotIn("55", body)

    async def test_cancel_disarms_scribe_keeps_note_design_hooks(self):
        from src.bot import PENDING_DESIGN_KEY, cmd_cancel
        from src import patient_files as pf
        from src import onboard as onboard_mod

        user_data: dict = {PENDING_DESIGN_KEY: {"n": 10}}
        arm_scribe(user_data)
        pf.arm_note(user_data)
        # Simulate active onboard field without full start
        user_data[onboard_mod.ONBOARD_KEY] = {"field": "age_years"}

        message = MagicMock()
        message.reply_text = AsyncMock()
        update = MagicMock()
        update.effective_message = message
        context = MagicMock()
        context.user_data = user_data
        context.args = []

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_cancel(update, context)

        self.assertFalse(is_armed(user_data))
        self.assertFalse(pf.is_armed(user_data))
        self.assertNotIn(PENDING_DESIGN_KEY, user_data)
        # end_onboard should have cleared active onboard
        self.assertFalse(onboard_mod.is_active(user_data))
        reply = message.reply_text.await_args.args[0]
        self.assertIn(MSG_CANCELLED, reply)
        self.assertIn("design", reply.lower())
        self.assertIn("note", reply.lower())

    async def test_cancel_scribe_only(self):
        from src.bot import cmd_cancel

        user_data: dict = {}
        arm_scribe(user_data)
        message = MagicMock()
        message.reply_text = AsyncMock()
        update = MagicMock()
        update.effective_message = message
        context = MagicMock()
        context.user_data = user_data

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_cancel(update, context)
        self.assertFalse(is_armed(user_data))
        message.reply_text.assert_awaited_once_with(MSG_CANCELLED)

    async def test_on_text_priority_scribe_after_note(self):
        from src.bot import on_text
        from src import patient_files as pf

        # When note is armed, note wins over scribe
        user_data: dict = {}
        # Need patient for note to save — arm note state directly
        pf.arm_note(user_data)
        arm_scribe(user_data)

        message = MagicMock()
        message.reply_text = AsyncMock()
        message.reply_document = AsyncMock()
        message.text = "a patient note body"
        update = MagicMock()
        update.effective_message = message
        context = MagicMock()
        context.user_data = user_data

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.patient_files.append_note",
                return_value="saved",
            ) as append:
                await on_text(update, context)
        append.assert_called_once()
        message.reply_document.assert_not_called()
        # scribe remains armed because note path returned first
        self.assertTrue(is_armed(user_data))

    async def test_on_text_runs_armed_scribe(self):
        from src.bot import on_text

        user_data: dict = {}
        arm_scribe(user_data)
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.reply_document = AsyncMock()
        message.text = "Standup: docking poses reviewed."
        update = MagicMock()
        update.effective_message = message
        context = MagicMock()
        context.user_data = user_data
        settings = MagicMock()
        settings.scribe_llm_url = "http://example.test/v1"
        settings.scribe_llm_key = "k"
        settings.scribe_llm_model = "m"
        context.application.bot_data = {"settings": settings}

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.asyncio.to_thread",
                new=AsyncMock(return_value=SAMPLE_LLM),
            ):
                await on_text(update, context)
        self.assertFalse(is_armed(user_data))
        message.reply_document.assert_awaited()
        self.assertEqual(
            message.reply_document.await_args.kwargs["caption"], CAPTION
        )

    async def test_help_lists_scribe(self):
        from src.bot import HELP_TEXT

        self.assertIn("/scribe", HELP_TEXT)
        self.assertIn("Unlinked", HELP_TEXT)

    async def test_no_discord_on_scribe(self):
        from src.bot import cmd_scribe

        update, context, message = self._ctx(["notes"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.asyncio.to_thread",
                new=AsyncMock(return_value=SAMPLE_LLM),
            ):
                with patch("src.discord_webhook.post_discord_message") as discord:
                    await cmd_scribe(update, context)
        discord.assert_not_called()


class TestConfigEnv(unittest.TestCase):
    def test_settings_fields_optional(self):
        from src.config import Settings

        fields = Settings.__dataclass_fields__
        self.assertIn("scribe_llm_url", fields)
        self.assertIn("scribe_llm_key", fields)
        self.assertIn("scribe_llm_model", fields)


if __name__ == "__main__":
    unittest.main()
