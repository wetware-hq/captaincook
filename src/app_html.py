"""Static HTML live view for /app — clinic.md Clinical + lab.ipynb Laboratory.

Visual lock (editor): white canvas, one column ≤42rem, serif body (Source Serif /
Georgia), sans for nav/chrome only. Vega-Lite only for non-secret vitals
(hr, spo2, temp_c, glucose_mmol). No secrets, no note bodies, no Cook art,
no dark mode, no patient photo chrome.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import board_md as board_md_mod
from . import measure as measure_mod
from . import onboard as onboard_mod
from . import patient_files as patient_files_mod
from . import store
from .context_card import load_card

CHART_KEYS = ("hr", "spo2", "temp_c", "glucose_mmol")
NONE_YET = "None yet."
MAX_STRUCTURE_VIEWERS = 3
MAX_CIF_BYTES = 25 * 1024 * 1024
MOLSTAR_CDN = "https://cdn.jsdelivr.net/npm/molstar@4.18.0/build/viewer"
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SECRETISH = re.compile(
    r"(?i)\b(age_years|weight_kg|height_cm|bmi|patient_id|secret)\b|"
    r"\b\d{1,3}\s*(?:kg|cm)\b"
)


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _section_body(md: str, header: str) -> str:
    matches = list(_SECTION_RE.finditer(md or ""))
    for i, m in enumerate(matches):
        if m.group(1).strip() == header:
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
            return (md[start:end] or "").strip()
    return ""


def _nonempty_section(body: str) -> bool:
    stripped = (body or "").strip()
    if not stripped or stripped in ("_", "-", "None.", "None", NONE_YET):
        return False
    return True



def _trim_claims_and_harvard(md: str, *, max_claims: int = 3) -> str:
    """Style guide: ≤3 claim→cite bullets + Harvard list; else None yet."""
    if not _nonempty_section(md):
        return ""
    lines = (md or "").splitlines()
    claims: list[str] = []
    harvard: list[str] = []
    other: list[str] = []
    in_refs = False
    for line in lines:
        low = line.strip().lower()
        if low.startswith("#### references") or low.startswith("## references") or low == "references":
            in_refs = True
            harvard.append(line)
            continue
        if in_refs:
            if line.strip():
                harvard.append(line)
            continue
        if re.match(r"^\s*[-*]\s+", line):
            if len(claims) < max_claims:
                claims.append(line)
            continue
        if line.startswith("### ") or line.startswith("#### "):
            # Keep a single heading if present before claims
            if not claims and not other:
                other.append(line)
            continue
        # Skip long prose dumps; one short intro sentence max later
        # Style lock: no paragraph intros — bullets + Harvard only
        continue
    if not claims and not harvard and not other:
        # Fallback: first max_claims bullets anywhere, else first 3 non-empty lines
        bullets = [ln for ln in lines if re.match(r"^\s*[-*]\s+", ln)]
        if bullets:
            claims = bullets[:max_claims]
        else:
            prose = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
            other = prose[:1]
    out: list[str] = []
    # Keep only heading lines from other (###), never prose intros
    out.extend([ln for ln in other if ln.lstrip().startswith("#")][:1])
    out.extend(claims[:max_claims])
    if harvard:
        out.append("")
        out.extend(harvard)
    return "\n".join(out).strip()


def _md_to_safe_html(md: str) -> str:
    """Minimal Markdown→HTML for Harvard lists; never promote tone."""
    if not _nonempty_section(md):
        return f"<p class=\"empty\">{_esc(NONE_YET)}</p>"
    lines = (md or "").splitlines()
    parts: list[str] = []
    in_ul = False
    for line in lines:
        # Strip paths that look like local artifact dumps with secrets-ish keys
        if _SECRETISH.search(line) and ("age" in line.lower() or "weight" in line.lower() or "height" in line.lower()):
            continue
        if line.startswith("### "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append(f"<h3>{_esc(line[4:].strip())}</h3>")
            continue
        if line.startswith("#### "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append(f"<h4>{_esc(line[5:].strip())}</h4>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            item = re.sub(r"^\s*[-*]\s+", "", line)
            parts.append(f"<li>{_esc(item)}</li>")
            continue
        if not line.strip():
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            continue
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        parts.append(f"<p>{_esc(line.strip())}</p>")
    if in_ul:
        parts.append("</ul>")
    return "\n".join(parts) if parts else f"<p class=\"empty\">{_esc(NONE_YET)}</p>"


def _read_clinic(user_id: int | str | None, patient_id: str | None) -> str:
    if user_id is None or not patient_id:
        return ""
    path = store.clinic_path(user_id, patient_id)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_lab_cells(user_id: int | str | None, patient_id: str | None) -> list[dict[str, Any]]:
    if user_id is None or not patient_id:
        return []
    path = store.lab_path(user_id, patient_id)
    if not path.is_file():
        return []
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    cells = nb.get("cells") or []
    return [c for c in cells if isinstance(c, dict)]


def _cell_text(cell: dict[str, Any]) -> str:
    src = cell.get("source") or []
    if isinstance(src, list):
        return "".join(str(x) for x in src)
    return str(src)


def _cell_tags(cell: dict[str, Any]) -> list[str]:
    return [str(t) for t in (cell.get("metadata") or {}).get("tags") or []]


def _is_preprint_cell(cell: dict[str, Any]) -> bool:
    tags = [t.lower() for t in _cell_tags(cell)]
    if any("literature-preprint" in t or t.startswith("research") for t in tags):
        return True
    text = _cell_text(cell).lower()
    return "preprint" in text and ("literature" in text or "research" in text or "biorxiv" in text or "medrxiv" in text)


def _is_design_cell(cell: dict[str, Any]) -> bool:
    for tag in _cell_tags(cell):
        if board_md_mod._DESIGN_TAG_RE.match(tag.strip()):
            return True
    text = _cell_text(cell).lower()
    return "ligand" in text or "binder" in text or "protein-binder" in text or "small-molecule" in text


def _redact_lab_text(text: str) -> str:
    """Keep design summaries; drop local filesystem paths (CIF/FASTA via download only)."""
    lines = []
    for line in (text or "").splitlines():
        if re.search(r"(?i)(/tmp/|/workspace/|patient-store/|\.cif|\.fasta)\b", line):
            # Replace path lines with download hint, not secret values
            if "artifact" in line.lower() or line.strip().startswith("-"):
                lines.append("- Structure available via /download; interactive Mol* viewer when /app live view is deployed.")
                continue
            continue
        if _SECRETISH.search(line) and any(
            k in line.lower() for k in ("age", "weight", "height", "bmi", "patient_id")
        ):
            continue
        lines.append(line)
    return "\n".join(lines).strip()



def collect_structure_assets(user_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Existing mmCIF paths from last_run for live Mol* viewers (max 3).

    Returns [{label, path: Path, format: "mmcif"}, ...] for files that still exist.
    Local paths are never written into HTML — callers upload bytes and pass public URLs.
    """
    out: list[dict[str, Any]] = []
    if not user_data:
        return out
    card = load_card(user_data)
    if card is None or not isinstance(card.last_run, dict):
        return out
    files = card.last_run.get("files") or []
    seen: set[str] = set()
    for rec in files:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("kind") or "").lower().strip()
        name = str(rec.get("name") or "")
        raw_path = str(rec.get("path") or "")
        is_cif = kind in ("cif", "mmcif", "structure_cif") or (
            not kind and (name.lower().endswith(".cif") or raw_path.lower().endswith(".cif"))
        )
        if not is_cif:
            continue
        path = Path(raw_path)
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= 0 or size > MAX_CIF_BYTES:
            continue
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        label = name or path.name
        out.append({"label": label, "path": path, "format": "mmcif"})
        if len(out) >= MAX_STRUCTURE_VIEWERS:
            break
    return out


