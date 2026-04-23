"""
bb-DPI — A Cloudflare WARP–inspired toggle for GoodbyeDPI.
PyQt6 · System-tray · Borderless · Fluent Dark Mode
"""

import sys, os, subprocess, time, logging, configparser
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel,
    QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect,
    QHBoxLayout, QFrame,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPoint, QSize, QRectF,
    QPropertyAnimation, pyqtProperty, QEasingCurve,
)
from PyQt6.QtGui import (
    QIcon, QPainter, QColor, QFont, QFontDatabase,
    QPen, QBrush, QRadialGradient, QLinearGradient,
    QAction, QPixmap, QPainterPath, QCursor,
)

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.environ.get("APPDATA", ""), "bb-DPI")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "app.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logging.info("--- Application Started ---")

# ── Paths ────────────────────────────────────────────────────────────────────
GOODBYEDPI_EXE = "goodbyedpi.exe"

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# ── Config ───────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(get_base_dir(), "config.ini")
config = configparser.ConfigParser()

if not os.path.exists(CONFIG_PATH):
    config["Settings"] = {
        "Arguments": "-5",
        "ModeText": "Mode 5  ·  Alternative 2"
    }
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)
        logging.info("Created default config.ini")
    except Exception as e:
        logging.error(f"Could not create config.ini: {e}")

config.read(CONFIG_PATH, encoding="utf-8")
try:
    GDPI_ARGS = config.get("Settings", "Arguments").split()
    MODE_TEXT = config.get("Settings", "ModeText")
except Exception as e:
    logging.error(f"Error reading config: {e}")
    GDPI_ARGS = ["-5"]
    MODE_TEXT = "Mode 5  ·  Alternative 2"

# Auto-detect: looks next to this script, in ./x86_64, ./goodbyedpi, etc.
def find_gdpi():
    import glob
    base = get_base_dir()
    candidates = [
        base,
        os.path.join(base, "x86_64"),
        os.path.join(base, "goodbyedpi"),
        os.path.join(base, "goodbyedpi", "x86_64"),
    ]
    for d in glob.glob(os.path.join(base, "goodbyedpi*")):
        if os.path.isdir(d):
            candidates.append(d)
            candidates.append(os.path.join(d, "x86_64"))
            
    for d in candidates:
        p = os.path.join(d, GOODBYEDPI_EXE)
        if os.path.isfile(p):
            return d, p
    return base, os.path.join(base, GOODBYEDPI_EXE)

GDPI_DIR, GDPI_PATH = find_gdpi()

