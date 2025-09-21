#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
import sys
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import av  # pip install av
import statistics

# ---------- Container-Erkennung via Magic Bytes ----------

MAGIC_MAP = [
    (b"\x1A\x45\xDF\xA3", "matroska/webm"),
    (b"RIFF", "avi/wav/riff"),
    (b"OggS", "ogg"),
    (b"\x47", "mpeg-ts"),
]

def sniff_container(path: Path) -> str:
    if not path.exists() or path.stat().st_size < 4:
        return "unknown"
    with open(path, "rb") as f:
        head = f.read(4096)
    if b"ftyp" in head[:64]:
        return "mp4/mov"
    if head.startswith(b"RIFF") and len(head) >= 12:
        fourcc = head[8:12]
        if fourcc == b"AVI ":
            return "avi"
        elif fourcc == b"WAVE":
            return "wav"
    for sig, name in MAGIC_MAP:
        if head.startswith(sig):
            if name == "mpeg-ts" and not _looks_like_mpeg_ts(head):
                continue
            return name
    if _looks_like_mpeg_ts(head):
        return "mpeg-ts"
    return "unknown"

def _looks_like_mpeg_ts(buf: bytes) -> bool:
    if len(buf) < 188 * 5:
        return False
    for off in range(188):
        ok = True
        for i in range(5):
            idx = off + 188 * i
            if idx >= len(buf) or buf[idx] != 0x47:
                ok = False
                break
        if ok:
            return True
    return False

# ---------- Pixelformat → Farbraum/Bittiefe ----------

KNOWN_8BIT_NO_NUMBER = {
    "yuv420p","yuv422p","yuv444p","yuvj420p","yuvj422p","yuvj444p","nv12","nv21",
    "rgba","bgra","argb","abgr","gbrp","gbrap","pal8","gray","ya8"
}

def classify_farbraum(pix_fmt: str) -> str:
    s = pix_fmt.lower()
    if s.startswith(("rgb","bgr","gbr")):
        return "RGB"
    if s.startswith(("gray","ya")):
        return "GRAY"
    if s.startswith(("yuv","nv","uyvy","yuyv","p0","p1")):
        return "YUV"
    return "UNKNOWN"

def bitdepth_from_pixfmt(pix_fmt: str) -> Optional[int]:
    if not pix_fmt:
        return None
    s = pix_fmt.lower()
    if s in KNOWN_8BIT_NO_NUMBER:
        return 8
    if "p010" in s:
        return 10
    if "p016" in s:
        return 16
    m = re.search(r"(\d{2})", s)
    if m:
        val = int(m.group(1))
        if s in ("rgb24","bgr24"):
            return 8
        if s.startswith(("rgba64","bgra64","argb64","abgr64")):
            return 16
        if s.startswith(("rgb48","bgr48")):
            return 16
        return val
    return 8

# ---------- CFR/VFR-Erkennung ----------

def detect_frame_rate_mode(pts_sec: List[float], tol_rel: float = 0.005, min_ratio: float = 0.95) -> Optional[str]:
    if len(pts_sec) < 3:
        return None
    dts = [pts_sec[i] - pts_sec[i-1] for i in range(1, len(pts_sec)) if pts_sec[i] > pts_sec[i-1]]
    if not dts:
        return None
    med = statistics.median(dts)
    if med <= 0:
        return None
    within = [abs(dt - med) / med <= tol_rel for dt in dts]
    return "CFR" if sum(within)/len(dts) >= min_ratio else "VFR"

# ---------- Dekodierung & Messung ----------

def decode_video_info(path: str) -> Tuple[Optional[str], Optional[Tuple[int,int]], Optional[float], Optional[str], Optional[float]]:
    try:
        container = av.open(path)
    except av.AVError:
        return None, None, None, None, None
    vstream = next((s for s in container.streams if s.type == "video"), None)
    if vstream is None:
        return None, None, None, None, None

    pts_sec: List[float] = []
    pix_fmt_name = None
    width = height = None
    duration_sec: Optional[float] = None

    for frame in container.decode(vstream):
        if pix_fmt_name is None:
            pix_fmt_name = frame.format.name
            width, height = frame.width, frame.height
        if frame.pts is not None and vstream.time_base is not None:
            pts_sec.append(float(frame.pts) * float(vstream.time_base))

    fps_measured = None
    if len(pts_sec) >= 2:
        span = pts_sec[-1] - pts_sec[0]
        if span > 0:
            fps_measured = (len(pts_sec) - 1) / span

    if vstream.duration is not None and vstream.time_base is not None:
        duration_sec = float(vstream.duration) * float(vstream.time_base)
    elif container.duration is not None:
        duration_sec = float(container.duration) * float(av.time_base)
    elif pts_sec:
        duration_sec = pts_sec[-1] - pts_sec[0]
        if len(pts_sec) > 1 and fps_measured:
            duration_sec += 1.0 / fps_measured

    return (
        pix_fmt_name,
        (width, height) if width and height else None,
        fps_measured,
        detect_frame_rate_mode(pts_sec),
        duration_sec,
    )

