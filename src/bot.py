"""Telegram bot entrypoint — long-polling handlers for Biohub ESMFold2 and Boltz.

Research-use only. No pathogen design, reverse-genetics, synthesis, or wet-lab features.
"""

from __future__ import annotations

import asyncio
import uuid
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .biohub_client import BiohubClient
from .boltz_client import BoltzClient
from .bioscreen import Decision, gate, refuse_message
from .config import (
    load_settings,
    validate_protein_sequence,
    validate_smiles,
)
from .context_card import (
    attach_last_run,
    clear_card,
    format_card,
    load_card,
    parse_load_text,
    store_card,
)
from . import onboard as onboard_mod
from . import patient_files as patient_files_mod
from .card_cache import (
    clear_cache,
    file_of_kind,
    lookup_result,
    remember_result,
    result_png_path,
)
from .downloads import (
    drop_files,
    drop_session,
    file_record,
    read_candidates_csv,
    stash_run_files,
)
from .interpret import interpret_binding, interpret_design, interpret_fold, target_label
from .result_photo import rank_candidates
from .intent import (
    DEFAULT_N_DESIGNS,
    MAX_N_DESIGNS,
    MIN_N_DESIGNS,
    looks_like_aa_sequence,
)
from . import bindcraft as bindcraft_mod
from . import modal_bindcraft as modal_bindcraft_mod
from .targets import (
    HOTSPOT_SOURCE_KRAS_SWITCH_II,
    pocket_residues_to_hotspot_list,
)
from .photo import (
    IMAGE_RENDER_FAILED,
    list_binder_cifs,
    send_binder_photo,
    send_design_photo,
    send_structure_photo,
)
from .research_client import ResearchServiceError, search_preprints
from .research_md import (
    MSG_FAIL_CLOSED,
    caption_for,
    render_research_md,
    topic_error,
)
from .evidence_client import EvidenceServiceError, search_peer_reviewed
from .evidence_md import (
    MSG_FAIL_CLOSED as EVIDENCE_MSG_FAIL_CLOSED,
    caption_for as evidence_caption_for,
    question_error,
    render_evidence_md,
)
from .scribe_client import (
    ScribeNotConfiguredError,
    ScribeServiceError,
    organise_minutes,
)
from . import scribe_md as scribe_md_mod
from . import history as history_mod
from . import sorter as sorter_mod
from . import store as store_mod

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = """\
*Research use only.* This bot predicts protein structure and binding via Biohub and Boltz, proposes in-silico small-molecule ligands via Boltz, and designs in-silico protein binders via BindCraft (optional Modal compute).

Commands:
/start — A brief introduction.
/help — This message.
/esm `<amino-acid-sequence>` — Biohub ESMFold2 structure prediction. A photograph is attached when rendering succeeds.
/boltz `<protein-sequence>` — Boltz-2.1 structure prediction.
/boltz `<protein-sequence> <ligand-smiles>` — Structure prediction together with ligand binding.
/design ligand [n] — Queue Boltz small-molecule design (confirm required).
/design binder [n] — Queue BindCraft protein-binder design (confirm required).
/design — Ask which mode: ligand or binder.
/load `<nl>` — Parse a request into a context card. No computation is started.
/load — Show the current card.
/load clear — Discard the card, patient biometrics, and patient files.
/download — Send the structure file, and the design table if present, from the last run on the current card.
/view — Show the stored photograph and description for this card, if a matching completed run exists. No new computation is started.
/confirm — Begin a pending ligand or binder design job. The reply is one photograph with a short clinical caption when rendering succeeds. Files follow via /download.
/cancel — Discard a pending design job, end an active /onboard question, or disarm a pending /note or /scribe, without clearing saved biometrics or patient files.
/onboard — Collect patient biometrics (age, sex, weight, height) one question at a time. Values are secrets and are never shown in card dumps.
/onboard status — Report whether biometrics are complete, without printing values.
/onboard clear — Delete patient biometric secrets and patient files on this card.
/note — After /onboard, arm the next message as a patient file on this card. Notes are separate from biometric secrets.
/note list — Report how many patient files are on this card (count only; contents are not shown).
/note clear — Clear patient files only. Biometric secrets are unchanged.
/research `<topic>` — Retrieve a Markdown brief of recent bioRxiv or medRxiv preprints for the topic. The reply is one document. This is for research use only and is not clinical advice.
/evidence `<question>` — Retrieve a Markdown evidence brief from peer-reviewed Europe PMC / MEDLINE articles for the question. Preprints are excluded. The reply is one document. This is for research use only and is not clinical advice.
/scribe — Arm the next message as meeting notes, or /scribe `<text>` for short text. Returns one organised Markdown minutes document. Unlinked from the context card and patient stores. Research use only; not a clinical or legal record.

Patient biometrics are for research context only. The user is responsible for lawful handling of personal data. This bot does not diagnose or give clinical advice from biometrics.

A bare /esm or /boltz uses the sequence on the loaded card when one is present. Bare /design asks which mode to use. /design ligand uses the card sequence when one is present.

On KRAS, naming Switch-II (or Switch 2 / SII) fills hotspot residues from the curated fixture map (residues 60–76). Other pocket names do not set a hotspot by themselves; supply residue numbers on the card if you want a hotspot, otherwise the run is target-wide.

Ligand design (/design ligand) requires at least ten molecules (about US$0.25) and at most one hundred. Binder design (/design binder) defaults to five designs and caps at twenty; jobs can take tens of minutes to a few hours. The confirm card states mode, count, and any cost estimate before work begins. Candidates are computer suggestions only. They are not validated inhibitors or therapeutics, and this bot does not advise synthesis or laboratory work.

A successful result is one photograph with a short clinical caption. Use /download to retrieve the structure file or the design table.

Sequences must use the standard amino-acid alphabet. Length is capped (default 800 residues).

Every sequence-bearing job is checked by a pre-compute biosecurity screen before any structure or design work begins.

This request class cannot be fulfilled: pathogen design, reverse-genetics, synthesis planning, laboratory protocols, or any attempt to engineer harmful biological agents.
"""

REFUSAL_KEYWORDS = (
    "pathogen",
    "reverse genetic",
    "reverse-genetic",
    "synthesize virus",
    "synthesis protocol",
    "wet-lab",
    "wet lab",
    "gain of function",
    "gain-of-function",
    "bioweapon",
    "weaponize",
)

PENDING_DESIGN_KEY = "pending_design"
DEFAULT_MAX_USD = 0.50
DESIGN_DISCLAIMER = (
    "These candidates are for research use only. They are computer suggestions, "
    "not validated inhibitors. This bot does not provide synthesis or laboratory guidance."
)

