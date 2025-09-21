#!/usr/bin/env bash
set -euo pipefail

APP_PATH="dist/MW_Auditor.app"
DMG_PATH="dist/MW_Auditor.dmg"
VOL_NAME="MW_Auditor"
IDENTITY=""
PROFILE=""
ENTITLEMENTS=""

usage() {
  cat <<USAGE
Usage: $0 -i "Developer ID Application: ..." [-a dist/VideoCheck.app] [-d dist/VideoCheck.dmg] [-v "VolumeName"] [-e entitlements.plist] [-p notary-profile]

-i  Codesign-Identität (Developer ID Application)
-a  Pfad zur .app (Standard: dist/VideoCheck.app)
-d  Ziel-DMG (Standard: dist/VideoCheck.dmg)
-v  Volume-Name für DMG (Standard: VideoCheck)
-e  Entitlements-Datei (optional)
-p  Name des notarytool-Profils für automatische Notarisierung (optional)

Beispiel:
  ./sign_and_package.sh -i "Developer ID Application: ACME Corp (ABCDE12345)" -p my-notary-profile
USAGE
}

while getopts "i:a:d:v:e:p:h" opt; do
  case "$opt" in
    i) IDENTITY="$OPTARG" ;;
    a) APP_PATH="$OPTARG" ;;
    d) DMG_PATH="$OPTARG" ;;
    v) VOL_NAME="$OPTARG" ;;
    e) ENTITLEMENTS="$OPTARG" ;;
    p) PROFILE="$OPTARG" ;;
    h) usage; exit 0 ;;
    *) usage; exit 1 ;;
  esac
done

shift $((OPTIND-1))

if [[ -z "$IDENTITY" ]]; then
  echo "Fehler: Codesign-Identität (-i) angeben." >&2
  usage
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "Fehler: App nicht gefunden unter $APP_PATH" >&2
  exit 1
fi

if ! command -v codesign >/dev/null; then
  echo "codesign nicht verfügbar (Xcode Command Line Tools installieren)." >&2
  exit 1
fi

if ! command -v hdiutil >/dev/null; then
  echo "hdiutil nicht verfügbar." >&2
  exit 1
fi

sign_args=(--deep --force --options runtime --timestamp --sign "$IDENTITY")
if [[ -n "$ENTITLEMENTS" ]]; then
  sign_args+=(--entitlements "$ENTITLEMENTS")
fi

printf "Signiere %s …\n" "$APP_PATH"
codesign "${sign_args[@]}" "$APP_PATH"

echo "Prüfe Codesign-Status …"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

if [[ -f "$DMG_PATH" ]]; then
  rm -f "$DMG_PATH"
fi

echo "Erstelle DMG unter $DMG_PATH …"
hdiutil create -volname "$VOL_NAME" -srcfolder "$APP_PATH" -format UDZO -ov "$DMG_PATH"

echo "DMG fertig: $DMG_PATH"

if [[ -n "$PROFILE" ]]; then
  if ! command -v xcrun >/dev/null; then
    echo "xcrun notarytool nicht verfügbar; Überspringe Notarisierung." >&2
    exit 0
  fi
  echo "Reiche DMG zur Notarisierung ein …"
  xcrun notarytool submit "$DMG_PATH" --keychain-profile "$PROFILE" --wait
  echo "Staple Notarisierungs-Ticket …"
  xcrun stapler staple "$APP_PATH"
  xcrun stapler staple "$DMG_PATH"
  echo "Notarisierung abgeschlossen."
fi

cat <<MSG

Vorgang abgeschlossen.
App: $APP_PATH
DMG: $DMG_PATH
MSG
