"""Modal BindCraft GPU app — compute only.

Deploy:
  modal deploy modal_app/bindcraft_app.py

Poller env:
  MODAL_BINDCRAFT_APP=bindcraft-gpu

Entrypoint: run_bindcraft(payload) → {designs, run_id, fasta_bytes, cif_bytes_list}

Fail-closed: missing AF2/BindCraft weights, missing structure, BindCraft crash,
or zero accepted designs after filters → raise (never empty-as-success; never invent).

No clinic.md / patient_files / Telegram / biometrics on this app or volume.
"""

from __future__ import annotations

import modal

APP_NAME = "bindcraft-gpu"
FUNCTION_NAME = "run_bindcraft"
REQUIRED_VOLUME = "bindcraft-weights"
REQUIRED_GPU = "A100"  # L40S / A10G also fine; adjust if quota blocks
BINDCRAFT_ROOT = "/opt/bindcraft"
WEIGHTS_ROOT = "/weights"
WEIGHTS_PARAMS = "/weights/params"

FORBIDDEN_ON_MODAL = (
    "clinic.md",
    "lab.ipynb",
    "patient_files",
    "biometrics",
    "TELEGRAM_BOT_TOKEN",
    "BIOHUB_API_TOKEN",
    "notes / scribe",
)

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "clinic",
        "clinic_md",
        "biometrics",
        "patient_files",
        "patient_id",
        "telegram_bot_token",
        "telegram_token",
        "note",
        "note_body",
        "notes",
        "age_years",
        "sex",
        "weight_kg",
        "height_cm",
        "bmi",
        "scribe",
        "inbox",
        "secrets",
        "biohub_api_token",
        "boltz_api_key",
    }
)


def _install_pyrosetta() -> None:
    """Bake PyRosetta into the image (academic quarterly wheels)."""
    import pyrosetta_installer

    pyrosetta_installer.install_pyrosetta()


app = modal.App(APP_NAME)

weights = modal.Volume.from_name(REQUIRED_VOLUME, create_if_missing=True)

# BindCraft + ColabDesign + PyRosetta. AF2 params (~5.3GB) live on the volume
# (not baked into the image) so deploy stays feasible; populate via
# populate_weights once after deploy.
bindcraft_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "git",
        "wget",
        "aria2",
        "tar",
        "ffmpeg",
        "libgfortran5",
        "libgomp1",
    )
    .pip_install("numpy<2.0", "pandas", "matplotlib==3.8.1")
    .pip_install(
        "biopython",
        "scipy",
        "seaborn",
        "tqdm",
        "joblib",
        "ml-collections",
        "immutabledict",
        "optax",
        "chex<0.1.90",  # jax<=0.6 compatible
        "dm-haiku",
        "dm-tree",
        "flax<0.10.0",
        "pdb-tools",
        "pyrosetta-installer",
    )
    .pip_install("git+https://github.com/sokrypton/ColabDesign.git")
    .run_commands(
        f"git clone --depth 1 https://github.com/martinpacesa/BindCraft {BINDCRAFT_ROOT}",
        f"chmod +x {BINDCRAFT_ROOT}/functions/dssp "
        f"{BINDCRAFT_ROOT}/functions/DAlphaBall.gcc || true",
        f"mkdir -p {BINDCRAFT_ROOT}/params",
    )
    .run_function(_install_pyrosetta)
    .pip_install(
        "numpy<2.0",
        "jax[cuda12]<0.7.0",
        "matplotlib==3.8.1",
        extra_options=(
            "--find-links https://storage.googleapis.com/jax-releases/jax_cuda_releases.html"
        ),
    )
)


def _weights_present(root: str = WEIGHTS_ROOT) -> bool:
    """True if AF2 / BindCraft param markers exist on the mounted volume."""
    from pathlib import Path

    base = Path(root)
    markers = (
        base / "params",
        base / "alphafold_params",
        base / "AF2_params",
        base / "bindcraft" / "params",
        base / "params" / "params_model_1.npz",
        base / "params" / "params_model_1_ptm.npz",
    )
    for m in markers:
        if m.is_file():
            return True
        if m.is_dir() and any(m.iterdir()):
            return True
    return False


def _assert_payload_clean(payload: dict) -> None:
    for k in payload:
        lk = str(k).lower()
        if lk in _FORBIDDEN_PAYLOAD_KEYS or str(k) in _FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError(f"Forbidden key in Modal payload: {k}")


