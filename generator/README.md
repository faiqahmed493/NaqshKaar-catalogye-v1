# Naqshkaar generation worker

Turns product images into GLB meshes with open-source image-to-3D models and sends them to the studio.

```
studio queue ──claim──▶ worker ──download images──▶ engine ──GLB──▶ upload ──▶ studio qualification
```

## Quick start (mock engine, any computer)

```bash
cd generator
pip install -e .
export STUDIO_URL=http://localhost:8000 STUDIO_API_KEY=nqk_...   # a key with scope 'worker'
ENGINES=mock python -m naqshkaar_generator
```

## Real engines

Install each engine in its own conda environment with the scripts in `envs/` (they clone the official
repository into `~/naqshkaar-engines` and install this package into the same env):

```bash
bash envs/triposr.sh        # or trellis.sh, trellis2.sh, hunyuan3d2.sh, hunyuan3d21.sh, sf3d.sh, instantmesh.sh
conda activate nq-triposr
export TRIPOSR_REPO=~/naqshkaar-engines/TripoSR ENGINES=triposr
python -m naqshkaar_generator --list-engines   # what is usable in this env, and why not
python -m naqshkaar_generator
```

One worker can serve several engines that share an environment (e.g. `ENGINES=hunyuan3d2,hunyuan3d2mv`).
`MAX_LOADED_ENGINES=1` keeps only one model in GPU memory at a time; `GPU_LOCK_FILE` stops two workers on the
same machine from generating at once.

The first job of each engine downloads its weights from Hugging Face (several GB). Set `HF_HOME` to a disk
with space. Gated models (Stable Fast 3D) need `huggingface-cli login` after accepting their terms.

## Colab

`colab/naqshkaar_worker_colab.ipynb`. Expose the studio API with a tunnel (`cloudflared tunnel --url http://localhost:8000`)
and paste that URL as `STUDIO_URL`.

## Custom command engine

Plug in any model with a command-line interface:

```bash
export ENGINES=command
export GENERATOR_COMMAND_TEMPLATE='python run.py --image {input} --output {output_dir}'
export GENERATOR_COMMAND_CWD=/opt/my-model
export GENERATOR_COMMAND_ROTATE=-90,0,0     # if the model writes Z-up meshes
```

Placeholders: `{input}`, `{inputs}`, `{output_dir}`, `{output}`, `{params_json}`. The newest
`.glb/.gltf/.obj/.ply/.stl` under `{output_dir}` is converted to GLB and uploaded.

## Behaviour

- Heartbeat every `HEARTBEAT_SECONDS`; the studio re-queues jobs from silent workers.
- Cancellation from the UI is honoured at the next progress step.
- Errors are reported with the log tail; the studio retries up to `max_attempts`.
- A missing engine install marks the engine unavailable on this worker and stops it claiming that engine.
- Each upload carries `seconds`, `peak_vram_gb`, GPU name and engine version for benchmarking.