# Locked COPY-design.md strings (biolang). Do not paraphrase.
COPY_DESIGN_MODE_PROMPT = (
    "Please choose a design mode: /design ligand or /design binder. "
    "Ligand uses Boltz for small molecules. Binder uses BindCraft for protein binders."
)
COPY_BINDCRAFT_NOT_CONFIGURED = (
    "This request cannot proceed. BindCraft is not configured on this host "
    "(BINDCRAFT_HOME), so no binder design was started. Ligand design via "
    "/design ligand remains available if Boltz is configured."
)
COPY_MODAL_BINDCRAFT_NOT_DEPLOYED = (
    "This request cannot proceed. Modal credentials are present, but the "
    "BindCraft Modal app is not deployed yet (set MODAL_BINDCRAFT_APP and "
    "deploy modal_app/bindcraft_app.py with GPU image + weights volume). "
    "No binder design was started. Ligand design via /design ligand remains "
    "available if Boltz is configured."
)
COPY_MODAL_BINDCRAFT_FAILED = (
    "This request cannot proceed. The Modal BindCraft job failed or timed out "
    "(weights/runner error, no filter-passing designs, or GPU timeout). "
    "No binder design was started. Ligand design via /design ligand remains "
    "available if Boltz is configured."
)
COPY_BINDER_NO_STRUCTURE = (
    "This request cannot proceed. Binder design needs a context card with a "
    "target structure. Please /load a target and obtain a structure "
    "(for example /esm or /boltz), then use /design binder."
)
COPY_BIND_STUB = "`/bind` has been withdrawn. Please use /design binder."
COPY_LIGAND_CONFIRM = (
    "Pending ligand design (Boltz). Molecules: {n}. Estimated cost: about US${cost}. "
    "Research use only — in-silico candidates, not validated inhibitors. "
    "Reply /confirm to spend or /cancel to stop."
)
COPY_BINDER_CONFIRM_HOTSPOT = (
    "Pending binder design (BindCraft). Designs: {n}. Hotspot residues will be "
    "used as supplied on the card. This job can take tens of minutes to a few hours. "
    "Research use only — in-silico protein binders, not validated therapeutics. "
    "Reply /confirm to spend or /cancel to stop."
)
COPY_BINDER_CONFIRM_SWITCH2_FIXTURE = (
    "Pending binder design (BindCraft). Designs: {n}. Hotspot residues 60–76 come from "
    "the curated KRAS Switch-II fixture map (not free-text invention). This job can take "
    "tens of minutes to a few hours. Research use only — in-silico protein binders, not "
    "validated therapeutics. Reply /confirm to spend or /cancel to stop."
)
COPY_BINDER_CONFIRM_TARGET_WIDE = (
    "Pending binder design (BindCraft). Designs: {n}. No hotspot was supplied; "
    "the run is target-wide. Hotspots are not invented. This job can take tens of "
    "minutes to a few hours. Research use only — in-silico protein binders, not "
    "validated therapeutics. Reply /confirm to spend or /cancel to stop."
)
COPY_BINDER_RESULT_PHOTO_N1 = (
    "This image shows the loaded target with one ranked in-silico protein binder "
    "from BindCraft. Scores and poses are computational estimates only. "
    "Research use only; not a validated binder or therapeutic."
)
COPY_BINDER_RESULT_PHOTO_GRID = (
    "This image is a grid of ranked in-silico protein binders from BindCraft on "
    "the loaded target. Each cell is a computational complex view. Scores and "
    "poses are estimates only. Research use only; not validated binders or therapeutics."
)
COPY_BINDER_RESULT_TEXT_FALLBACK = (
    "BindCraft returned ranked in-silico protein binder designs for the loaded "
    "target. Structure files are available via /download. Scores are computational "
    "estimates only. Research use only; not a validated binder or therapeutic."
)
# Back-compat alias (prefer photo N1 when a single complex is shown).
COPY_BINDER_RESULT_CAPTION = COPY_BINDER_RESULT_PHOTO_N1

# Binder N defaults (BindCraft path; distinct from Boltz ligand floor of 10).
DEFAULT_BINDER_N = 5
MIN_BINDER_N = 1
MAX_BINDER_N = 20

REFUSAL_TEXT = (
    "This request cannot be fulfilled. The bot does not support pathogen design, "
    "reverse-genetics, synthesis planning, or laboratory workflows."
)


def _metric(text: str, *labels: str) -> float | None:
    import re

    blob = text or ""
    for label in labels:
        m = re.search(rf"{re.escape(label)}:\s*([-+]?[0-9]*\.?[0-9]+)", blob)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


TELEGRAM_CAPTION_MAX = 1024


