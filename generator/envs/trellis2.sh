#!/usr/bin/env bash
# TRELLIS.2 (microsoft/TRELLIS.2). Linux + NVIDIA GPU with >= 24 GB. CUDA 12.4 recommended.
source "$(dirname "$0")/common.sh"
cd "$ENGINES_DIR"
[ -d TRELLIS.2 ] || git clone -b main --recursive https://github.com/microsoft/TRELLIS.2.git
cd TRELLIS.2
. ./setup.sh --new-env --basic --flash-attn --nvdiffrast --nvdiffrec --cumesh --o-voxel --flexgemm
conda activate trellis2
pip install -e "$ROOT"
done_msg trellis2 trellis2 "TRELLIS2_REPO=$ENGINES_DIR/TRELLIS.2"
