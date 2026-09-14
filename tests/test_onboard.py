"""Unit tests for /onboard clinical biometrics (secrets)."""

from __future__ import annotations

import unittest

from src.card_cache import fingerprint
from src.context_card import ContextCard, clear_card, format_card, load_card, store_card
from src import onboard as onboard_mod


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


class TestValidateRanges(unittest.TestCase):
    def test_age_ok(self):
        v, err = onboard_mod.validate_field("age_years", "75")
        self.assertEqual(v, 75)
        self.assertIsNone(err)

    def test_age_999_rejected(self):
        v, err = onboard_mod.validate_field("age_years", "999")
        self.assertIsNone(v)
        self.assertIsNotNone(err)

    def test_age_float_rejected(self):
        v, err = onboard_mod.validate_field("age_years", "40.5")
        self.assertIsNone(v)

    def test_sex(self):
        for letter in ("F", "M", "X", "f", "m", "x"):
            v, err = onboard_mod.validate_field("sex", letter)
            self.assertEqual(v, letter.upper())
            self.assertIsNone(err)
        v, err = onboard_mod.validate_field("sex", "female")
        self.assertIsNone(v)

    def test_weight_height(self):
        v, err = onboard_mod.validate_field("weight_kg", "70.5")
        self.assertEqual(v, 70.5)
        self.assertIsNone(err)
        v, err = onboard_mod.validate_field("weight_kg", "0.5")
        self.assertIsNone(v)
        v, err = onboard_mod.validate_field("height_cm", "175")
        self.assertEqual(v, 175.0)
        v, err = onboard_mod.validate_field("height_cm", "10")
        self.assertIsNone(v)


class TestQuestionOrder(unittest.TestCase):
    def test_order(self):
        user_data: dict = {}
        reply, field = onboard_mod.start_or_resume(user_data)
        self.assertEqual(field, "age_years")
        self.assertIn("age", reply.lower())
        self.assertTrue(onboard_mod.is_active(user_data))

        r = onboard_mod.apply_answer(user_data, "75")
        self.assertEqual(onboard_mod.current_field(user_data), "sex")
        self.assertIn("sex", r.lower())

        r = onboard_mod.apply_answer(user_data, "F")
        self.assertEqual(onboard_mod.current_field(user_data), "weight_kg")

        r = onboard_mod.apply_answer(user_data, "70")
        self.assertEqual(onboard_mod.current_field(user_data), "height_cm")

        r = onboard_mod.apply_answer(user_data, "175")
        self.assertFalse(onboard_mod.is_active(user_data))
        self.assertIn("complete", r.lower())
        patient = onboard_mod.get_patient(user_data)
        assert patient is not None
        self.assertTrue(patient["complete"])
        self.assertEqual(patient["age_years"], 75)
        self.assertEqual(patient["sex"], "F")
        self.assertEqual(patient["weight_kg"], 70.0)
        self.assertEqual(patient["height_cm"], 175.0)
        self.assertIsNotNone(patient["bmi"])
        self.assertTrue(patient["secret"])

    def test_invalid_age_not_stored(self):
        user_data: dict = {}
        onboard_mod.start_or_resume(user_data)
        r = onboard_mod.apply_answer(user_data, "999")
        self.assertIn("0 to 120", r)
        patient = onboard_mod.get_patient(user_data)
        assert patient is not None
        self.assertIsNone(patient["age_years"])
        self.assertEqual(onboard_mod.current_field(user_data), "age_years")


class TestStatusNoRawValues(unittest.TestCase):
    def test_complete_status_hides_values(self):
        user_data: dict = {}
        onboard_mod.start_or_resume(user_data)
        for ans in ("75", "M", "82.3", "168.5"):
            onboard_mod.apply_answer(user_data, ans)
        status = onboard_mod.status_text(onboard_mod.get_patient(user_data))
        self.assertEqual(status, "Patient biometrics are complete.")
        self.assertNotIn("75", status)
        self.assertNotIn("82", status)
        self.assertNotIn("168", status)
        self.assertNotIn("M", status)
        # status string itself must not contain the sex letter as a token
        self.assertNotRegex(status, r"\bM\b")

    def test_incomplete_status(self):
        user_data: dict = {}
        onboard_mod.start_or_resume(user_data)
        onboard_mod.apply_answer(user_data, "40")
        status = onboard_mod.status_text(onboard_mod.get_patient(user_data))
        self.assertIn("incomplete", status.lower())
        self.assertIn("sex", status)
        self.assertNotIn("40", status)


