#!/bin/bash
# Install Mike's neural voice (Qwen3-TTS 0.6B, 4-bit).
#
# The voice runs in its own Python environment, separate from Mike's. That is
# deliberate: it needs a release-candidate build of transformers, and Mike's
# environment is certified against a passing test suite that should not take
# on a pre-release dependency. Keeping them apart means the voice can be
# installed, upgraded or removed without touching the assistant.
#
# Mike works without this. If the voice is absent he speaks with the macOS
# system voice instead, and says so in the logs rather than falling silent.
#
#   ./scripts/install_voice.sh            install to the default location
#   MIKE_VOICE_HOME=/path install_voice.sh    install somewhere else

set -euo pipefail

HOME_DIR="${MIKE_VOICE_HOME:-$HOME/Library/Application Support/Mike/voice}"
MODEL="mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit"

echo "Installing Mike's voice to:"
echo "  $HOME_DIR"
echo

# About 1.7 GB of model plus 700 MB of runtime.
NEEDED_GB=4
FREE_GB=$(df -g "$HOME" | tail -1 | awk '{print $4}')
if [ "$FREE_GB" -lt "$NEEDED_GB" ]; then
    echo "Not enough disk: ${FREE_GB}GB free, about ${NEEDED_GB}GB needed." >&2
    exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
    echo "This voice runs on Apple Silicon (MLX). This machine is $(uname -m)." >&2
    echo "Mike will use the macOS system voice instead." >&2
    exit 1
fi

mkdir -p "$HOME_DIR"
python3 -m venv "$HOME_DIR"
"$HOME_DIR/bin/python" -m pip install --quiet --upgrade pip
echo "Installing the speech runtime (this takes a few minutes)…"
"$HOME_DIR/bin/python" -m pip install --quiet "mlx-audio>=0.3.2" "transformers==5.0.0rc3"

echo "Downloading the voice model (about 1.7 GB)…"
HF_HOME="$HOME_DIR/hf" "$HOME_DIR/bin/python" - <<PY
from huggingface_hub import snapshot_download
snapshot_download("$MODEL")
print("model ready")
PY

echo
echo "Done. Turn the voice on with:"
echo "  voice_provider = \"qwen\"  in Mike's preferences"
