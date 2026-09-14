"""Unit tests for /note patient files (separate from biometric secrets)."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.card_cache import fingerprint
from src.context_card import ContextCard, clear_card, format_card, load_card, store_card
from src import onboard as onboard_mod
from src import patient_files as pf
from src import research_md
from src import discord_webhook
from src import interpret


KRAS_SEQ = (
    "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRTGEG"
    "FLCVFAINNTKSFEDIHHYREQIKRVKDSEDVPMVLVGNKCDLPSRTVDTKQAQDLARSYGIPFIETSAKTRQGVDDA"
    "FYTLVREIRKHKEK"
)


def _g12c_card() -> ContextCard:
    return ContextCard(
        intent="small_molecule_design",
        gene="KRAS",
        variant="G12C",
        sequence=KRAS_SEQ,
        n_designs=10,
        chemical_space="enamine_real",
        state="GDP",
        covalent=False,
    )


def _onboard_complete(user_data: dict) -> None:
    store_card(user_data, _g12c_card())
    onboard_mod.start_or_resume(user_data)
    for ans in ("75", "F", "70", "175"):
        onboard_mod.apply_answer(user_data, ans)


class TestCopyExact(unittest.TestCase):
    def test_locked_phrases(self):
        self.assertEqual(
            pf.MSG_ARMED,
            "Send your note in the next message. It will be saved to patient files on this card. "
            "Biometric secrets from /onboard are separate and are not changed.",
        )
        self.assertEqual(
            pf.MSG_SAVED,
            "Note saved to patient files ({n} on file). Biometric secrets are unchanged.",
        )
        self.assertEqual(
            pf.MSG_LIST,
            "Patient files on this card: {n}. Contents are not shown. Biometric secrets are separate.",
        )
        self.assertEqual(
            pf.MSG_LIST_ZERO,
            "No patient files on this card. Biometric secrets, if any, are separate.",
        )
        self.assertEqual(
            pf.MSG_CLEAR,
            "Patient files have been cleared. Biometric secrets are unchanged.",
        )
        self.assertEqual(
            pf.MSG_NO_PATIENT,
            "This request cannot proceed. There is no patient on the current card. "
            "Complete /onboard first, then use /note to add patient files. "
            "Biometric secrets and patient files are separate stores.",
        )
        self.assertEqual(
            pf.MSG_TOO_LONG,
            "This note is too long. Please shorten it to 2000 characters or fewer and send it again.",
        )
        self.assertEqual(
            pf.MSG_REFUSE_LM,
            "This request cannot be fulfilled. Patient files and biometric secrets stay on this "
            "chat’s card for research context only. They are not sent to language models, "
            "research briefs, or Discord, and this bot does not diagnose from them.",
        )
        for s in (
            pf.MSG_ARMED,
            pf.MSG_SAVED,
            pf.MSG_LIST,
            pf.MSG_LIST_ZERO,
            pf.MSG_CLEAR,
            pf.MSG_NO_PATIENT,
            pf.MSG_TOO_LONG,
            pf.MSG_REFUSE_LM,
        ):
            self.assertNotIn("patient data", s.lower())


class TestRefuseWithoutPatient(unittest.TestCase):
    def test_refuse_empty(self):
        user_data: dict = {}
        reply = pf.start_note(user_data)
        self.assertEqual(reply, pf.MSG_NO_PATIENT)
        self.assertFalse(pf.is_armed(user_data))
        self.assertEqual(pf.get_patient_files(user_data), [])

    def test_refuse_card_without_patient(self):
        user_data: dict = {}
        store_card(user_data, _g12c_card())
        reply = pf.start_note(user_data)
        self.assertEqual(reply, pf.MSG_NO_PATIENT)
        self.assertIsNone(onboard_mod.get_patient(user_data))


class TestSaveAfterOnboard(unittest.TestCase):
    def test_arm_save_list(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        reply = pf.start_note(user_data)
        self.assertEqual(reply, pf.MSG_ARMED)
        self.assertTrue(pf.is_armed(user_data))

        secret_body = "Research note: prior KRAS inhibitor exposure; do not echo this body."
        saved = pf.append_note(user_data, secret_body)
        self.assertEqual(saved, pf.MSG_SAVED.format(n=1))
        self.assertNotIn(secret_body, saved)
        self.assertFalse(pf.is_armed(user_data))

        files = pf.get_patient_files(user_data)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["text"], secret_body)
        self.assertIn("id", files[0])
        self.assertIn("created_at", files[0])

        listed = pf.list_text(user_data)
        self.assertEqual(listed, pf.MSG_LIST.format(n=1))
        self.assertNotIn(secret_body, listed)

        # /load style card must not echo note body
        body = format_card(
            load_card(user_data), patient=onboard_mod.get_patient(user_data)
        )
        self.assertIn("Patient: on file.", body)
        self.assertNotIn(secret_body, body)
        self.assertNotIn("75", body)


class TestClearFilesKeepBiometrics(unittest.TestCase):
    def test_note_clear(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        pf.start_note(user_data)
        pf.append_note(user_data, "file one")
        self.assertEqual(len(pf.get_patient_files(user_data)), 1)

        cleared = pf.clear_text(user_data)
        self.assertEqual(cleared, pf.MSG_CLEAR)
        self.assertEqual(pf.get_patient_files(user_data), [])
        patient = onboard_mod.get_patient(user_data)
        assert patient is not None
        self.assertTrue(patient["complete"])
        self.assertEqual(patient["age_years"], 75)

    def test_onboard_clear_drops_both(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        pf.start_note(user_data)
        pf.append_note(user_data, "will vanish with patient")
        self.assertTrue(onboard_mod.clear_patient(user_data))
        self.assertIsNone(onboard_mod.get_patient(user_data))
        self.assertEqual(pf.get_patient_files(user_data), [])

    def test_load_clear_drops_card_biometrics_files(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        pf.start_note(user_data)
        pf.append_note(user_data, "gone with card")
        self.assertTrue(clear_card(user_data))
        self.assertIsNone(load_card(user_data))
        self.assertIsNone(onboard_mod.get_patient(user_data))
        self.assertEqual(pf.get_patient_files(user_data), [])


class TestFingerprintUnchanged(unittest.TestCase):
    def test_notes_do_not_change_fingerprint(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        card = load_card(user_data)
        assert card is not None
        fp_before = fingerprint(card)

        pf.start_note(user_data)
        pf.append_note(user_data, "alpha note")
        pf.start_note(user_data)
        pf.append_note(user_data, "beta note")

        loaded = load_card(user_data)
        assert loaded is not None
        self.assertEqual(fp_before, fingerprint(loaded))
        self.assertEqual(len(pf.get_patient_files(user_data)), 2)
        # patient_files not on dataclass
        self.assertFalse(hasattr(loaded, "patient_files"))


class TestTooLongRejected(unittest.TestCase):
    def test_reject_keeps_armed(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        pf.start_note(user_data)
        huge = "x" * (pf.NOTE_MAX_CHARS + 1)
        reply = pf.append_note(user_data, huge)
        self.assertEqual(reply, pf.MSG_TOO_LONG)
        self.assertTrue(pf.is_armed(user_data))
        self.assertEqual(pf.get_patient_files(user_data), [])
        # re-ask: shorter note works
        ok = pf.append_note(user_data, "short enough")
        self.assertEqual(ok, pf.MSG_SAVED.format(n=1))


class TestCancelDisarms(unittest.TestCase):
    def test_cancel_keeps_files(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        pf.start_note(user_data)
        pf.append_note(user_data, "keep me")
        pf.start_note(user_data)
        self.assertTrue(pf.is_armed(user_data))
        self.assertTrue(pf.end_note(user_data))
        self.assertFalse(pf.is_armed(user_data))
        self.assertEqual(len(pf.get_patient_files(user_data)), 1)


class TestStorePreservesFiles(unittest.TestCase):
    def test_store_preserves(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        pf.start_note(user_data)
        pf.append_note(user_data, "persist across store")
        store_card(user_data, _g12c_card())
        self.assertEqual(len(pf.get_patient_files(user_data)), 1)
        self.assertEqual(pf.get_patient_files(user_data)[0]["text"], "persist across store")
        self.assertEqual(onboard_mod.get_patient(user_data)["age_years"], 75)


class TestListZero(unittest.TestCase):
    def test_zero(self):
        user_data: dict = {}
        _onboard_complete(user_data)
        self.assertEqual(pf.list_text(user_data), pf.MSG_LIST_ZERO)


class TestGuards(unittest.TestCase):
    def test_assert_blocks_patient_keys(self):
        with self.assertRaises(ValueError):
            pf.assert_no_secret_payload({"patient": {"age_years": 1}}, where="test")
        with self.assertRaises(ValueError):
            pf.assert_no_secret_payload(
                {"patient_files": [{"text": "no"}]}, where="test"
            )
        pf.assert_no_secret_payload({"topic": "KRAS", "n": 1}, where="test")

    def test_downstream_modules_do_not_reference_patient_files(self):
        src_root = Path(__file__).resolve().parents[1] / "src"
        offenders = []
        for name in ("research_md.py", "discord_webhook.py", "interpret.py", "result_photo.py"):
            blob = (src_root / name).read_text(encoding="utf-8")
            if "patient_files" in blob or "age_years" in blob:
                offenders.append(name)
        self.assertEqual(offenders, [])

    def test_research_md_caption_no_note(self):
        cap = research_md.caption_for("KRAS", 2)
        self.assertNotIn("patient", cap.lower())
        # ensure builder accepts only topic/records shape
        md = research_md.render_research_md("KRAS", [])
        self.assertNotIn("patient files", md.lower())


if __name__ == "__main__":
    unittest.main()
