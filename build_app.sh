#!/usr/bin/env bash
set -euo pipefail

APP_NAME="MW_Auditor"
VENV_DIR=".venv-build"
FFMPEG_DIR="bundle/ffmpeg"
FFMPEG_BIN="$FFMPEG_DIR/ffmpeg"
FFPROBE_BIN="$FFMPEG_DIR/ffprobe"
FFMPEG_VERSION="6.1"
FFMPEG_URL="https://evermeet.cx/ffmpeg/ffmpeg-${FFMPEG_VERSION}.zip"
FFPROBE_URL="https://evermeet.cx/ffmpeg/ffprobe-${FFMPEG_VERSION}.zip"

download_ffmpeg() {
  if [[ -f "$FFMPEG_BIN" && -f "$FFPROBE_BIN" ]]; then
    return
  fi
  echo "Lade FFmpeg ${FFMPEG_VERSION}…"
  mkdir -p "$FFMPEG_DIR"
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT

  if [[ ! -f "$FFMPEG_BIN" ]]; then
    curl -L "$FFMPEG_URL" -o "$tmpdir/ffmpeg.zip"
    unzip -j "$tmpdir/ffmpeg.zip" ffmpeg -d "$FFMPEG_DIR"
    chmod +x "$FFMPEG_BIN"
  fi

  if [[ ! -f "$FFPROBE_BIN" ]]; then
    curl -L "$FFPROBE_URL" -o "$tmpdir/ffprobe.zip"
    unzip -j "$tmpdir/ffprobe.zip" ffprobe -d "$FFMPEG_DIR"
    chmod +x "$FFPROBE_BIN"
  fi

  rm -rf "$tmpdir"
  trap - EXIT
}

command -v curl >/dev/null 2>&1 || { echo "curl wird benötigt." >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo "unzip wird benötigt." >&2; exit 1; }

download_ffmpeg

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python3 -m pip install --upgrade pip wheel setuptools
python3 -m pip install -r requirements.txt pyinstaller

deactivate
source "$VENV_DIR/bin/activate"

rm -rf build dist "$APP_NAME.spec"

pyinstaller \
  --noconfirm \
  --windowed \
  --name "$APP_NAME" \
  --icon mw.icns \
  --add-data "check_media.py:." \
  --add-data "pixfmt_map.json:." \
  --add-data "zielwerte.json:." \
  --add-data "zielwerte_template.json:." \
  --add-data "mw-emblem.svg:." \
  --add-data "logo.png:." \
  --add-data "media:media" \
  --add-binary "$FFMPEG_BIN:ffmpeg" \
  --add-binary "$FFPROBE_BIN:ffprobe" \
  videocheck_gui.py

deactivate

cat <<MSG

Fertig: dist/$APP_NAME.app
Für Weitergabe: zippen mit
  ditto -c -k --sequesterRsrc --keepParent dist/$APP_NAME.app dist/$APP_NAME.zip
Bei Bedarf Codesign/Notarisierung durchführen.
MSG