def clinical_blocks(
    user_data: dict[str, Any] | None,
    *,
    user_id: int | str | None,
) -> dict[str, str]:
    """Peer-reviewed Evidence + minutes + note stubs from clinic.md / board projection."""
    patient_id = board_md_mod._peek_patient_id(user_data) if user_data else None
    clinic = _read_clinic(user_id, patient_id)
    evidence = board_md_mod._evidence_from_last_run(load_card(user_data) if user_data else None)
    if not evidence:
        evidence = board_md_mod._evidence_from_clinic(user_id, patient_id)
    minutes = _section_body(clinic, "Meeting minutes") if clinic else ""
    files_n = board_md_mod.patient_files_count(user_data)
    notes_line = (
        f"Patient files: {files_n} on file (contents not shown)."
        if files_n
        else NONE_YET
    )
    return {
        "evidence": evidence or "",
        "minutes": minutes if _nonempty_section(minutes) else "",
        "notes": notes_line,
    }


def laboratory_blocks(
    user_data: dict[str, Any] | None,
    *,
    user_id: int | str | None,
) -> dict[str, str]:
    """Preprint research + design summaries from lab.ipynb (tone fence: never peer-reviewed voice)."""
    patient_id = board_md_mod._peek_patient_id(user_data) if user_data else None
    cells = _read_lab_cells(user_id, patient_id)
    preprint_parts: list[str] = []
    design_parts: list[str] = []
    for cell in cells:
        text = _redact_lab_text(_cell_text(cell))
        if not text.strip():
            continue
        if _is_preprint_cell(cell):
            # Explicit preprint label — no peer-reviewed upgrade
            if "preprint" not in text.lower()[:200]:
                text = "Preprint literature (not peer-reviewed):\n\n" + text
            preprint_parts.append(text)
        elif _is_design_cell(cell):
            design_parts.append(text)
    # Also surface board design ids if lab empty of prose
    designs = board_md_mod.collect_designs(user_data, user_id=user_id, patient_id=patient_id)
    if designs and not design_parts:
        design_parts.append(
            "\n".join(
                f"- `{mode}:{did}` — {board_md_mod.LAB_RESEARCH_LINE}"
                for mode, did in designs
            )
        )
    return {
        "preprints": "\n\n".join(preprint_parts),
        "designs": "\n\n".join(design_parts),
    }


