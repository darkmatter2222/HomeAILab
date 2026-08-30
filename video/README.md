# Qwen3.8 GPU Fleet — 3-Minute Animated Topology

A React (Vite) + framer-motion web app that animates the **entire** Qwen3.8-27B GPU
fleet end-to-end: the Claude Code client → the priority router → the three GPUs,
their two engines (vLLM + llama.cpp), speeds, context windows, the MTP speculative
decode win, how Portainer deploys everything, and how Prometheus + Grafana watch
TTFT / prefix-cache hit-rate / spec-decode acceptance. Styled in the NVIDIA dark /
green (`#76B900`) design language. Built to be **screen-recorded into a YouTube video**.

> The deliverable lives in the `video/` root: `src/` (scenes) + `verify/` (frame
> capture). `video/qwen-fleet/` is an earlier, simpler parallel scaffold — safe to
> delete if you only want the root app.

## Run / record

```bash
cd video
npm install
npm run dev          # http://localhost:5173  (add ?clean to hide the dev restart button)
```

- **Space / Enter** starts the playthrough; **R** restarts. `?seek=N` (or `#N`) jumps
  straight to second N — used by the capture tooling. `?clean` hides dev chrome for a
  pristine screen-capture.
- The whole run is **186 s (~3:06)**, driven by a master clock in `src/timeline.js`.
- For a clean YouTube capture: open at 1920×1080 (or 4K), hit **Space**, record 3 min
  at 60 fps. Hide the dev button with `?clean`.

## The 9 scenes (`src/scenes/`, timings in `src/timeline.js`)

| # | Scene | File | 0:00–3:06 |
|---|---|---|---|
| 01 | Boot sequence — the client points at one door | `Boot.jsx` | 0–12 |
| 02 | The model — hybrid arch, two paths, KV math | `Model.jsx` | 12–34 |
| 03 | Fleet topology — 3 hosts, router, monitor plane | `Topology.jsx` | 34–58 |
| 04 | Portainer control plane — the deploy recipe | `Portainer.jsx` | 58–86 |
| 05 | GPU router — strict-priority ingress, 500 at cap | `Router.jsx` | 86–116 |
| 06 | Engines + speed — vLLM vs llama.cpp, sweeps | `Engines.jsx` | 116–142 |
| 07 | MTP speculative decode — draft-3 + NVFP4 drafter fix | `MTP.jsx` | 142–162 |
| 08 | Observability — Prometheus jobs + Grafana panels | `Monitoring.jsx` | 162–176 |
| 09 | Outro — three GPUs, one signature, 262K | `Outro.jsx` | 176–186 |

Every number is sourced from the repo's source-of-truth (CLAUDE.md, the YAMLs,
`qwen3.8-27b/RESULTS.md`, `monitoring/`), so the animation matches the real fleet.

## Frame capture (verify a build without watching 3 min)

```bash
npm run dev            # keep it running
PORT=5173 node verify/shot.mjs "3,15,45,70,100,125,150,168,182"
```

Drops a PNG per timestamp into `verify/`.

## Files

- `src/timeline.js` — scene list + master clock; edit `dur`/windows here to retime.
- `src/App.jsx` — scene sequencer, HUD, captions, progress, keyboard controls.
- `src/ui.jsx` — shared building blocks (Card, KV, Stat, Bar, TokenStream, …).
- `src/theme.css` — NVIDIA palette + grid + HUD frame + card primitives.
- `src/scenes/*.jsx` — one file per scene.