def _ensure_params_symlink() -> None:
    """Point BindCraft's params dir at the volume (af_params_dir parent)."""
    import os
    from pathlib import Path

    link = Path(BINDCRAFT_ROOT) / "params"
    target = Path(WEIGHTS_PARAMS)
    if not target.is_dir() or not any(target.iterdir()):
        raise RuntimeError(
            f"AF2 params missing under {WEIGHTS_PARAMS}. "
            "Run populate_weights once. No binder design was started."
        )
    if link.is_symlink() or link.exists():
        if link.is_symlink() and os.path.realpath(link) == os.path.realpath(target):
            return
        if link.is_dir() and not link.is_symlink():
            # Replace empty image placeholder with volume link.
            if not any(link.iterdir()):
                link.rmdir()
            else:
                # Prefer volume; rename local aside.
                link.rename(Path(BINDCRAFT_ROOT) / "params.image.bak")
        elif link.is_symlink():
            link.unlink()
        else:
            link.unlink()
    link.symlink_to(target)


def _hotspot_to_str(hotspot) -> str | None:
    """Pass-through hotspot string; never invent residues."""
    if hotspot is None:
        return None
    if isinstance(hotspot, str):
        s = hotspot.strip()
        return s or None
    if isinstance(hotspot, (list, tuple)):
        parts = [str(h).strip() for h in hotspot if str(h).strip()]
        return ",".join(parts) if parts else None
    return str(hotspot).strip() or None


def _structure_to_pdb(work: "Path", payload: dict) -> "Path":
    """Write starting_pdb. BindCraft requires PDB; convert mmCIF when needed."""
    from pathlib import Path

    cif_bytes = payload.get("cif_bytes")
    cif_name = str(payload.get("cif_name") or "target.cif")
    pdb_bytes = payload.get("pdb_bytes")

    out = work / "target.pdb"

    if pdb_bytes is not None:
        raw = pdb_bytes if isinstance(pdb_bytes, (bytes, bytearray)) else str(pdb_bytes).encode()
        out.write_bytes(bytes(raw))
        return out

    if cif_bytes is None:
        raise RuntimeError(
            "BindCraft requires a target structure (cif_bytes or pdb_bytes). "
            "No binder design was started."
        )

    raw = cif_bytes if isinstance(cif_bytes, (bytes, bytearray)) else str(cif_bytes).encode()
    name_lower = cif_name.lower()
    # Already PDB content mislabeled, or explicit .pdb
    head = bytes(raw[:64]).decode("utf-8", errors="ignore")
    if name_lower.endswith(".pdb") or head.lstrip().startswith(("ATOM", "HETATM", "HEADER", "MODEL", "REMARK")):
        out.write_bytes(bytes(raw))
        return out

    cif_path = work / (cif_name if name_lower.endswith(".cif") else "target.cif")
    cif_path.write_bytes(bytes(raw))
    try:
        from Bio.PDB import MMCIFParser, PDBIO
    except ImportError as exc:
        raise RuntimeError(
            "biopython missing in BindCraft image; cannot convert CIF→PDB. "
            "No binder design was started."
        ) from exc

    parser = MMCIFParser(QUIET=True)
    structure = parser.get_structure("target", str(cif_path))
    io = PDBIO()
    io.set_structure(structure)
    io.save(str(out))
    if not out.is_file() or out.stat().st_size < 64:
        raise RuntimeError(
            "CIF→PDB conversion produced an empty structure. "
            "No binder design was started."
        )
    return out


def _detect_chains(pdb_path: "Path") -> str:
    chains: list[str] = []
    seen: set[str] = set()
    for line in pdb_path.read_text(errors="ignore").splitlines():
        if line.startswith(("ATOM", "HETATM")) and len(line) >= 22:
            ch = line[21].strip() or "A"
            if ch not in seen:
                seen.add(ch)
                chains.append(ch)
    return ",".join(chains) if chains else "A"


def _pdb_to_cif_bytes(pdb_path: "Path") -> bytes:
    from Bio.PDB import MMCIFIO, PDBParser

    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("binder", str(pdb_path))
    import io as _io

    buf = _io.StringIO()
    writer = MMCIFIO()
    writer.set_structure(structure)
    writer.save(buf)
    return buf.getvalue().encode("utf-8")