def chart_series(user_data: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """Non-secret time-series for CHART_KEYS only — never secret values."""
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in CHART_KEYS}
    if not user_data:
        return out
    for m in measure_mod.get_measurements(user_data):
        if m.get("secret"):
            continue
        key = str(m.get("key") or "")
        if key not in CHART_KEYS:
            continue
        val = m.get("value")
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        ts = str(m.get("ts") or "")
        if not ts:
            continue
        out[key].append({"t": ts, "v": num})
    for key in CHART_KEYS:
        out[key].sort(key=lambda r: r["t"])
    return out


def case_context_html(user_data: dict[str, Any] | None) -> str:
    card = load_card(user_data) if user_data else None
    biometrics = board_md_mod.biometrics_label(user_data)
    files_n = board_md_mod.patient_files_count(user_data)
    items = [
        f"<li>Intent: {_esc(board_md_mod._intent_line(card))}</li>",
        f"<li>Gene / variant: {_esc(board_md_mod._gene_variant_line(card))}</li>",
        f"<li>Patient biometrics: {_esc(biometrics)}</li>",
        f"<li>Patient files: {files_n} on file (contents not shown)</li>",
    ]
    return "<ul>\n" + "\n".join(items) + "\n</ul>"


def _vega_spec(key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    unit = measure_mod._DEFAULT_UNITS.get(key, "")
    title = f"{key}" + (f" ({unit})" if unit else "")
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": board_md_mod.FIGURE_CAPTION.format(key=key),
        "width": "container",
        "height": 160,
        "data": {"values": rows},
        "mark": {"type": "line", "strokeWidth": 1.5, "color": "#5b7c99", "point": False},
        "encoding": {
            "x": {
                "field": "t",
                "type": "temporal",
                "axis": {"title": None, "grid": False, "labelColor": "#666", "tickColor": "#ccc"},
            },
            "y": {
                "field": "v",
                "type": "quantitative",
                "axis": {"title": title, "grid": True, "gridColor": "#eee", "labelColor": "#666"},
            },
        },
        "config": {
            "view": {"stroke": "transparent"},
            "axis": {"domainColor": "#ccc"},
            "legend": {"disable": True},
        },
    }


