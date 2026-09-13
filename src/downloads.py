"""Durable artifact stash for /download.

Copies CIF and design CSV into a session directory. Temp render PNGs stay
ephemeral. Durable copies live until /load clear, a new /load, a newer run,
or ~24h TTL.
"""

from __future__ import annotations

import csv
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

SESSION_ROOT = Path(__file__).resolve().parent.parent / "boltz-experiments"
TTL_SEC = 24 * 60 * 60

_CSV_FIELDS = (
    "id",
    "smiles",
    "binding_confidence",
    "optimization_score",
    "structure_confidence",
    "adme_solubility",
    "adme_lipophilicity",
    "adme_permeability",
)


def session_dir(chat_id: int | str) -> Path:
    return SESSION_ROOT / f"session_{chat_id}"


def new_run_dir(chat_id: int | str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = session_dir(chat_id) / f"run_{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def file_record(path: Path, filename: str, kind: str) -> dict[str, str]:
    return {"path": str(path), "filename": filename, "kind": kind}


def copy_cif(
    src: Path | str | None,
    dest_dir: Path,
    filename: str = "result.cif",
) -> dict[str, str] | None:
    if not src:
        return None
    src_path = Path(src)
    if not src_path.exists():
        return None
    dest = dest_dir / filename
    shutil.copy2(src_path, dest)
    return file_record(dest, filename, "cif")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def write_candidates_csv(
    candidates: Sequence[Any],
    dest_dir: Path,
    filename: str = "candidates.csv",
) -> dict[str, str] | None:
    if not candidates:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for cand in candidates:
            row = {field: _get(cand, field, "") for field in _CSV_FIELDS}
            for key in row:
                if row[key] is None:
                    row[key] = ""
            writer.writerow(row)
    return file_record(dest, filename, "design_csv")


def copy_png(
    src: Path | str | None,
    dest_dir: Path,
    filename: str = "result.png",
) -> dict[str, str] | None:
    if not src:
        return None
    src_path = Path(src)
    if not src_path.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.copy2(src_path, dest)
    return file_record(dest, filename, "result_png")


def stash_run_files(
    chat_id: int | str,
    *,
    cif_path: Path | str | None = None,
    cif_name: str = "result.cif",
    candidates: Sequence[Any] | None = None,
    png_path: Path | str | None = None,
) -> tuple[list[dict[str, str]], Path]:
    """Copy artifacts into a new run dir. Always returns (files, dest)."""
    prune_expired(chat_id)
    dest = new_run_dir(chat_id)
    files: list[dict[str, str]] = []
    rec = copy_cif(cif_path, dest, cif_name)
    if rec:
        files.append(rec)
    if candidates:
        csv_rec = write_candidates_csv(candidates, dest)
        if csv_rec:
            files.append(csv_rec)
    png_rec = copy_png(png_path, dest)
    if png_rec:
        files.append(png_rec)
    return files, dest


def read_candidates_csv(path: Path | str) -> list[dict[str, str]]:
    src = Path(path)
    if not src.exists():
        return []
    with src.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def drop_files(files: Sequence[Mapping[str, Any]] | None) -> None:
    """Unlink recorded durable files and empty parent run dirs."""
    parents: set[Path] = set()
    for rec in files or []:
        raw = rec.get("path") if isinstance(rec, Mapping) else None
        if not raw:
            continue
        path = Path(str(raw))
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("could not unlink stashed file %s", path)
        parents.add(path.parent)
    for parent in parents:
        try:
            if parent.exists() and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass


def drop_session(chat_id: int | str) -> None:
    d = session_dir(chat_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def prune_expired(chat_id: int | str | None = None) -> None:
    """Drop run dirs older than TTL. If chat_id is set, only that session."""
    roots = [session_dir(chat_id)] if chat_id is not None else []
    if chat_id is None:
        if not SESSION_ROOT.exists():
            return
        roots = [p for p in SESSION_ROOT.glob("session_*") if p.is_dir()]
    now = time.time()
    for root in roots:
        if not root.exists():
            continue
        for run in list(root.glob("run_*")):
            try:
                if now - run.stat().st_mtime > TTL_SEC:
                    shutil.rmtree(run, ignore_errors=True)
            except OSError:
                continue
        try:
            if root.exists() and root.is_dir() and not any(root.iterdir()):
                root.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    cif = tmp / "in.cif"
    cif.write_text("data_test\n")
    dest = tmp / "run"
    dest.mkdir()
    rec = copy_cif(cif, dest, "esm.cif")
    assert rec and Path(rec["path"]).read_text() == "data_test\n"
    csv_rec = write_candidates_csv(
        [{"smiles": "CCO", "binding_confidence": 0.9, "optimization_score": 0.1}],
        dest,
    )
    assert csv_rec and "CCO" in Path(csv_rec["path"]).read_text()
    drop_files([rec, csv_rec])
    assert not Path(rec["path"]).exists()
    print("downloads self-check passed")
