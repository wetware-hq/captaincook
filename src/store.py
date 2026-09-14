"""Durable per-user / per-patient paths under patient-store/.

Layout:
  patient-store/{telegram_user_id}/
    queue.jsonl
    processed.json
    inbox/
    {patient_id}/
      clinic.md
      lab.ipynb
      search.json
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

# Repo root: .../telegram-biomodel-bot
STORE_ROOT = Path(__file__).resolve().parent.parent / "patient-store"

CLINIC_NAME = "clinic.md"
LAB_NAME = "lab.ipynb"
SEARCH_NAME = "search.json"
QUEUE_NAME = "queue.jsonl"
PROCESSED_NAME = "processed.json"
INBOX_NAME = "inbox"

CLINIC_SKELETON = """\
# Clinic file

Patient record for research-use documentation only. This file is not a legal medical record and is not clinical advice.

Demographics: not on file.

## Notes

## Evidence

## Meeting minutes

## Biosecurity

## General

## Oncology

## Haematology

## Cardiology

## Infectious disease

## Imaging

## Pharmacy
"""

EMPTY_NOTEBOOK: dict[str, Any] = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    "cells": [],
}

EMPTY_SEARCH: dict[str, Any] = {"updated_at": "", "entries": []}


def user_dir(user_id: int | str) -> Path:
    return STORE_ROOT / str(user_id)


def patient_dir(user_id: int | str, patient_id: str) -> Path:
    return user_dir(user_id) / patient_id


def inbox_dir(user_id: int | str) -> Path:
    return user_dir(user_id) / INBOX_NAME


def queue_path(user_id: int | str) -> Path:
    return user_dir(user_id) / QUEUE_NAME


def processed_path(user_id: int | str) -> Path:
    return user_dir(user_id) / PROCESSED_NAME


def clinic_path(user_id: int | str, patient_id: str) -> Path:
    return patient_dir(user_id, patient_id) / CLINIC_NAME


def lab_path(user_id: int | str, patient_id: str) -> Path:
    return patient_dir(user_id, patient_id) / LAB_NAME


def search_path(user_id: int | str, patient_id: str) -> Path:
    return patient_dir(user_id, patient_id) / SEARCH_NAME


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def ensure_user_dirs(user_id: int | str) -> Path:
    root = user_dir(user_id)
    (root / INBOX_NAME).mkdir(parents=True, exist_ok=True)
    if not processed_path(user_id).exists():
        atomic_write_json(processed_path(user_id), {"ids": []})
    if not queue_path(user_id).exists():
        queue_path(user_id).touch()
    return root


def ensure_patient_files(user_id: int | str, patient_id: str) -> Path:
    ensure_user_dirs(user_id)
    pdir = patient_dir(user_id, patient_id)
    pdir.mkdir(parents=True, exist_ok=True)
    cpath = clinic_path(user_id, patient_id)
    if not cpath.exists():
        atomic_write_text(cpath, CLINIC_SKELETON)
    lpath = lab_path(user_id, patient_id)
    if not lpath.exists():
        atomic_write_json(lpath, EMPTY_NOTEBOOK)
    spath = search_path(user_id, patient_id)
    if not spath.exists():
        atomic_write_json(spath, dict(EMPTY_SEARCH))
    return pdir


def new_patient_id() -> str:
    return str(uuid.uuid4())


def load_processed(user_id: int | str) -> set[str]:
    ensure_user_dirs(user_id)
    raw = json.loads(processed_path(user_id).read_text(encoding="utf-8"))
    ids = raw.get("ids") if isinstance(raw, dict) else raw
    if not isinstance(ids, list):
        return set()
    return {str(x) for x in ids}


def mark_processed(user_id: int | str, event_id: str) -> None:
    ensure_user_dirs(user_id)
    ids = load_processed(user_id)
    ids.add(event_id)
    atomic_write_json(processed_path(user_id), {"ids": sorted(ids)})


def list_user_ids() -> list[str]:
    if not STORE_ROOT.exists():
        return []
    return sorted(
        p.name
        for p in STORE_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