def _charts_html(series: dict[str, list[dict[str, Any]]]) -> str:
    blocks: list[str] = []
    any_data = False
    for key in CHART_KEYS:
        rows = series.get(key) or []
        if not rows:
            blocks.append(
                f'<figure class="chart empty-chart" data-key="{_esc(key)}">'
                f"<figcaption>{_esc(board_md_mod.FIGURE_CAPTION.format(key=key))}</figcaption>"
                f'<p class="empty">{_esc(NONE_YET)}</p></figure>'
            )
            continue
        any_data = True
        spec = _vega_spec(key, rows)
        spec_json = json.dumps(spec, separators=(",", ":"))
        blocks.append(
            f'<figure class="chart" data-key="{_esc(key)}">'
            f'<div class="vega" data-spec="{_esc(spec_json)}"></div>'
            f"<figcaption>{_esc(board_md_mod.FIGURE_CAPTION.format(key=key))}</figcaption>"
            f"</figure>"
        )
    if not any_data and all(not (series.get(k) or []) for k in CHART_KEYS):
        return f'<p class="empty">{_esc(NONE_YET)}</p>\n' + "\n".join(blocks)
    return "\n".join(blocks)


def render_app_html(
    user_data: dict[str, Any] | None,
    *,
    user_id: int | str | None = None,
    expires_at: datetime | None = None,
    mol_viewers: list[dict[str, Any]] | None = None,
) -> str:
    """Build static HTML+JS artifact. Never embeds secret measure or biometric values.

    mol_viewers: optional [{id, label, url, format}] with public HTTPS CIF URLs (mmcif).
    """
    clin = clinical_blocks(user_data, user_id=user_id)
    lab = laboratory_blocks(user_data, user_id=user_id)
    series = chart_series(user_data)
    expires_iso = ""
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        expires_iso = expires_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    evidence_html = _md_to_safe_html(_trim_claims_and_harvard(clin["evidence"]))
    minutes_html = (
        _md_to_safe_html(_trim_claims_and_harvard(clin["minutes"], max_claims=3))
        if clin["minutes"]
        else f'<p class="empty">{_esc(NONE_YET)}</p>'
    )
    notes_html = f"<p>{_esc(clin['notes'])}</p>"
    preprint_html = _md_to_safe_html(_trim_claims_and_harvard(lab["preprints"]))
    designs_html = _md_to_safe_html(_trim_claims_and_harvard(lab["designs"]))
    charts = _charts_html(series)
    context = case_context_html(user_data)
    open_q = board_md_mod._format_open_questions(
        biometrics=board_md_mod.biometrics_label(user_data),
        files_n=board_md_mod.patient_files_count(user_data),
        has_evidence=bool(clin["evidence"]),
        has_designs=bool(lab["designs"]),
        card=load_card(user_data) if user_data else None,
    )
    open_html = _md_to_safe_html(open_q)

    viewers = [v for v in (mol_viewers or []) if isinstance(v, dict) and v.get("url") and v.get("id")]
    viewers = viewers[:MAX_STRUCTURE_VIEWERS]
    structures_nav = (
        '\n    <a href="#structures">Structures</a>' if viewers else ""
    )
    structures_block = ""
    mol_cdn_css = ""
    mol_cdn_js = ""
    mol_init_script = ""
    mol_extra_css = ""
    if viewers:
        mol_extra_css = """
.mol-viewer {
  width: 100%; height: 360px;
  border: 1px solid var(--rule);
  position: relative;
  background: #fafafa;
}
figure.mol-fig { margin: 1.25rem 0; padding: 0; }
figure.mol-fig figcaption {
  font-family: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.8rem; color: var(--muted); margin-bottom: 0.4rem;
}
"""
        figs: list[str] = []
        for v in viewers:
            vid = _esc(str(v["id"]))
            label = _esc(str(v.get("label") or "Structure"))
            figs.append(
                f'<figure class="mol-fig">'
                f"<figcaption>{label}</figcaption>"
                f'<div id="{vid}" class="mol-viewer" '
                f'style="width:100%;height:360px;border:1px solid var(--rule)"></div>'
                f"</figure>"
            )
        structures_block = (
            '\n    <h3 id="structures">Structures</h3>\n    '
            + "\n    ".join(figs)
        )
        mol_cdn_css = (
            f'<link rel="stylesheet" type="text/css" href="{MOLSTAR_CDN}/molstar.css"/>'
        )
        mol_cdn_js = f'<script src="{MOLSTAR_CDN}/molstar.js"></script>'
        # Safe JSON for init — urls are public HTTPS only
        payload = [
            {
                "id": str(v["id"]),
                "url": str(v["url"]),
                "format": str(v.get("format") or "mmcif"),
            }
            for v in viewers
        ]
        mol_init_script = f"""
<script>
(function () {{
  var viewers = {json.dumps(payload)};
  if (typeof molstar === "undefined" || !molstar.Viewer) {{ return; }}
  viewers.forEach(function (spec) {{
    var el = document.getElementById(spec.id);
    if (!el) {{ return; }}
    molstar.Viewer.create(spec.id, {{
      layoutIsExpanded: false,
      layoutShowControls: false,
      layoutShowRemoteState: false,
      layoutShowSequence: false,
      layoutShowLog: false,
      layoutShowLeftPanel: false,
      viewportShowExpand: false,
      viewportShowSelectionMode: false,
      viewportShowAnimation: false
    }}).then(function (viewer) {{
      return viewer.loadStructureFromUrl(spec.url, spec.format || "mmcif");
    }}).catch(function () {{
      el.textContent = "Structure viewer unavailable.";
    }});
  }});
}})();
</script>"""

    expired_msg = _esc(board_md_mod.MSG_EXPIRED_PAGE)
    banner = _esc(board_md_mod.LIVE_BANNER)
    footer = _esc(board_md_mod.LIVE_FOOTER)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="robots" content="noindex, nofollow"/>
