#!/usr/bin/env bash
# Hunyuan3D-2.1 (Tencent-Hunyuan/Hunyuan3D-2.1). Shape ~10 GB, with PBR paint ~21-24 GB.
# Licence: Tencent Hunyuan non-commercial. Fine for the FYP, not for a commercial product.
source "$(dirname "$0")/common.sh"
make_env nq-hunyuan21 3.10
cd "$ENGINES_DIR"
[ -d Hunyuan3D-2.1 ] || git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git
cd Hunyuan3D-2.1
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
(cd hy3dpaint/custom_rasterizer && pip install -e .)
(cd hy3dpaint/DifferentiableRenderer && bash compile_mesh_painter.sh)
mkdir -p hy3dpaint/ckpt
[ -f hy3dpaint/ckpt/RealESRGAN_x4plus.pth ] || \
  wget -q https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -P hy3dpaint/ckpt
done_msg nq-hunyuan21 hunyuan3d21 "HUNYUAN21_REPO=$ENGINES_DIR/Hunyuan3D-2.1"
