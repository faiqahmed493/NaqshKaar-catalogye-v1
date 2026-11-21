#!/usr/bin/env bash
# Stable Fast 3D (Stability-AI/stable-fast-3d). ~6-7 GB VRAM.
# The model is gated: accept the terms at https://huggingface.co/stabilityai/stable-fast-3d first.
source "$(dirname "$0")/common.sh"
make_env nq-sf3d 3.10
cd "$ENGINES_DIR"
[ -d stable-fast-3d ] || git clone https://github.com/Stability-AI/stable-fast-3d.git
cd stable-fast-3d
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -U setuptools==69.5.1 wheel
pip install -r requirements.txt
pip install rembg onnxruntime-gpu
huggingface-cli login
done_msg nq-sf3d sf3d "SF3D_REPO=$ENGINES_DIR/stable-fast-3d"