<title>Case conference — research use only</title>
<link rel="preconnect" href="https://cdn.jsdelivr.net"/>
<style>
:root {{
  --bg: #ffffff;
  --ink: #1a1a1a;
  --muted: #555555;
  --rule: #dddddd;
  --banner-bg: #f7f7f5;
  --link: #3a5a7a;
  --max: 42rem;
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0;
  background: var(--bg); color: var(--ink);
  font-family: "Source Serif 4", "Source Serif Pro", Georgia, "Times New Roman", serif;
  font-size: 1.05rem; line-height: 1.55;
}}
.wrap {{
  max-width: var(--max);
  margin: 0 auto;
  padding: 1.25rem 1.25rem 3rem;
}}
.banner {{
  font-family: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.85rem; line-height: 1.4; color: var(--muted);
  background: var(--banner-bg); border: 1px solid var(--rule);
  padding: 0.75rem 1rem; margin-bottom: 1rem;
}}
nav.anchors {{
  font-family: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.9rem; margin: 0 0 1.5rem; padding: 0;
  border-bottom: 1px solid var(--rule); padding-bottom: 0.75rem;
}}
nav.anchors a {{
  color: var(--link); text-decoration: none; margin-right: 1rem;
}}
nav.anchors a:hover {{ text-decoration: underline; }}
h1 {{
  font-size: 1.6rem; font-weight: 600; margin: 0 0 0.75rem;
}}
h2 {{
  font-size: 1.25rem; font-weight: 600;
  margin: 2rem 0 0.75rem; padding-bottom: 0.35rem;
  border-bottom: 1px solid var(--ink);
}}
h3 {{ font-size: 1.05rem; font-weight: 600; margin: 1.25rem 0 0.5rem; }}
h4 {{ font-size: 1rem; font-weight: 600; margin: 1rem 0 0.4rem; }}
ul {{ padding-left: 1.25rem; }}
li {{ margin: 0.25rem 0; }}
p.empty {{ color: var(--muted); font-style: italic; }}
figure.chart {{ margin: 1.25rem 0; padding: 0; }}
figure.chart figcaption {{
  font-family: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.8rem; color: var(--muted); margin-top: 0.4rem;
}}
.vega {{ width: 100%; min-height: 160px; }}
footer {{
  font-family: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.8rem; color: var(--muted);
  margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--rule);
}}
#expired {{
  display: none; font-family: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  padding: 2rem 1.25rem; max-width: var(--max); margin: 0 auto;
}}
{mol_extra_css}
</style>
{mol_cdn_css}
</head>
<body>
<div id="expired"><p>{expired_msg}</p></div>
<div class="wrap" id="live">
  <div class="banner">{banner}</div>
  <nav class="anchors" aria-label="Sections">
    <a href="#clinical">Clinical</a>
    <a href="#laboratory">Laboratory</a>
    <a href="#measurements">Measurements</a>{structures_nav}
  </nav>
  <h1>Case conference packet</h1>
  <section id="context" aria-label="Case context">
    <h2>Case context</h2>
    {context}
  </section>
  <section id="measurements">
    <h2>Measurements</h2>
    {charts}
  </section>
  <section id="clinical">
    <h2>Clinical</h2>
    <h3>Evidence</h3>
    {evidence_html}
    <h3>Meeting minutes</h3>
    {minutes_html}
    <h3>Notes</h3>
    {notes_html}
  </section>
  <section id="laboratory">
    <h2>Laboratory</h2>
    <h3>Designs</h3>
    {designs_html}{structures_block}
    <h3>Preprint literature</h3>
    {preprint_html}
  </section>
  <section id="open-questions">
    <h2>Open questions</h2>
    {open_html}
  </section>
  <footer>{footer}</footer>
