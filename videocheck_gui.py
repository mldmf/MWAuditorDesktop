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

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QBrush
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
    QPlainTextEdit,
    QFormLayout,
    QGroupBox,
)

APP_TITLE = "VideoCheck"

# --- Ressourcenpfade (PyInstaller-kompatibel) ---
def resource_path(rel_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base_path = Path(__file__).parent
    return str((base_path / rel_path).resolve())

CHECK_MEDIA = resource_path("check_media.py")
DEFAULT_PROFILE = resource_path("zielwerte.json")  # optional
LOGO_PATH = resource_path("logo.png")              # optional (Header/Window-Icon)

SUPPORTED_EXTS = {".mp4", ".mov", ".mkv", ".ts", ".mxf", ".avi", ".webm"}

# ---------------- Worker -----------------
class Worker(QThread):
    finished_one = Signal(str, int, str)  # filepath, exitcode, details
    finished_all = Signal()

    def __init__(self, files: List[str], profile_path: Optional[str]):
        super().__init__()
        self.files = files
        self.profile_path = profile_path

    def run(self):
        for f in self.files:
            code, details = self.run_check(f)
            self.finished_one.emit(f, code, details)
        self.finished_all.emit()

    def run_check(self, filepath: str) -> Tuple[int, str]:
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
            details = extract_brief_summary(out)
            return code, details
        except Exception as e:
            return 99, f"ERROR: {e}"


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

        # Editor
        group = QGroupBox("Inhalt der Zielwerte (JSON)")
        group_layout = QVBoxLayout(group)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("{\n  \"zielwerte_beispiel\": true\n}")
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(' '))
        group_layout.addWidget(self.editor)
        root.addWidget(group)

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
            try:
                self.editor.setPlainText(Path(self.current_path).read_text(encoding="utf-8"))
                self.profile_changed.emit(self.current_path)
            except Exception:
                pass

    # --- Actions ---
    def create_new(self):
        template = {
            "auflösung": {"x": {"min": 0, "max": 99999}, "y": {"min": 0, "max": 99999}},
            "bildrate_fps": {"min": 0, "max": 1000},
            "frame_rate_mode": ["CFR", "VFR"],
            "farbraum": ["RGB", "YUV", "GRAY"],
            "bit_tiefe": {"min": 1, "max": 16},
            "dateiformat": ["mp4", "mov", "mkv", "ts", "mxf", "avi", "webm"],
        }
        self.editor.setPlainText(json.dumps(template, ensure_ascii=False, indent=2))
        self.validate_label.setText("–")
        self.current_path = None
        self.path_edit.setText("")
        self.profile_changed.emit("")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Zielwerte öffnen", str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            json.loads(content)  # sanity check
            self.editor.setPlainText(content)
            self.current_path = path
            self.path_edit.setText(path)
            self.profile_changed.emit(path)
            self.validate_label.setText("–")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Datei konnte nicht geladen werden:\n{e}")

    def save(self):
        if not self.current_path:
            return self.save_as()
        try:
            data = json.loads(self.editor.toPlainText())
            Path(self.current_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.validate_label.setText("Gespeichert ✔")
            self.profile_changed.emit(self.current_path)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Zielwerte speichern unter…", str(Path.home()/"zielwerte.json"), "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(self.editor.toPlainText())
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.current_path = path
            self.path_edit.setText(path)
            self.validate_label.setText("Gespeichert ✔")
            self.profile_changed.emit(path)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def validate(self):
        try:
            data = json.loads(self.editor.toPlainText())
            required = ["auflösung", "bildrate_fps", "frame_rate_mode", "farbraum", "bit_tiefe", "dateiformat"]
            missing = [k for k in required if k not in data]
            if missing:
                self.validate_label.setText(f"Fehlende Felder: {', '.join(missing)}")
                return
            self.validate_label.setText("Valid JSON ✔")
        except Exception as e:
            self.validate_label.setText(f"Ungültig: {e}")

    def get_current_profile_path(self) -> Optional[str]:
        return self.current_path


class CheckTab(QWidget):
    def __init__(self, logo_path: Optional[str]):
        super().__init__()
        v = QVBoxLayout(self)

        # Header mit Logo + Titel
        header = QHBoxLayout()
        logo_label = QLabel()
        if logo_path and Path(logo_path).exists():
            pm = QPixmap(logo_path)
            if not pm.isNull():
                logo_label.setPixmap(pm.scaledToHeight(36, Qt.SmoothTransformation))
        title = QLabel("VideoCheck — MatchWinners")
        title.setStyleSheet("font-weight: 600; font-size: 18px;")
        header.addWidget(logo_label)
        header.addWidget(title)
        header.addStretch()
        v.addLayout(header)

        # Drop-Zone
        self.drop = DropArea()
        v.addWidget(self.drop)

        # Tabelle
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Datei", "Pfad", "Status", "Details"])
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
        if Path(LOGO_PATH).exists():
            self.setWindowIcon(QIcon(LOGO_PATH))  # Laufzeit-Icon (Dock-Icon via --icon beim Build)

        self.files: List[str] = []
        self.worker: Optional[Worker] = None
        self.active_profile: Optional[str] = DEFAULT_PROFILE if Path(DEFAULT_PROFILE).exists() else None

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # Tab 1: Prüfen
        self.check_tab = CheckTab(LOGO_PATH if Path(LOGO_PATH).exists() else None)
        tabs.addTab(self.check_tab, "Prüfen")

        # Tab 2: Zielwerte
        self.profile_tab = ProfileEditor(self.active_profile)
        self.profile_tab.profile_changed.connect(self.set_active_profile)
        tabs.addTab(self.profile_tab, "Zielwerte")

        # Verkabelung Check-Tab
        self.check_tab.drop.files_dropped.connect(self.add_files)
        self.check_tab.btn_add.clicked.connect(self.pick_files)
        self.check_tab.btn_run.clicked.connect(self.run_checks)
        self.check_tab.btn_clear.clicked.connect(self.clear_all)
        self.check_tab.btn_export.clicked.connect(self.export_log)

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
                added += 1
        if added:
            self.run_checks()

    def add_row(self, filepath: str):
        row = self.check_tab.table.rowCount()
        self.check_tab.table.insertRow(row)
        name_item = QTableWidgetItem(Path(filepath).name)
        path_item = QTableWidgetItem(filepath)
        status_item = QTableWidgetItem("WARTET")
        details_item = QTableWidgetItem("")
        for it in (name_item, path_item, status_item, details_item):
            it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.check_tab.table.setItem(row, 0, name_item)
        self.check_tab.table.setItem(row, 1, path_item)
        self.check_tab.table.setItem(row, 2, status_item)
        self.check_tab.table.setItem(row, 3, details_item)

    def clear_all(self):
        self.files.clear()
        self.check_tab.table.setRowCount(0)

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
                "details": self.check_tab.table.item(row, 3).text(),
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
            self.check_tab.table.item(row, 3).setText("")
        self.check_tab.btn_run.setEnabled(False)
        self.worker = Worker(self.files, self.active_profile)
        self.worker.finished_one.connect(self.update_result)
        self.worker.finished_all.connect(self.finish_run)
        self.worker.start()

    def update_result(self, filepath: str, code: int, details: str):
        for row in range(self.check_tab.table.rowCount()):
            if self.check_tab.table.item(row, 1).text() == filepath:
                status_item = self.check_tab.table.item(row, 2)
                details_item = self.check_tab.table.item(row, 3)

                if code == 0:
                    status_item.setText("PASS")
                    status_item.setBackground(QBrush(QColor(144, 238, 144)))  # hellgrün
                elif code == 2:
                    status_item.setText("FAIL")
                    status_item.setBackground(QBrush(QColor(255, 182, 193)))  # hellrot/rosa
                elif code == 99:
                    status_item.setText("ERROR")
                    status_item.setBackground(QBrush(QColor(255, 255, 153)))  # gelb
                else:
                    status_item.setText(f"Exit {code}")
                    status_item.setBackground(QBrush())  # Standard

                details_item.setText(details)
                break



    def finish_run(self):
        self.check_tab.btn_run.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    if Path(LOGO_PATH).exists():
        app.setWindowIcon(QIcon(LOGO_PATH))  # Laufzeit-Icon
    w = MainWindow()
    w.resize(980, 640)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