# ---------- Hashing ----------

def compute_file_hash(path: Path, algo: str = "sha256", chunk_size: int = 1024 * 1024) -> Optional[str]:
    algo = algo.lower()
    try:
        h = hashlib.new(algo)
    except ValueError:
        h = hashlib.sha256()
        algo = "sha256"
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

# ---------- Media-Profil ----------

def build_media_profile(input_path: str, hash_algo: str) -> Dict[str, Any]:
    p = Path(input_path)
    exists = p.exists()
    size = p.stat().st_size if exists else 0

    file_id = {
        "algorithm": hash_algo.lower(),
        "hash": compute_file_hash(p, hash_algo) if exists and size > 0 else None
    }

    prof: Dict[str, Any] = {
        "filename": p.name,
        "file_id": file_id,
        "quelle": str(p),
        "lesbar": False,
        "non_zero_bytes": size > 0,
        "dateiformat": None,
        "auflösung": {"x": None, "y": None},
        "bildrate_fps": None,
        "frame_rate_mode": None,
        "farbraum": None,
        "bit_tiefe": None,
        "videolänge_s": None,
    }

    if not exists or size == 0:
        return prof

    prof["dateiformat"] = sniff_container(p)
    pix_fmt, res, fps, frm_mode, duration_sec = decode_video_info(str(p))
    if pix_fmt or res or fps:
        prof["lesbar"] = True
    if res:
        prof["auflösung"]["x"], prof["auflösung"]["y"] = res
    if fps:
        prof["bildrate_fps"] = round(fps, 6)
    if frm_mode:
        prof["frame_rate_mode"] = frm_mode
    if pix_fmt:
        prof["farbraum"] = classify_farbraum(pix_fmt)
        prof["bit_tiefe"] = bitdepth_from_pixfmt(pix_fmt)
    if duration_sec is not None:
        prof["videolänge_s"] = round(duration_sec, 6)
    return prof

# ---------- Validation ----------

CRITERIA_ORDER = [
    "dateiformat",
    "farbraum",
    "bit_tiefe",
    "bildrate_fps",
    "videolänge_s",
    "frame_rate_mode",
    "auflösung.x",
    "auflösung.y",
]

def _as_allowed_list(value: Any) -> Optional[List[str]]:
    if value is None: return None
    if isinstance(value, str):
        items = [s.strip().lower() for s in value.split(",") if s.strip()]
        return items or None
    if isinstance(value, list):
        return [str(s).strip().lower() for s in value]
    return None

def _in_allowed(val: Optional[str], allowed: Optional[List[str]]) -> Tuple[bool, str, bool]:
    if allowed is None: return True, "keine Prüfung", False
    if val is None:    return False, "Wert fehlt", True
    ok = val.lower() in allowed
    return ok, (f"'{val}' erlaubt" if ok else f"'{val}' nicht in {allowed}"), True

def _in_range(num: Optional[float], spec: Optional[Dict[str, Any]]) -> Tuple[bool, str, bool]:
    if spec is None: return True, "keine Prüfung", False
    if num is None:  return False, "Wert fehlt", True
    mn = spec.get("min", None); mx = spec.get("max", None)
    if isinstance(mn, str) and mn.strip() == "": mn = None
    if isinstance(mx, str) and mx.strip() == "": mx = None
    ok = ((mn is None) or (num >= float(mn))) and ((mx is None) or (num <= float(mx)))
    parts = []
    parts.append(f"min={mn}" if mn is not None else "min=-∞")
    parts.append(f"max={mx}" if mx is not None else "max=+∞")
    parts.append(f"wert={num}")
    return ok, ", ".join(parts), True

