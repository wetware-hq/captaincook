"""Unit tests for /measure paste observations (FEATURE-measure + TEMPLATE-measure)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import board_md
from src import measure as measure_mod
from src import store
from src.card_cache import fingerprint
from src.context_card import (
    ContextCard,
    format_card,
    load_card,
    parse_load_text,
    store_card,
)
from src import history as history_mod
from src import sorter as sorter_mod


class TestTemplateVerbatim(unittest.TestCase):
    def test_locked_strings(self):
        self.assertIn("Send your measurements in the next message.", measure_mod.MSG_ARMED)
        self.assertIn("HR 72 bpm", measure_mod.MSG_ARMED)
        self.assertEqual(
            measure_mod.MSG_SAVED,
            "Saved {n} measurement(s) on this card ({n_secret} secret). "
            "Secret values are not shown.",
        )
        self.assertEqual(measure_mod.MSG_LIST_EMPTY, "No measurements on this card.")
        self.assertEqual(
            measure_mod.MSG_CLEAR_ALL,
            "Cleared all measurements on this card.",
        )
        self.assertIn("no context card", measure_mod.MSG_NO_CARD.lower())
        self.assertEqual(
            measure_mod.BOARD_NONE,
            "None yet. Paste observations with /measure.",
        )
        self.assertEqual(
            measure_mod.HELP_ONE_LINER,
            "/measure — Paste patient observations onto the current card "
            "(HR, BP, weight_kg=…, optional secret). /measure list shows keys; "
            "secret values are never shown. Research use only; not a diagnosis.",
        )


class TestRefuseNoCard(unittest.TestCase):
    def test_arm_without_card(self):
        user_data: dict = {}
        reply = measure_mod.start_measure(user_data)
        self.assertEqual(reply, measure_mod.MSG_NO_CARD)
        self.assertFalse(measure_mod.is_armed(user_data))


class TestPasteHrBpSecret(unittest.TestCase):
    def _card(self) -> dict:
        user_data: dict = {}
        store_card(user_data, parse_load_text("find inhibitor for KRAS G12C GDP covalent"))
        return user_data

    def test_paste_hr_bp_secret_list_redacts(self):
        user_data = self._card()
        paste = (
            "HR 72 bpm\n"
            "BP 120/80 mmHg\n"
            "weight_kg=81.2 secret\n"
            "device: ward_monitor_3\n"
        )
        reply = measure_mod.append_measurements(user_data, paste)
        self.assertTrue(reply.startswith("Saved "))
        self.assertIn("secret", reply.lower())
        self.assertNotIn("81.2", reply)

        items = measure_mod.get_measurements(user_data)
        keys = {m["key"] for m in items}
        self.assertIn("hr", keys)
        self.assertIn("bp_sys", keys)
        self.assertIn("bp_dia", keys)
        self.assertIn("weight_kg", keys)
        weight = next(m for m in items if m["key"] == "weight_kg")
        self.assertTrue(weight["secret"])
        self.assertEqual(weight["value"], 81.2)
        # device sticky applied to subsequent? device line before readings would stick;
        # here device is last — prior readings may have None; that's OK.
        hr = next(m for m in items if m["key"] == "hr")
        self.assertEqual(hr["value"], 72)
        self.assertEqual(hr["unit"], "bpm")
        self.assertFalse(hr["secret"])

        listed = measure_mod.list_text(user_data)
        self.assertIn("hr:", listed)
        self.assertIn("72", listed)
        self.assertIn("Secret measures on file: 1", listed)
        self.assertNotIn("81.2", listed)

    def test_device_sticky_before_readings(self):
        user_data = self._card()
        paste = "device: ward_monitor_3\nHR 72 bpm\n"
        measure_mod.append_measurements(user_data, paste)
        hr = measure_mod.get_measurements(user_data)[0]
        self.assertEqual(hr["device"], "ward_monitor_3")


class TestBoardNonSecretAndCount(unittest.TestCase):
    def test_board_shows_hr_secret_count_only(self):
        user_data: dict = {}
        store_card(user_data, parse_load_text("find inhibitor for KRAS G12C GDP covalent"))
        measure_mod.append_measurements(
            user_data,
            "HR 72 bpm\nweight_kg=81.2 secret\n",
        )
        body = board_md.render_board_md(user_data)
        self.assertIn("## Measurements", body)
        self.assertIn("- hr: 72 bpm", body)
        self.assertIn("Secret measures on file: 1 (values not shown).", body)
        self.assertNotIn("81.2", body)
        # load dump count-only
        dump = format_card(
            load_card(user_data),
            measurements_line=measure_mod.load_dump_line(user_data),
        )
        self.assertIn("Measurements: 2 on file (1 secret).", dump)
        self.assertNotIn("81.2", dump)
        self.assertNotIn("72 bpm", dump)


class TestClearKey(unittest.TestCase):
    def test_clear_key_keeps_others(self):
        user_data: dict = {}
        store_card(user_data, ContextCard(raw_text="case", intent="fold"))
        measure_mod.append_measurements(user_data, "HR 72 bpm\ntemp_c=36.8\n")
        self.assertEqual(len(measure_mod.get_measurements(user_data)), 2)
        msg = measure_mod.clear_measurements(user_data, "hr")
        self.assertEqual(msg, measure_mod.MSG_CLEAR_KEY.format(key="hr"))
        left = measure_mod.get_measurements(user_data)
        self.assertEqual(len(left), 1)
        self.assertEqual(left[0]["key"], "temp_c")
        msg_all = measure_mod.clear_measurements(user_data, "all")
        self.assertEqual(msg_all, measure_mod.MSG_CLEAR_ALL)
        self.assertEqual(measure_mod.get_measurements(user_data), [])


class TestCoerceOther(unittest.TestCase):
    def test_unknown_free_key_without_secret_coerced(self):
        user_data: dict = {}
        store_card(user_data, ContextCard(raw_text="case", intent="fold"))
        measure_mod.append_measurements(user_data, "lactate 2.1 mmol\n")
        items = measure_mod.get_measurements(user_data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["key"], "other:lactate")
        self.assertFalse(items[0]["secret"])

    def test_free_key_with_secret_kept(self):
        user_data: dict = {}
        store_card(user_data, ContextCard(raw_text="case", intent="fold"))
        measure_mod.append_measurements(user_data, "lactate=2.1 secret\n")
        items = measure_mod.get_measurements(user_data)
        self.assertEqual(items[0]["key"], "lactate")
        self.assertTrue(items[0]["secret"])

    def test_explicit_other_slug(self):
        self.assertEqual(
            measure_mod.coerce_key("other:Foo-Bar", secret=False),
            "other:foo_bar",
        )


class TestFingerprintExcludesMeasures(unittest.TestCase):
    def test_measures_do_not_change_fingerprint(self):
        user_data: dict = {}
        card = parse_load_text("find inhibitor for KRAS G12C GDP covalent")
        store_card(user_data, card)
        fp_before = fingerprint(load_card(user_data))
        measure_mod.append_measurements(user_data, "HR 72 bpm\nweight_kg=80 secret\n")
        self.assertEqual(fp_before, fingerprint(load_card(user_data)))
        self.assertFalse(hasattr(load_card(user_data), "measurements"))


class TestStorePreserves(unittest.TestCase):
    def test_store_preserves_measurements(self):
        user_data: dict = {}
        store_card(user_data, parse_load_text("find inhibitor for KRAS G12C GDP covalent"))
        measure_mod.append_measurements(user_data, "HR 72 bpm\n")
        store_card(user_data, parse_load_text("find inhibitor for KRAS G12C GDP covalent"))
        self.assertEqual(len(measure_mod.get_measurements(user_data)), 1)


class TestSearchIndexNonSecret(unittest.TestCase):
    def test_measure_keys_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(store, "STORE_ROOT", root):
                uid = 99
                pid = "patient-measure-1"
                store.ensure_patient_files(uid, pid)
                eid = history_mod.emit(
                    uid,
                    history_mod.KIND_MEASURE,
                    {
                        "measure_keys": ["hr", "bp_sys"],
                        "n": 3,
                        "n_secret": 1,
                        "patient_id": pid,
                    },
                )
                self.assertTrue(eid)
                sorter_mod.process_user(uid)
                search = json.loads(store.search_path(uid, pid).read_text(encoding="utf-8"))
                titles = {e.get("title") for e in search.get("entries") or []}
                self.assertIn("measure:hr", titles)
                self.assertIn("measure:bp_sys", titles)
                # No values in search entries
                blob = json.dumps(search)
                self.assertNotIn("81.2", blob)


class TestBoardNone(unittest.TestCase):
    def test_empty_measurements_block(self):
        self.assertEqual(
            measure_mod.board_measurements_block({}),
            measure_mod.BOARD_NONE,
        )


if __name__ == "__main__":
    unittest.main()