</div>
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
{mol_cdn_js}
<script>
(function () {{
  var expiresIso = {json.dumps(expires_iso)};
  if (expiresIso) {{
    var exp = Date.parse(expiresIso);
    if (!isNaN(exp) && Date.now() > exp) {{
      document.getElementById("live").style.display = "none";
      document.getElementById("expired").style.display = "block";
      return;
    }}
  }}
  var nodes = document.querySelectorAll(".vega[data-spec]");
  nodes.forEach(function (el) {{
    try {{
      var spec = JSON.parse(el.getAttribute("data-spec"));
      vegaEmbed(el, spec, {{actions: false, renderer: "svg"}});
    }} catch (e) {{
      el.textContent = "Chart unavailable.";
    }}
  }});
}})();
</script>
{mol_init_script}
</body>
</html>
"""


def html_contains_secrets(html_text: str, user_data: dict[str, Any] | None) -> list[str]:
    """Return list of secret values found in HTML (for tests). Empty = clean.

    Ignores ambiguous single-character biometrics (e.g. sex letter) that collide
    with ordinary English/CSS. Requires distinctive numeric/string values.
    """
    found: list[str] = []
    if not user_data:
        return found
    patient = onboard_mod.get_patient(user_data) or {}
    for key in onboard_mod.FIELD_ORDER:
        val = patient.get(key)
        if val is None:
            continue
        s = str(val)
        if len(s) < 2:
            continue  # sex letter etc. — too ambiguous
        # Whole-token match so CSS "1.55" does not flag age 55
        if re.search(r"(?<![\d.])" + re.escape(s) + r"(?![\d.])", html_text):
            found.append(f"biometric:{key}")
    for m in measure_mod.get_measurements(user_data):
        if not m.get("secret"):
            continue
        val = m.get("value")
        if val is None:
            continue
        s = str(val)
        if len(s) >= 1 and s in html_text:
            found.append(f"secret_measure:{m.get('key')}")
    for f in patient_files_mod.get_patient_files(user_data):
        body = str(f.get("text") or "")
        if len(body) >= 4 and body in html_text:
            found.append("note_body")
    return found
