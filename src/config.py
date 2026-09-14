"""Load and validate environment configuration."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Canonical 20 amino acids + common ambiguous codes used in research sequences.
AMINO_ACID_ALPHABET = set("ACDEFGHIKLMNPQRSTVWYBXZJU")
DEFAULT_MAX_SEQUENCE_LENGTH = 800


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    biohub_api_token: str
    boltz_api_key: str
    telegram_allowed_user_id: int | None
    biohub_url: str
    boltz_base_url: str
    max_sequence_length: int
    commec_bin: str = "commec"
    commec_timeout_sec: int = 60
    # Model names from live docs (Biohub README / Boltz predictions guide).
    esmfold2_model: str = "esmfold2-fast-2026-05"
    esmc_model: str = "esmc-6b-2024-12"
    boltz_model: str = "boltz-2.1"
    # Optional /scribe OpenAI-compatible chat completions (fail-closed if URL unset).
    scribe_llm_url: str = ""
    scribe_llm_key: str = ""
    scribe_llm_model: str = ""


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example to .env and set {name}, then re-run: python -m src.bot"
        )
    return value


def load_settings() -> Settings:
    allowed_raw = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
    allowed_id: int | None = None
    if allowed_raw:
        try:
            allowed_id = int(allowed_raw)
        except ValueError:
            raise SystemExit(
                "TELEGRAM_ALLOWED_USER_ID must be an integer Telegram user id."
            ) from None

    max_len_raw = os.getenv("MAX_SEQUENCE_LENGTH", str(DEFAULT_MAX_SEQUENCE_LENGTH)).strip()
    try:
        max_len = int(max_len_raw)
    except ValueError:
        raise SystemExit("MAX_SEQUENCE_LENGTH must be an integer.") from None
    if max_len < 1:
        raise SystemExit("MAX_SEQUENCE_LENGTH must be >= 1.")

    commec_bin = (os.getenv("COMMEC_BIN") or "commec").strip() or "commec"
    timeout_raw = (os.getenv("COMMEC_TIMEOUT_SEC") or "60").strip()
    try:
        commec_timeout = int(timeout_raw)
    except ValueError:
        raise SystemExit("COMMEC_TIMEOUT_SEC must be an integer.") from None
    if commec_timeout < 1:
        raise SystemExit("COMMEC_TIMEOUT_SEC must be >= 1.")

    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        biohub_api_token=_require("BIOHUB_API_TOKEN"),
        boltz_api_key=_require("BOLTZ_API_KEY"),
        telegram_allowed_user_id=allowed_id,
        biohub_url=os.getenv("BIOHUB_URL", "https://biohub.ai").rstrip("/"),
        boltz_base_url=os.getenv("BOLTZ_BASE_URL", "https://api.boltz.bio").rstrip("/"),
        max_sequence_length=max_len,
        commec_bin=commec_bin,
        commec_timeout_sec=commec_timeout,
        scribe_llm_url=(os.getenv("SCRIBE_LLM_URL") or "").strip(),
        scribe_llm_key=(os.getenv("SCRIBE_LLM_KEY") or "").strip(),
        scribe_llm_model=(os.getenv("SCRIBE_LLM_MODEL") or "").strip(),
    )


def validate_protein_sequence(sequence: str, max_length: int) -> str:
    """Normalize and validate an amino-acid sequence. Raises ValueError with a clear message."""
    seq = "".join(sequence.split()).upper()
    if not seq:
        raise ValueError("The sequence is empty. Please provide a protein amino-acid sequence.")
    if len(seq) > max_length:
        raise ValueError(
            f"Sequence length {len(seq)} exceeds the cap of {max_length} residues. "
            "Shorten the sequence or raise MAX_SEQUENCE_LENGTH if your account allows it."
        )
    bad = sorted({c for c in seq if c not in AMINO_ACID_ALPHABET})
    if bad:
        raise ValueError(
            "The sequence contains invalid amino-acid characters: "
            + ", ".join(repr(c) for c in bad)
            + ". Use standard IUPAC one-letter codes."
        )
    return seq


def validate_smiles(smiles: str) -> str:
    s = smiles.strip()
    if not s:
        raise ValueError("The ligand SMILES string is empty. Please provide a chemical structure in SMILES form.")
    if len(s) > 2000:
        raise ValueError("The ligand SMILES string is too long. The limit is 2000 characters.")
    # Keep validation light; the Boltz API will reject invalid chemistry.
    if any(c.isspace() for c in s):
        raise ValueError("The ligand SMILES string must not contain spaces. Telegram sometimes turns the letter O into the digit 0; please check the string and try again.")
    return s


if __name__ == "__main__":
    # Quick sanity check when developing without Telegram secrets.
    try:
        load_settings()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise
