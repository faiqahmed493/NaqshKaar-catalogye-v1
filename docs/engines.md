# 3D generation engines

All engines receive the job's images as normalised PNGs and return one GLB. The studio then orients, scales
to the recorded W × D × H and checks the result, so engines do not need to produce metric output.

| Code | Model | Inputs | VRAM (approx.) | Output | Licence | Good for |
|---|---|---|---|---|---|---|
| `trellis` | microsoft/TRELLIS-image-large | 1–4 images | 16 GB | textured mesh | MIT | default quality choice; multi-image helps hidden sides |
| `trellis_hf` | TRELLIS-image-large on the `trellis-community/TRELLIS` Hugging Face Space | 1 image | none (runs on the Space) | textured mesh | MIT | TRELLIS quality without a GPU; images go to Hugging Face, free ZeroGPU quota |
| `trellis2` | microsoft/TRELLIS.2-4B | 1 image | 24 GB | PBR textured mesh | MIT | best detail when a 24 GB GPU is available |
| `triposr` | stabilityai/TripoSR | 1 image | 6 GB | vertex-coloured mesh | MIT | fast drafts; free Colab T4 |
| `hunyuan3d2` | tencent/Hunyuan3D-2 (or 2mini) | 1 image | 6 GB shape, ~16 GB with texture | textured mesh | Tencent Hunyuan Community | clean shapes; `texture: false` for small GPUs |
| `hunyuan3d2mv` | tencent/Hunyuan3D-2mv | front (+left/back/right) | ~10 GB | shape | Tencent Hunyuan Community | products with several catalogue views |
| `hunyuan3d21` | tencent/Hunyuan3D-2.1 | 1 image | 10 GB shape, ~24 GB PBR | PBR textured mesh | Tencent **non-commercial** | FYP evaluation only |
| `sf3d` | stabilityai/stable-fast-3d | 1 image | 7 GB | UV-textured mesh | Stability AI Community (gated) | fast, tidy UVs |
| `instantmesh` | TencentARC/InstantMesh | 1 image | ~16 GB | textured mesh | Apache-2.0 + Zero123++ | alternative reconstruction |
| `command` | any CLI model | 1+ images | depends | any mesh format | depends | trying a new open-source model without code |
| `meshy` | Meshy API (paid) | 1–4 images | none | textured mesh | proprietary | comparison baseline; images leave your machines |
| `mock` | built in | 1 image | none | textured box | internal | testing the pipeline |

VRAM figures are starting points from each project's documentation. Measure on your GPU: every job records
`seconds` and `peak_vram_gb` in `generation_job.runtime_meta`, which gives you the benchmark data the
SRS asks for (§8.3: usable yield, correction effort, failed categories).

## Choosing inputs

- One clean product shot on a plain background gives the best single-image results. Lifestyle photos with
  rugs or plants usually fuse those props into the mesh (the reviewer must then reject it).
- Tag images by view on upload. Multi-image engines use all selected images; `hunyuan3d2mv` maps
  `front / left / back / right` tags to its views and needs `front`.
- Image backgrounds are removed by each engine's own preprocessing (rembg or the repository's remover).
  Transparent PNGs are used as they are.

## Parameters

Defaults live in `generation_engine.default_params` (editable via `PATCH /api/engines/{code}`). Override per run in
the UI under **Advanced: engine parameters**, e.g. `{"trellis": {"seed": 7, "texture_size": 2048}}`.

| Engine | Useful parameters |
|---|---|
| trellis | `seed`, `ss_steps`, `ss_cfg`, `slat_steps`, `slat_cfg`, `simplify` (0–1), `texture_size`, `multi_image_mode` (`stochastic` / `multidiffusion`) |
| trellis_hf | `seed`, `ss_steps`, `ss_cfg`, `slat_steps`, `slat_cfg`, `simplify`, `texture_size`, `space`, `timeout_seconds` |
| trellis2 | `seed`, `decimation_target`, `texture_size`, `pipeline_type` |
| triposr | `mc_resolution` (higher = finer), `foreground_ratio`, `chunk_size` |
| hunyuan3d2 | `model`, `subfolder` (e.g. `tencent/Hunyuan3D-2mini` + `hunyuan3d-dit-v2-mini`), `texture`, `steps`, `octree_resolution`, `seed` |
| hunyuan3d21 | `texture`, `max_num_view` (6–9), `paint_resolution` (512 / 768) |
| sf3d | `texture_resolution`, `remesh` (`none` / `triangle` / `quad`), `vertex_count`, `foreground_ratio` |
| instantmesh | `config`, `seed`, `export_texmap`, `timeout_seconds` |
| meshy | `ai_model`, `should_texture`, `target_polycount` |

## Adding an engine

1. Write an adapter in `generator/naqshkaar_generator/engines/`: subclass `Engine`, set `code`, implement
   `available()` (cheap check), `load()` (load weights once) and `generate(ctx)` (write one GLB in `ctx.work_dir`,
   +Y up). Call `ctx.step(percent, message)` between stages so progress and cancellation work.
   Convert other formats with `meshutil.to_glb(path_or_trimesh, out, rotate_deg=(…))`.
2. Register it in `engines/__init__.py`.
3. Add a row to `backend/sql/0003_seed_reference.sql` with the same `code` and run `python -m app.cli seed`.
4. Start a worker with `ENGINES=<code>`.
