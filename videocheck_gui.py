"""
VideoCheck GUI (macOS) — Drag & Drop App für check_media.py

Features (2 Tabs):
- Tab „Prüfen“: Drop-Zone/Dateiauswahl, Tabelle, Prüfen/Leeren/Export
- Tab „Zielwerte“: JSON-Editor mit Neu/Öffnen/Speichern/Validieren
- Logo links + Titel, optional Fenster-Icon; beim .app-Build eigenes Dock-Icon

Voraussetzungen:
  pip install PySide6
  # plus deine PyAV/FFmpeg-Setups laut README

Build (.app):
  pip install pyinstaller
  pyinstaller --noconfirm --windowed --name "VideoCheck" \
    --icon mw.icns \
    --add-data "check_media.py:." \
    --add-data "pixfmt_map.json:." \
    --add-data "logo.png:." \
    videocheck_gui.py
"""

import ast
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict

import av

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QIcon, QColor, QBrush, QFont, QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QTabWidget,
    QLineEdit,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QDoubleSpinBox,
    QListWidget,
    QListWidgetItem,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QSplitter,
    QToolButton,
    QStyle,
    QSizePolicy,
)

APP_TITLE = "Matchwinners Auditor"

# --- Ressourcenpfade (PyInstaller-kompatibel) ---
def resource_path(rel_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base_path = Path(__file__).parent
    return str((base_path / rel_path).resolve())

CHECK_MEDIA = resource_path("check_media.py")
DEFAULT_PROFILE = resource_path("zielwerte.json")  # optional
EMBLEM_PATH = resource_path("mw-emblem.svg")       # optional (Header/Window-Icon)

SUPPORTED_EXTS = {".mp4", ".mov", ".mkv", ".ts", ".mxf", ".avi", ".webm"}

CRITERIA_META = {
    "dateiformat": {"label": "Dateiformat"},
    "farbraum": {"label": "Farbraum"},
    "bit_tiefe": {"label": "Farbgenauigkeit", "unit": "bit"},
    "bildrate_fps": {"label": "Bildrate", "unit": "fps"},
    "videolänge_s": {"label": "Videolänge", "unit": "Sekunden"},
    "frame_rate_mode": {"label": "Bildraten Modus"},
    "auflösung.x": {"label": "Horizontale Auflösung", "unit": "Pixel"},
    "auflösung.y": {"label": "Vertikale Auflösung", "unit": "Pixel"},
}

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


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    try:
        if abs(value - int(round(value))) < 1e-6:
            return f"{int(round(value)):,}".replace(",", ".")
        return ("{:.3f}".format(value)).rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def _format_value(key: str, value: Optional[object]) -> str:
    if value is None:
        return "-"
    meta = CRITERIA_META.get(key, {})
    unit = meta.get("unit")
    if isinstance(value, (int, float)):
        formatted = _format_number(float(value))
    else:
        formatted = str(value)
    if unit and formatted != "-":
        unit_lower = unit.lower()
        if unit_lower == "pixel":
            formatted = f"{formatted} Pixel"
        elif unit_lower == "sekunden":
            formatted = f"{formatted} Sekunden"
        elif unit_lower == "fps":
            formatted = f"{formatted} fps"
        else:
            formatted = f"{formatted} {unit}"
    return formatted


def _get_actual_value(report: Optional[dict], key: str) -> Optional[object]:
    if not report:
        return None
    media = report.get("media_profile", {}) if isinstance(report, dict) else {}
    if key == "videolänge_s":
        return media.get("videolänge_s")
    if key == "bit_tiefe":
        return media.get("bit_tiefe")
    if key == "bildrate_fps":
        return media.get("bildrate_fps")
    if key == "dateiformat":
        return media.get("dateiformat")
    if key == "farbraum":
        return media.get("farbraum")
    if key == "frame_rate_mode":
        return media.get("frame_rate_mode")
    if key == "auflösung.x":
        return media.get("auflösung", {}).get("x")
    if key == "auflösung.y":
        return media.get("auflösung", {}).get("y")
    return None


def _parse_range_info(info: str) -> Tuple[Optional[float], Optional[float]]:
    min_val = max_val = None
    try:
        parts = dict(part.split("=", 1) for part in info.split(",") if "=" in part)
        if "min" in parts:
            min_val = float(parts["min"].strip())
        if "max" in parts:
            max_val = float(parts["max"].strip())
    except Exception:
        return None, None
    return min_val, max_val


def _parse_allowed_info(info: str) -> Tuple[Optional[str], Optional[List[str]]]:
    info = info.strip()
    if " nicht in " in info:
        actual_part, allowed_part = info.split(" nicht in ", 1)
        actual = actual_part.strip().strip("'\"")
        try:
            allowed = ast.literal_eval(allowed_part.strip())
            if isinstance(allowed, list):
                allowed = [str(a).strip() for a in allowed]
            else:
                allowed = [str(allowed)]
        except Exception:
            allowed = [allowed_part.strip()]
        return actual, allowed
    if info.endswith(" erlaubt"):
        actual = info.rsplit(" ", 1)[0].strip().strip("'\"")
        return actual, [actual]
    return None, None


def _expected_from_info(key: str, info: str) -> str:
    if not info:
        return "-"
    info = info.strip()
    if info.startswith("min=") or " min=" in info or "max=" in info:
        min_val, max_val = _parse_range_info(info)
        if min_val is None and max_val is None:
            return info
        if min_val is not None and max_val is not None:
            if abs(min_val - max_val) < 1e-6:
                return _format_value(key, min_val)
            midpoint = (min_val + max_val) / 2.0
            return _format_value(key, midpoint)
        if min_val is not None:
            return _format_value(key, min_val)
        if max_val is not None:
            return _format_value(key, max_val)
        return info
    actual, allowed = _parse_allowed_info(info)
    if allowed:
        return ", ".join(allowed)
    return info


def _actual_from_info_or_report(key: str, info: str, report: Optional[dict]) -> str:
    actual, _allowed = _parse_allowed_info(info)
    if actual:
        return _format_value(key, actual)
    if "wert=" in info:
        try:
            parts = dict(part.split("=", 1) for part in info.split(",") if "=" in part)
            if "wert" in parts:
                return _format_value(key, float(parts["wert"].strip()))
        except Exception:
            pass
    return _format_value(key, _get_actual_value(report, key))

# ---------------- Worker -----------------
class Worker(QThread):
    finished_one = Signal(str, int, object)  # payload enthält u.a. Fehlermetriken
    finished_all = Signal()

    def __init__(self, files: List[str], profile_path: Optional[str]):
        super().__init__()
        self.files = files
        self.profile_path = profile_path

    def run(self):
        for f in self.files:
            code, payload = self.run_check(f)
            self.finished_one.emit(f, code, payload)
        self.finished_all.emit()

    def run_check(self, filepath: str) -> Tuple[int, dict]:
        # python check_media.py <file> [--profile <json>] --summary-only
        cmd = [sys.executable, CHECK_MEDIA, filepath, "--summary-only"]
        if self.profile_path:
            cmd.extend(["--profile", self.profile_path])
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            out = proc.stdout or ""
            code = proc.returncode
            summary = extract_brief_summary(out)
            report = self._load_validation_report(filepath)
            fail_ratio, fail_total = self._compute_fail_ratio(report)
            clipboard_text = self._build_clipboard_text(filepath, code, report, summary, fail_ratio)
            payload = {
                "summary": summary,
                "report": report,
                "fail_ratio": fail_ratio,
                "total": fail_total,
                "clipboard": clipboard_text,
            }
            return code, payload
        except Exception as e:
            return 99, {
                "summary": f"ERROR: {e}",
                "report": None,
                "fail_ratio": "-",
                "total": 0,
                "clipboard": f"Prüfung konnte nicht durchgeführt werden: {e}",
            }

    def _load_validation_report(self, filepath: str) -> Optional[dict]:
        try:
            report_path = Path(filepath).parent / f"{Path(filepath).name}.validationreport.json"
            if report_path.exists():
                return json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def _compute_fail_ratio(self, report: Optional[dict]) -> Tuple[str, int]:
        if not report:
            return "-", 0
        details = report.get("validation", {}).get("details", {})
        if not isinstance(details, dict):
            return "-", 0
        evaluated = [v for v in details.values() if isinstance(v, dict) and v.get("info") != "keine Prüfung"]
        if not evaluated:
            return "-", 0
        fails = sum(1 for v in evaluated if not v.get("ok", False))
        total = len(evaluated)
        return f"{fails}/{total}", total

    def _build_clipboard_text(
        self,
        filepath: str,
        code: int,
        report: Optional[dict],
        summary: str,
        fail_ratio: str,
    ) -> str:
        if not report:
            return summary or f"Prüfung für {Path(filepath).name} (Exit {code})."
        details = report.get("validation", {}).get("details", {})
        status = report.get("validation", {}).get("status", "unbekannt").upper()
        filename = report.get("filename") or Path(filepath).name

        passed_lines: List[str] = []
        failed_lines: List[str] = []
        if isinstance(details, dict):
            for key, info in details.items():
                if not isinstance(info, dict):
                    continue
                text = info.get("info", "")
                if text == "keine Prüfung":
                    continue
                entry = f"- {key}: {'OK' if info.get('ok') else 'NICHT OK'} ({text})"
                if info.get("ok"):
                    passed_lines.append(entry)
                else:
                    failed_lines.append(entry)

        status_text = "Datenprüfung bestanden" if status == "PASSEND" else "Datenprüfung nicht bestanden"
        lines = [
            f"Video: {filename}",
            f"Status: {status_text}",
            f"Fehler: {fail_ratio}",
        ]

        formatted_failed: List[str] = []
        formatted_passed: List[str] = []

        for key in CRITERIA_ORDER:
            if not isinstance(details, dict) or key not in details:
                continue
            info = details[key]
            if not isinstance(info, dict):
                continue
            if info.get("info") == "keine Prüfung":
                continue
            label = CRITERIA_META.get(key, {}).get("label", key)
            expected = _expected_from_info(key, info.get("info", ""))
            actual = _actual_from_info_or_report(key, info.get("info", ""), report)
            if info.get("ok"):
                formatted_passed.append(f"- {label}: {actual}")
            else:
                formatted_failed.append(f"- {label}: {expected} | {actual}")

        if formatted_failed:
            lines.append("")
            lines.append("Nicht erfüllte Kriterien (Soll | Ist):")
            lines.extend(formatted_failed)
        if formatted_passed:
            lines.append("")
            lines.append("Erfüllte Kriterien (Ist):")
            lines.extend(formatted_passed)

        return "\n".join(lines)


def extract_brief_summary(output: str) -> str:
    lines = [ln.strip() for ln in (output or "").splitlines() if ln.strip()]
    # Summary-Block extrahieren
    summary_lines = []
    take = False
    for ln in lines:
        if ln.upper().startswith("SUMMARY"):
            take = True
            continue
        if take:
            if any(ln.upper().startswith(h) for h in ["DETAIL", "DEBUG", "TRACE"]):
                break
            summary_lines.append(ln)
    if summary_lines:
        s = " ".join(summary_lines)
        return s[:600]
    return " ".join(lines[:3])[:600]


# --------------- UI Widgets ---------------
class DropArea(QWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        self.setStyleSheet(
            """
            QWidget { border: 2px dashed #888; border-radius: 12px; }
            QWidget:hover { border-color: #555; }
            """
        )
        layout = QVBoxLayout(self)
        title = QLabel("Dateien hierher ziehen … oder unten 'Dateien wählen' klicken")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

    # Hinweis-Text entfällt, deshalb Methode optional weg:
    # def set_help_text(self, text: str):
    #     pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if not p:
                continue
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in files:
                        if Path(fn).suffix.lower() in SUPPORTED_EXTS:
                            paths.append(str(Path(root) / fn))
            else:
                if Path(p).suffix.lower() in SUPPORTED_EXTS:
                    paths.append(p)
        if paths:
            self.files_dropped.emit(paths)

class ProfileEditor(QWidget):
    """Einfacher JSON-Editor für zielwerte.json mit Laden/Speichern/Neu."""

    profile_changed = Signal(str)  # emits path of currently active profile

    def __init__(self, initial_path: Optional[str]):
        super().__init__()
        self.current_path: Optional[str] = initial_path if initial_path and Path(initial_path).exists() else None

        root = QVBoxLayout(self)

        # Kopf mit aktuellem Pfad + Buttons
        top = QHBoxLayout()
        self.path_edit = QLineEdit(self.current_path or "")
        self.path_edit.setPlaceholderText("Pfad zur Zielwerte-Datei…")
        self.path_edit.setReadOnly(True)
        btn_new = QPushButton("Neu…")
        btn_open = QPushButton("Öffnen…")
        btn_save = QPushButton("Speichern")
        btn_save_as = QPushButton("Speichern unter…")
        for b in (btn_new, btn_open, btn_save, btn_save_as):
            b.setMinimumWidth(120)
        top.addWidget(self.path_edit, 1)
        top.addWidget(btn_new)
        top.addWidget(btn_open)
        top.addWidget(btn_save)
        top.addWidget(btn_save_as)
        root.addLayout(top)

        # Formularfelder
        group = QGroupBox("Zielwerte")
        group_layout = QFormLayout(group)

        def make_spin(minimum: int, maximum: int) -> QSpinBox:
            box = QSpinBox()
            box.setRange(minimum, maximum)
            box.setAlignment(Qt.AlignRight)
            return box

        def make_dspin(minimum: float, maximum: float, decimals: int = 3) -> QDoubleSpinBox:
            box = QDoubleSpinBox()
            box.setRange(minimum, maximum)
            box.setDecimals(decimals)
            box.setAlignment(Qt.AlignRight)
            return box

        self.res_x_min = make_spin(0, 100000)
        self.res_x_max = make_spin(0, 100000)
        self.res_y_min = make_spin(0, 100000)
        self.res_y_max = make_spin(0, 100000)
        self.fps_min = make_dspin(0.0, 1000.0, 3)
        self.fps_max = make_dspin(0.0, 1000.0, 3)
        self.duration_min = make_dspin(0.0, 100000.0, 3)
        self.duration_max = make_dspin(0.0, 100000.0, 3)
        self.bit_min = make_spin(1, 64)
        self.bit_max = make_spin(1, 64)

        self.frame_mode_edit = QLineEdit()
        self.frame_mode_edit.setPlaceholderText("z.B. CFR, VFR")
        self.color_space_edit = QLineEdit()
        self.color_space_edit.setPlaceholderText("z.B. RGB, YUV")
        self.format_edit = QLineEdit()
        self.format_edit.setPlaceholderText("z.B. mp4/mov")

        group_layout.addRow("Auflösung X (min/max)", self._make_min_max_row(self.res_x_min, self.res_x_max))
        group_layout.addRow("Auflösung Y (min/max)", self._make_min_max_row(self.res_y_min, self.res_y_max))
        group_layout.addRow("Bildrate FPS (min/max)", self._make_min_max_row(self.fps_min, self.fps_max))
        group_layout.addRow("Videolänge in s (min/max)", self._make_min_max_row(self.duration_min, self.duration_max))
        group_layout.addRow("Bittiefe (min/max)", self._make_min_max_row(self.bit_min, self.bit_max))
        group_layout.addRow("Frame-Rate-Modus", self.frame_mode_edit)
        group_layout.addRow("Farbraum", self.color_space_edit)
        group_layout.addRow("Dateiformat", self.format_edit)

        root.addWidget(group)

        self._set_defaults()

        # Validierung
        form = QFormLayout()
        self.validate_btn = QPushButton("Validieren")
        self.validate_label = QLabel("–")
        form.addRow(self.validate_btn, self.validate_label)
        root.addLayout(form)

        # Events
        btn_new.clicked.connect(self.create_new)
        btn_open.clicked.connect(self.open_file)
        btn_save.clicked.connect(self.save)
        btn_save_as.clicked.connect(self.save_as)
        self.validate_btn.clicked.connect(self.validate)

        # initial laden
        if self.current_path:
            self._load_from_path(self.current_path, show_errors=False)

    def _make_min_max_row(self, min_widget, max_widget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("min"))
        layout.addWidget(min_widget)
        layout.addWidget(QLabel("max"))
        layout.addWidget(max_widget)
        return row

    def _set_numeric(self, widget, value) -> None:
        if value is None:
            return
        try:
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            else:
                widget.setValue(int(value))
        except (TypeError, ValueError):
            pass

    def _csv_text(self, value) -> str:
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        if value is None:
            return ""
        return str(value)

    def _normalized_csv(self, text: str) -> str:
        items = [part.strip() for part in (text or "").split(",") if part.strip()]
        return ", ".join(items)

    def _default_profile(self) -> dict:
        return {
            "auflösung": {"x": {"min": 0, "max": 99999}, "y": {"min": 0, "max": 99999}},
            "bildrate_fps": {"min": 0.0, "max": 1000.0},
            "videolänge_s": {"min": 0.0, "max": 100000.0},
            "frame_rate_mode": "CFR, VFR",
            "farbraum": "RGB, YUV, GRAY",
            "bit_tiefe": {"min": 1, "max": 16},
            "dateiformat": "mp4, mov, mkv, ts, mxf, avi, webm",
        }

    def _set_defaults(self) -> None:
        self._apply_profile_data(self._default_profile())

    def _apply_profile_data(self, data: dict) -> None:
        aufloesung = data.get("auflösung") if isinstance(data.get("auflösung"), dict) else {}
        ax = aufloesung.get("x") if isinstance(aufloesung, dict) else {}
        ay = aufloesung.get("y") if isinstance(aufloesung, dict) else {}
        if isinstance(ax, dict):
            self._set_numeric(self.res_x_min, ax.get("min"))
            self._set_numeric(self.res_x_max, ax.get("max"))
        if isinstance(ay, dict):
            self._set_numeric(self.res_y_min, ay.get("min"))
            self._set_numeric(self.res_y_max, ay.get("max"))

        fps = data.get("bildrate_fps") if isinstance(data.get("bildrate_fps"), dict) else {}
        if isinstance(fps, dict):
            self._set_numeric(self.fps_min, fps.get("min"))
            self._set_numeric(self.fps_max, fps.get("max"))

        duration = data.get("videolänge_s") if isinstance(data.get("videolänge_s"), dict) else {}
        if isinstance(duration, dict):
            self._set_numeric(self.duration_min, duration.get("min"))
            self._set_numeric(self.duration_max, duration.get("max"))

        bits = data.get("bit_tiefe") if isinstance(data.get("bit_tiefe"), dict) else {}
        if isinstance(bits, dict):
            self._set_numeric(self.bit_min, bits.get("min"))
            self._set_numeric(self.bit_max, bits.get("max"))

        self.frame_mode_edit.setText(self._csv_text(data.get("frame_rate_mode")))
        self.color_space_edit.setText(self._csv_text(data.get("farbraum")))
        self.format_edit.setText(self._csv_text(data.get("dateiformat")))

    def _load_from_path(self, path: str, show_errors: bool = True) -> None:
        try:
            content = Path(path).read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as e:
            if show_errors:
                QMessageBox.critical(self, "Fehler", f"Datei konnte nicht geladen werden:\n{e}")
            return
        self._set_defaults()
        self._apply_profile_data(data)
        self.current_path = path
        self.path_edit.setText(path)
        self.validate_label.setText("–")
        self.profile_changed.emit(path)

    def collect_values(self) -> dict:
        return {
            "auflösung": {
                "x": {"min": int(self.res_x_min.value()), "max": int(self.res_x_max.value())},
                "y": {"min": int(self.res_y_min.value()), "max": int(self.res_y_max.value())},
            },
            "bildrate_fps": {
                "min": round(float(self.fps_min.value()), 6),
                "max": round(float(self.fps_max.value()), 6),
            },
            "videolänge_s": {
                "min": round(float(self.duration_min.value()), 6),
                "max": round(float(self.duration_max.value()), 6),
            },
            "frame_rate_mode": self._normalized_csv(self.frame_mode_edit.text()),
            "farbraum": self._normalized_csv(self.color_space_edit.text()),
            "bit_tiefe": {
                "min": int(self.bit_min.value()),
                "max": int(self.bit_max.value()),
            },
            "dateiformat": self._normalized_csv(self.format_edit.text()),
        }

    def _validate_data(self, data: dict) -> List[str]:
        errors: List[str] = []
        ranges = [
            ("Auflösung X", data["auflösung"]["x"]["min"], data["auflösung"]["x"]["max"]),
            ("Auflösung Y", data["auflösung"]["y"]["min"], data["auflösung"]["y"]["max"]),
            ("Bildrate", data["bildrate_fps"]["min"], data["bildrate_fps"]["max"]),
            ("Videolänge", data["videolänge_s"]["min"], data["videolänge_s"]["max"]),
            ("Bittiefe", data["bit_tiefe"]["min"], data["bit_tiefe"]["max"]),
        ]
        for label, mn, mx in ranges:
            if mn > mx:
                errors.append(f"Min darf nicht größer als Max sein ({label})")

        for label, text in [
            ("Frame-Rate-Modus", data.get("frame_rate_mode")),
            ("Farbraum", data.get("farbraum")),
            ("Dateiformat", data.get("dateiformat")),
        ]:
            if not text:
                errors.append(f"{label} darf nicht leer sein")

        return errors

    # --- Actions ---
    def create_new(self):
        self._set_defaults()
        self.validate_label.setText("–")
        self.current_path = None
        self.path_edit.setText("")
        self.profile_changed.emit("")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Zielwerte öffnen", str(Path.home()), "JSON (*.json)")
        if not path:
            return
        self._load_from_path(path)

    def save(self):
        if not self.current_path:
            return self.save_as()
        data = self.collect_values()
        errors = self._validate_data(data)
        if errors:
            QMessageBox.warning(self, "Ungültige Eingaben", "\n".join(errors))
            return
        try:
            Path(self.current_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.validate_label.setText("Gespeichert ✔")
            self.profile_changed.emit(self.current_path)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Zielwerte speichern unter…", str(Path.home()/"zielwerte.json"), "JSON (*.json)")
        if not path:
            return
        data = self.collect_values()
        errors = self._validate_data(data)
        if errors:
            QMessageBox.warning(self, "Ungültige Eingaben", "\n".join(errors))
            return
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.current_path = path
            self.path_edit.setText(path)
            self.validate_label.setText("Gespeichert ✔")
            self.profile_changed.emit(path)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def validate(self):
        data = self.collect_values()
        errors = self._validate_data(data)
        if errors:
            self.validate_label.setText("; ".join(errors))
        else:
            self.validate_label.setText("Valid ✔")

    def get_current_profile_path(self) -> Optional[str]:
        return self.current_path


class FrameLoader(QThread):
    frame_ready = Signal(int, QImage)
    metadata_ready = Signal(float)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            container = av.open(self.path)
        except av.AVError as exc:
            self.failed.emit(f"Video konnte nicht geöffnet werden: {exc}")
            self.finished.emit()
            return

        fps = 25.0
        try:
            stream = next((s for s in container.streams if s.type == "video"), None)
            if stream is None:
                raise ValueError("Kein Videostream gefunden")

            if stream.average_rate:
                try:
                    fps = float(stream.average_rate)
                except Exception:
                    fps = float(stream.average_rate.numerator) / float(stream.average_rate.denominator)
            elif stream.time_base and stream.duration:
                tb = float(stream.time_base)
                if tb > 0 and stream.duration:
                    duration_sec = float(stream.duration) * tb
                    if duration_sec > 0 and stream.frames:
                        fps = max(1.0, stream.frames / duration_sec)
            fps = max(1.0, fps)
            self.metadata_ready.emit(fps)

            for index, frame in enumerate(container.decode(stream)):
                if self._stop:
                    break
                rgb = frame.to_ndarray(format="rgb24")
                height, width, _ = rgb.shape
                image = QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()
                self.frame_ready.emit(index, image)
        except Exception as exc:
            if not self._stop:
                self.failed.emit(str(exc))
        finally:
            container.close()
            self.finished.emit()


class VideoPreviewTab(QWidget):
    def __init__(self):
        super().__init__()
        self.items: Dict[str, QListWidgetItem] = {}
        self.results: Dict[str, Dict[str, str]] = {}
        self.frames: List[QImage] = []
        self.fps: float = 25.0
        self.loader: Optional[FrameLoader] = None
        self.current_index: int = 0
        self.zoom_factor: float = 1.0
        self.pixmap_item: Optional[QGraphicsPixmapItem] = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance_frame)

        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(240)
        self.list_widget.currentItemChanged.connect(self._handle_selection_changed)
        splitter.addWidget(self.list_widget)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.view, 1)

        controls = QHBoxLayout()

        self.prev_btn = QToolButton()
        self.prev_btn.setText("⟨ Frame")
        self.prev_btn.clicked.connect(self.step_previous)
        controls.addWidget(self.prev_btn)

        self.play_btn = QToolButton()
        self.play_btn.setText("Play")
        self.play_btn.clicked.connect(self.toggle_playback)
        controls.addWidget(self.play_btn)

        self.next_btn = QToolButton()
        self.next_btn.setText("Frame ⟩")
        self.next_btn.clicked.connect(self.step_next)
        controls.addWidget(self.next_btn)

        controls.addSpacing(20)

        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setText("Zoom -")
        self.zoom_out_btn.clicked.connect(lambda: self.adjust_zoom(1 / 1.25))
        controls.addWidget(self.zoom_out_btn)

        self.zoom_reset_btn = QToolButton()
        self.zoom_reset_btn.setText("Original")
        self.zoom_reset_btn.clicked.connect(self.reset_zoom)
        controls.addWidget(self.zoom_reset_btn)

        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setText("Zoom +")
        self.zoom_in_btn.clicked.connect(lambda: self.adjust_zoom(1.25))
        controls.addWidget(self.zoom_in_btn)

        controls.addStretch()

        right_layout.addLayout(controls)

        self.info_label = QLabel("Keine Datei geladen")
        right_layout.addWidget(self.info_label)

        self.list_widget.setCurrentRow(-1)

    # --- Public API ---
    def register_file(self, filepath: str) -> None:
        if filepath in self.items:
            return
        item = QListWidgetItem(f"{Path(filepath).name} — WARTET")
        item.setData(Qt.UserRole, filepath)
        self.list_widget.addItem(item)
        self.items[filepath] = item
        self.results[filepath] = {"status": "WARTET", "fail_ratio": "-", "clipboard": ""}

    def set_result(self, filepath: str, status: str, payload: Optional[dict]) -> None:
        if filepath not in self.items:
            self.register_file(filepath)
        fail_ratio = "-"
        clipboard = ""
        if isinstance(payload, dict):
            fail_ratio = payload.get("fail_ratio", "-") or "-"
            clipboard = payload.get("clipboard", "")
        self.results[filepath] = {
            "status": status,
            "fail_ratio": fail_ratio,
            "clipboard": clipboard,
        }
        self._refresh_item(filepath)

    def clear(self) -> None:
        self.timer.stop()
        self.list_widget.clear()
        self.scene.clear()
        self.pixmap_item = None
        self.items.clear()
        self.results.clear()
        self._stop_loader()
        self.frames = []
        self.info_label.setText("Keine Datei geladen")

    # --- Slots ---
    def toggle_playback(self) -> None:
        if not self.frames:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.play_btn.setText("Play")
            return
        interval = int(1000 / self.fps) if self.fps else 40
        self.timer.start(max(10, interval))
        self.play_btn.setText("Pause")

    def step_next(self) -> None:
        self._advance_frame(step=1, loop=False)

    def step_previous(self) -> None:
        self._advance_frame(step=-1, loop=False)

    def adjust_zoom(self, factor: float) -> None:
        self.zoom_factor *= factor
        self.zoom_factor = max(0.1, min(self.zoom_factor, 10.0))
        self._apply_zoom()

    def reset_zoom(self) -> None:
        self.zoom_factor = 1.0
        self._apply_zoom()

    # --- Internals ---
    def _handle_selection_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        filepath = current.data(Qt.UserRole)
        if not filepath:
            return
        self.load_clip(str(filepath))

    def load_clip(self, filepath: str) -> None:
        self.timer.stop()
        self.play_btn.setText("Play")
        self._stop_loader()
        self.frames = []
        self.current_index = 0
        self.zoom_factor = 1.0
        self.scene.clear()
        self.pixmap_item = None
        self.info_label.setText("Lade Video…")
        self.loader = FrameLoader(filepath)
        self.loader.metadata_ready.connect(self._on_metadata_ready)
        self.loader.frame_ready.connect(self._on_frame_ready)
        self.loader.failed.connect(self._on_loader_failed)
        self.loader.finished.connect(self._on_loader_finished)
        self.loader.start()

    def _advance_frame(self, step: int = 1, loop: bool = True) -> None:
        if not self.frames:
            self.timer.stop()
            self.play_btn.setText("Play")
            return
        frame_count = len(self.frames)
        self.current_index += step
        if self.current_index >= frame_count:
            if loop:
                self.current_index = 0
            else:
                self.current_index = frame_count - 1
                self.timer.stop()
                self.play_btn.setText("Play")
        elif self.current_index < 0:
            if loop:
                self.current_index = frame_count - 1
            else:
                self.current_index = 0
        self._show_current_frame()

    def _show_current_frame(self) -> None:
        if not self.frames:
            return
        if self.current_index >= len(self.frames):
            self.current_index = max(0, len(self.frames) - 1)
        image = self.frames[self.current_index]
        pixmap = QPixmap.fromImage(image)
        if self.pixmap_item is None:
            self.scene.clear()
            self.pixmap_item = self.scene.addPixmap(pixmap)
        else:
            self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self._apply_zoom()
        status = ""
        current_item = self.list_widget.currentItem()
        if current_item:
            filepath = current_item.data(Qt.UserRole)
            status = self.results.get(filepath, {}).get("status", "")
        self._update_info_label(status)

    def _apply_zoom(self) -> None:
        self.view.resetTransform()
        self.view.scale(self.zoom_factor, self.zoom_factor)

    def _refresh_item(self, filepath: str) -> None:
        item = self.items.get(filepath)
        if not item:
            return
        result = self.results.get(filepath, {})
        status = result.get("status", "WARTET")
        fail_ratio = result.get("fail_ratio", "-")
        name = Path(filepath).name
        if status == "PASS":
            text = f"{name} — PASS"
            item.setForeground(QBrush(QColor(34, 139, 34)))
        elif status == "FAIL":
            text = f"{name} — FAIL ({fail_ratio})"
            item.setForeground(QBrush(QColor(178, 34, 34)))
        else:
            text = f"{name} — {status}"
            item.setForeground(QBrush())
        item.setText(text)

    def _update_info_label(self, status: str) -> None:
        if not self.frames:
            self.info_label.setText("Keine Datei geladen")
            return
        frame_count = len(self.frames)
        time_pos = self.current_index / self.fps if self.fps else 0.0
        status_text = status or ""
        info_parts = [
            f"Frame {self.current_index + 1}/{frame_count}",
            f"Zeit {time_pos:.2f}s",
        ]
        if status_text:
            info_parts.append(f"Status: {status_text}")
        self.info_label.setText(" | ".join(info_parts))

    def _stop_loader(self) -> None:
        if self.loader and self.loader.isRunning():
            self.loader.stop()
            self.loader.wait(200)
        self.loader = None

    def _on_metadata_ready(self, fps: float) -> None:
        self.fps = max(1.0, fps)

    def _on_frame_ready(self, index: int, image: QImage) -> None:
        if index >= len(self.frames):
            self.frames.append(image)
        else:
            self.frames[index] = image
        if index == self.current_index or len(self.frames) == 1:
            self._show_current_frame()

    def _on_loader_failed(self, message: str) -> None:
        self.frames = []
        self.scene.clear()
        self.pixmap_item = None
        self.info_label.setText(message)

    def _on_loader_finished(self) -> None:
        if not self.frames:
            return
        if self.current_index >= len(self.frames):
            self.current_index = len(self.frames) - 1
            self._show_current_frame()

class CheckTab(QWidget):
    def __init__(self, logo_path: Optional[str]):
        super().__init__()
        v = QVBoxLayout(self)

        # Header mit Logo + Titel
        header = QHBoxLayout()
        logo_label = QLabel()
        if logo_path and Path(logo_path).exists():
            icon = QIcon(logo_path)
            pm = icon.pixmap(96, 96)
            if not pm.isNull():
                logo_label.setPixmap(pm.scaledToHeight(56, Qt.SmoothTransformation))
        title = QLabel("Matchwinners Auditor")
        title.setStyleSheet("font-weight: 600; font-size: 20px;")
        header.addStretch()
        header.addWidget(logo_label, alignment=Qt.AlignCenter)
        header.addWidget(title, alignment=Qt.AlignCenter)
        header.addStretch()
        v.addLayout(header)

        # Drop-Zone
        self.drop = DropArea()
        v.addWidget(self.drop)

        # Tabelle
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Datei", "Pfad", "Status", "Fehler"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.addWidget(self.table)

        # Buttons
        h = QHBoxLayout()
        self.btn_add = QPushButton("Dateien wählen…")
        self.btn_run = QPushButton("Prüfen")
        self.btn_clear = QPushButton("Leeren")
        self.btn_export = QPushButton("Export Log…")
        for b in (self.btn_add, self.btn_run, self.btn_clear, self.btn_export):
            b.setMinimumWidth(120)
        h.addWidget(self.btn_add)
        h.addWidget(self.btn_run)
        h.addWidget(self.btn_clear)
        h.addWidget(self.btn_export)
        h.addStretch()
        v.addLayout(h)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        icon_path = None
        mw_icns = Path(resource_path("mw.icns"))
        if mw_icns.exists():
            icon_path = mw_icns
        elif Path(EMBLEM_PATH).exists():
            icon_path = Path(EMBLEM_PATH)
        else:
            fallback_png = Path(resource_path("logo.png"))
            if fallback_png.exists():
                icon_path = fallback_png
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))

        self.files: List[str] = []
        self.worker: Optional[Worker] = None
        self.active_profile: Optional[str] = DEFAULT_PROFILE if Path(DEFAULT_PROFILE).exists() else None

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # Tab 1: Prüfen
        self.check_tab = CheckTab(EMBLEM_PATH if Path(EMBLEM_PATH).exists() else None)
        tabs.addTab(self.check_tab, "Prüfen")

        # Tab 2: Zielwerte
        self.profile_tab = ProfileEditor(self.active_profile)
        self.profile_tab.profile_changed.connect(self.set_active_profile)
        tabs.addTab(self.profile_tab, "Zielwerte")

        self.preview_tab = VideoPreviewTab()
        tabs.addTab(self.preview_tab, "Vorschau")

        self.statusBar()  # Statusleiste für kurze Hinweise anlegen

        # Verkabelung Check-Tab
        self.check_tab.drop.files_dropped.connect(self.add_files)
        self.check_tab.btn_add.clicked.connect(self.pick_files)
        self.check_tab.btn_run.clicked.connect(self.run_checks)
        self.check_tab.btn_clear.clicked.connect(self.clear_all)
        self.check_tab.btn_export.clicked.connect(self.export_log)
        self.check_tab.table.itemClicked.connect(self.handle_table_item_clicked)

    # --- Profile ---
    def set_active_profile(self, path: str):
        self.active_profile = path if path else None

    # --- Prüfen ---
    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Videos auswählen",
            str(Path.home()),
            "Video Files (*.mp4 *.mov *.mkv *.ts *.mxf *.avi *.webm);;Alle Dateien (*)",
        )
        if files:
            self.add_files(files)

    def add_files(self, files: List[str]):
        added = 0
        for f in files:
            if f not in self.files:
                self.files.append(f)
                self.add_row(f)
                self.preview_tab.register_file(f)
                added += 1
        if added:
            self.run_checks()

    def add_row(self, filepath: str):
        row = self.check_tab.table.rowCount()
        self.check_tab.table.insertRow(row)
        name_item = QTableWidgetItem(Path(filepath).name)
        path_item = QTableWidgetItem(filepath)
        status_item = QTableWidgetItem("WARTET")
        details_item = QTableWidgetItem("-")
        details_item.setData(Qt.UserRole, None)
        for it in (name_item, path_item, status_item, details_item):
            it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.check_tab.table.setItem(row, 0, name_item)
        self.check_tab.table.setItem(row, 1, path_item)
        self.check_tab.table.setItem(row, 2, status_item)
        self.check_tab.table.setItem(row, 3, details_item)

    def clear_all(self):
        self.files.clear()
        self.check_tab.table.setRowCount(0)
        self.preview_tab.clear()

    def export_log(self):
        if self.check_tab.table.rowCount() == 0:
            QMessageBox.information(self, "Export Log", "Keine Einträge zum Exportieren.")
            return
        default = str(Path.home() / "videocheck_log.json")
        path, _ = QFileDialog.getSaveFileName(self, "Als JSON speichern", default, "JSON (*.json)")
        if not path:
            return
        data = []
        for row in range(self.check_tab.table.rowCount()):
            data.append({
                "file": self.check_tab.table.item(row, 1).text(),
                "status": self.check_tab.table.item(row, 2).text(),
                "fehler": self.check_tab.table.item(row, 3).text(),
            })
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "Export Log", f"Gespeichert: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Konnte nicht speichern:\n{e}")

    def run_checks(self):
        if not self.files:
            return
        if not Path(CHECK_MEDIA).exists():
            QMessageBox.critical(self, "Fehler", f"check_media.py nicht gefunden unter\n{CHECK_MEDIA}")
            return
        # Reset Status
        for row in range(self.check_tab.table.rowCount()):
            self.check_tab.table.item(row, 2).setText("LÄUFT…")
            self.check_tab.table.item(row, 3).setText("-")
            self.check_tab.table.item(row, 3).setData(Qt.UserRole, None)
            filepath = self.check_tab.table.item(row, 1).text()
            self.preview_tab.set_result(filepath, "LÄUFT…", None)
        self.check_tab.btn_run.setEnabled(False)
        self.worker = Worker(self.files, self.active_profile)
        self.worker.finished_one.connect(self.update_result)
        self.worker.finished_all.connect(self.finish_run)
        self.worker.start()

    def update_result(self, filepath: str, code: int, payload: object):
        for row in range(self.check_tab.table.rowCount()):
            if self.check_tab.table.item(row, 1).text() == filepath:
                status_item = self.check_tab.table.item(row, 2)
                details_item = self.check_tab.table.item(row, 3)

                status_label = ""
                if code == 0:
                    status_item.setText("PASS")
                    status_item.setBackground(QBrush(QColor(144, 238, 144)))  # hellgrün
                    status_label = "PASS"
                elif code == 2:
                    status_item.setText("FAIL")
                    status_item.setBackground(QBrush(QColor(255, 182, 193)))  # hellrot/rosa
                    status_label = "FAIL"
                elif code == 99:
                    status_item.setText("ERROR")
                    status_item.setBackground(QBrush(QColor(255, 255, 153)))  # gelb
                    status_label = "ERROR"
                else:
                    status_item.setText(f"Exit {code}")
                    status_item.setBackground(QBrush())  # Standard
                    status_label = status_item.text()

                fail_ratio = "-"
                clipboard_text = ""
                if isinstance(payload, dict):
                    fail_ratio = payload.get("fail_ratio", "-") or "-"
                    clipboard_text = payload.get("clipboard") or payload.get("summary") or ""
                else:
                    clipboard_text = str(payload)
                details_item.setText(fail_ratio)
                details_item.setData(Qt.UserRole, clipboard_text)

                self.preview_tab.set_result(filepath, status_label, payload if isinstance(payload, dict) else {"fail_ratio": fail_ratio, "clipboard": clipboard_text})
                break



    def finish_run(self):
        self.check_tab.btn_run.setEnabled(True)

    def handle_table_item_clicked(self, item: QTableWidgetItem):
        if item.column() != 3:
            return
        clip_text = item.data(Qt.UserRole)
        if not clip_text:
            return
        QApplication.clipboard().setText(str(clip_text))
        self.statusBar().showMessage("Fehlerbericht in die Zwischenablage kopiert", 3000)


def main():
    app = QApplication(sys.argv)
    icon_path = None
    mw_icns = Path(resource_path("mw.icns"))
    if mw_icns.exists():
        icon_path = mw_icns
    elif Path(EMBLEM_PATH).exists():
        icon_path = Path(EMBLEM_PATH)
    else:
        fallback_png = Path(resource_path("logo.png"))
        if fallback_png.exists():
            icon_path = fallback_png
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setFont(QFont("Helvetica Neue"))
    w = MainWindow()
    w.resize(980, 640)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