def validate_full(media_profile: Dict[str, Any], profile_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    overall_ok = True
    counted_any = False

    pf = profile_spec or {}
    pf_dateiformat = _as_allowed_list(pf.get("dateiformat"))
    pf_farbraum   = _as_allowed_list(pf.get("farbraum"))
    pf_bit_tiefe  = pf.get("bit_tiefe") if isinstance(pf.get("bit_tiefe"), dict) else None
    pf_fps        = pf.get("bildrate_fps") if isinstance(pf.get("bildrate_fps"), dict) else None
    pf_duration   = pf.get("videolänge_s") if isinstance(pf.get("videolänge_s"), dict) else None
    pf_frmode     = _as_allowed_list(pf.get("frame_rate_mode"))
    pf_ax         = pf.get("auflösung", {}).get("x") if isinstance(pf.get("auflösung"), dict) else None
    pf_ay         = pf.get("auflösung", {}).get("y") if isinstance(pf.get("auflösung"), dict) else None

    ok, info, counted = _in_allowed(media_profile.get("dateiformat"), pf_dateiformat)
    details["dateiformat"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    ok, info, counted = _in_allowed(media_profile.get("farbraum"), pf_farbraum)
    details["farbraum"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    ok, info, counted = _in_range(media_profile.get("bit_tiefe"), pf_bit_tiefe)
    details["bit_tiefe"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    ok, info, counted = _in_range(media_profile.get("bildrate_fps"), pf_fps)
    details["bildrate_fps"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    ok, info, counted = _in_range(media_profile.get("videolänge_s"), pf_duration)
    details["videolänge_s"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    ok, info, counted = _in_allowed(media_profile.get("frame_rate_mode"), pf_frmode)
    details["frame_rate_mode"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    ok, info, counted = _in_range(media_profile.get("auflösung", {}).get("x"), pf_ax)
    details["auflösung.x"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    ok, info, counted = _in_range(media_profile.get("auflösung", {}).get("y"), pf_ay)
    details["auflösung.y"] = {"ok": ok, "info": info}
    overall_ok &= (ok if counted else True); counted_any |= counted

    status = "passend" if (overall_ok or not counted_any) else "failed"
    return {"status": status, "details": {k: details[k] for k in CRITERIA_ORDER}}

# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(description="Media-Profil & Validation-Report (JSON), Hash-ID, CFR/VFR-Erkennung, farbige Konsole.")
    ap.add_argument("input", help="Pfad zur Datei")
    ap.add_argument("--profile", required=True, help="Pfad zur Zielwerte-JSON")
    ap.add_argument("--pretty", action="store_true", help="JSON schön formatiert")
    ap.add_argument("--media-out", help="Pfad für Media-Profil (Default: <cwd>/<input_name>.mediaprofile.json)")
    ap.add_argument("--report-out", help="Pfad für Validation-Report (Default: <cwd>/<input_name>.validationreport.json)")
    ap.add_argument("--out-dir", help="Zielverzeichnis für JSON-Outputs (Default: aktuelles Arbeitsverzeichnis)")
    ap.add_argument("--hash-algo", default="sha256",
                    choices=["md5","sha1","sha256","sha512"],
                    help="Hash-Verfahren für file_id (Default: sha256)")
    ap.add_argument("--summary-only", action="store_true",
                    help="Nur Validierungs-Zusammenfassung in der Konsole ausgeben")
    args = ap.parse_args()

    in_path = Path(args.input)
    base_name = in_path.name

    profile_path = Path(args.profile)
    if not profile_path.exists():
        print(f"Fehler: Zielwerte-Datei '{profile_path}' nicht gefunden.", file=sys.stderr)
        sys.exit(1)

    try:
        profile_spec = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Fehler: Zielwerte-Datei '{profile_path}' konnte nicht geladen werden: {e}", file=sys.stderr)
        sys.exit(1)

    if args.out_dir:
        default_out_dir = Path(args.out_dir)
    else:
        try:
            default_out_dir = in_path.resolve().parent
        except FileNotFoundError:
            default_out_dir = in_path.parent if in_path.parent != Path("") else Path.cwd()
    default_out_dir = default_out_dir if default_out_dir else Path.cwd()

    media_out = Path(args.media_out) if args.media_out else default_out_dir / f"{base_name}.mediaprofile.json"
    report_out = Path(args.report_out) if args.report_out else default_out_dir / f"{base_name}.validationreport.json"

    if not args.summary_only:
        print(f"Schreibe Media-Profil nach: {media_out}")
        print(f"Schreibe Validation-Report nach: {report_out}")

    # Media-Profil inkl. Hash erstellen
    media_profile = build_media_profile(in_path, args.hash_algo)

    # Media-Profil schreiben
    def _write_json(target: Path, payload: Any, label: str) -> bool:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2 if args.pretty else None)
            return True
        except PermissionError:
            print(f"Warnung: Kein Schreibzugriff für {label} '{target}'. Überspringe.")
        except OSError as e:
            print(f"Warnung: Konnte {label} '{target}' nicht schreiben: {e}. Überspringe.")
        return False

    _write_json(media_out, media_profile, "Media-Profil")

    # Profil laden (optional) & Report bauen
    validation = validate_full(media_profile, profile_spec)

    report_obj = {
        "filename": media_profile.get("filename"),
        "file_id": media_profile.get("file_id"),
        "media_profile": media_profile,
        "validation": validation
    }

    # Report schreiben
    _write_json(report_out, report_obj, "Validation-Report")

    # Konsole
    if not args.summary_only:
        print(json.dumps(report_obj, ensure_ascii=False, indent=2 if args.pretty else None))

    if args.summary_only:
        print(f"Datei: {report_obj['filename']}")
        file_id = report_obj.get("file_id", {})
        algo = file_id.get("algorithm")
        hsh = file_id.get("hash")
        print(f"Hash ({algo}): {hsh}\n")

    status = report_obj["validation"]["status"]
    details = report_obj["validation"]["details"]
    print()
    if status == "passend":
        print("\033[92mPASSED\033[0m\n")
    else:
        print("\033[91mFAILED\033[0m\n")
    for key, val in details.items():
        if val["ok"]:
            print(f"  {key:<16} \033[92m✅ {val['info']}\033[0m")
        else:
            print(f"  {key:<16} \033[91m❌ {val['info']}\033[0m")

    sys.exit(0 if status == "passend" else 2)

if __name__ == "__main__":
    main()
