#!/usr/bin/env bash
# Hunyuan3D-2 / 2mini / 2mv (Tencent-Hunyuan/Hunyuan3D-2). Shape ~6-10 GB; shape + texture ~16 GB.
source "$(dirname "$0")/common.sh"
make_env nq-hunyuan2 3.10
cd "$ENGINES_DIR"
[ -d Hunyuan3D-2 ] || git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git
cd Hunyuan3D-2
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
pip install -e .
# Texture painting needs two compiled extensions:
(cd hy3dgen/texgen/custom_rasterizer && python setup.py install)
(cd hy3dgen/texgen/differentiable_renderer && python setup.py install)
done_msg nq-hunyuan2 "hunyuan3d2,hunyuan3d2mv"