# ── Palette ──────────────────────────────────────────────────────────────────
C = dict(
    bg="#020617",       card="#0f172a",      surface="#1e293b",
    border="#1e293b",    text="#f8fafc",      muted="#94a3b8",
    dim="#64748b",       accent="#3b82f6",    green="#10b981",
    red="#ef4444",       ring_off="#334155",  glow="#3b82f6",
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Worker thread – runs goodbyedpi.exe
# ═══════════════════════════════════════════════════════════════════════════════
class DPIWorker(QThread):
    started  = pyqtSignal()
    failed   = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.proc = None

    def run(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            self.proc = subprocess.Popen(
                [GDPI_PATH] + GDPI_ARGS,
                cwd=GDPI_DIR,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            time.sleep(1.2)
            if self.proc.poll() is not None:
                err = self.proc.stderr.read().decode(errors="ignore")
                self.failed.emit(err or "Process exited immediately.")
                return
            self.started.emit()
            self.proc.wait()
        except FileNotFoundError:
            self.failed.emit(f"goodbyedpi.exe not found in:\n{GDPI_DIR}")
        except PermissionError:
            self.failed.emit("Permission denied – run as Administrator.")
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            self.finished_signal.emit()

    def kill(self):
        if self.proc:
            pid = self.proc.pid
            logging.info(f"Terminating goodbyedpi.exe (PID {pid})...")
            try:
                subprocess.run(["taskkill", "/pid", str(pid), "/t", "/f"],
                               capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                logging.info(f"Successfully killed PID {pid}.")
            except Exception as e:
                logging.error(f"Error terminating PID {pid}: {e}")
            try: self.proc.terminate()
            except: pass
            try: self.proc.kill()
            except: pass
            self.proc = None
        else:
            logging.info("No active process to terminate.")


# ═══════════════════════════════════════════════════════════════════════════════
#  Animated toggle switch widget
# ═══════════════════════════════════════════════════════════════════════════════
class ToggleSwitch(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._on = False
        self._connecting = False
        self._hover = False
        self._spin_angle = 0
        self._pulse = 0.0
        self._knob_pos = 0.0  # 0=off, 1=on for internal anim

        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(16)
        self._spin_timer.timeout.connect(self._tick_spin)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(30)
        self._pulse_timer.timeout.connect(self._tick_pulse)

    # ── state setters ──
    def set_connecting(self):
        self._connecting = True
        self._on = False
        self._spin_timer.start()
        self._pulse_timer.stop()
        self.update()

    def set_on(self):
        self._connecting = False
        self._on = True
        self._spin_timer.stop()
        self._pulse_timer.start()
        self.update()

    def set_off(self):
        self._connecting = False
        self._on = False
        self._spin_timer.stop()
        self._pulse_timer.stop()
        self._pulse = 0.0
        self.update()

    # ── timers ──
    def _tick_spin(self):
        self._spin_angle = (self._spin_angle + 4) % 360
        self.update()

    def _tick_pulse(self):
        self._pulse += 0.04
        if self._pulse > 6.2832:
            self._pulse -= 6.2832
        self.update()

    # ── events ──
    def enterEvent(self, ev):
        self._hover = True
        self.update()

    def leaveEvent(self, ev):
        self._hover = False
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    # ── paint ──
    def paintEvent(self, ev):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # Active accent colour
        if self._on:
            accent = QColor(C["green"])
        elif self._connecting:
            accent = QColor(C["accent"])
        else:
            accent = QColor(C["ring_off"])

        # ════════════════════════════════════════════
        #  Outer glow (only when on / connecting)
        # ════════════════════════════════════════════
        if self._on or self._connecting:
            pulse_s = 1.0 + 0.05 * math.sin(self._pulse) if self._on else 1.0
            for i in range(6):
                r = 84 + i * 6
                gc = QColor(accent)
                gc.setAlpha(max(0, 45 - i * 8))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(gc))
                p.drawEllipse(QRectF(cx - r * pulse_s, cy - r * pulse_s,
                                     r * 2 * pulse_s, r * 2 * pulse_s))

        # ════════════════════════════════════════════
        #  Outer ring
        # ════════════════════════════════════════════
        ring_r = 78
        if self._connecting:
            # Background ring
            p.setPen(QPen(QColor(C["surface"]), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2))
            # Spinning accent arc
            arc_pen = QPen(accent, 5)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(arc_pen)
            p.drawArc(QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2),
                       int(self._spin_angle * 16), 100 * 16)
        else:
            thickness = 5 if self._on else 4
            ring_color = QColor(accent)
            if not self._on and self._hover:
                ring_color = QColor("#475569")
            p.setPen(QPen(ring_color, thickness))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2))

        # ════════════════════════════════════════════
        #  Inner face — radial gradient for 3D depth
        # ════════════════════════════════════════════
        face_r = 64
        grad = QRadialGradient(cx, cy - face_r * 0.3, face_r * 1.4)
        if self._on:
            grad.setColorAt(0, QColor("#064e3b"))
            grad.setColorAt(1, QColor("#022c22"))
        else:
            center = QColor("#1e293b") if not self._hover else QColor("#334155")
            edge   = QColor("#0f172a") if not self._hover else QColor("#1e293b")
            grad.setColorAt(0, center)
            grad.setColorAt(1, edge)

        # Face border — subtle ring inside the main ring
        fb = QColor(accent)
        fb.setAlpha(70 if self._on else 50)
        p.setPen(QPen(fb, 2))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(cx - face_r, cy - face_r, face_r * 2, face_r * 2))

        # ════════════════════════════════════════════
        #  Power icon — large & bold
        # ════════════════════════════════════════════
        if self._on:
            ic = QColor(C["green"])
        elif self._connecting:
            ic = QColor(C["accent"])
        else:
            ic = QColor("#94a3b8") if not self._hover else QColor("#cbd5e1")

        icon_pen = QPen(ic, 4.0)
        icon_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        # --- Shape 1: Arc (open circle with gap at top) ---
        # Centered exactly at (cx, cy), radius 22px
        # Gap = 80° at top (from 50° to 130°), so arc starts at 130° spans 280°
        arc_r = 22
        arc_rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
        p.setPen(icon_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, 130 * 16, 280 * 16)

        # --- Shape 2: Vertical bar (separate from arc) ---
        # Originates slightly above center and extends upward past the arc
        p.setPen(icon_pen)
        p.drawLine(int(cx), int(cy - 6), int(cx), int(cy - arc_r - 4))

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("bb-DPI")
        self.setWindowIcon(QIcon(get_resource_path("icon.ico")))
        self.setFixedSize(276, 396)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Remove Windows 11 1px border
        try:
            import ctypes
            hwnd = int(self.winId())
            DWMWA_BORDER_COLOR = 34
            value = ctypes.c_int(0xFFFFFFFE) # DWMWA_COLOR_NONE
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_BORDER_COLOR, ctypes.byref(value), ctypes.sizeof(value)
            )
        except Exception:
            pass

        self._is_running = False
        self._worker = None
        self._uptime_start = 0

        self._build_ui()
        self._build_tray()

        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._update_uptime)

        # For window dragging
        self._drag_pos = QPoint()

        # Startup Validation
        gdpi_d, gdpi_p = find_gdpi()
        if not os.path.isfile(gdpi_p):
            msg = f"goodbyedpi.exe not found!\nPlease place it in:\n{get_base_dir()}"
            logging.error(msg.replace("\n", " "))
            self.status_lbl.setText("Error")
            self.status_lbl.setStyleSheet(f"color: {{C['red']}}; background: transparent;")
            self.sub_lbl.setText("goodbyedpi.exe missing")
            self.toggle.setEnabled(False)

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Root layout
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Card container with rounded corners
        self.card = QFrame(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet(f"""
            #card {{
                background-color: {C['card']};
                border-radius: 18px;
                border: none;
            }}
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── Title bar ──
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(20, 14, 14, 0)

        title_lbl = QLabel("bb-DPI")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {C['text']}; background: transparent;")
        title_bar.addWidget(title_lbl)

        title_bar.addStretch()

        close_btn = QLabel("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close_btn.setFont(QFont("Segoe UI", 11))
        close_btn.setStyleSheet(f"""
            color: {C['muted']};
            background: transparent;
            border-radius: 14px;
        """)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.mousePressEvent = lambda e: self.hide()
        title_bar.addWidget(close_btn)

        card_layout.addLayout(title_bar)

        # ── Toggle ──
        self.toggle = ToggleSwitch()
        self.toggle.clicked.connect(self._on_toggle)
        toggle_wrapper = QHBoxLayout()
        toggle_wrapper.addStretch()
        toggle_wrapper.addWidget(self.toggle)
        toggle_wrapper.addStretch()
        card_layout.addSpacing(18)
        card_layout.addLayout(toggle_wrapper)

        # ── Status ──
        self.status_lbl = QLabel("Disconnected")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setFont(QFont("Segoe UI", 17, QFont.Weight.DemiBold))
        self.status_lbl.setStyleSheet(f"color: {C['dim']}; background: transparent;")
        card_layout.addSpacing(14)
        card_layout.addWidget(self.status_lbl)

        # ── Subtitle ──
        self.sub_lbl = QLabel("Tap the button to connect")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setFont(QFont("Segoe UI", 10))
        self.sub_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        card_layout.addSpacing(2)
        card_layout.addWidget(self.sub_lbl)

        # ── Uptime ──
        self.uptime_lbl = QLabel("")
        self.uptime_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.uptime_lbl.setFont(QFont("Consolas", 11))
        self.uptime_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        card_layout.addSpacing(6)
        card_layout.addWidget(self.uptime_lbl)

        # ── Bottom pill ──
        pill = QFrame()
        pill.setFixedHeight(38)
        pill.setStyleSheet(f"""
            background-color: {C['bg']};
            border-radius: 19px;
        """)
        pill_lay = QHBoxLayout(pill)
        pill_lay.setContentsMargins(16, 0, 16, 0)
        shield = QLabel("🛡")
        shield.setFont(QFont("Segoe UI Emoji", 12))
        shield.setStyleSheet("background: transparent;")
        pill_lay.addWidget(shield)
        self.mode_lbl = QLabel(MODE_TEXT)
        self.mode_lbl.setFont(QFont("Segoe UI", 9))
        self.mode_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        pill_lay.addWidget(self.mode_lbl)
        pill_lay.addStretch()

        card_layout.addStretch()
        card_layout.addWidget(pill, 0, Qt.AlignmentFlag.AlignCenter)
        card_layout.addSpacing(16)

        # Put card in root
        root.addWidget(self.card)

    # ── Tray ────────────────────────────────────────────────────────────
    def _build_tray(self):
        # Build a simple coloured icon in-memory
        self.tray_icon = QSystemTrayIcon(self)
        self._set_tray_icon("off")

        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item:selected {{
                background-color: {C['surface']};
            }}
        """)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _set_tray_icon(self, state):
        """Create a tray icon using the logo with a status indicator."""
        size = 64
        base_pm = QPixmap(get_resource_path(os.path.join("assets", "logo_square.png")))
        if base_pm.isNull():
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
        else:
            pm = base_pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if state == "on":
            colour = QColor(C["green"])
        elif state == "connecting":
            colour = QColor(C["accent"])
        else:
            colour = QColor(C["dim"])
            
        # Draw status indicator (small circle bottom right)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(QBrush(colour))
        p.drawEllipse(44, 44, 16, 16)
        p.end()
        
        self.tray_icon.setIcon(QIcon(pm))

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        # Position near tray (bottom-right of screen)
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 16
        y = screen.bottom() - self.height() - 16
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    # ── Toggle logic ────────────────────────────────────────────────────
    def _on_toggle(self):
        if self._is_running:
            self._stop()
        else:
            self._start()

    def _start(self):
        self.toggle.set_connecting()
        self.status_lbl.setText("Connecting…")
        self.status_lbl.setStyleSheet(f"color: {C['accent']}; background: transparent;")
        self.sub_lbl.setText("Starting bb-DPI")
        self._set_tray_icon("connecting")

        self._worker = DPIWorker()
        self._worker.started.connect(self._on_started)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished_signal.connect(self._on_worker_done)
        self._worker.start()

    def _on_started(self):
        self._is_running = True
        self.toggle.set_on()
        self.status_lbl.setText("Connected")
        self.status_lbl.setStyleSheet(f"color: {C['green']}; background: transparent;")
        self.sub_lbl.setText("DPI bypass is active")
        self._set_tray_icon("on")
        self._uptime_start = time.time()
        self._uptime_timer.start()

    def _on_failed(self, msg):
        self.toggle.set_off()
        self.status_lbl.setText("Failed")
        self.status_lbl.setStyleSheet(f"color: {C['red']}; background: transparent;")
        self.sub_lbl.setText(msg[:60])
        self._set_tray_icon("off")
        QTimer.singleShot(3000, self._reset_ui)

    def _on_worker_done(self):
        if self._is_running:
            self._is_running = False
            self._reset_ui()

    def _stop(self):
        self.status_lbl.setText("Disconnecting…")
        self.status_lbl.setStyleSheet(f"color: {C['accent']}; background: transparent;")
        if self._worker:
            self._worker.kill()
        self._is_running = False
        self._uptime_timer.stop()
        self._reset_ui()

    def _reset_ui(self):
        self.toggle.set_off()
        self.status_lbl.setText("Disconnected")
        self.status_lbl.setStyleSheet(f"color: {C['dim']}; background: transparent;")
        self.sub_lbl.setText("Tap the button to connect")
        self.uptime_lbl.setText("")
        self._set_tray_icon("off")

    def _update_uptime(self):
        if not self._is_running:
            return
        elapsed = int(time.time() - self._uptime_start)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self.uptime_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")

    # ── Custom Shadow Painting ──────────────────────────────────────────
    def paintEvent(self, ev):
        pass

    # ── Dragging ────────────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    # ── Close hides, Quit kills ─────────────────────────────────────────
    def closeEvent(self, ev):
        ev.ignore()
        self.hide()

    def _quit_app(self):
        if self._worker:
            self._worker.kill()
        self.tray_icon.hide()
        QApplication.quit()


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    # Fix High DPI scaling artifacts (like 1px gaps) on Windows 11
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app.setFont(QFont("Segoe UI", 10))

    win = MainWindow()
    win._show_window()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
