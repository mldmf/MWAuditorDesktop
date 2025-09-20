# check_media.py — Video Profiling & Validation (PyAV)

`check_media.py` liest ein **Video tatsächlich ein** (keine reinen Metadaten), misst technische Kennwerte (Container, Auflösung, FPS, CFR/VFR, Farbraum, Bittiefe), erstellt einen **Hash** (als eindeutige ID), und schreibt zwei JSON-Dateien:

1. `<input_name>.mediaprofile.json` – nur Messwerte  
2. `<input_name>.validationreport.json` – Messwerte **+** Validierung gegen Zielwerte

Die Ausgabe in der Konsole ist farbig (grün/rot) und enthält eine Kurz-Zusammenfassung der Validierung.

---

## Features

- 🧪 **Messung via Dekodierung** mit [PyAV] (FFmpeg-Bindings), keine blinde Metadaten-Übernahme  
- 🧾 **Zwei JSON-Outputs**: Media-Profil & Validierungsreport  
- 🔐 **Hash/ID** des Videofiles (Standard `sha256`)  
- 🎯 **Validierung** gegen frei definierbare Zielwerte (Ranges & Whitelists)  
- 🎛️ **CFR/VFR-Erkennung** aus tatsächlichen Frame-Abständen  
- 🌈 **Farbige Konsole** und deterministische Reihenfolge der Prüfungen  
- 📂 Flexible Ausgabeorte: CWD, gemeinsames `--out-dir`, oder explizit je Datei

[PyAV]: https://pyav.org/

---

## Systemvoraussetzungen

- macOS (Intel oder Apple Silicon)
- **Python 3.10+**
- **FFmpeg** (Systembibliotheken), z. B. via Homebrew

---

## Installation auf macOS (genau)

1) **Homebrew (falls nicht vorhanden)**  
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

2) **FFmpeg installieren**  
```bash
brew install ffmpeg
```

3) **Python & venv einrichten**  
```bash
python3 -m venv .venv
source .venv/bin/activate
python -V
```

4) **Dependencies installieren**  
`requirements.txt`:
```txt
av>=11.0.0,<13.0.0
```
```bash
pip install -r requirements.txt
```

---

## Quick Start

```bash
python3 check_media.py /Pfad/zum/video.mp4 --pretty
```

Outputs im aktuellen Arbeitsverzeichnis:
- `video.mp4.mediaprofile.json`
- `video.mp4.validationreport.json`

---

## CLI-Referenz

```bash
python3 check_media.py INPUT
  [--profile ZIELWERTE.json]
  [--pretty]
  [--out-dir DIR]
  [--media-out PFAD.json]
  [--report-out PFAD.json]
  [--hash-algo md5|sha1|sha256|sha512]
```

**Exit Codes**  
- `0` → passend  
- `2` → failed

---

## Validierungs-Config (Zielwerte.json)

```json
{
  "dateiformat": "mp4/mov,matroska/webm",
  "farbraum": "RGB,YUV",
  "bit_tiefe": { "min": 8, "max": 8 },
  "bildrate_fps": { "min": 29.9, "max": 30.1 },
  "frame_rate_mode": "CFR", 
  "auflösung": {
    "x": { "min": 1920, "max": 1920 },
    "y": { "min": 1080, "max": 1080 }
  }
}
```

---

## Output-Beispiele

### `<input>.mediaprofile.json`
```json
{
  "filename": "video.mp4",
  "file_id": { "algorithm": "sha256", "hash": "ab12...ef" },
  "quelle": "/Pfad/video.mp4",
  "lesbar": true,
  "non_zero_bytes": true,
  "dateiformat": "mp4/mov",
  "auflösung": { "x": 1920, "y": 1080 },
  "bildrate_fps": 29.97003,
  "frame_rate_mode": "CFR",
  "farbraum": "YUV",
  "bit_tiefe": 8
}
```

### `<input>.validationreport.json`
```json
{
  "filename": "video.mp4",
  "file_id": { "algorithm": "sha256", "hash": "ab12...ef" },
  "media_profile": { ... },
  "validation": {
    "status": "passend",
    "details": {
      "dateiformat":   { "ok": true,  "info": "'mp4/mov' erlaubt" },
      "farbraum":      { "ok": true,  "info": "'YUV' erlaubt" },
      "bit_tiefe":     { "ok": true,  "info": "min=8, max=8, wert=8" },
      "bildrate_fps":  { "ok": true,  "info": "min=29.9, max=30.1, wert=29.97003" },
      "frame_rate_mode": { "ok": true, "info": "'CFR' erlaubt" },
      "auflösung.x":   { "ok": true,  "info": "min=1920, max=1920, wert=1920" },
      "auflösung.y":   { "ok": true,  "info": "min=1080, max=1080, wert=1080" }
    }
  }
}
```

---

## .gitignore

```gitignore
*.mediaprofile.json
*.validationreport.json
```