def _collect_designs(design_path: "Path", run_id: str) -> dict:
    """Read Accepted/Ranked (or Accepted) PDBs + stats. Empty → caller fails closed."""
    from pathlib import Path

    import pandas as pd

    ranked = design_path / "Accepted" / "Ranked"
    accepted = design_path / "Accepted"
    pdb_files: list[Path] = []
    if ranked.is_dir():
        pdb_files = sorted(ranked.glob("*.pdb"))
    if not pdb_files and accepted.is_dir():
        pdb_files = sorted(
            p for p in accepted.glob("*.pdb") if p.is_file() and not p.name.startswith(".")
        )

    # Sequence / scores from final or mpnn CSV
    seq_by_design: dict[str, dict] = {}
    for csv_name in ("final_design_stats.csv", "mpnn_design_stats.csv"):
        csv_path = design_path / csv_name
        if not csv_path.is_file():
            continue
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue
        if "Design" not in df.columns or "Sequence" not in df.columns:
            continue
        for _, row in df.iterrows():
            name = str(row["Design"])
            seq = str(row["Sequence"]).strip().upper()
            if not seq or name in seq_by_design:
                continue
            entry = {"name": name, "sequence": seq}
            for key in (
                "Average_i_pTM",
                "Average_pLDDT",
                "Average_pTM",
                "Average_i_pAE",
                "Rank",
                "MPNN_score",
            ):
                if key in df.columns and pd.notna(row.get(key)):
                    try:
                        entry[key.lower().replace("average_", "")] = float(row[key])
                    except (TypeError, ValueError):
                        entry[key] = row[key]
            seq_by_design[name] = entry
        if seq_by_design:
            break

    designs: list[dict] = []
    cif_bytes_list: list[bytes] = []
    fasta_parts: list[str] = []

    for i, pdb in enumerate(pdb_files):
        stem = pdb.stem
        # Ranked names: "{rank}_{design}_model{N}"
        design_key = stem
        meta = None
        for k, v in seq_by_design.items():
            if k in stem or stem.startswith(k) or k in design_key:
                meta = dict(v)
                break
        if meta is None:
            # Try stripping rank prefix and _model suffix
            body = stem
            if "_" in body and body.split("_", 1)[0].isdigit():
                body = body.split("_", 1)[1]
            if "_model" in body:
                body = body.rsplit("_model", 1)[0]
            meta = dict(seq_by_design.get(body) or {})
            if not meta.get("sequence"):
                # Last resort: refuse inventing — skip file without known sequence
                continue
            meta.setdefault("name", body)

        seq = str(meta.get("sequence") or "").strip().upper()
        if not seq or any(c not in "ACDEFGHIKLMNPQRSTVWY" for c in seq):
            continue

        try:
            cif_blob = _pdb_to_cif_bytes(pdb)
        except Exception:
            # Fall back to PDB bytes still as structure artifact (labeled cif key
            # for poller sync); prefer real conversion.
            cif_blob = pdb.read_bytes()

        rank = i + 1
        designs.append(
            {
                "name": meta.get("name") or stem,
                "sequence": seq,
                "rank": int(meta.get("rank") or rank),
                "i_ptm": meta.get("i_ptm"),
                "plddt": meta.get("plddt"),
                "ptm": meta.get("ptm"),
                "source_pdb": pdb.name,
            }
        )
        cif_bytes_list.append(cif_blob)
        fasta_parts.append(f">binder_{run_id}_{rank} {meta.get('name') or stem}\n{seq}\n")

    fasta_bytes = "".join(fasta_parts).encode("utf-8") if fasta_parts else None
    return {
        "designs": designs,
        "run_id": run_id,
        "fasta_bytes": fasta_bytes,
        "cif_bytes_list": cif_bytes_list,
    }


