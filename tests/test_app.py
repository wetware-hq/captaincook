"""Tests for /app rename parity, HTML redaction, fail-closed deploy."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src import app_deploy
from src import app_html
from src import board_md
from src import measure as measure_mod
from src import onboard as onboard_mod
from src.context_card import CONTEXT_CARD_KEY, attach_last_run, parse_load_text, store_card


class TestAppBoardRedactionParity(unittest.TestCase):
    def test_app_md_equals_board_md(self):
        user_data: dict = {}
        card = parse_load_text("find inhibitor for KRAS G12C")
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
        a = board_md.render_app_md(user_data)
        b = board_md.render_board_md(user_data)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("# Case conference packet"))
        self.assertIn("Patient biometrics: on file", a)
        self.assertNotIn("67", a)
        self.assertNotIn("72.5", a)

    def test_secret_measures_counts_only(self):
        user_data: dict = {}
        store_card(user_data, parse_load_text("KRAS G12C"))
        shell = user_data[CONTEXT_CARD_KEY]
        shell["measurements"] = [
            {
                "key": "hr",
                "value": 72,
                "unit": "bpm",
                "secret": False,
                "ts": "2026-09-20T01:00:00Z",
            },
            {
                "key": "weight_kg",
                "value": 81.2,
                "unit": "kg",
                "secret": True,
                "ts": "2026-09-20T01:00:00Z",
            },
        ]
        body = board_md.render_app_md(user_data)
        self.assertIn("hr:", body)
        self.assertIn("72", body)
        self.assertNotIn("81.2", body)
        self.assertIn("Secret measures on file: 1", body)


class TestAppHtmlOmitsSecrets(unittest.TestCase):
    def test_html_no_secrets_dual_audience(self):
        user_data: dict = {}
        store_card(user_data, parse_load_text("find inhibitor for KRAS G12C"))
        patient = onboard_mod.empty_patient()
        patient.update(
            {"age_years": 67, "sex": "M", "weight_kg": 91.7, "height_cm": 178.5}
        )
        onboard_mod.set_patient(user_data, patient)
        shell = user_data[CONTEXT_CARD_KEY]
        shell["measurements"] = [
            {
                "key": "hr",
                "value": 68,
                "unit": "bpm",
                "secret": False,
                "ts": "2026-09-20T02:00:00Z",
            },
            {
                "key": "hr",
                "value": 999,
                "unit": "bpm",
                "secret": True,
                "ts": "2026-09-20T03:00:00Z",
            },
        ]
        shell["patient_files"] = [
            {"id": "n1", "text": "SECRET_NOTE_BODY_XYZ", "created_at": "t"}
        ]
        html = app_html.render_app_html(user_data, user_id=1)
        self.assertIn('id="clinical"', html)
        self.assertIn('id="laboratory"', html)
        self.assertIn('id="measurements"', html)
        self.assertIn("Clinical", html)
        self.assertIn("Laboratory", html)
        # Visual lock
        self.assertIn("max-width: var(--max)", html)
        self.assertIn("42rem", html)
        self.assertIn("Source Serif", html)
        self.assertIn("Georgia", html)
        # Hierarchy: measurements section before clinical in source order
        self.assertLess(html.index('id="measurements"'), html.index('id="clinical"'))
        # No section intros
        self.assertNotIn("Peer-reviewed findings follow", html)
        self.assertNotIn("In-silico designs and preprint", html)
        # Secrets omitted
        leaked = app_html.html_contains_secrets(html, user_data)
        self.assertEqual(leaked, [])
        self.assertNotIn("67", html)
        self.assertNotIn("91.7", html)
        self.assertNotIn("178.5", html)
        self.assertNotIn("SECRET_NOTE_BODY_XYZ", html)
        self.assertNotIn("999", html)  # secret hr value
        self.assertIn("68", html)  # public hr in chart spec
        # Empty preprint → None yet
        self.assertIn("None yet.", html)

    def test_vega_only_chart_keys(self):
        user_data: dict = {}
        store_card(user_data, parse_load_text("case"))
        shell = user_data[CONTEXT_CARD_KEY]
        shell["measurements"] = [
            {
                "key": "bp_sys",
                "value": 120,
                "unit": "mmHg",
                "secret": False,
                "ts": "2026-09-20T02:00:00Z",
            },
            {
                "key": "spo2",
                "value": 98,
                "unit": "%",
                "secret": False,
                "ts": "2026-09-20T02:00:00Z",
            },
        ]
        series = app_html.chart_series(user_data)
        self.assertEqual(series["spo2"][0]["v"], 98.0)
        self.assertEqual(series["hr"], [])
        html = app_html.render_app_html(user_data)
        # bp not a chart key — no vega for bp_sys
        self.assertNotIn('"bp_sys"', html)
        self.assertIn("spo2", html)


class TestDeployFailClosed(unittest.TestCase):
    def test_not_configured(self):
        cfg = app_deploy.DeployConfig(
            provider="",
            token="",
            base_url="",
            put_url_template="",
            delete_url_template="",
            signing_secret="",
            account_id="",
            project="",
            ttl_days=7,
        )
        self.assertFalse(cfg.configured)
        res = app_deploy.deploy_live_html("<html></html>", cfg=cfg)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "not_configured")

    def test_ttl_clamp(self):
        self.assertEqual(app_deploy.clamp_ttl_days(100), 30)
        self.assertEqual(app_deploy.clamp_ttl_days(0), 1)
        self.assertEqual(app_deploy.clamp_ttl_days(7), 7)

    def test_url_has_no_secret_values(self):
        cfg = app_deploy.DeployConfig(
            provider="generic",
            token="tok",
            base_url="https://views.example.com",
            put_url_template="https://api.example.com/{slug}",
            delete_url_template="",
            signing_secret="sign",
            account_id="",
            project="",
            ttl_days=7,
        )
        exp = datetime.now(timezone.utc) + timedelta(days=7)
        url = app_deploy.public_url(cfg, "abc123", exp)
        self.assertIn("abc123.html", url)
        self.assertIn("exp=", url)
        self.assertIn("sig=", url)
        self.assertNotIn("weight", url)
        self.assertNotIn("patient", url)


class TestCmdAppAliases(unittest.IsolatedAsyncioTestCase):
    async def _run(self, cmd, user_data, args=None):
        update = MagicMock()
        update.effective_user = MagicMock(id=1)
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.reply_document = AsyncMock()
        context = MagicMock()
        context.user_data = user_data
        context.args = args or []
        context.application.bot_data = {
            "settings": MagicMock(telegram_allowed_user_id=None)
        }
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd(update, context)
        return update

    async def test_app_and_board_same_md(self):
        from src.bot import cmd_app, cmd_board
        from src import app_deploy as app_deploy_mod

        user_data: dict = {}
        card = parse_load_text("find inhibitor for KRAS G12C")
        card = attach_last_run(
            card, kind="binder_design", interpretation="ok", run_id="bind99"
        )
        store_card(user_data, card)

        # Force fail-closed deploy so this test stays env-independent
        fake_cfg = app_deploy_mod.DeployConfig(
            provider="",
            token="",
            base_url="",
            put_url_template="",
            delete_url_template="",
            signing_secret="",
            account_id="",
            project="",
            ttl_days=7,
        )
        with patch(
            "src.bot.app_deploy_mod.load_deploy_config_from_env",
            return_value=fake_cfg,
        ):
            u1 = await self._run(cmd_app, dict(user_data))
            u2 = await self._run(cmd_board, dict(user_data), args=["update"])

        u1.effective_message.reply_document.assert_awaited()
        u2.effective_message.reply_document.assert_awaited()
        b1 = u1.effective_message.reply_document.await_args.kwargs["document"]
        b2 = u2.effective_message.reply_document.await_args.kwargs["document"]
        b1.seek(0)
        b2.seek(0)
        self.assertEqual(b1.read(), b2.read())
        # Fail-closed link message present (no deploy creds)
        u1.effective_message.reply_text.assert_awaited()
        self.assertEqual(
            u1.effective_message.reply_text.await_args.args[0],
            board_md.MSG_LIVE_FAIL,
        )
        cap = u1.effective_message.reply_document.await_args.kwargs["caption"]
        self.assertEqual(cap, board_md.CAPTION_MD_ONLY)
        self.assertEqual(
            u1.effective_message.reply_document.await_args.kwargs["filename"],
            "case-conference-packet.md",
        )

    async def test_app_update_alias(self):
        from src.bot import cmd_app

        user_data: dict = {}
        store_card(user_data, parse_load_text("KRAS"))
        u = await self._run(cmd_app, user_data, args=["update"])
        u.effective_message.reply_document.assert_awaited()

    async def test_revoke_none(self):
        from src.bot import cmd_app

        user_data: dict = {}
        store_card(user_data, parse_load_text("KRAS"))
        u = await self._run(cmd_app, user_data, args=["revoke"])
        u.effective_message.reply_text.assert_awaited_once_with(board_md.MSG_REVOKE_NONE)

    async def test_refuse(self):
        from src.bot import cmd_app

        u = await self._run(cmd_app, {})
        u.effective_message.reply_text.assert_awaited_once_with(board_md.MSG_REFUSE_APP)
        u.effective_message.reply_document.assert_not_called()




class TestMolstarStructures(unittest.TestCase):
    def test_collect_structure_assets_max_two(self):
        user_data: dict = {}
        card = parse_load_text("KRAS G12C fold")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = []
            for i in range(4):
                p = root / f"model{i}.cif"
                p.write_text("data_test\n_entry.id test\n", encoding="utf-8")
                files.append({"kind": "cif", "path": str(p), "name": p.name})
            # missing path should be skipped
            files.append({"kind": "cif", "path": str(root / "gone.cif"), "name": "gone.cif"})
            files.append({"kind": "fasta", "path": str(root / "x.fasta"), "name": "x.fasta"})
            card = attach_last_run(
                card, kind="fold", interpretation="ok", run_id="r1", files=files
            )
            store_card(user_data, card)
            assets = app_html.collect_structure_assets(user_data)
            self.assertEqual(len(assets), 2)
            self.assertTrue(all(a["format"] == "mmcif" for a in assets))
            self.assertTrue(all(a["path"].is_file() for a in assets))
            self.assertEqual(assets[0]["label"], "model0.cif")

    def test_render_includes_molstar_when_viewers(self):
        user_data: dict = {}
        store_card(user_data, parse_load_text("find inhibitor for KRAS G12C"))
        patient = onboard_mod.empty_patient()
        patient.update(
            {"age_years": 67, "sex": "F", "weight_kg": 72.5, "height_cm": 165.0}
        )
        onboard_mod.set_patient(user_data, patient)
        viewers = [
            {
                "id": "mol-viewer-0",
                "label": "boltz.cif",
                "url": "https://pub.example/r2/abc-mol0.cif",
                "format": "mmcif",
            }
        ]
        html = app_html.render_app_html(user_data, user_id=1, mol_viewers=viewers)
        self.assertIn("cdn.jsdelivr.net/npm/molstar@4.18.0/build/viewer/molstar.js", html)
        self.assertIn("molstar.css", html)
        self.assertIn('id="mol-viewer-0"', html)
        self.assertIn('class="mol-viewer"', html)
        self.assertIn('id="structures"', html)
        self.assertIn('href="#structures"', html)
        self.assertIn("loadStructureFromUrl", html)
        self.assertIn("https://pub.example/r2/abc-mol0.cif", html)
        self.assertNotIn("/workspace/", html)
        self.assertNotIn("patient-store/", html)
        leaked = app_html.html_contains_secrets(html, user_data)
        self.assertEqual(leaked, [])
        self.assertNotIn("67", html)
        self.assertNotIn("72.5", html)


    def test_collect_ligand_assets_from_design_csv(self):
        user_data: dict = {}
        card = parse_load_text("find inhibitor for KRAS G12C")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / "candidates.csv"
            csv_path.write_text(
                "id,smiles,binding_confidence,optimization_score,structure_confidence,"
                "adme_solubility,adme_lipophilicity,adme_permeability\n"
                "a,CCO,0.5,0.1,,,,\n"
                "b,CCN,0.9,0.2,,,,\n"
                "c,CCC,0.7,0.15,,,,\n"
                "d,CCCC,0.8,0.05,,,,\n",
                encoding="utf-8",
            )
            files = [{"kind": "design_csv", "path": str(csv_path), "name": "candidates.csv"}]
            card = attach_last_run(
                card, kind="small_molecule_design", interpretation="ok", run_id="d1", files=files
            )
            store_card(user_data, card)
            ligs = app_html.collect_ligand_assets(user_data)
            self.assertEqual(len(ligs), 3)
            self.assertEqual(ligs[0]["smiles"], "CCN")  # highest binding_confidence
            self.assertEqual(ligs[0]["format"], "smi")

    def test_render_includes_both_molstar_and_3dmol(self):
        user_data: dict = {}
        store_card(user_data, parse_load_text("KRAS G12C"))
        patient = onboard_mod.empty_patient()
        patient.update({"age_years": 67, "weight_kg": 72.5, "height_cm": 165.0})
        onboard_mod.set_patient(user_data, patient)
        html = app_html.render_app_html(
            user_data,
            user_id=1,
            mol_viewers=[
                {
                    "id": "mol-viewer-0",
                    "label": "boltz.cif",
                    "url": "https://pub.example/a.cif",
                    "format": "mmcif",
                }
            ],
            chem_viewers=[
                {
                    "id": "chem-viewer-0",
                    "label": "lig-1",
                    "format": "smi",
                    "data": "CCO",
                    "is_url": False,
                }
            ],
        )
        self.assertIn("molstar@4.18.0", html)
        self.assertIn("3dmol@2.4.2", html)
        self.assertIn("Biological (mmCIF)", html)
        self.assertIn("Chemical (ligands)", html)
        self.assertIn("CCO", html)
        self.assertIn("$3Dmol", html)
        self.assertNotIn("/workspace/", html)
        self.assertEqual(app_html.html_contains_secrets(html, user_data), [])
        self.assertNotIn("67", html)

    def test_sdf_preferred_over_smiles(self):
        user_data: dict = {}
        card = parse_load_text("design ligand")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sdf = root / "lig.sdf"
            sdf.write_text("lig\n  Mrv\n\n  0  0\nM  END\n$$$$\n", encoding="utf-8")
            csv_path = root / "candidates.csv"
            csv_path.write_text(
                "id,smiles,binding_confidence,optimization_score,structure_confidence,"
                "adme_solubility,adme_lipophilicity,adme_permeability\n"
                "a,CCO,0.9,0.1,,,,\n",
                encoding="utf-8",
            )
            files = [
                {"kind": "sdf", "path": str(sdf), "name": "lig.sdf"},
                {"kind": "design_csv", "path": str(csv_path), "name": "candidates.csv"},
            ]
            card = attach_last_run(
                card, kind="small_molecule_design", interpretation="ok", run_id="d2", files=files
            )
            store_card(user_data, card)
            ligs = app_html.collect_ligand_assets(user_data)
            self.assertEqual(len(ligs), 1)
            self.assertEqual(ligs[0]["format"], "sdf")
            self.assertNotIn("smiles", ligs[0])


    def test_render_omits_mol_without_viewers(self):
        html = app_html.render_app_html({})
        self.assertNotIn("molstar@", html)
        self.assertNotIn("3dmol@", html)
        self.assertNotIn("mol-viewer", html)
        self.assertNotIn("chem-viewer", html)
        self.assertNotIn('id="structures"', html)


class TestHelpAppPrimary(unittest.TestCase):
    def test_help(self):
        from src.bot import HELP_TEXT

        self.assertIn("/app —", HELP_TEXT)
        self.assertIn("/app update", HELP_TEXT)
        self.assertIn("/app revoke", HELP_TEXT)
        self.assertIn("Alias of /app", HELP_TEXT)
        self.assertIn("/board — Alias of /app", HELP_TEXT)
        low = HELP_TEXT.lower()
        self.assertNotIn("oncology-only", low)
        self.assertNotIn("dashboard", low)


if __name__ == "__main__":
    unittest.main()
