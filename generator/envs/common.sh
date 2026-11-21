#!/usr/bin/env bash
# Shared helpers for the per-engine installers. Each engine gets its own conda env
# because their CUDA extensions pin different torch versions.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINES_DIR="${ENGINES_DIR:-$HOME/naqshkaar-engines}"
mkdir -p "$ENGINES_DIR"

need() { command -v "$1" >/dev/null || { echo "missing: $1"; exit 1; }; }
need git; need conda
eval "$(conda shell.bash hook)"

make_env() {  # make_env <name> <python-version>
  conda env list | grep -q "^$1 " || conda create -y -n "$1" "python=$2"
  conda activate "$1"
  pip install -e "$ROOT"
}

done_msg() {  # done_msg <env> <engine> <VAR=value...>
  local env="$1" engine="$2"; shift 2
  echo
  echo "Installed. Start the worker with:"
  echo "  conda activate $env"
  for kv in "$@"; do echo "  export $kv"; done
  echo "  export STUDIO_URL=... STUDIO_API_KEY=nqk_... ENGINES=$engine"
  echo "  python -m naqshkaar_generator"
}
