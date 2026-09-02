#!/usr/bin/env bash
# video-dub one-time setup
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check system deps
for bin in ffmpeg ffprobe python3; do
  command -v "$bin" &>/dev/null || { echo "ERROR: $bin not found on PATH"; exit 1; }
done

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
  echo "ERROR: Python 3.10+ required (found $PYTHON_VERSION)"
  exit 1
fi

VENV="$SKILL_DIR/.venv"
if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi

echo "Installing Python dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$SKILL_DIR/requirements.txt"

echo ""
echo "✅  video-dub installed."
echo "    Python env: $VENV"
echo ""
echo "    Usage:"
echo "      $VENV/bin/python3 $SKILL_DIR/pipeline.py \\"
echo "        --video /path/to/source.mp4 --lang ja --out output_ja.mp4"
echo ""
echo "    Set API key for translation:"
echo "      export ANTHROPIC_API_KEY=sk-ant-..."
echo "      export OPENAI_API_KEY=sk-..."
