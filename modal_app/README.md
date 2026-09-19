# Modal BindCraft app

Status: **deployed runner** — real BindCraft + default filters. Poller needs `MODAL_BINDCRAFT_APP=bindcraft-gpu`.

- GPU image: BindCraft + ColabDesign + PyRosetta + JAX CUDA
- Volume `bindcraft-weights`: AF2 params only (no clinic/secrets) — symlink to `/opt/bindcraft/params`
- Entrypoint: `run_bindcraft` — fail-closed if weights missing, structure missing, crash, or zero filter-passing designs (never invents binders)
- Probe: `probe_bindcraft` — imports + weights + GPU without starting a design

```bash
modal volume create bindcraft-weights   # once
modal deploy modal_app/bindcraft_app.py
# optional (~5.3GB): modal run modal_app/bindcraft_app.py::populate_weights
modal run modal_app/bindcraft_app.py::probe_bindcraft
```

See `/workspace/FEATURE-modal-bindcraft-compute.md`.
