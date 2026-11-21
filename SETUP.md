# Naqshkaar Catalogue Studio: setup guide

This guide takes you from an empty machine to a running studio with a 3D worker.
Everything you must set yourself (passwords, keys, URLs) is marked **YOU SET**.

## Quick start (recommended)

1. Install **Docker Desktop** and start it (Windows: keep the default WSL 2 backend). Wait until it says *Engine running*.
2. Unzip the project somewhere without spaces in the path, e.g. `C:\dev\naqshkaar-catalogue-studio`.
3. Run the setup script from that folder:
   - **Windows:** double-click `setup.cmd`
   - **macOS / Linux:** `./setup.sh`
4. Answer two questions (admin email and password). The script then:
   - creates `.env` with a random database password and secret key, and picks free ports
   - builds and starts the database, API, CPU worker and web UI
   - creates a worker API key and starts the mock 3D worker
   - runs the end-to-end self-test (`docker compose exec api python -m app.smoke`)
5. Open the web UI it prints (normally **http://localhost:8080**) and sign in.

Run the same script again any time to rebuild and restart; it keeps your `.env`.
The sections below explain each piece, and how to do every step by hand.

- [1. What you are installing](#1-what-you-are-installing)
- [2. Prerequisites](#2-prerequisites)
- [3. Credentials and configuration](#3-credentials-and-configuration)
- [4. Start with Docker (recommended)](#4-start-with-docker-recommended)
- [5. Database connection](#5-database-connection)
- [6. First sign-in, team and API keys](#6-first-sign-in-team-and-api-keys)
- [7. 3D generation workers](#7-3d-generation-workers)
- [8. Feeding data in: manual and API](#8-feeding-data-in-manual-and-api)
- [9. Serving the catalogue to the Naqshkaar planner](#9-serving-the-catalogue-to-the-naqshkaar-planner)
- [10. File storage (local or S3/MinIO)](#10-file-storage-local-or-s3minio)
- [11. Running without Docker (development)](#11-running-without-docker-development)
- [12. Tests](#12-tests)
- [13. Backups and maintenance](#13-backups-and-maintenance)
- [14. Troubleshooting](#14-troubleshooting)
- [15. Security and data notes](#15-security-and-data-notes)
- [Appendix A: every environment variable](#appendix-a-every-environment-variable)

---

## 1. What you are installing

| Piece | Folder | Runs as | Job |
|---|---|---|---|
| PostgreSQL 16 (+ pgvector) | `docker-compose.yml` → `db` | container | All catalogue data |
| API | `backend/` | container `api` (FastAPI, port 8000) | Products, prices, dimensions, images, review rules, job queue, worker and ingest APIs |
| CPU worker | `backend/app/worker.py` | container `worker` | Qualifies every uploaded mesh: orientation, metric scaling, tolerance, GLB checks |
| Web UI | `frontend/` | container `web` (nginx, port 8080) | Curator and reviewer screens with the Three.js preview |
| 3D generation workers | `generator/` | your GPU machine(s), Colab, or a container | Run TRELLIS, TRELLIS.2, TripoSR, Hunyuan3D, SF3D, InstantMesh, Meshy or any CLI model |

Workers connect **out** to the API over HTTP with an API key. They never need database access,
so a GPU in the lab, a teammate's laptop or a Colab notebook can all serve the same queue.

## 2. Prerequisites

**For the studio (any OS):**
- Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux). Check with `docker compose version`.
- 4 GB free RAM, 10 GB disk to start (product images and GLBs grow over time).

**For GPU workers:**
- Linux with an NVIDIA GPU and a recent driver (`nvidia-smi` must work). Windows users can use WSL2.
- Conda (Miniconda or Mambaforge) for the per-engine environments, Git, and a CUDA toolkit matching the engine
  (most engines build CUDA extensions; see each script in `generator/envs/`).
- Free disk for model weights: roughly 2 GB (TripoSR) to 20+ GB (TRELLIS.2, Hunyuan3D-2.1).
- Or Google Colab: TripoSR and Hunyuan3D-2mini (shape only) fit a free T4.

## 3. Credentials and configuration

```bash
cp .env.example .env
```

Open `.env` and set these (**YOU SET**):

| Variable | What to put | Example |
|---|---|---|
| `POSTGRES_PASSWORD` | Database password. Use letters and digits, or URL-encode special characters, because it is placed inside `DATABASE_URL`. | `nq7Kx2pR9aZ4` |
| `SECRET_KEY` | Long random string. Signs logins and file links. Changing it signs everyone out. | output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `BOOTSTRAP_ADMIN_EMAIL` | Your email; the first admin account is created with it. | `you@example.com` |
| `BOOTSTRAP_ADMIN_PASSWORD` | 10+ characters. Change it after the first sign-in if you like. | |
| `WORKER_API_KEY` | Leave empty for now; you create it in step 6. | |

Optional: `API_PORT`, `WEB_PORT`, `DB_PORT` if 8000/8080/5432 are taken; `MESHY_API_KEY` only if you will use the paid Meshy API.

## 4. Start with Docker (recommended)

```bash
docker compose up -d --build      # first build takes a few minutes
docker compose ps                 # db, api, worker, web should be "running" / "healthy"
docker compose logs -f api        # watch migrations run and the admin account get created
```

What happens on first start:
1. `db` creates the database from `POSTGRES_*`.
2. `api` waits for the database, runs `alembic upgrade head` (schema, optional pgvector table, seed of
   categories and the engine registry), then creates the bootstrap admin.
3. `worker` starts polling for meshes to qualify.

Open **http://localhost:8080** and sign in with the bootstrap admin. The API docs are at
**http://localhost:8000/docs**.

## 5. Database connection

### Using the bundled database (default)
Nothing else to do. From your machine you can connect with any client:

```
host: localhost   port: 5432 (DB_PORT)   database: naqshkaar_catalogue
user: naqshkaar   password: the POSTGRES_PASSWORD you set
```

or `make psql` (runs `psql` inside the container).

### Using your own PostgreSQL (university server, Supabase, Neon, RDS…)
1. Create a role and database (run as a superuser):
   ```sql
   CREATE ROLE naqshkaar LOGIN PASSWORD 'YOUR_PASSWORD';
   CREATE DATABASE naqshkaar_catalogue OWNER naqshkaar;
   \c naqshkaar_catalogue
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   CREATE EXTENSION IF NOT EXISTS citext;
   CREATE EXTENSION IF NOT EXISTS vector;   -- optional; skip if the server lacks pgvector
   ```
   The migrations create `pgcrypto` and `citext` themselves when the role is allowed to; managed services
   often require you to enable extensions from their dashboard instead.
2. Point the API and worker at it. In `docker-compose.yml`, replace the `DATABASE_URL` line under
   `x-backend-env` with your URL and remove the `db` service and the `depends_on: db` block:
   ```
   DATABASE_URL: postgresql+psycopg://naqshkaar:YOUR_PASSWORD@db.example.edu:5432/naqshkaar_catalogue?sslmode=require
   ```
   The `postgresql+psycopg://` prefix is required (it selects the psycopg 3 driver).
3. `docker compose up -d --build api worker web`.

### Applying migrations by hand
```bash
docker compose exec api alembic upgrade head      # or, without Docker: cd backend && alembic upgrade head
# Plain SQL alternative (same files, same order):
psql "$URL" -f backend/sql/0001_initial_schema.sql
psql "$URL" -f backend/sql/0002_optional_pgvector.sql
psql "$URL" -f backend/sql/0003_seed_reference.sql
```

The schema is documented in [docs/database.md](docs/database.md).

## 6. First sign-in, team and API keys

1. **Sign in** at http://localhost:8080 with the bootstrap admin.
2. **Settings → Team**: add teammates. Roles:
   - `admin`: everything, including users, keys and engine switches
   - `curator`: create and edit products, prices, dimensions, images; admit variants to the catalogue
   - `asset_reviewer`: start 3D jobs, upload corrected meshes, approve or reject 3D assets
   - `viewer`: read-only
3. **Settings → Retailers**: add the Pakistani retailers you collect from, with notes on permission to use their images.
4. **Settings → API keys** (shown once, copy immediately):
   - scope **worker**: one per GPU machine or Colab session
   - scope **ingest**: for your data-collection software
   - scope **catalogue_read**: for the Naqshkaar planner backend

Command-line alternatives:
```bash
make admin EMAIL=you@example.com NAME="Your Name"          # extra admin
make key NAME=lab-gpu-trellis SCOPES=worker                 # prints the key once
```

## 7. 3D generation workers

### 7.1 Try the whole pipeline without a GPU (mock engine)
1. Create a **worker** key and put it in `.env` as `WORKER_API_KEY=nqk_...`.
2. `docker compose --profile mock up -d --build generator-mock`
3. In the UI: add a product with dimensions and an image → **3D model** tab → choose **Mock engine** → Generate.
   The mock builds a textured box; you will see it queued, generated, checked and ready for review.

### 7.2 A real engine on a Linux GPU machine
Each engine has its own installer because their CUDA extensions pin different PyTorch versions:

| Engine | Installer | VRAM (approx.) | Licence |
|---|---|---|---|
| TripoSR | `generator/envs/triposr.sh` | ~6 GB | MIT |
| Stable Fast 3D | `generator/envs/sf3d.sh` | ~7 GB | Stability AI Community (gated on Hugging Face) |
| Hunyuan3D-2 / 2mini / 2mv | `generator/envs/hunyuan3d2.sh` | 6–16 GB | Tencent Hunyuan Community |
| TRELLIS | `generator/envs/trellis.sh` | 16 GB | MIT |
| InstantMesh | `generator/envs/instantmesh.sh` | ~16 GB | Apache-2.0 (+ Zero123++ terms) |
| Hunyuan3D-2.1 | `generator/envs/hunyuan3d21.sh` | 10–24 GB | Tencent non-commercial |
| TRELLIS.2 | `generator/envs/trellis2.sh` | 24 GB | MIT |

Example (TripoSR):
```bash
cd generator
bash envs/triposr.sh                         # creates conda env nq-triposr, clones TripoSR into ~/naqshkaar-engines
conda activate nq-triposr
export STUDIO_URL=http://<studio-host>:8000  # YOU SET: where the API is reachable from this machine
export STUDIO_API_KEY=nqk_...                # YOU SET: a worker key
export TRIPOSR_REPO=$HOME/naqshkaar-engines/TripoSR
export ENGINES=triposr WORKER_ID=lab-gpu-triposr
python -m naqshkaar_generator --list-engines # confirms the engine is usable here
python -m naqshkaar_generator                # leave running
```
You can keep these in `generator/.env` instead (copy `generator/.env.example`).

Several workers on one GPU: give each its own engine env and keep the default
`GPU_LOCK_FILE=/tmp/naqshkaar-gpu.lock`, so only one generates at a time.

The **Engines & workers** page shows each worker's heartbeat, GPU and engines.

### 7.3 Google Colab
Open `generator/colab/naqshkaar_worker_colab.ipynb` in Colab. Colab cannot reach `localhost` on your PC,
so expose the API first. The simplest option is Cloudflare's quick tunnel, run on the studio machine:
```bash
cloudflared tunnel --url http://localhost:8000    # prints https://<random>.trycloudflare.com
```
Paste that URL and a worker key into the notebook. Quick-tunnel URLs change every run; for a fixed URL use a
named Cloudflare tunnel or ngrok with a reserved domain.

### 7.4 Docker GPU worker (TripoSR)
With the NVIDIA Container Toolkit installed: set `WORKER_API_KEY` in `.env`, then
`docker compose --profile gpu-triposr up -d --build`.

### 7.5 Meshy (paid API, not open source)
Set `MESHY_API_KEY` and add `meshy` to a worker's `ENGINES` (it needs no GPU, e.g.
`CPU_ENGINES=mock,meshy` for the Docker CPU worker). Product photos are sent to Meshy's servers.

### 7.6 Any other open-source model
Use the `command` engine: set `GENERATOR_COMMAND_TEMPLATE` on the worker to a CLI that writes a mesh into
`{output_dir}`. See `generator/README.md`. To list it as its own engine in the UI, copy its row in
`backend/sql/0003_seed_reference.sql` and add an adapter class (about 40 lines).

### 7.7 What happens to a generated mesh
The CPU worker turns it upright using your orientation settings, swaps width/depth when that matches the recorded
footprint better, centres it, stands it on the floor and scales each axis to the recorded W × D × H. It then
checks every axis is within max(5 mm, 1 %) (NFR-ACC-002), that the exported GLB re-opens, embeds its textures and passes the
Khronos glTF-Validator. A person then ticks the six-point visual checklist (§6.2) before the asset can qualify.

## 8. Feeding data in: manual and API

**Manual:** **Add product** in the UI. Upload one or many PNG/JPEG/WebP/SVG images per variant
(SVGs are rasterised for the engines). Tag views (front, left, back…) for multi-view engines.

**From your collector software:** use an **ingest** key.
```bash
python scripts/collector_example.py --studio http://localhost:8000 --key nqk_... scripts/sample_product.json
python scripts/import_csv.py --studio http://localhost:8000 --key nqk_... scripts/sample_products.csv   # spreadsheets
```
The payload format is in [docs/api.md](docs/api.md#ingest-api). Re-sending a product is safe; each send adds a
dated price observation. Pushed records stay drafts, and pushed attributes stay unverified, until a curator reviews them.

## 9. Serving the catalogue to the Naqshkaar planner

The planner reads with a **catalogue_read** key:
```bash
curl -H "X-API-Key: nqk_..." "http://localhost:8000/api/catalogue/variants?asset_ready=true&room_type=study&max_price_pkr=60000"
```
Each item has the variant identity, current dimension revision, latest dated PKR price, purchase link and,
when `asset_ready` is true, a signed `glb_url` (relative; prefix the API host). Only `eligible` variants
are returned unless `eligible_only=false`. The same data is the SQL view `v_catalogue_variant`.

## 10. File storage (local or S3/MinIO)

- **local** (default): files live in the Docker volume `storage` (`/data/storage` in the containers).
- **S3-compatible**: set `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and for MinIO or R2 also
  `S3_ENDPOINT_URL`. For a local MinIO: `docker compose --profile s3 up -d minio`, open http://localhost:9001,
  create the bucket, then set `S3_ENDPOINT_URL=http://minio:9000` and restart `api` and `worker`.

Files are always served through the API with signed, expiring links, so buckets can stay private.

## 11. Running without Docker (development)

```bash
# database: any PostgreSQL 14+ (see section 5)
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                     # YOU SET: DATABASE_URL, SECRET_KEY
alembic upgrade head
python -m app.cli create-user --email you@example.com --name "You" --role admin
uvicorn app.main:app --reload                            # API on :8000
python -m app.worker                                      # second terminal: CPU worker

# optional: the Khronos validator (needs Node 18+)
cd tools && npm install && cd ..
# then in backend/.env: GLTF_VALIDATOR_CMD=node /absolute/path/to/backend/tools/validate.mjs

cd ../frontend
npm install
npm run dev                                              # UI on :5173, proxies /api to :8000
```
SVG uploads need the Cairo library: `apt install libcairo2` (Linux), `brew install cairo` (macOS);
on Windows use Docker or WSL.

## 12. Tests

```bash
cd backend && pytest -q          # unit conversion, tolerance, mesh scaling, GLB checks, admission rules
cd frontend && npm run typecheck
```

## 13. Backups and maintenance

```bash
docker compose exec db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > backup-$(date +%F).dump
docker run --rm -v naqshkaar-catalogue-studio_storage:/s -v "$PWD":/b alpine tar czf /b/storage-$(date +%F).tgz -C /s .
```
(the volume name prefix is your project folder name; see `docker volume ls`). Restore with `pg_restore` and by
untarring into the volume. Upgrading: `git pull && docker compose up -d --build`; new migrations run automatically.

## 14. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `api` restarts, log says *password authentication failed* | `.env` password changed after the database volume was created. Use the original, or `docker compose down -v` to start over (deletes data). |
| Login says *Email or password is incorrect* for the bootstrap admin | The admin is created only if the email does not exist yet. Use `make admin` or reset in Settings → Team. |
| Jobs stay **Queued** | No worker online for that engine (Engines & workers page). Check the worker's `STUDIO_URL` is reachable from that machine and the key has the `worker` scope. |
| Worker says *engine unavailable* | The `*_REPO` variable or the conda env is wrong; run `python -m naqshkaar_generator --list-engines` inside the engine's env. |
| Job fails with *CUDA out of memory* | The engine needs more VRAM than the GPU has. Use a lighter engine or parameters (e.g. Hunyuan `texture: false`, TRELLIS `texture_size: 512`). |
| Asset **Needs correction**: *scale_distortion* | The mesh proportions do not match the recorded dimensions. Usually the model lies on its side: turn it (X or Z +90°) and re-run checks, or try another image or engine. |
| *gltf_validator* not run / failed with REQUIRE on | Outside Docker, install the validator (section 11) or set `REQUIRE_GLTF_VALIDATOR=false` for development. |
| SVG upload rejected | Cairo is missing (outside Docker) or the SVG references external files; export a self-contained SVG. |
| Colab worker cannot connect | Quick-tunnel URL changed or the API port is not the one tunnelled. |
| *Bind for 0.0.0.0:5432 failed: port is already allocated* | Another program (often a local PostgreSQL install) uses the port. Change `DB_PORT`, `API_PORT` or `WEB_PORT` in `.env` and run `docker compose up -d`. The setup script picks free ports automatically on first run. |
| `api` exits with *exec ./docker-entrypoint.sh: no such file or directory* | Windows line endings in the script. Rebuild (`docker compose build --no-cache api worker`); the image now strips them. If you use Git, keep the included `.gitattributes`. |
| Docker Desktop: *WSL 2 installation is incomplete* or *Virtualization not enabled* | Run `wsl --install` in an admin PowerShell and restart; enable virtualization (Intel VT-x / AMD-V) in the BIOS. |
| `setup.cmd` closes immediately or says scripts are disabled | Open PowerShell in the folder and run `powershell -ExecutionPolicy Bypass -File .\setup.ps1`. If Windows marked the zip as downloaded, right-click it → Properties → Unblock before extracting. |
| Build fails at `npm install` or `pip install` with network errors | A slow or filtered connection. Run `docker compose build` again; it resumes from cache. University networks sometimes block Docker Hub: try a mobile hotspot. |
| Self-test: *no worker is online for 'mock'* | Start it: `docker compose --profile mock up -d generator-mock`. If it keeps restarting, `docker compose logs generator-mock` usually shows an empty or wrong `WORKER_API_KEY` in `.env`. |
| Want to start completely fresh | `docker compose --profile mock down -v` (deletes the database and files), delete `.env`, run the setup script again. |

## 15. Security and data notes

- Change every `CHANGE_ME`. Keep `.env` out of Git (already in `.gitignore`).
- API keys are stored as SHA-256 hashes; revoke a lost key in Settings and make a new one.
- For anything beyond your own machine, put the studio behind HTTPS (a reverse proxy such as Caddy or
  Traefik) and restrict `CORS_ORIGINS`.
- Record each retailer's permission for using listing images in **Settings → Retailers → Usage terms**.
- Meshy and other external APIs receive product photos. Room data never enters this tool.
- Engine licences differ (see section 7.2). Hunyuan3D-2.1 is non-commercial; check before any commercial use.

---

## Appendix A: every environment variable

### Studio (`.env` at the repository root; also read from `backend/.env` when running without Docker)

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | — | Bundled database credentials (compose only) |
| `DATABASE_URL` | built from the above in compose | `postgresql+psycopg://user:pass@host:5432/db` |
| `SECRET_KEY` | — | Signs sessions and file links |
| `ACCESS_TOKEN_MINUTES` | 720 | Session length |
| `FILE_URL_TTL_SECONDS` | 21600 | Lifetime of signed file links |
| `CORS_ORIGINS` | `http://localhost:8080,http://localhost:5173` | Browser origins allowed to call the API directly |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` / `_NAME` | — | First admin, created on start if missing |
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `STORAGE_ROOT` | `/data/storage` | Local storage folder |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | — | S3-compatible storage |
| `MAX_UPLOAD_MB` | 25 | Per image |
| `MAX_MESH_UPLOAD_MB` | 200 | Per GLB |
| `INGEST_AUTO_CREATE_RETAILER` | true | Create unknown retailer slugs from ingest payloads |
| `INGEST_FETCH_IMAGES` | true | Download `images[].url` from ingest payloads |
| `PRICE_STALE_DAYS` | 30 | Advisory warning age for prices |
| `ASSET_EXTENT_MIN_TOLERANCE_M`, `ASSET_EXTENT_REL_TOLERANCE` | 0.005, 0.01 | NFR-ACC-002. Changing them changes an SRS requirement. |
| `ASSET_DISTORTION_WARN`, `ASSET_DISTORTION_FAIL` | 1.15, 1.5 | Per-axis scale ratio for warning / failure |
| `ASSET_TRIANGLE_BUDGET` | 300000 | Warning above this many triangles |
| `GLTF_VALIDATOR_CMD` | `node /opt/gltf-validator/validate.mjs` | Empty disables the validator |
| `REQUIRE_GLTF_VALIDATOR` | false (true in compose) | Fail qualification if the validator cannot run |
| `JOB_STALE_MINUTES` | 20 | Re-queue jobs without a worker heartbeat |
| `WORKER_API_KEY`, `CPU_ENGINES`, `MESHY_API_KEY` | — | Dockerised workers only |

### Generation worker (`generator/.env` or the shell)

| Variable | Default | Meaning |
|---|---|---|
| `STUDIO_URL` | `http://localhost:8000` | API base URL reachable from the worker |
| `STUDIO_API_KEY` | — | Key with scope `worker` |
| `ENGINES` | `mock` | Comma list of engine codes to serve |
| `WORKER_ID` | hostname-pid | Name shown in the UI |
| `WORK_DIR` | `./work` | Temporary job folders |
| `POLL_SECONDS` / `HEARTBEAT_SECONDS` | 5 / 30 | Queue polling and heartbeat |
| `GPU_LOCK_FILE` | `/tmp/naqshkaar-gpu.lock` | Empty disables; serialises GPU use across workers |
| `MAX_LOADED_ENGINES` | 1 | Models kept in GPU memory at once |
| `KEEP_WORK_FILES` | false | Keep job folders for debugging |
| `TRELLIS_REPO`, `TRELLIS_MODEL`, `ATTN_BACKEND` | — | TRELLIS |
| `TRELLIS2_REPO`, `TRELLIS2_MODEL` | — | TRELLIS.2 |
| `TRIPOSR_REPO` | — | TripoSR |
| `HUNYUAN21_REPO` | — | Hunyuan3D-2.1 (2.0/2mv use the installed `hy3dgen` package) |
| `SF3D_REPO` | — | Stable Fast 3D (if not pip-installed) |
| `INSTANTMESH_REPO`, `INSTANTMESH_PYTHON` | — | InstantMesh |
| `GENERATOR_COMMAND_TEMPLATE`, `GENERATOR_COMMAND_CWD`, `GENERATOR_COMMAND_ROTATE` | — | Custom command engine |
| `MESHY_API_KEY`, `MESHY_API_BASE` | — | Meshy |
