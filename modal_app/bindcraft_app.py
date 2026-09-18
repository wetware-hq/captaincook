"""Skeleton Modal app for BindCraft GPU jobs.

NOT DEPLOYED YET — poller client fail-closes until this is deployed with:

1. GPU image containing BindCraft + AlphaFold2 deps
2. Persistent Modal Volume mounted with AF2 / BindCraft weights
   (NOT clinic.md, secrets, patient_files, Telegram tokens)
3. App name matching poller env MODAL_BINDCRAFT_APP
4. Entrypoint function name: run_bindcraft

Deploy (when ready):
  modal deploy modal_app/bindcraft_app.py

Poller sends only: target_sequence / cif_bytes + optional hotspot + n_designs.
Returns: {designs: [...], run_id, fasta_bytes?, cif_bytes_list?}
"""

from __future__ import annotations

# Placeholder — replace with real Modal Image + Volume when weights exist.
#
# import modal
#
# app = modal.App("bindcraft-gpu")  # ← must match MODAL_BINDCRAFT_APP
#
# weights = modal.Volume.from_name("bindcraft-weights", create_if_missing=False)
#
# bindcraft_image = (
#     modal.Image.debian_slim(python_version="3.11")
#     .apt_install("git", "wget", ...)
#     .pip_install(...)  # BindCraft / AF2 deps
#     # OR: modal.Image.from_registry("your-bindcraft-gpu:tag")
# )
#
# @app.function(
#     image=bindcraft_image,
#     gpu="A100",  # or L40S / H100 as available
#     timeout=3600,
#     volumes={"/weights": weights},
#     secrets=[],  # no Telegram / clinic / patient secrets
# )
# def run_bindcraft(payload: dict) -> dict:
#     """Run BindCraft on target CIF/seq. Never invent binders.
#
#     payload keys allowed: target_sequence, cif_bytes, cif_name, hotspot, n_designs
#     """
#     # 1. Write cif_bytes to scratch
#     # 2. Invoke BindCraft CLI with /weights params
#     # 3. Collect ranked designs + FASTA/CIF bytes
#     # 4. Return dict — empty designs = failure (poller refuse)
#     raise NotImplementedError("BindCraft Modal runner not wired")
#
# @app.local_entrypoint()
# def main():
#     print("Deploy with: modal deploy modal_app/bindcraft_app.py")

APP_NAME = "bindcraft-gpu"  # default; override via MODAL_BINDCRAFT_APP on poller
FUNCTION_NAME = "run_bindcraft"
REQUIRED_VOLUME = "bindcraft-weights"  # AF2 / BindCraft params only
REQUIRED_GPU = "A100"  # document intent; adjust at deploy

# Explicit non-goals (must stay off this app / volume):
FORBIDDEN_ON_MODAL = (
    "clinic.md",
    "lab.ipynb",
    "patient_files",
    "biometrics",
    "TELEGRAM_BOT_TOKEN",
    "BIOHUB_API_TOKEN",
    "notes / scribe",
)
