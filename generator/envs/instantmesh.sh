#!/usr/bin/env bash
# InstantMesh (TencentARC/InstantMesh). ~16 GB VRAM. The worker calls its run.py in this env.
source "$(dirname "$0")/common.sh"
make_env nq-instantmesh 3.10
cd "$ENGINES_DIR"
[ -d InstantMesh ] || git clone https://github.com/TencentARC/InstantMesh.git
cd InstantMesh
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu121
pip install xformers==0.0.22.post7
pip install -r requirements.txt
done_msg nq-instantmesh instantmesh "INSTANTMESH_REPO=$ENGINES_DIR/InstantMesh" \
  "INSTANTMESH_PYTHON=$(conda info --base)/envs/nq-instantmesh/bin/python"