class TestFingerprintExclude(unittest.TestCase):
    def test_patient_change_does_not_change_fingerprint(self):
        card = _g12c_card()
        user_data: dict = {}
        store_card(user_data, card)
        fp_before = fingerprint(load_card(user_data))

        onboard_mod.start_or_resume(user_data)
        for ans in ("75", "F", "70", "175"):
            onboard_mod.apply_answer(user_data, ans)

        loaded = load_card(user_data)
        assert loaded is not None
        fp_after = fingerprint(loaded)
        self.assertEqual(fp_before, fp_after)
        # patient lives on the dict, not the dataclass
        patient = onboard_mod.get_patient(user_data)
        self.assertTrue(patient and patient["complete"])
        self.assertFalse(hasattr(loaded, "patient") and getattr(loaded, "patient", None))


class TestClearBehavior(unittest.TestCase):
    def test_onboard_clear_patient_only(self):
        user_data: dict = {}
        store_card(user_data, _g12c_card())
        onboard_mod.start_or_resume(user_data)
        onboard_mod.apply_answer(user_data, "50")
        self.assertTrue(onboard_mod.clear_patient(user_data))
        self.assertIsNone(onboard_mod.get_patient(user_data))
        card = load_card(user_data)
        self.assertIsNotNone(card)
        self.assertEqual(card.gene, "KRAS")

    def test_load_clear_drops_card_and_patient(self):
        user_data: dict = {}
        store_card(user_data, _g12c_card())
        onboard_mod.ensure_patient(user_data)
        onboard_mod.apply_answer  # noqa: B018 — ensure module loaded
        p = onboard_mod.empty_patient()
        p["age_years"] = 30
        onboard_mod.set_patient(user_data, p)
        onboard_mod.end_onboard(user_data)
        self.assertTrue(clear_card(user_data))
        self.assertIsNone(load_card(user_data))
        self.assertIsNone(onboard_mod.get_patient(user_data))

    def test_cancel_ends_active_keeps_secrets(self):
        user_data: dict = {}
        onboard_mod.start_or_resume(user_data)
        onboard_mod.apply_answer(user_data, "33")
        self.assertTrue(onboard_mod.end_onboard(user_data))
        self.assertFalse(onboard_mod.is_active(user_data))
        patient = onboard_mod.get_patient(user_data)
        assert patient is not None
        self.assertEqual(patient["age_years"], 33)

    def test_resume_after_partial(self):
        user_data: dict = {}
        onboard_mod.start_or_resume(user_data)
        onboard_mod.apply_answer(user_data, "33")
        onboard_mod.end_onboard(user_data)
        reply, field = onboard_mod.start_or_resume(user_data)
        self.assertEqual(field, "sex")
        self.assertIn("sex", reply.lower())


class TestFormatCardPatientLine(unittest.TestCase):
    def test_patient_line_no_values(self):
        card = _g12c_card()
        user_data: dict = {}
        store_card(user_data, card)
        onboard_mod.start_or_resume(user_data)
        for ans in ("75", "F", "70", "175"):
            onboard_mod.apply_answer(user_data, ans)
        body = format_card(card, patient=onboard_mod.get_patient(user_data))
        self.assertIn("Patient: on file.", body)
        self.assertNotIn("75", body)
        self.assertNotIn("70", body)


class TestRefuseDiagnose(unittest.TestCase):
    def test_refuse(self):
        self.assertTrue(
            onboard_mod.looks_like_diagnose_from_biometrics(
                "diagnose me from my BMI and weight"
            )
        )
        self.assertIn("research", onboard_mod.REFUSE_DIAGNOSE_BIOMETRICS.lower())


class TestStorePreservesPatient(unittest.TestCase):
    def test_store_preserves(self):
        user_data: dict = {}
        store_card(user_data, _g12c_card())
        onboard_mod.start_or_resume(user_data)
        onboard_mod.apply_answer(user_data, "60")
        # overwrite card formal fields
        store_card(user_data, _g12c_card())
        patient = onboard_mod.get_patient(user_data)
        assert patient is not None
        self.assertEqual(patient["age_years"], 60)


if __name__ == "__main__":
    unittest.main()
