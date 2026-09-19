"""Unit tests for /board packet assembly (FEATURE-board + TEMPLATE-board)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src import board_md
from src import onboard as onboard_mod
from src import patient_files as patient_files_mod
from src import store
from src.context_card import (
    CONTEXT_CARD_KEY,
    ContextCard,
    attach_last_run,
    parse_load_text,
    store_card,
)


class TestTemplateVerbatim(unittest.TestCase):
    def test_locked_strings(self):
        self.assertIn("research use only", board_md.DISCLAIMER.lower())
        self.assertNotIn("oncology-only", board_md.DISCLAIMER.lower())
        self.assertEqual(
            board_md.CAPTION,
            "Board packet for this session. Research use only; not a clinical record.",
        )
        self.assertIn("/load", board_md.MSG_REFUSE)
        self.assertIn("/onboard", board_md.MSG_REFUSE)
        self.assertEqual(
            board_md.EVIDENCE_NONE,
            "None yet. Run /evidence with a clear clinical or scientific question.",
        )
        self.assertIn("/design ligand", board_md.LAB_NONE)


class TestEmptyRefuse(unittest.TestCase):
    def test_empty_user_data_has_no_inputs(self):
        self.assertFalse(board_md.has_board_inputs({}))
        self.assertFalse(board_md.has_board_inputs(None))

    def test_render_empty_uses_none_yet_lines(self):
        # Caller should refuse; if render is invoked anyway, lines are honest.
        body = board_md.render_board_md({})
        self.assertIn(board_md.EVIDENCE_NONE, body)
        self.assertIn(board_md.LAB_NONE, body)
        self.assertIn("Patient biometrics: none", body)
        self.assertIn("Patient files: 0 on file", body)
        self.assertNotIn("diagnose", body.lower())


class TestBiometricsNeverRaw(unittest.TestCase):
    def test_complete_biometrics_label_only(self):
        user_data: dict = {}
        card = parse_load_text("find inhibitor for KRAS G12C GDP covalent")
        store_card(user_data, card)
        patient = onboard_mod.empty_patient()
        patient.update(
            {
                "age_years": 67,
                "sex": "F",
                "weight_kg": 72.5,
                "height_cm": 165.0,
            }
        )
        onboard_mod.set_patient(user_data, patient)
        self.assertEqual(board_md.biometrics_label(user_data), "on file")
        body = board_md.render_board_md(user_data)
        self.assertIn("Patient biometrics: on file", body)
        self.assertNotIn("67", body)
        self.assertNotIn("72.5", body)
        self.assertNotIn("165", body)
        self.assertNotIn(" F", body)  # sex letter not echoed as value line
        # BMI must not appear
        bmi = onboard_mod.get_patient(user_data).get("bmi")
        if bmi is not None:
            self.assertNotIn(str(bmi), body)

    def test_incomplete_biometrics(self):
        user_data: dict = {}
        store_card(user_data, ContextCard(raw_text="case", intent="fold"))
        patient = onboard_mod.empty_patient()
        patient["age_years"] = 42
        onboard_mod.set_patient(user_data, patient)
        self.assertEqual(board_md.biometrics_label(user_data), "incomplete")
        body = board_md.render_board_md(user_data)
        self.assertIn("Patient biometrics: incomplete", body)
        self.assertNotIn("42", body)


class TestCardAndBinder(unittest.TestCase):
    def test_packet_includes_design_id_without_secrets(self):
        user_data: dict = {}
        card = parse_load_text("design a de novo protein binder to KRAS G12C")
        card = attach_last_run(
            card,
            kind="binder_design",
            interpretation="Binder designs ready for research use only.",
            run_id="abc12deadbeef",
            metrics={"n": 5},
        )
        store_card(user_data, card)
        body = board_md.render_board_md(user_data)
        self.assertIn("KRAS", body)
        self.assertIn("G12C", body)
        self.assertIn("`binder:abc12deadbeef`", body)
        self.assertIn(board_md.LAB_RESEARCH_LINE, body)
        self.assertIn(board_md.EVIDENCE_NONE, body)
        # No secret-looking fields
        self.assertNotIn("weight_kg", body)
        self.assertNotIn("patient_id", body.lower().split("patient files")[0])  # loose


class TestLabAndSearchDesigns(unittest.TestCase):
    def test_lab_tag_and_search_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(store, "STORE_ROOT", root):
                uid = 42
                pid = "patient-test-1"
                store.ensure_patient_files(uid, pid)
                lab = {
                    "cells": [
                        {
                            "cell_type": "markdown",
                            "metadata": {"tags": ["binder:des99"]},
                            "source": ["## Protein-binder design\n"],
                        }
                    ]
                }
                store.lab_path(uid, pid).write_text(json.dumps(lab), encoding="utf-8")
                search = {
                    "entries": [
                        {
                            "title": "ligand:lig77",
                            "section": "Small-molecule design",
                            "tokens": ["ligand:lig77"],
                        }
                    ]
                }
                store.search_path(uid, pid).write_text(
                    json.dumps(search), encoding="utf-8"
                )
                user_data: dict = {}
                store_card(
                    user_data,
                    parse_load_text("find inhibitor for KRAS G12C"),
                )
                # Attach patient_id so store lookup works
                patient = onboard_mod.empty_patient()
                patient["patient_id"] = pid
                onboard_mod.set_patient(user_data, patient)
                body = board_md.render_board_md(user_data, user_id=uid)
                self.assertIn("`binder:des99`", body)
                self.assertIn("`ligand:lig77`", body)


class TestEvidenceFromClinic(unittest.TestCase):
    def test_clinic_evidence_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(store, "STORE_ROOT", root):
                uid = 7
                pid = "p-ev"
                store.ensure_patient_files(uid, pid)
                clinic = store.clinic_path(uid, pid).read_text(encoding="utf-8")
                # Replace empty Evidence section
                unit = (
                    "## Evidence\n\n"
                    "### 10.1000/example.1\n\n"
                    "- Sotorasib improves outcomes (Smith et al., 2024).\n\n"
                    "#### References\n\n"
                    "Smith, J.A., 2024. Title. Nature. https://doi.org/10.1000/example.1\n"
                )
                import re

                clinic2 = re.sub(
                    r"## Evidence\n",
                    unit,
                    clinic,
                    count=1,
                )
                store.clinic_path(uid, pid).write_text(clinic2, encoding="utf-8")
                user_data: dict = {}
                store_card(user_data, parse_load_text("KRAS G12C"))
                patient = onboard_mod.empty_patient()
                patient["patient_id"] = pid
                onboard_mod.set_patient(user_data, patient)
                body = board_md.render_board_md(user_data, user_id=uid)
                self.assertIn("Sotorasib improves outcomes", body)
                self.assertIn("10.1000/example.1", body)
                self.assertNotIn(board_md.EVIDENCE_NONE, body)


class TestPatientFilesCount(unittest.TestCase):
    def test_count_only(self):
        user_data: dict = {}
        store_card(user_data, ContextCard(raw_text="x", intent="fold"))
        onboard_mod.ensure_patient(user_data)
        patient_files_mod.set_patient_files(
            user_data,
            [
                {"id": "a", "text": "SECRET NOTE BODY", "created_at": "t"},
                {"id": "b", "text": "ANOTHER SECRET", "created_at": "t"},
            ],
        )
        body = board_md.render_board_md(user_data)
        self.assertIn("Patient files: 2 on file", body)
        self.assertNotIn("SECRET NOTE BODY", body)
        self.assertNotIn("ANOTHER SECRET", body)


class TestCmdBoard(unittest.IsolatedAsyncioTestCase):
    async def test_refuse_when_empty(self):
        update = MagicMock()
        update.effective_user = MagicMock(id=1)
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.reply_document = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        context.application.bot_data = {
            "settings": MagicMock(telegram_allowed_user_id=None)
        }
        from src.bot import cmd_board

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_board(update, context)
        update.effective_message.reply_text.assert_awaited_once()
        args = update.effective_message.reply_text.await_args
        self.assertEqual(args.args[0], board_md.MSG_REFUSE_APP)
        update.effective_message.reply_document.assert_not_called()

    async def test_document_with_card(self):
        user_data: dict = {}
        card = parse_load_text("find inhibitor for KRAS G12C")
        card = attach_last_run(
            card,
            kind="binder_design",
            interpretation="ok",
            run_id="bind42",
        )
        store_card(user_data, card)
        update = MagicMock()
        update.effective_user = MagicMock(id=1)
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.reply_document = AsyncMock()
        context = MagicMock()
        context.user_data = user_data
        context.application.bot_data = {
            "settings": MagicMock(telegram_allowed_user_id=None)
        }
        from src.bot import cmd_board

        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_board(update, context)
        update.effective_message.reply_document.assert_awaited_once()
        kwargs = update.effective_message.reply_document.await_args.kwargs
        self.assertEqual(kwargs["filename"], "case-conference-packet.md")
        self.assertEqual(kwargs["caption"], board_md.CAPTION_MD_ONLY)
        doc = kwargs["document"]
        doc.seek(0)
        body = doc.read().decode("utf-8")
        self.assertIn("`binder:bind42`", body)
        self.assertIn("# Case conference packet", body)
        # Optional stash
        stored = user_data.get(CONTEXT_CARD_KEY) or {}
        lr = stored.get("last_run") or {}
        self.assertEqual(lr.get("board_md"), "case-conference-packet.md")


class TestHelpMentionsBoard(unittest.TestCase):
    def test_help_has_board_specialty_agnostic(self):
        from src.bot import HELP_TEXT

        self.assertIn("/board", HELP_TEXT)
        # Must not brand HELP as oncology-only product identity
        low = HELP_TEXT.lower()
        self.assertNotIn("oncology-only", low)
        self.assertNotIn("tumour board only", low)
        self.assertIn("specialty-agnostic", low)


if __name__ == "__main__":
    unittest.main()


class TestBoardUpdateAlias(unittest.TestCase):
    def test_help_lists_board_update(self):
        from src import bot as bot_mod
        self.assertIn("/board update", bot_mod.HELP_TEXT)
        self.assertIn("/app", bot_mod.HELP_TEXT)
        self.assertIn("Alias of /app", bot_mod.HELP_TEXT)

    def test_feature_doc_alias(self):
        from pathlib import Path
        feat = Path("docs/FEATURE-board.md").read_text()
        self.assertIn("`/board update`", feat)
        self.assertIn("Strict alias", feat)
