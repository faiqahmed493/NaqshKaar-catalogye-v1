#!/usr/bin/env bash
# TripoSR (VAST-AI-Research/TripoSR). ~6 GB VRAM; works on a Colab T4.
source "$(dirname "$0")/common.sh"
make_env nq-triposr 3.10
cd "$ENGINES_DIR"
[ -d TripoSR ] || git clone https://github.com/VAST-AI-Research/TripoSR.git
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r TripoSR/requirements.txt
pip install rembg onnxruntime-gpu
done_msg nq-triposr triposr "TRIPOSR_REPO=$ENGINES_DIR/TripoSR"
