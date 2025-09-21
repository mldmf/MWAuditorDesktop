# MW Auditor

MW Auditor ist ein macOS- und Python-Tool zur automatisierten Prüfung von Videodateien. Es kombiniert das CLI-Script `check_media.py` mit einer PySide6-basierten Oberfläche (`videocheck_gui.py`). Die App liefert Media-Profile, Validierungsberichte und bietet eine integrierte Vorschau mit Frame-Steuerung, Zoom, Cropping-Screenshots und einer redaktionell verwertbaren Fehlermeldung.

## Funktionsumfang

- **Drag & Drop / Dateiauswahl**: Mehrere Videos einfügen, Status-Überblick (Pass/Fail, Fehlerquote) und JSON-Export.
- **Zielwerte-Editor**: Zielwerte (`zielwerte.json`) komfortabel anpassen und validieren.
- **Video-Vorschau**: Frame-by-Frame, Play/Pause, Zoom/Pan, Timeline-Slider, Screenshot (PNG & Clipboard, gezoomter Ausschnitt) und Mail-tauglicher Prüfbericht.
- **Kommandozeile**: `check_media.py` erzeugt Media-Profile & Validierungsreports, prüft gegen Zielwerte und lässt sich aus Python wiederverwenden (`run_validation`).

## Schnellstart (Python)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
python3 videocheck_gui.py
```

> Hinweis: Für die CLI benötigt `check_media.py` zwingend eine Zielwerte-Datei (`zielwerte.json`).

## Prebuilt macOS-App nutzen

1. ZIP von `MW_Auditor.app` entpacken.
2. `MW_Auditor.app` nach `/Applications` ziehen (empfohlen, sonst blockt Gatekeeper).
3. Beim ersten Start ggf. Rechtsklick → **Öffnen** (falls noch nicht signiert/notarisiert).
4. Videos prüfen – Media-/Report-JSON liegen neben den jeweiligen Videodateien.

## Build-Anleitung (macOS)

Voraussetzungen: `python3`, `curl`, `unzip`, Apple Command Line Tools.

```bash
# sauberes Build-Venv + PyInstaller
rm -rf .venv-build
./build_app.sh
```

Das Skript erzeugt `dist/MW_Auditor.app` und lädt automatisch statische FFmpeg-Binaries (`bundle/ffmpeg/...`).

### Signieren & notarisiertes DMG erstellen

```bash
./sign_and_package.sh \
  -i "Developer ID Application: Dein Name (TEAMID12345)" \
  -p mein-notarytool-profile   # optional, falls notarytool konfiguriert
```

Ergebnis: `dist/MW_Auditor.app` (signiert) und `dist/MW_Auditor.dmg` (optional notarisiert + gestapelt).

**DMG zippen:**
```bash
ditto -c -k --sequesterRsrc --keepParent dist/MW_Auditor.dmg dist/MW_Auditor.dmg.zip
```

## Slack-Message (Kurzfassung)

> siehe eigenständige Nachricht unten – enthält Download-/Start-Hinweise für Kolleg:innen.

## Projektstruktur

```
.
├─ videocheck_gui.py        # PySide6 GUI (MW Auditor)
├─ check_media.py           # Media-Analyse + Validierung (CLI & import)
├─ requirements.txt         # av, PySide6, numpy
├─ build_app.sh             # PyInstaller-Build inkl. FFmpeg-Download
├─ sign_and_package.sh      # Codesign + DMG + optionale Notarisierung
├─ bundle/ffmpeg/           # ffmpeg/ffprobe (wird bei Bedarf heruntergeladen)
├─ zielwerte.json           # Beispiel-Zielwerte (optional)
└─ media/                   # Beispiel-Videos (optional)
```

## Troubleshooting

- **App startet nicht / „kann nicht geöffnet werden“**: Gatekeeper → App in `/Applications` kopieren oder notarisiertes DMG verwenden.
- **ModuleNotFoundError (PySide6/numpy/av)**: `pip install -r requirements.txt` im aktiven Venv ausführen.
- **FFmpeg nicht gefunden**: sicherstellen, dass `bundle/ffmpeg/ffmpeg` und `ffprobe` vorhanden sind (Build-Skript lädt sie automatisch).
- **CLI verlangt Zielwerte**: `python check_media.py <video> --profile zielwerte.json --summary-only` – ohne `--profile` bricht das Script ab.

Viel Spaß mit MW Auditor! Verbesserungswünsche bitte direkt hier im Repo aufmachen.