def _run_bindcraft_pipeline(payload: dict) -> dict:
    """Prepare inputs, invoke upstream bindcraft.py, collect filter-passing designs."""
    import json
    import shutil
    import subprocess
    import uuid
    from pathlib import Path

    n_designs = int(payload.get("n_designs") or 5)
    if n_designs < 1:
        raise ValueError("n_designs must be >= 1")
    n_designs = min(n_designs, 20)

    run_id = uuid.uuid4().hex[:12]
    work = Path(f"/tmp/bindcraft_runs/{run_id}")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    design_path = work / "out"
    design_path.mkdir(parents=True, exist_ok=True)

    _ensure_params_symlink()

    pdb_path = _structure_to_pdb(work, payload)
    chains = str(payload.get("chains") or "").strip() or _detect_chains(pdb_path)
    hotspot = _hotspot_to_str(payload.get("hotspot"))
    lengths = payload.get("lengths") or [65, 150]
    if isinstance(lengths, str):
        lengths = [int(x) for x in lengths.split(",")]
    lengths = [int(lengths[0]), int(lengths[-1] if len(lengths) > 1 else lengths[0])]

    # Cap trajectories so Modal timeout can finish; still fail-closed if zero accept.
    max_traj = payload.get("max_trajectories")
    if max_traj is None:
        max_traj = max(n_designs * 50, 25)
    else:
        max_traj = int(max_traj)

    settings = {
        "design_path": str(design_path),
        "binder_name": f"cc_{run_id}",
        "starting_pdb": str(pdb_path),
        "chains": chains,
        "target_hotspot_residues": hotspot,
        "lengths": lengths,
        "number_of_final_designs": n_designs,
    }
    settings_path = work / "target_settings.json"
    settings_path.write_text(json.dumps(settings, indent=2))

    # Default filters (BindCraft v1 lock — no Boltz re-score).
    filters_path = Path(BINDCRAFT_ROOT) / "settings_filters" / "default_filters.json"
    if not filters_path.is_file():
        raise RuntimeError(
            f"BindCraft default_filters.json missing at {filters_path}. "
            "No binder design was started."
        )

    advanced_src = (
        Path(BINDCRAFT_ROOT) / "settings_advanced" / "default_4stage_multimer.json"
    )
    if not advanced_src.is_file():
        raise RuntimeError(
            f"BindCraft advanced settings missing at {advanced_src}. "
            "No binder design was started."
        )
    advanced = json.loads(advanced_src.read_text())
    # Parent of params/ — ColabDesign loads {af_params_dir}/params/*.npz
    advanced["af_params_dir"] = BINDCRAFT_ROOT
    advanced["dssp_path"] = str(Path(BINDCRAFT_ROOT) / "functions" / "dssp")
    advanced["dalphaball_path"] = str(
        Path(BINDCRAFT_ROOT) / "functions" / "DAlphaBall.gcc"
    )
    advanced["max_trajectories"] = max_traj
    # Disable early acceptance-rate abort for small N smokes
    advanced["enable_rejection_check"] = bool(payload.get("enable_rejection_check", False))
    advanced_path = work / "advanced_settings.json"
    advanced_path.write_text(json.dumps(advanced, indent=2))

    bindcraft_py = Path(BINDCRAFT_ROOT) / "bindcraft.py"
    if not bindcraft_py.is_file():
        raise RuntimeError(
            "BindCraft install missing in image (bindcraft.py). "
            "No binder design was started."
        )

    import os as _os

    env = {**_os.environ, "PYTHONUNBUFFERED": "1"}
    # Ensure `from functions import *` resolves
    cmd = [
        "python",
        "-u",
        str(bindcraft_py),
        "--settings",
        str(settings_path),
        "--filters",
        str(filters_path),
        "--advanced",
        str(advanced_path),
    ]
    proc = subprocess.run(
        cmd,
        cwd=BINDCRAFT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    # Keep tails for debugging without dumping secrets (none expected).
    log_tail = (proc.stdout or "")[-4000:] + "\n" + (proc.stderr or "")[-2000:]
    (work / "bindcraft_stdout.log").write_text(proc.stdout or "")
    (work / "bindcraft_stderr.log").write_text(proc.stderr or "")

    if proc.returncode != 0:
        raise RuntimeError(
            "BindCraft process failed "
            f"(exit={proc.returncode}). No binder designs returned. "
            f"Log tail:\n{log_tail[-1500:]}"
        )

    result = _collect_designs(design_path, run_id)
    if not result["designs"]:
        # Fail-closed: never treat empty as success / never invent sequences.
        traj_n = 0
        traj_dir = design_path / "Trajectory" / "Relaxed"
        if traj_dir.is_dir():
            traj_n = len(list(traj_dir.glob("*.pdb")))
        raise RuntimeError(
            "BindCraft finished but zero designs passed default filters "
            f"(trajectories_relaxed≈{traj_n}, max_trajectories={max_traj}, "
            f"n_designs={n_designs}). No binder design was returned "
            "(fail-closed; no invented binders)."
        )
    return result


@app.function(
    image=bindcraft_image,
    gpu=REQUIRED_GPU,
    timeout=10800,  # 3h — BindCraft trajectories are slow; still fail-closed
    volumes={WEIGHTS_ROOT: weights},
    secrets=[],  # no Telegram / clinic / patient secrets
    memory=65536,
)
def run_bindcraft(payload: dict) -> dict:
    """Run BindCraft on target CIF/PDB. Never invent binders.

    payload keys allowed: target_sequence, cif_bytes, cif_name, pdb_bytes,
    hotspot, n_designs, chains, lengths, max_trajectories
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    _assert_payload_clean(payload)

    if not _weights_present(WEIGHTS_ROOT):
        raise RuntimeError(
            "BindCraft weights missing on Modal volume "
            f"'{REQUIRED_VOLUME}' (expected AF2 params under {WEIGHTS_PARAMS}). "
            "Run populate_weights once, then retry. No binder design was started."
        )

    bindcraft_root = __import__("pathlib").Path(BINDCRAFT_ROOT)
    if not bindcraft_root.is_dir():
        raise RuntimeError(
            "BindCraft install missing in image. No binder design was started."
        )

    return _run_bindcraft_pipeline(payload)


@app.function(
    image=bindcraft_image,
    gpu=REQUIRED_GPU,
    timeout=600,
    volumes={WEIGHTS_ROOT: weights},
    secrets=[],
)
def probe_bindcraft() -> dict:
    """Dry-run: imports + weights + GPU. Does not invent binders or start design."""
    import importlib
    from pathlib import Path

    out: dict = {"ok": False, "weights": False, "imports": {}, "gpu": None, "errors": []}
    out["weights"] = _weights_present(WEIGHTS_ROOT)
    try:
        _ensure_params_symlink()
        out["params_link"] = str((Path(BINDCRAFT_ROOT) / "params").resolve())
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"params_link: {type(exc).__name__}: {exc}")

    for mod in ("colabdesign", "pyrosetta", "jax", "Bio", "pandas"):
        try:
            importlib.import_module(mod)
            out["imports"][mod] = True
        except Exception as exc:  # noqa: BLE001
            out["imports"][mod] = False
            out["errors"].append(f"import {mod}: {type(exc).__name__}: {exc}")

    try:
        import jax

        devices = [str(d) for d in jax.devices()]
        out["gpu"] = devices
        out["has_gpu"] = any("gpu" in d.lower() or "cuda" in d.lower() for d in devices)
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"jax: {type(exc).__name__}: {exc}")
        out["has_gpu"] = False

    out["bindcraft_py"] = (Path(BINDCRAFT_ROOT) / "bindcraft.py").is_file()
    out["default_filters"] = (
        Path(BINDCRAFT_ROOT) / "settings_filters" / "default_filters.json"
    ).is_file()
    out["ok"] = bool(
        out["weights"]
        and out["bindcraft_py"]
        and out["default_filters"]
        and out["imports"].get("colabdesign")
        and out["imports"].get("pyrosetta")
        and out["imports"].get("jax")
        and out.get("has_gpu")
        and not out["errors"]
    )
    return out


@app.function(
    image=bindcraft_image,
    timeout=3600,
    volumes={WEIGHTS_ROOT: weights},
)
def populate_weights() -> dict:
    """Download AF2 params (~5.3GB) into bindcraft-weights volume. Idempotent."""
    import subprocess
    from pathlib import Path

    dest = Path(WEIGHTS_PARAMS)
    dest.mkdir(parents=True, exist_ok=True)
    if _weights_present(WEIGHTS_ROOT):
        weights.commit()
        return {"status": "already_present", "path": str(dest)}

    tar_path = Path("/tmp/alphafold_params_2022-12-06.tar")
    url = "https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar"
    subprocess.check_call(
        ["aria2c", "-q", "-x", "16", "-d", "/tmp", "-o", tar_path.name, url]
    )
    subprocess.check_call(["tar", "-xf", str(tar_path), "-C", str(dest)])
    tar_path.unlink(missing_ok=True)
    weights.commit()
    if not _weights_present(WEIGHTS_ROOT):
        raise RuntimeError("AF2 weight download finished but markers not found")
    return {"status": "downloaded", "path": str(dest)}


@app.local_entrypoint()
def main():
    print(f"App={APP_NAME} fn={FUNCTION_NAME} volume={REQUIRED_VOLUME} gpu={REQUIRED_GPU}")
    print("Deploy: modal deploy modal_app/bindcraft_app.py")
    print("Probe:  modal run modal_app/bindcraft_app.py::probe_bindcraft")
    print("Weights: modal run modal_app/bindcraft_app.py::populate_weights")
