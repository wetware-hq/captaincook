"""Tests for Modal BindCraft client — tokens ready, fail-closed, no PHI."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from src import bindcraft as bindcraft_mod
from src import modal_bindcraft as modal_bc


class TestModalBindCraft(unittest.TestCase):
    def test_tokens_present_binder_compute_ready(self):
        self.assertTrue(
            bindcraft_mod.binder_compute_ready(
                "",
                modal_token_id="ak-test",
                modal_token_secret="as-test-secret",
            )
        )
        self.assertTrue(modal_bc.modal_tokens_present("ak-test", "as-test-secret"))
        self.assertFalse(modal_bc.modal_tokens_present("", "as-test-secret"))
        self.assertFalse(modal_bc.modal_tokens_present("ak-test", ""))

    def test_missing_app_fail_closed_on_run(self):
        with self.assertRaises(modal_bc.ModalBindCraftError) as ctx:
            modal_bc.run_bindcraft_modal(
                target_sequence="ACDE",
                n_designs=5,
                token_id="ak-test",
                token_secret="as-test-secret",
                app_name="",  # missing MODAL_BINDCRAFT_APP
            )
        self.assertEqual(ctx.exception.kind, "not_deployed")
        self.assertIn("not deployed", str(ctx.exception).lower())

        # Via bindcraft router — same fail-closed, no invented designs
        with self.assertRaises(modal_bc.ModalBindCraftError) as ctx2:
            bindcraft_mod.run_binder_design(
                structure_path=None,
                n_designs=5,
                target_sequence="ACDE",
                modal_token_id="ak-test",
                modal_token_secret="as-test-secret",
                modal_bindcraft_app="",
            )
        self.assertEqual(ctx2.exception.kind, "not_deployed")

    def test_no_phi_in_modal_payload_builder(self):
        payload = modal_bc.build_modal_payload(
            target_sequence="ACDEFGHIK",
            hotspot=["A123", "B45"],
            n_designs=5,
        )
        self.assertEqual(payload["target_sequence"], "ACDEFGHIK")
        self.assertEqual(payload["n_designs"], 5)
        self.assertEqual(payload["hotspot"], ["A123", "B45"])
        forbidden = {
            "clinic",
            "clinic_md",
            "biometrics",
            "patient_files",
            "patient_id",
            "telegram_bot_token",
            "note_body",
            "age_years",
            "secrets",
        }
        self.assertTrue(forbidden.isdisjoint(payload.keys()))

        with self.assertRaises(ValueError):
            modal_bc.build_modal_payload(
                target_sequence="ACDE",
                n_designs=1,
                extra={"patient_files": "/tmp/x"},
            )
        with self.assertRaises(ValueError):
            modal_bc.build_modal_payload(
                target_sequence="ACDE",
                n_designs=1,
                extra={"biometrics": {"age_years": 40}},
            )

        with TemporaryDirectory() as td:
            cif = Path(td) / "target.cif"
            cif.write_text("data_test\n")
            p2 = modal_bc.build_modal_payload(
                cif_path=cif,
                n_designs=3,
            )
            self.assertIn("cif_bytes", p2)
            self.assertEqual(p2["cif_name"], "target.cif")
            self.assertNotIn("patient_id", p2)

    def test_app_not_found_maps_to_not_deployed(self):
        fake_modal = MagicMock()
        fake_modal.Function.from_name.side_effect = Exception("Lookup failed: app not found")

        with patch.dict("sys.modules", {"modal": fake_modal}):
            with self.assertRaises(modal_bc.ModalBindCraftError) as ctx:
                modal_bc.run_bindcraft_modal(
                    target_sequence="ACDE",
                    n_designs=2,
                    token_id="ak-test",
                    token_secret="as-test-secret",
                    app_name="bindcraft-gpu",
                )
            self.assertEqual(ctx.exception.kind, "not_deployed")


if __name__ == "__main__":
    unittest.main()
