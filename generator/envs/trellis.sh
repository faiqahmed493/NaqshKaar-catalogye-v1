#!/usr/bin/env bash
# TRELLIS (microsoft/TRELLIS). Linux + NVIDIA GPU with >= 16 GB. CUDA 11.8 or 12.2 toolkit.
source "$(dirname "$0")/common.sh"
cd "$ENGINES_DIR"
[ -d TRELLIS ] || git clone --recurse-submodules https://github.com/microsoft/TRELLIS.git
cd TRELLIS
# The repository's own script creates the 'trellis' conda env and builds its CUDA extensions.
. ./setup.sh --new-env --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast
conda activate trellis
pip install -e "$ROOT"
done_msg trellis trellis "TRELLIS_REPO=$ENGINES_DIR/TRELLIS" "ATTN_BACKEND=xformers"
