#!/usr/bin/env python3
# genius_remapper_app.py
import os, sys, json, queue
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui
from mouse_remapper import Remapper, list_pointer_candidates

APP_NAME = "genius-remapper"
CFG_DIR = Path.home()/".config"/APP_NAME
CFG_PATH = CFG_DIR/"config.json"
AUTOSTART_DIR = Path.home()/".config"/"autostart"
AUTOSTART_PATH = AUTOSTART_DIR/"genius-remapper.desktop"

DEFAULTS = dict(
    device_name="Genius Wireless Mouse",
    vendor=0x0458, product=0x0189,
    tap_window=0.20, scroll_idle=0.15,
    div_y=60.0, div_x=120.0,
    remember=True, autostart=False
)

def load_cfg():
    try:
        if CFG_PATH.exists():
            return {**DEFAULTS, **json.loads(CFG_PATH.read_text())}
    except Exception: pass
    return dict(DEFAULTS)

def save_cfg(cfg):
    if not cfg.get("remember", True): return
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    CFG_PATH.write_text(json.dumps(cfg, indent=2))

def set_autostart(enabled):
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    if enabled:
        exe = sys.executable or "python3"
        script = os.path.abspath(sys.argv[0])
        AUTOSTART_PATH.write_text(
            f"[Desktop Entry]\nType=Application\nName=Genius Remapper\nExec={exe} {script} --autostart\nX-GNOME-Autostart-enabled=true\n"
        )
    else:
        if AUTOSTART_PATH.exists(): AUTOSTART_PATH.unlink()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Genius Remapper"); self.setMinimumSize(520, 420)
        self.cfg = load_cfg()
        self.debug_q = queue.Queue()
        self.remap = None

        # tray
        self.tray = QtWidgets.QSystemTrayIcon(self)
        icon = QtGui.QIcon.fromTheme("input-mouse")
        if icon.isNull():
            pm = QtGui.QPixmap(16,16); pm.fill(QtGui.QColor("#4caf50")); icon = QtGui.QIcon(pm)
        self.tray.setIcon(icon)
        m = QtWidgets.QMenu()
        m.addAction("Show/Hide", self.toggle_visible)
        self.act_start = m.addAction("Start", self.start_remap)
        self.act_stop  = m.addAction("Stop", self.stop_remap); self.act_stop.setEnabled(False)
        m.addSeparator(); m.addAction("Quit", QtWidgets.qApp.quit)
        self.tray.setContextMenu(m); self.tray.show()

        # ui
        w = QtWidgets.QWidget(); self.setCentralWidget(w)
        lay = QtWidgets.QVBoxLayout(w)
        form = QtWidgets.QFormLayout(); lay.addLayout(form)

        self.cb_device = QtWidgets.QComboBox(); form.addRow("Device:", self.cb_device)
        self.sb_tap = QtWidgets.QDoubleSpinBox(); self.sb_tap.setRange(0.05,1.0); self.sb_tap.setSingleStep(0.05); self.sb_tap.setSuffix(" s")
        self.sb_idle= QtWidgets.QDoubleSpinBox(); self.sb_idle.setRange(0.05,1.0); self.sb_idle.setSingleStep(0.05); self.sb_idle.setSuffix(" s")
        self.sb_v   = QtWidgets.QDoubleSpinBox(); self.sb_v.setRange(5.0,400.0); self.sb_v.setSingleStep(5.0)
        self.sb_h   = QtWidgets.QDoubleSpinBox(); self.sb_h.setRange(5.0,400.0); self.sb_h.setSingleStep(5.0)
        form.addRow("Tap Window:", self.sb_tap)
        form.addRow("Scroll Idle:", self.sb_idle)
        form.addRow("Vertical speed (↓ faster):", self.sb_v)
        form.addRow("Horizontal speed:", self.sb_h)

        hb = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start"); self.btn_start.clicked.connect(self.start_remap)
        self.btn_stop  = QtWidgets.QPushButton("Stop");  self.btn_stop.clicked.connect(self.stop_remap)
        hb.addWidget(self.btn_start); hb.addWidget(self.btn_stop); lay.addLayout(hb)

        self.cb_remember = QtWidgets.QCheckBox("Remember last config")
        self.cb_autostart= QtWidgets.QCheckBox("Start with system"); self.cb_autostart.toggled.connect(self.on_autostart_toggled)
        hb2 = QtWidgets.QHBoxLayout(); hb2.addWidget(self.cb_remember); hb2.addWidget(self.cb_autostart); hb2.addStretch(1)
        lay.addLayout(hb2)

        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(1000)
        lay.addWidget(self.log, 1)
        self.status = QtWidgets.QLabel("Idle"); lay.addWidget(self.status)

        self.cb_device.currentIndexChanged.connect(self.on_cfg_change)
        for s in (self.sb_tap, self.sb_idle, self.sb_v, self.sb_h):
            s.valueChanged.connect(self.on_cfg_change)
        self.cb_remember.toggled.connect(self.on_cfg_change)

        self.populate_devices()
        self.apply_cfg_to_ui()

        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.pump_debug); self.timer.start(50)

        if "--autostart" in sys.argv and self.cfg.get("autostart", False):
            QtCore.QTimer.singleShot(500, self.start_remap)

    def populate_devices(self):
        self.keys = list_pointer_candidates()  # [(name,v,p)]
        self.cb_device.clear()
        if not self.keys:
            self.cb_device.addItem("(no devices)")
        else:
            for (n,v,p) in self.keys:
                self.cb_device.addItem(f"{n} (v={hex(v)} p={hex(p)})")
 stop_remap(self):
      
    def apply_cfg_to_ui(self):
        idx = 0
        for i,(n,v,p) in enumerate(self.keys):
            if n==self.cfg["device_name"] and v==self.cfg["vendor"] and p==self.cfg["product"]:
                idx=i; break
        self.cb_device.setCurrentIndex(idx)
        self.sb_tap.setValue(self.cfg["tap_window"])
        self.sb_idle.setValue(self.cfg["scroll_idle"])
        self.sb_v.setValue(self.cfg["div_y"])
        self.sb_h.setValue(self.cfg["div_x"])
        self.cb_remember.setChecked(self.cfg.get("remember", True))
        self.cb_autostart.setChecked(self.cfg.get("autostart", False))
        self.update_tray_tip()

    def collect_cfg(self):
        i = max(0, self.cb_device.currentIndex())
        n,v,p = self.keys[i] if self.keys else ("",0,0)
        return {
            "device_name": n, "vendor": v, "product": p,
            "tap_window": float(self.sb_tap.value()),
            "scroll_idle": float(self.sb_idle.value()),
            "div_y": float(self.sb_v.value()),
            "div_x": float(self.sb_h.value()),
            "remember": bool(self.cb_remember.isChecked()),
            "autostart": bool(self.cb_autostart.isChecked()),
        }

    def on_cfg_change(self, *a):
        self.cfg = self.collect_cfg()
        save_cfg(self.cfg); self.update_tray_tip()

    def on_autostart_toggled(self, on):
        self.cfg["autostart"] = bool(on); save_cfg(self.cfg)
        try: set_autostart(bool(on))
        except Exception as e: self.debug_q.put(f"Autostart error: {e}")

    def start_remap(self):
        if self.remap and self.remap.is_running(): return
        self.cfg = self.collect_cfg(); save_cfg(self.cfg)
        if not self.cfg["device_name"]:
            self.debug_q.put("No device selected."); return
        self.remap = Remapper(
            self.cfg["device_name"], self.cfg["vendor"], self.cfg["product"],
            self.cfg["tap_window"], self.cfg["scroll_idle"], self.cfg["div_y"], self.cfg["div_x"],
            on_debug=self.debug_q.put
        )
        self.remap.start()
        self.status.setText("Running"); self.act_start.setEnabled(False); self.act_stop.setEnabled(True)
        self.debug_q.put(f"Starting: {self.cfg['device_name']}")

    def stop_remap(self):
        if self.remap: self.remap.stop()
        self.status.setText("Stopped"); self.act_start.setEnabled(True); self.act_stop.setEnabled(False)
        self.update_tray_tip()

    def pump_debug(self):
        pushed = False
        while True:
            try:
                msg = self.debug_q.get_nowait()
            except queue.Empty:
                break
            self.log.appendPlainText(msg); pushed = True
        if pushed: self.update_tray_tip()

    def update_tray_tip(self):
        self.tray.setToolTip(f"{self.cfg.get('device_name','')} | tap={self.cfg.get('tap_window',0):.2f}s idle={self.cfg.get('scroll_idle',0):.2f}s")

    def toggle_visible(self):
        self.setVisible(not self.isVisible())

    def closeEvent(self, e):
        self.hide(); e.ignore()  # minimize to tray

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