def _photo_caption(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= TELEGRAM_CAPTION_MAX:
        return text
    return text[: TELEGRAM_CAPTION_MAX - 1] + "…"


def _caption_with_scores(blurb: str, scores: str | None) -> str:
    """3C paragraph plus a brief score line if it still fits in one caption."""
    base = (blurb or "").strip()
    extra = (scores or "").strip()
    if extra:
        combo = f"{base}\n{extra}"
        if len(combo) <= TELEGRAM_CAPTION_MAX:
            return combo
    return _photo_caption(base)


def _chat_id(update: Update) -> int | None:
    chat = update.effective_chat
    return chat.id if chat is not None else None


def _stash_if_card(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | None,
    *,
    cif_path: Path | None = None,
    cif_name: str = "result.cif",
    candidates: list[Any] | None = None,
) -> tuple[list[dict[str, str]], Path | None]:
    """Durable-copy artifacts only when a context card exists."""
    if chat_id is None or load_card(context.user_data) is None:
        return [], None
    files, dest = stash_run_files(
        chat_id,
        cif_path=cif_path,
        cif_name=cif_name,
        candidates=candidates,
    )
    return files, dest


def _keep_result_png(
    files: list[dict[str, str]], dest: Path | None
) -> tuple[list[dict[str, str]], str | None]:
    if dest is None:
        return files, None
    keep = dest / "result.png"
    if not keep.exists():
        return files, None
    out = list(files)
    out.append(file_record(keep, "result.png", "result_png"))
    return out, str(keep)


async def _persist_interpretation(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    kind: str,
    metrics: dict[str, Any] | None = None,
    run_id: str | None = None,
    files: list[dict[str, Any]] | None = None,
    result_png: str | None = None,
) -> None:
    """Store 3C caption + file paths on an existing /load card only. No chat text."""
    card = load_card(context.user_data)
    if card is None:
        return
    prior = (card.last_run or {}).get("files") if card.last_run else None
    if prior:
        drop_files(prior)
    attach_last_run(
        card,
        kind=kind,
        interpretation=text,
        metrics=metrics,
        run_id=run_id,
        files=files,
        result_png=result_png,
    )
    store_card(context.user_data, card)
    remember_result(context.user_data, card)


async def _send_details(message, body: str) -> None:
    await message.reply_text("Further scores and files follow.\n" + body)


def _settings(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["settings"]



def _target_from_context(context: ContextTypes.DEFAULT_TYPE) -> str:
    card = load_card(context.user_data)
    if card:
        return target_label(card.gene, card.variant)
    return target_label(None, None)

async def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = _settings(context)
    if settings.telegram_allowed_user_id is None:
        return True
    user = update.effective_user
    if user is None or user.id != settings.telegram_allowed_user_id:
        if update.effective_message:
            await update.effective_message.reply_text(
                "This chat is not authorised to use the bot. Please set TELEGRAM_ALLOWED_USER_ID "
                "to your numeric user identifier, or clear that setting."
            )
        return False
    return True


def _looks_like_refusal_request(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in REFUSAL_KEYWORDS)


def _user_id(update: Update) -> int | None:
    user = update.effective_user
    return int(user.id) if user is not None else None


def _patient_id_from_user_data(user_data: dict[str, Any] | None) -> str | None:
    """Read-only peek at stable patient_id. Never creates/mutates patient or biometrics.

    /evidence /research /scribe must not call onboard.get_patient (privacy lock).
    """
    if not user_data:
        return None
    from .context_card import CONTEXT_CARD_KEY

    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict):
        return None
    patient = raw.get("patient")
    if not isinstance(patient, dict):
        return None
    pid = patient.get("patient_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return None


def _safe_emit(user_id: int | None, kind: str, payload: dict[str, Any] | None = None) -> None:
    """Emit history event; never fail the Telegram reply path."""
    if user_id is None:
        return
    try:
        history_mod.emit(user_id, kind, payload or {})
    except Exception:  # noqa: BLE001
        logger.warning("emit failed kind=%s user=%s", kind, user_id, exc_info=True)




async def _refuse_if_blocked(
    message,
    sequence: str,
    settings,
    *,
    user_id: int | None = None,
    user_data: dict[str, Any] | None = None,
) -> bool:
    """Run bioscreen.gate; reply locked refuse and return True if REVIEW/BLOCK."""
    result = gate(
        sequence,
        bin_name=getattr(settings, "commec_bin", None),
        timeout_sec=float(getattr(settings, "commec_timeout_sec", 60)),
    )
    if result.decision in (Decision.REVIEW, Decision.BLOCK):
        logger.info(
            "bioscreen refuse decision=%s screen=%s alphabet=%s",
            result.decision.value,
            result.screen,
            result.alphabet,
        )
        await message.reply_text(refuse_message(result))
        _safe_emit(
            user_id,
            history_mod.KIND_BIOSECURITY,
            {
                "decision": result.decision.value,
                "patient_id": _patient_id_from_user_data(user_data),
            },
        )
        return True
    return False


async def cmd_research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Europe PMC preprint brief. No bioscreen. No Biohub/Boltz/commec."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    topic = " ".join(context.args or []).strip()
    err = topic_error(topic)
    if err:
        await message.reply_text(err)
        return
    try:
        records = await asyncio.to_thread(search_preprints, topic)
    except ResearchServiceError:
        await message.reply_text(MSG_FAIL_CLOSED)
        return
    except Exception:  # noqa: BLE001 — fail-closed; never invent cites
        logger.exception("research search failed")
        await message.reply_text(MSG_FAIL_CLOSED)
        return
    body = render_research_md(topic, records)
    caption = caption_for(topic, len(records))
    buf = BytesIO(body.encode("utf-8"))
    await message.reply_document(
        document=buf,
        filename="research-brief.md",
        caption=caption,
    )
    dois = history_mod.extract_dois(body)
    _safe_emit(
        _user_id(update),
        history_mod.KIND_RESEARCH,
        {
            "brief_md": body,
            "dois": dois,
            "patient_id": _patient_id_from_user_data(context.user_data),
        },
    )


async def cmd_evidence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Europe PMC peer-reviewed evidence brief. No bioscreen. No patient secrets in query."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    question = " ".join(context.args or []).strip()
    err = question_error(question)
    if err:
        await message.reply_text(err)
        return
    # Privacy lock: never read biometric secrets or patient_files into the query or brief.
    try:
        records = await asyncio.to_thread(search_peer_reviewed, question)
    except EvidenceServiceError:
        await message.reply_text(EVIDENCE_MSG_FAIL_CLOSED)
        return
    except Exception:  # noqa: BLE001 — fail-closed; never invent cites
        logger.exception("evidence search failed")
        await message.reply_text(EVIDENCE_MSG_FAIL_CLOSED)
        return
    body = render_evidence_md(question, records)
    caption = evidence_caption_for(question, len(records))
    buf = BytesIO(body.encode("utf-8"))
    await message.reply_document(
        document=buf,
        filename="evidence-brief.md",
        caption=caption,
    )
    dois = history_mod.extract_dois(body)
    _safe_emit(
        _user_id(update),
        history_mod.KIND_EVIDENCE,
        {
            "brief_md": body,
            "dois": dois,
            "patient_id": _patient_id_from_user_data(context.user_data),
        },
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update, context):
        return
    await update.effective_message.reply_text(
        "This is a research bot for Biohub, Boltz, and BindCraft models. Send /help for the list "
        "of commands. It predicts protein structure and binding, proposes in-silico small-molecule "
        "ligands, and designs in-silico protein binders after /design and /confirm. It does not offer "
        "clinical advice, and it does not guide laboratory work."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update, context):
        return
    await update.effective_message.reply_markdown(HELP_TEXT)




def _format_card_for_user(user_data: dict[str, Any]) -> str:
    card = load_card(user_data)
    if card is None:
        return ""
    return format_card(card, patient=onboard_mod.get_patient(user_data))


SEQUENCE_WITHDRAWN_TEXT = (
    "`/sequence` has been withdrawn. Please use /load with the same arguments."
)


async def cmd_load(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parse NL into a context card. Never starts a GPU / API job."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    args = list(context.args or [])
    chat_id = _chat_id(update)
    if args and args[0].lower() == "clear":
        if chat_id is not None:
            drop_session(chat_id)
        clear_cache(context.user_data)
        onboard_mod.end_onboard(context.user_data)
        patient_files_mod.end_note(context.user_data)
        if clear_card(context.user_data):
            await message.reply_text(
                "The context card, patient biometrics, and patient files have been cleared."
            )
        else:
            await message.reply_text("No context card is loaded.")
        return
    if not args:
        card = load_card(context.user_data)
        if card is None:
            await message.reply_text(
                "No context card is loaded. Please use /load with a clear request, "
                "then run a job. For example: /load find me an inhibitor for KRAS G12C GDP covalent"
            )
            return
        await message.reply_text(format_card(card, patient=onboard_mod.get_patient(context.user_data)))
        return

    joined = " ".join(args)
    if _looks_like_refusal_request(joined):
        await message.reply_text(
            REFUSAL_TEXT
        )
        return

    card = parse_load_text(joined)
    if card.sequence:
        settings = _settings(context)
        if await _refuse_if_blocked(message, card.sequence, settings, user_id=_user_id(update), user_data=context.user_data):
            return
    store_card(context.user_data, card)
    body = format_card(card, patient=onboard_mod.get_patient(context.user_data))
    hit = lookup_result(context.user_data, card)
    if hit:
        when = hit.get("at") or (hit.get("last_run") or {}).get("at") or "an earlier run"
        body = (
            f"{body}\n\n"
            f"This request matches a completed card from {when}. "
            "Send /view to see that earlier result, including the image and description. "
            "You may also continue with /esm, /boltz, or /design to run the job again."
        )
    await message.reply_text(body)


async def cmd_sequence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Withdrawn alias: one-line stub per COPY-load, then same behaviour as /load."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    await message.reply_text(SEQUENCE_WITHDRAWN_TEXT)
    await cmd_load(update, context)


async def cmd_esm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    raw = " ".join(context.args) if context.args else ""
    if not raw:
        card = load_card(context.user_data)
        if card and card.sequence:
            raw = card.sequence
        else:
            await message.reply_text(
                "A protein sequence is required. Please send /esm followed by an "
                "amino-acid sequence, or use /load first and then send /esm alone."
            )
            return
    if _looks_like_refusal_request(raw):
        await message.reply_text(
            REFUSAL_TEXT
        )
        return

    settings = _settings(context)
    if await _refuse_if_blocked(message, raw, settings, user_id=_user_id(update), user_data=context.user_data):
        return
    try:
        sequence = validate_protein_sequence(raw, settings.max_sequence_length)
    except ValueError as exc:
        await message.reply_text(str(exc))
        return

    await message.reply_text(
        f"The structure prediction has begun for a sequence of {len(sequence)} "
        "amino acids. This may take several minutes."
    )

    client: BiohubClient = context.application.bot_data["biohub"]
    try:
        result = await asyncio.to_thread(client.fold, sequence)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(_service_fail(exc))
        return

    plddt = _metric(result.summary, "pLDDT mean")
    ptm = _metric(result.summary, "pTM")
    blurb = interpret_fold(
        n_aa=len(sequence),
        target=_target_from_context(context),
        structure_confidence=plddt,
        ptm=ptm,
    )
    caption = blurb
    cif = result.cif_path if result.cif_path and result.cif_path.exists() else None
    files, dest = _stash_if_card(
        context,
        _chat_id(update),
        cif_path=cif,
        cif_name="esm.cif",
    )
    keep = (dest / "result.png") if dest is not None else None
    if cif is not None:
        try:
            ok = await send_structure_photo(
                message,
                cif,
                caption=caption,
                keep_path=keep,
            )
            if not ok:
                await message.reply_text(f"{IMAGE_RENDER_FAILED}\n\n{caption}")
        finally:
            _safe_unlink(cif)
    else:
        await message.reply_text(
            "The fold returned no structure file to display. " + caption
        )
    files, png = _keep_result_png(files, dest)
    await _persist_interpretation(
        context,
        caption,
        kind="esm_fold",
        metrics={"plddt": plddt, "ptm": ptm, "n_aa": len(sequence)},
        files=files,
        result_png=png,
    )


async def cmd_boltz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    if not context.args:
        card = load_card(context.user_data)
        if not (card and card.sequence):
            await message.reply_text(
                "A protein sequence is required. Please send /boltz followed by an "
                "amino-acid sequence, or add a ligand SMILES after the sequence. "
                "If you /load a natural-language request that does not resolve to a "
                "sequence, bare /boltz cannot run — paste a sequence or /load a curated "
                "target (for example KRAS G12C), then /boltz again after a successful "
                "fold is available for later /design binder. "
                "For small-molecule design, please use /design ligand."
            )
            return
        protein_raw = card.sequence
        ligand_raw = card.smiles
    else:
        joined = " ".join(context.args)
        if _looks_like_refusal_request(joined):
            await message.reply_text(
                REFUSAL_TEXT
            )
            return
        protein_raw = context.args[0]
        ligand_raw = context.args[1] if len(context.args) > 1 else None
        if len(context.args) > 2:
            last = context.args[-1]
            if any(c in last for c in "=#@()[]\\/+") or any(ch.isdigit() for ch in last):
                protein_raw = "".join(context.args[:-1])
                ligand_raw = last
            else:
                protein_raw = "".join(context.args)
                ligand_raw = None

    settings = _settings(context)
    if await _refuse_if_blocked(message, protein_raw, settings, user_id=_user_id(update), user_data=context.user_data):
        return

    try:
        sequence = validate_protein_sequence(protein_raw, settings.max_sequence_length)
        smiles = validate_smiles(ligand_raw) if ligand_raw else None
    except ValueError as exc:
        await message.reply_text(str(exc))
        return

    mode = "with ligand binding" if smiles else "structure only"
    await message.reply_text(
        f"The structure prediction has begun ({mode}) for a sequence of "
        f"{len(sequence)} amino acids. The service will be polled until the work is complete."
    )

    client: BoltzClient = context.application.bot_data["boltz"]
    try:
        result = await asyncio.to_thread(client.predict_structure, sequence, smiles)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(_service_fail(exc))
        return

    sc = _metric(result.summary, "structure_confidence", "complex_plddt")
    ptm = _metric(result.summary, "pTM")
    bind = _metric(result.summary, "binding_confidence")
    opt = _metric(result.summary, "optimization_score")
    if smiles:
        blurb = interpret_binding(
            n_aa=len(sequence),
            target=_target_from_context(context),
            binding_confidence=bind,
            optimization_score=opt,
            structure_confidence=sc,
        )
        kind = "boltz_binding"
    else:
        blurb = interpret_fold(
            n_aa=len(sequence),
            target=_target_from_context(context),
            structure_confidence=sc,
            ptm=ptm,
        )
        kind = "boltz_structure"
    caption = blurb
    cif = result.cif_path if result.cif_path and result.cif_path.exists() else None
    files, dest = _stash_if_card(
        context,
        _chat_id(update),
        cif_path=cif,
        cif_name="boltz.cif",
    )
    keep = (dest / "result.png") if dest is not None else None
    if cif is not None:
        try:
            ok = await send_structure_photo(
                message,
                cif,
                caption=caption,
                keep_path=keep,
            )
            if not ok:
                await message.reply_text(f"{IMAGE_RENDER_FAILED}\n\n{caption}")
        finally:
            _safe_unlink(cif)
    else:
        await message.reply_text(
            "Boltz returned no structure file to display. " + caption
        )
    files, png = _keep_result_png(files, dest)
    await _persist_interpretation(
        context,
        caption,
        kind=kind,
        metrics={
            "structure_confidence": sc,
            "ptm": ptm,
            "binding_confidence": bind,
            "optimization_score": opt,
            "n_aa": len(sequence),
        },
        files=files,
        result_png=png,
    )


def _parse_design_n(args: list[str]) -> tuple[list[str], int]:
    """Split optional trailing molecule count from /design ligand args (Boltz floor)."""
    n = DEFAULT_N_DESIGNS
    seq_args = list(args)
    if seq_args and seq_args[-1].isdigit():
        n = int(seq_args.pop())
    elif seq_args and seq_args[-1].lower().startswith("n="):
        raw = seq_args.pop().split("=", 1)[1]
        if raw.isdigit():
            n = int(raw)
    if n < MIN_N_DESIGNS:
        n = MIN_N_DESIGNS
    if n > MAX_N_DESIGNS:
        n = MAX_N_DESIGNS
    return seq_args, n


def _parse_binder_n(args: list[str]) -> tuple[list[str], int]:
    """Split optional trailing design count for /design binder (default 5, min 1, cap 20)."""
    n = DEFAULT_BINDER_N
    rest = list(args)
    if rest and rest[-1].isdigit():
        n = int(rest.pop())
    elif rest and rest[-1].lower().startswith("n="):
        raw = rest.pop().split("=", 1)[1]
        if raw.isdigit():
            n = int(raw)
    if n < MIN_BINDER_N:
        n = MIN_BINDER_N
    if n > MAX_BINDER_N:
        n = MAX_BINDER_N
    return rest, n


def _card_has_structure(card) -> bool:
    """True when the loaded card has a durable CIF from a prior /esm or /boltz run."""
    if card is None:
        return False
    last = card.last_run
    if not isinstance(last, dict):
        return False
    return file_of_kind(last, "cif") is not None


def _card_hotspot_source(card) -> str | None:
    """Provenance for binder confirm COPY. Never invent."""
    if card is None:
        return None
    src = getattr(card, "hotspot_source", None)
    if src:
        return src
    raw = getattr(card, "to_dict", lambda: {})()
    if isinstance(raw, dict) and raw.get("hotspot_source"):
        return raw.get("hotspot_source")
    return None


def _card_hotspot(card) -> list | None:
    """Return hotspot residues only from explicit card supply or curated fixture map.

    Never LM-invent. Ordinary pocket_residues without hotspot_source are not a hotspot.
    """
    if card is None:
        return None
    hotspot = getattr(card, "hotspot_residues", None)
    if hotspot:
        return hotspot
    raw = card.last_run if isinstance(card.last_run, dict) else {}
    hs = raw.get("hotspot_residues") if isinstance(raw, dict) else None
    if hs:
        return hs
    # KRAS Switch-II curated fixture → pocket_residues as binder hotspot.
    if _card_hotspot_source(card) == HOTSPOT_SOURCE_KRAS_SWITCH_II:
        pocket = getattr(card, "pocket_residues", None)
        return pocket_residues_to_hotspot_list(pocket)
    return None


async def _queue_ligand_design(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    seq_args: list[str],
    n: int | None,
) -> None:
    """Boltz small-molecule design confirm/cost path (shared by /design ligand and legacy)."""
    message = update.effective_message
    assert message is not None
    card = load_card(context.user_data)
    covalent = False
    pocket = None
    refs = None
    max_usd = DEFAULT_MAX_USD
    if not seq_args:
        if not (card and card.sequence):
            await message.reply_text(
                "A protein sequence is required. Please send /design ligand followed by an "
                "amino-acid sequence, or add a molecule count after the sequence. "
                "You may also /load a target first and then send /design ligand. "
                f"The default count is {DEFAULT_N_DESIGNS} (the service minimum; about US$0.25). "
                "Send /confirm to proceed, or /cancel to stop."
            )
            return
        seq_args = [card.sequence]
        if n is None:
            n = card.n_designs
        covalent = bool(card.covalent) if card.covalent is not None else False
        pocket = card.pocket_residues
        refs = card.reference_ligands
        max_usd = float(card.max_usd)
    elif n is None:
        n = DEFAULT_N_DESIGNS

    settings = _settings(context)
    raw_seq = "".join(seq_args)
    if await _refuse_if_blocked(
        message, raw_seq, settings, user_id=_user_id(update), user_data=context.user_data
    ):
        return
    try:
        sequence = validate_protein_sequence(raw_seq, settings.max_sequence_length)
    except ValueError as exc:
        await message.reply_text(
            f"{exc} Please pass an amino-acid sequence, not a gene name. "
            "You may also /load a curated target such as KRAS first. "
            "Example: /design ligand MKTIIALSYIFCLVFA"
        )
        return

    client: BoltzClient = context.application.bot_data["boltz"]
    try:
        est = await asyncio.to_thread(client.estimate_design_cost, sequence, n)
        est_usd = float(est.estimated_cost_usd)
        n_used = int(est.num_molecules)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(
            "The cost estimate could not be obtained. "
            f"{_user_err(exc)}. Please try again shortly."
        )
        return

    context.user_data[PENDING_DESIGN_KEY] = {
        "mode": "ligand",
        "sequence": sequence,
        "n_designs": n_used,
        "max_usd": max_usd,
        "estimated_cost_usd": est_usd,
        "covalent": covalent,
        "pocket_residues": pocket,
        "reference_ligands": refs,
    }
    cost_s = f"{est_usd:.2f}"
    await message.reply_text(COPY_LIGAND_CONFIRM.format(n=n_used, cost=cost_s))


async def _queue_binder_design(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    n: int,
) -> None:
    """BindCraft path: fail-closed without BINDCRAFT_HOME; else card+structure confirm."""
    message = update.effective_message
    assert message is not None
    settings = _settings(context)
    home = getattr(settings, "bindcraft_home", "") or ""
    # Fail-closed until local BINDCRAFT_HOME *or* Modal creds (compute-only; no PHI on Modal).
    if not bindcraft_mod.binder_compute_ready(
        home,
        modal_token_id=getattr(settings, "modal_token_id", "") or "",
        modal_token_secret=getattr(settings, "modal_token_secret", "") or "",
    ):
        await message.reply_text(COPY_BINDCRAFT_NOT_CONFIGURED)
        return

    card = load_card(context.user_data)
    if card is None or not _card_has_structure(card):
        await message.reply_text(COPY_BINDER_NO_STRUCTURE)
        return

    hotspot = _card_hotspot(card)
    hotspot_source = _card_hotspot_source(card)
    cif = file_of_kind(card.last_run or {}, "cif")
    context.user_data[PENDING_DESIGN_KEY] = {
        "mode": "binder",
        "n_designs": n,
        "structure_path": str(cif) if cif else None,
        "hotspot_residues": hotspot,
        "hotspot_source": hotspot_source,
        "sequence": card.sequence,  # for bioscreen on confirm if present
    }
    if hotspot and hotspot_source == HOTSPOT_SOURCE_KRAS_SWITCH_II:
        await message.reply_text(COPY_BINDER_CONFIRM_SWITCH2_FIXTURE.format(n=n))
    elif hotspot:
        await message.reply_text(COPY_BINDER_CONFIRM_HOTSPOT.format(n=n))
    else:
        await message.reply_text(COPY_BINDER_CONFIRM_TARGET_WIDE.format(n=n))


async def cmd_design(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dual-mode /design: ligand (Boltz) · binder (BindCraft). Never auto-guess mode."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    args = list(context.args or [])
    if args and _looks_like_refusal_request(" ".join(args)):
        await message.reply_text(REFUSAL_TEXT)
        return

    # Bare /design → mode prompt (no GPU). Also when args are neither mode nor sequence.
    if not args:
        await message.reply_text(COPY_DESIGN_MODE_PROMPT)
        return

    mode0 = args[0].lower()
    if mode0 == "ligand":
        rest = args[1:]
        seq_args, n = _parse_design_n(rest) if rest else ([], None)
        # _parse_design_n with empty rest isn't called; bare ligand → card / prompt
        if not rest:
            seq_args, n = [], None
        else:
            seq_args, n = _parse_design_n(rest)
        await _queue_ligand_design(update, context, seq_args=seq_args, n=n)
        return

    if mode0 == "binder":
        rest = args[1:]
        _ignored, n = _parse_binder_n(rest) if rest else ([], DEFAULT_BINDER_N)
        if not rest:
            n = DEFAULT_BINDER_N
        else:
            _ignored, n = _parse_binder_n(rest)
        await _queue_binder_design(update, context, n=n)
        return

    # Legacy: /design <seq> [n] — treat as ligand if first token looks like AA sequence.
    joined = "".join(args)
    # If last token is a count, check the sequence portion.
    seq_probe_args, _n_probe = _parse_design_n(args)
    probe = "".join(seq_probe_args) if seq_probe_args else joined
    if seq_probe_args and looks_like_aa_sequence(probe, min_len=1):
        seq_args, n = _parse_design_n(args)
        await _queue_ligand_design(update, context, seq_args=seq_args, n=n)
        return

    await message.reply_text(COPY_DESIGN_MODE_PROMPT)


async def cmd_bind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Withdrawn standalone /bind — point users at /design binder."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    await message.reply_text(COPY_BIND_STUB)


async def _handle_structure_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    req: StructureRequest,
) -> None:
    message = update.effective_message
    assert message is not None
    settings = _settings(context)
    if await _refuse_if_blocked(message, req.sequence, settings, user_id=_user_id(update), user_data=context.user_data):
        return
    try:
        sequence = validate_protein_sequence(req.sequence, settings.max_sequence_length)
        smiles = validate_smiles(req.smiles) if req.smiles else None
    except ValueError as exc:
        await message.reply_text(str(exc))
        return

    mode = "with ligand binding" if smiles else "structure only"
    await message.reply_text(
        f"The structure prediction has begun ({mode}) for a sequence of "
        f"{len(sequence)} amino acids. The service will be polled until the work is complete."
    )

    client: BoltzClient = context.application.bot_data["boltz"]
    try:
        result = await asyncio.to_thread(client.predict_structure, sequence, smiles)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(_service_fail(exc))
        return

    await message.reply_text(result.summary)
    if result.cif_path and result.cif_path.exists():
        try:
            with result.cif_path.open("rb") as fh:
                await message.reply_document(
                    document=fh,
                    filename="boltz.cif",
                    caption="Predicted structure file (mmCIF). For research use only.",
                )
        finally:
            _safe_unlink(result.cif_path)


async def _handle_design_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    req: DesignRequest,
) -> None:
    message = update.effective_message
    assert message is not None

    missing = missing_design_fields(req)
    try:
        resolved = resolve(req.target, req.variant)
    except ValueError as exc:
        await message.reply_text(str(exc))
        return

    if missing:
        lines = [
            "A design request was parsed. It is incomplete, and no computation has been started.",
            f"• target: {req.target}",
            f"• variant: {req.variant or '(pick) WT | G12C | G12D | G12V'}",
            f"• state: {req.state or '(pick) GDP | GTP'}",
            f"• covalent: {_fmt_covalent(req.covalent) if req.covalent is not None else '(pick) yes | no'}",
            f"• n_designs: {req.n_designs}"
            + (
                f" (API minimum 10 — US$0.25; you asked {req.n_designs_clamped_from})"
                if req.n_designs_clamped_from is not None
                else ""
            ),
            f"• sequence: {resolved.accession} ({len(resolved.sequence)} aa) "
            f"{resolved.sequence[:10]}…{resolved.sequence[-10:]}",
            "",
            "These fields remain to be specified: " + "; ".join(missing) + ".",
            "Please repeat the request with those fields filled. For example:",
            "/load find inhibitors for KRAS G12C GDP covalent",
        ]
        await message.reply_text("\n".join(lines))
        context.user_data.pop(PENDING_DESIGN_KEY, None)
        return

    # Full card + live cost estimate; store pending until /confirm.
    settings = _settings(context)
    if await _refuse_if_blocked(message, resolved.sequence, settings, user_id=_user_id(update), user_data=context.user_data):
        return

    client: BoltzClient = context.application.bot_data["boltz"]
    estimate_note = ""
    est_usd: float | None = None
    try:
        est = await asyncio.to_thread(
            client.estimate_design_cost,
            resolved.sequence,
            req.n_designs,
            pocket_residues=resolved.pocket_residues,
            reference_ligands=resolved.reference_ligands,
        )
        est_usd = float(est.estimated_cost_usd)
        clamp_note = ""
        if req.n_designs_clamped_from is not None:
            clamp_note = (
                f"; {req.n_designs_clamped_from} were requested, and the "
                "service minimum of ten will be used (about US$0.25)"
            )
        estimate_note = f"The estimated cost is US${est_usd:.4f}{clamp_note}."
    except Exception as exc:  # noqa: BLE001
        logger.warning("estimate_design_cost failed: %s", exc)
        estimate_note = (
            f"The estimated cost is unavailable ({_user_err(exc)}). "
            "The service minimum is ten molecules, about US$0.25."
        )

    card = _format_confirm_card(req, resolved, estimate_note)
    context.user_data[PENDING_DESIGN_KEY] = {
        "request": req,
        "resolved": resolved,
        "max_usd": DEFAULT_MAX_USD,
        "estimated_cost_usd": est_usd,
    }
    await message.reply_text(card)


def _fmt_covalent(val: bool | None) -> str:
    if val is None:
        return "unspecified"
    return "requested" if val else "not requested"


def _format_confirm_card(
    req: DesignRequest, resolved: ResolvedTarget, estimate_note: str
) -> str:
    n_line = (
        f"The job will request {req.n_designs} molecules. "
        f"The spending cap is about US${DEFAULT_MAX_USD:.2f}."
    )
    if req.n_designs_clamped_from is not None:
        n_line += (
            f" The service minimum is ten (about US$0.25); "
            f"{req.n_designs_clamped_from} were requested."
        )
    lines = [
        "A design request has been prepared.",
        "The intent is small-molecule design.",
        f"The target is {req.target}.",
        f"The variant is {req.variant}.",
        f"The nucleotide state is {req.state}.",
        f"Covalent design is {_fmt_covalent(req.covalent)}.",
        n_line,
        estimate_note,
        f"The sequence source is UniProt {resolved.accession}.",
        f"The sequence comprises {len(resolved.sequence)} amino acids "
        f"({resolved.sequence[:10]}…{resolved.sequence[-10:]}).",
        f"Notes: {resolved.notes}",
    ]
    if resolved.pocket_residues:
        lines.append(f"Optional pocket residues: {resolved.pocket_residues}.")
    if resolved.reference_ligands:
        ref_preview = resolved.reference_ligands[0]
        if len(ref_preview) > 48:
            ref_preview = ref_preview[:45] + "..."
        lines.append(f"An optional reference ligand is {ref_preview}.")
    if req.covalent:
        lines.append(
            "Covalent design requires an explicit bonds list. None is configured "
            "in this version. /confirm will report that error rather than invent a warhead."
        )
    lines.extend(
        [
            "",
            "Send /confirm to begin, or /cancel to discard this plan.",
            DESIGN_DISCLAIMER,
        ]
    )
    return "\n".join(lines)


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    pending: dict[str, Any] | None = context.user_data.get(PENDING_DESIGN_KEY)
    if not pending:
        await message.reply_text(
            "There is nothing to confirm. Please begin with /design, or /load and then /design."
        )
        return

    mode = str(pending.get("mode") or "ligand")
    if mode == "binder":
        # Shared pending slot with ligand. Fail-closed — never invent binders.
        # Modal = GPU compute only; payload is target seq/CIF + hotspot + N (no PHI).
        context.user_data.pop(PENDING_DESIGN_KEY, None)
        settings = _settings(context)
        home = getattr(settings, "bindcraft_home", "") or ""
        seq = pending.get("sequence") or ""
        if seq and await _refuse_if_blocked(
            message, seq, settings, user_id=_user_id(update), user_data=context.user_data
        ):
            return
        n_designs = int(pending.get("n_designs") or DEFAULT_BINDER_N)
        structure = (
            Path(pending["structure_path"])
            if pending.get("structure_path")
            else None
        )
        try:
            result = await asyncio.to_thread(
                bindcraft_mod.run_binder_design,
                structure_path=structure,
                n_designs=n_designs,
                hotspot=pending.get("hotspot_residues"),
                home=home,
                timeout_sec=int(getattr(settings, "bindcraft_timeout_sec", 3600) or 3600),
                target_sequence=seq or None,
                modal_token_id=getattr(settings, "modal_token_id", "") or "",
                modal_token_secret=getattr(settings, "modal_token_secret", "") or "",
                modal_bindcraft_app=getattr(settings, "modal_bindcraft_app", "") or "",
            )
        except modal_bindcraft_mod.ModalBindCraftError as exc:
            kind = getattr(exc, "kind", "") or ""
            if kind == "not_deployed":
                await message.reply_text(COPY_MODAL_BINDCRAFT_NOT_DEPLOYED)
            elif kind == "failed":
                await message.reply_text(COPY_MODAL_BINDCRAFT_FAILED)
            else:
                # no_tokens / unknown — same shape as missing BINDCRAFT_HOME
                await message.reply_text(COPY_BINDCRAFT_NOT_CONFIGURED)
            return
        except Exception:
            await message.reply_text(COPY_BINDCRAFT_NOT_CONFIGURED)
            return

        # Real result only — sync artifacts to last_run + sorter binder:<design-id>.
        # Prefer reply_photo (N=1 single complex / N>1 ranked grid); text only if render fails.
        design_id = result.run_id or uuid.uuid4().hex[:12]
        artifact_paths: list[str] = list(result.artifact_paths or [])
        card = load_card(context.user_data)
        files_meta: list[dict[str, Any]] = []
        keep_png: Path | None = None
        if card is not None and artifact_paths:
            for ap in artifact_paths:
                p = Path(ap)
                if p.is_file():
                    kind = "fasta" if p.suffix.lower() in {".fasta", ".fa"} else "cif"
                    files_meta.append({"kind": kind, "path": str(p), "name": p.name})
            # Stash result.png beside first artifact when possible.
            keep_png = Path(artifact_paths[0]).resolve().parent / "result.png"

        binder_cifs = list_binder_cifs(artifact_paths)
        caption_used = COPY_BINDER_RESULT_TEXT_FALLBACK
        photo_caption = None
        if binder_cifs:
            photo_caption = await send_binder_photo(
                message,
                binder_cifs,
                caption_n1=COPY_BINDER_RESULT_PHOTO_N1,
                caption_grid=COPY_BINDER_RESULT_PHOTO_GRID,
                keep_path=keep_png,
            )
            if photo_caption:
                caption_used = photo_caption
                if keep_png is not None and keep_png.is_file():
                    files_meta.append(
                        {"kind": "result_png", "path": str(keep_png), "name": "result.png"}
                    )
        if not photo_caption:
            caption_used = COPY_BINDER_RESULT_TEXT_FALLBACK
            await message.reply_text(caption_used)

        if card is not None:
            await _persist_interpretation(
                context,
                caption_used,
                kind="binder_design",
                metrics={
                    "n": len(result.designs),
                    "source": result.source,
                    "n_cif": len(binder_cifs),
                    "photo": bool(photo_caption),
                },
                run_id=design_id,
                files=files_meta or None,
                result_png=str(keep_png) if (keep_png and keep_png.is_file()) else None,
            )
        _safe_emit(
            _user_id(update),
            history_mod.KIND_DESIGN,
            {
                "mode": "binder",
                "design_id": design_id,
                "patient_id": _patient_id_from_user_data(context.user_data),
                "artifact_paths": artifact_paths,
            },
        )
        return

    sequence: str = pending["sequence"]
    n_designs: int = pending["n_designs"]
    max_usd: float = pending.get("max_usd", DEFAULT_MAX_USD)

    settings = _settings(context)
    if await _refuse_if_blocked(message, sequence, settings, user_id=_user_id(update), user_data=context.user_data):
        return

    await message.reply_text(
        f"Small-molecule design has begun for a sequence of {len(sequence)} "
        f"amino acids, requesting {n_designs} candidates. This may take some time."
    )

    client: BoltzClient = context.application.bot_data["boltz"]
    try:
        result = await asyncio.to_thread(
            client.design_small_molecules,
            sequence,
            n_designs,
            covalent=pending.get("covalent") or False,
            max_usd=max_usd,
            pocket_residues=pending.get("pocket_residues"),
            reference_ligands=pending.get("reference_ligands"),
        )
    except NotImplementedError as exc:
        context.user_data.pop(PENDING_DESIGN_KEY, None)
        await message.reply_text(
            "The design service is not ready on this build. "
            f"{exc} Please try again after the interface is restored."
        )
        return
    except Exception as exc:  # noqa: BLE001
        # Includes covalent=True without bonds RuntimeError from BoltzClient.
        context.user_data.pop(PENDING_DESIGN_KEY, None)
        await message.reply_text(_service_fail(exc))
        return

    context.user_data.pop(PENDING_DESIGN_KEY, None)
    candidates = getattr(result, "candidates", []) or []
    ranked = rank_candidates(candidates)
    run_id = getattr(result, "run_id", None)
    blurb = interpret_design(
        n=len(ranked) or n_designs,
        candidates=ranked,
        target=_target_from_context(context),
    )
    top = ranked[0] if ranked else {}
    bind = None
    opt = None
    if isinstance(top, dict):
        bind = top.get("binding_confidence")
        opt = top.get("optimization_score")
    else:
        bind = getattr(top, "binding_confidence", None)
        opt = getattr(top, "optimization_score", None)
    caption = blurb
    cif = getattr(result, "best_cif_path", None)
    cif_path = Path(cif) if cif else None
    if cif_path is not None and not cif_path.exists():
        cif_path = None
    files, dest = _stash_if_card(
        context,
        _chat_id(update),
        cif_path=cif_path,
        cif_name="boltz.cif",
        candidates=ranked or None,
    )
    keep = (dest / "result.png") if dest is not None else None
    if ranked:
        meta = {
            "run_id": run_id or "design",
            "n": len(ranked),
            "estimated_cost_usd": getattr(result, "estimated_cost_usd", None),
            "sequence_length": len(sequence),
            "disclaimer": DESIGN_DISCLAIMER,
        }
        ok = await send_design_photo(
            message,
            ranked,
            meta,
            caption=caption,
            keep_path=keep,
        )
        if not ok:
            await message.reply_text(caption)
    else:
        await message.reply_text(caption)

    if cif_path is not None:
        _safe_unlink(cif_path)
    files, png = _keep_result_png(files, dest)
    await _persist_interpretation(
        context,
        caption,
        kind="small_molecule_design",
        metrics={
            "n": len(ranked) or n_designs,
            "binding_confidence": bind,
            "optimization_score": opt,
        },
        run_id=run_id,
        files=files,
        result_png=png,
    )


def _format_design_table(sequence: str, n_designs: int, result: Any) -> str:
    """Prefer client summary; add a compact ranked header."""
    header = (
        f"Small-molecule design for a sequence of {len(sequence)} amino acids, "
        f"requesting {n_designs} candidates."
    )
    summary = getattr(result, "summary", None)
    if summary:
        return f"{header}\n{summary}\n{DESIGN_DISCLAIMER}"

    lines = [header, "#  SMILES  binding_confidence  optimization_score  ADME"]
    candidates = getattr(result, "candidates", []) or []
    for i, c in enumerate(candidates[:10], 1):
        bc = getattr(c, "binding_confidence", None)
        opt = getattr(c, "optimization_score", None)
        sol = getattr(c, "adme_solubility", None) or "—"
        smiles = getattr(c, "smiles", "") or ""
        bc_s = f"{bc:.3f}" if bc is not None else "—"
        opt_s = f"{opt:.3f}" if opt is not None else "—"
        lines.append(f"{i}  {smiles}  {bc_s}  {opt_s}  {sol}")
    lines.append(DESIGN_DISCLAIMER)
    return "\n".join(lines)


async def cmd_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Replay a cached result as one photo+caption. No hosted GPU job."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    card = load_card(context.user_data)
    if card is None:
        await message.reply_text(
            "No context card is loaded. Please use /load with a clear request, then run a job."
        )
        return
    hit = lookup_result(context.user_data, card)
    if hit is None:
        await message.reply_text(
            "No stored result for this card yet. Please run /esm, /boltz, or /design followed by /confirm."
        )
        return
    last_run = hit.get("last_run") or hit
    caption = str(hit.get("interpretation") or last_run.get("interpretation") or "").strip()
    if not caption:
        await message.reply_text(
            "No stored result for this card yet. Please run /esm, /boltz, or /design followed by /confirm."
        )
        return

    png = result_png_path(last_run)
    if png is not None:
        try:
            data = png.read_bytes()
        except OSError:
            data = b""
        if data and len(data) >= 64:
            await message.reply_photo(photo=data, caption=caption[:1024])
            return
        # Fall through to CIF / CSV redraw if stored PNG is empty or unreadable.

    cif = file_of_kind(last_run, "cif")
    if cif is not None:
        ok = await send_structure_photo(message, cif, caption=caption)
        if ok:
            return
        await message.reply_text(
            "The stored image could not be opened, and a new drawing from the "
            "structure file also failed. Please run the job again."
        )
        return

    csv_path = file_of_kind(last_run, "design_csv")
    if csv_path is not None:
        candidates = read_candidates_csv(csv_path)
        if candidates:
            ok = await send_design_photo(
                message,
                candidates,
                {"run_id": last_run.get("run_id") or "view", "n": len(candidates)},
                caption=caption,
            )
            if ok:
                return
        await message.reply_text(
            "The stored image could not be opened, and the design table could not "
            "be redrawn. Please run /design and /confirm again."
        )
        return

    await message.reply_text(
        "The stored files for this card could not be found. "
        "Please run /esm, /boltz, or /design again."
    )


async def cmd_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send last-run artifacts from the current context card."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    card = load_card(context.user_data)
    if card is None:
        await message.reply_text(
            "No context card is loaded. Please use /load with a clear request, then run a job."
        )
        return
    files = (card.last_run or {}).get("files") or []
    if not files:
        await message.reply_text(
            "No downloadable files are available yet. Please run /esm, /boltz, or /design followed by /confirm."
        )
        return

    present: list[dict[str, Any]] = []
    missing: list[str] = []
    for rec in files:
        if not isinstance(rec, dict):
            continue
        path = Path(str(rec.get("path") or ""))
        name = str(rec.get("filename") or path.name or "file")
        if path.exists():
            present.append({"path": path, "filename": name})
        else:
            missing.append(name)

    if missing:
        await message.reply_text(
            "These files could not be found on disk and were skipped: " + ", ".join(missing) + "."
        )
    if not present:
        if not missing:
            await message.reply_text(
                "No downloadable files are available yet. Please run /esm, /boltz, or /design followed by /confirm."
            )
        return

    lines = ["The following files are available from the current card."]
    lines.extend(f"• {item['filename']}" for item in present)
    await message.reply_text("\n".join(lines))
    for item in present:
        with item["path"].open("rb") as fh:
            await message.reply_document(document=fh, filename=item["filename"])





async def cmd_scribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Organise meeting notes into Markdown minutes. Unlinked from card/patient/files."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    # Inline text after /scribe, or arm next message when bare.
    inline = " ".join(context.args or []).strip()
    if not inline:
        scribe_md_mod.arm_scribe(context.user_data)
        await message.reply_text(scribe_md_mod.MSG_ARMED)
        return
    await _run_scribe(message, context, inline, user_id=_user_id(update))


async def _run_scribe(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    source: str,
    *,
    user_id: int | None = None,
) -> None:
    """Fail-closed organise + reply_document. Never reads/writes card or patient stores."""
    err = scribe_md_mod.source_error(source)
    if err:
        await message.reply_text(err)
        return
    settings = context.application.bot_data.get("settings") if context.application else None
    url = getattr(settings, "scribe_llm_url", None) if settings is not None else None
    key = getattr(settings, "scribe_llm_key", None) if settings is not None else None
    model = getattr(settings, "scribe_llm_model", None) if settings is not None else None
    # Prefer settings when present; empty string means fall through to env in client.
    kwargs = {}
    if url:
        kwargs["url"] = url
    if key:
        kwargs["api_key"] = key
    if model:
        kwargs["model"] = model
    try:
        raw = await asyncio.to_thread(organise_minutes, source, **kwargs)
    except ScribeNotConfiguredError:
        await message.reply_text(scribe_md_mod.MSG_NOT_CONFIGURED)
        return
    except ScribeServiceError:
        await message.reply_text(scribe_md_mod.MSG_FAIL_CLOSED)
        return
    except Exception:  # noqa: BLE001 — fail-closed; never invent minutes
        logger.exception("scribe organise failed")
        await message.reply_text(scribe_md_mod.MSG_FAIL_CLOSED)
        return
    body = scribe_md_mod.ensure_skeleton(raw)
    buf = BytesIO(body.encode("utf-8"))
    await message.reply_document(
        document=buf,
        filename="meeting-minutes.md",
        caption=scribe_md_mod.CAPTION,
    )
    # v1 unlinked → inbox via sorter (no patient minutes).
    _safe_emit(
        user_id,
        history_mod.KIND_SCRIBE,
        {
            "minutes_md": body,
            "linked": False,
            "patient_id": _patient_id_from_user_data(context.user_data),
        },
    )

async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Append patient files on the card. Separate from biometric secrets. No LM/Discord."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    args = [a.lower() for a in (context.args or [])]
    if args and args[0] == "clear":
        await message.reply_text(patient_files_mod.clear_text(context.user_data))
        return
    if args and args[0] == "list":
        await message.reply_text(patient_files_mod.list_text(context.user_data))
        return
    if args:
        await message.reply_text(patient_files_mod.MSG_BAD_OPTION)
        return
    await message.reply_text(patient_files_mod.start_note(context.user_data))


async def cmd_onboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect fixed patient biometrics one field at a time. Research-use secrets."""
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    args = [a.lower() for a in (context.args or [])]
    if args and args[0] == "clear":
        had = onboard_mod.clear_patient(context.user_data)
        if had:
            await message.reply_text(
            "Patient biometric secrets and patient files have been cleared."
        )
        else:
            await message.reply_text("No patient biometrics were on file.")
        return
    if args and args[0] == "status":
        patient = onboard_mod.get_patient(context.user_data)
        await message.reply_text(onboard_mod.status_text(patient))
        return
    if args:
        await message.reply_text(
            "Unrecognised /onboard option. Use /onboard, /onboard status, or /onboard clear."
        )
        return
    reply, _field = onboard_mod.start_or_resume(context.user_data)
    await message.reply_text(reply)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    ended_onboard = onboard_mod.end_onboard(context.user_data)
    ended_note = patient_files_mod.end_note(context.user_data)
    ended_scribe = scribe_md_mod.end_scribe(context.user_data)
    had_design = context.user_data.pop(PENDING_DESIGN_KEY, None) is not None
    parts: list[str] = []
    if had_design:
        parts.append("The pending design job has been cancelled.")
    if ended_onboard:
        parts.append(
            "The onboard questions have been ended. Saved patient biometrics were kept."
        )
    if ended_note:
        parts.append(
            "The pending note was cancelled. Saved patient files were kept."
        )
    if ended_scribe:
        parts.append(scribe_md_mod.MSG_CANCELLED)
    if parts:
        await message.reply_text(" ".join(parts))
        return
    await message.reply_text("There is nothing to cancel.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update, context):
        return
    message = update.effective_message
    assert message is not None
    text = message.text or ""
    if onboard_mod.is_active(context.user_data):
        # Plain text answers the current biometric question (before unknown-command).
        reply = onboard_mod.apply_answer(context.user_data, text)
        await message.reply_text(reply)
        patient = onboard_mod.get_patient(context.user_data)
        if (
            patient
            and patient.get("complete")
            and "complete" in reply.lower()
            and "values are stored" in reply.lower()
        ):
            pid = onboard_mod.ensure_patient_id(patient)
            onboard_mod.set_patient(context.user_data, patient)
            _safe_emit(
                _user_id(update),
                history_mod.KIND_ONBOARD,
                {"patient_id": pid},
            )
        return
    if patient_files_mod.is_armed(context.user_data):
        reply = patient_files_mod.append_note(context.user_data, text)
        await message.reply_text(reply)
        if reply.startswith("Note saved"):
            meta = patient_files_mod.last_note_meta(context.user_data)
            if meta and meta.get("id"):
                _safe_emit(
                    _user_id(update),
                    history_mod.KIND_NOTE,
                    {
                        "note_id": meta["id"],
                        "ts": meta.get("created_at"),
                        "patient_id": _patient_id_from_user_data(context.user_data),
                    },
                )
        return
    if scribe_md_mod.is_armed(context.user_data):
        # Priority: onboard > note > scribe armed > generic.
        scribe_md_mod.end_scribe(context.user_data)
        await _run_scribe(message, context, text, user_id=_user_id(update))
        return
    if patient_files_mod.looks_like_diagnose_from_files_or_biometrics(text):
        await message.reply_text(patient_files_mod.MSG_REFUSE_LM)
        return
    if _looks_like_refusal_request(text):
        await message.reply_text(REFUSAL_TEXT)
        return
    await message.reply_text(
        "That message is not a recognised command. Please send /help for the list of commands."
    )


def _user_err(exc: BaseException) -> str:
    msg = str(exc).strip() or type(exc).__name__
    if len(msg) > 500:
        msg = msg[:497] + "..."
    return msg


def _service_fail(exc: BaseException) -> str:
    return (
        f"The remote service could not complete this request. {_user_err(exc)}. "
        "Please try again shortly."
    )


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


async def _post_init(application: Application) -> None:
    stop = asyncio.Event()
    application.bot_data["sorter_stop"] = stop
    application.bot_data["sorter_task"] = asyncio.create_task(
        sorter_mod.run_forever(stop_event=stop),
        name="history_sorter",
    )
    logger.info("history_sorter task scheduled")


async def _post_shutdown(application: Application) -> None:
    stop = application.bot_data.get("sorter_stop")
    task = application.bot_data.get("sorter_task")
    if stop is not None:
        stop.set()
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("history_sorter task stopped")


def main() -> None:
    settings = load_settings()
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(True)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["biohub"] = BiohubClient(settings)
    application.bot_data["boltz"] = BoltzClient(settings)
    store_mod.STORE_ROOT.mkdir(parents=True, exist_ok=True)

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("esm", cmd_esm))
    application.add_handler(CommandHandler("boltz", cmd_boltz))
    application.add_handler(CommandHandler("design", cmd_design))
    application.add_handler(CommandHandler("bind", cmd_bind))
    application.add_handler(CommandHandler("load", cmd_load))
    application.add_handler(CommandHandler("sequence", cmd_sequence))
    application.add_handler(CommandHandler("view", cmd_view))
    application.add_handler(CommandHandler("download", cmd_download))
    application.add_handler(CommandHandler("confirm", cmd_confirm))
    application.add_handler(CommandHandler("cancel", cmd_cancel))
    application.add_handler(CommandHandler("onboard", cmd_onboard))
    application.add_handler(CommandHandler("note", cmd_note))
    application.add_handler(CommandHandler("research", cmd_research))
    application.add_handler(CommandHandler("evidence", cmd_evidence))
    application.add_handler(CommandHandler("scribe", cmd_scribe))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Starting long-polling bot (research-use only)…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
