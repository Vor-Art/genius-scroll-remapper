#!/usr/bin/env python3
# mouse_remapper_app.py
import os, sys, json, queue
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui
from mouse_remapper_core import RemapperScroll, list_pointer_candidates

APP = "genius-remapper"
CFG_DIR = Path.home()/".config"/APP
CFG = CFG_DIR/"config.json"
AUTOSTART_DIR = Path.home()/".config"/"autostart"
AUTOSTART = AUTOSTART_DIR/"genius-remapper.desktop"

DEFAULTS = dict(
    device_name="Genius Wireless Mouse", vendor=0x0458, product=0x0189,
    scroll_idle=0.15, div_y=60.0, div_x=120.0,
    deadzone=3.0, max_step=3, hold_grace=0.08, click_gap=0.04,
    remember=True, autostart=False
)

def load_cfg():
    try:
        if CFG.exists():
            stored = json.loads(CFG.read_text())
            if "hold_grace" not in stored and "tick_grace" in stored:
                stored["hold_grace"] = stored.get("tick_grace", DEFAULTS["hold_grace"])
            if "click_gap" not in stored:
                stored["click_gap"] = DEFAULTS["click_gap"]
            return {**DEFAULTS, **stored}
    except Exception: pass
    return dict(DEFAULTS)

def save_cfg(c):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(c)
    if not payload.get("remember", True):
        payload = {k: payload[k] for k in ("remember", "autostart")}
    CFG.write_text(json.dumps(payload, indent=2))

def set_autostart(on):
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    if on:
        exe = sys.executable or "python3"
        script = os.path.abspath(sys.argv[0])
        AUTOSTART.write_text(
            f"[Desktop Entry]\nType=Application\nName=Genius Remapper\nExec={exe} {script} --autostart\nX-GNOME-Autostart-enabled=true\n"
        )
    else:
        if AUTOSTART.exists(): AUTOSTART.unlink()

class Main(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Genius Remapper (Scroll only)")
        self.setMinimumSize(700, 520)
        self.cfg = load_cfg()
        self.keys = list_pointer_candidates()
        self.q_in = queue.Queue()
        self.q_act = queue.Queue()
        self.remap = None

        self.tray = QtWidgets.QSystemTrayIcon(self)
        ic = QtGui.QIcon.fromTheme("input-mouse")
        if ic.isNull():
            pm = QtGui.QPixmap(16,16); pm.fill(QtGui.QColor("#4caf50")); ic = QtGui.QIcon(pm)
        self.tray.setIcon(ic)
        menu = QtWidgets.QMenu()
        menu.addAction("Show/Hide", self.toggle_visible)
        self.act_start = menu.addAction("Start", self.start_remap)
        self.act_stop  = menu.addAction("Stop", self.stop_remap); self.act_stop.setEnabled(False)
        menu.addSeparator(); menu.addAction("Quit", QtWidgets.qApp.quit)
        self.tray.setContextMenu(menu); self.tray.show()

        w = QtWidgets.QWidget(); self.setCentralWidget(w)
        outer = QtWidgets.QVBoxLayout(w)

        device_box = QtWidgets.QGroupBox("Pointer device")
        device_form = QtWidgets.QFormLayout(device_box)
        self.cb_dev = QtWidgets.QComboBox()
        self.cb_dev.addItems([f"{n} (v={hex(v)} p={hex(p)})" for n,v,p in self.keys] or ["(no devices)"])
        device_form.addRow("Device:", self.cb_dev)
        outer.addWidget(device_box)

        scroll_box = QtWidgets.QGroupBox("Scroll tuning")
        scroll_form = QtWidgets.QFormLayout(scroll_box)
        self.sb_idle = QtWidgets.QDoubleSpinBox(); self.sb_idle.setRange(0.05,1.0); self.sb_idle.setSingleStep(0.05); self.sb_idle.setSuffix(" s")
        self.sb_v = QtWidgets.QDoubleSpinBox(); self.sb_v.setRange(5.0,400.0); self.sb_v.setSingleStep(5.0)
        self.sb_h = QtWidgets.QDoubleSpinBox(); self.sb_h.setRange(5.0,400.0); self.sb_h.setSingleStep(5.0)
        self.sb_dead = QtWidgets.QDoubleSpinBox(); self.sb_dead.setRange(0.0,20.0); self.sb_dead.setSingleStep(0.5); self.sb_dead.setSuffix(" px")
        self.sb_max = QtWidgets.QSpinBox(); self.sb_max.setRange(1,10)
        scroll_form.addRow("Scroll idle:", self.sb_idle)
        scroll_form.addRow("Vertical speed (↓ faster):", self.sb_v)
        scroll_form.addRow("Horizontal speed:", self.sb_h)
        scroll_form.addRow("Deadzone:", self.sb_dead)
        scroll_form.addRow("Max step per frame:", self.sb_max)
        outer.addWidget(scroll_box)

        detect_box = QtWidgets.QGroupBox("Hold && click detection")
        detect_form = QtWidgets.QFormLayout(detect_box)
        self.sb_hold = QtWidgets.QDoubleSpinBox(); self.sb_hold.setRange(0.05,0.30); self.sb_hold.setSingleStep(0.01); self.sb_hold.setSuffix(" s")
        self.sb_click = QtWidgets.QDoubleSpinBox(); self.sb_click.setRange(0.02,0.20); self.sb_click.setSingleStep(0.005); self.sb_click.setDecimals(3); self.sb_click.setSuffix(" s")
        detect_form.addRow("Hold grace (release delay):", self.sb_hold)
        detect_form.addRow("Click gap (MMB window):", self.sb_click)
        outer.addWidget(detect_box)

        hb = QtWidgets.QHBoxLayout()
        b1 = QtWidgets.QPushButton("Start"); b1.clicked.connect(self.start_remap)
        b2 = QtWidgets.QPushButton("Stop");  b2.clicked.connect(self.stop_remap)
        hb.addWidget(b1); hb.addWidget(b2); outer.addLayout(hb)

        self.chk_mem = QtWidgets.QCheckBox("Remember last config")
        self.chk_auto = QtWidgets.QCheckBox("Start with system"); self.chk_auto.toggled.connect(self.on_auto)
        hb2 = QtWidgets.QHBoxLayout(); hb2.addWidget(self.chk_mem); hb2.addWidget(self.chk_auto); hb2.addStretch(1)
        outer.addLayout(hb2)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        left = QtWidgets.QWidget(); right = QtWidgets.QWidget()
        l_lay = QtWidgets.QVBoxLayout(left); r_lay = QtWidgets.QVBoxLayout(right)
        l_title = QtWidgets.QLabel("Input (received)"); r_title = QtWidgets.QLabel("Actions (emitted)")
        self.log_in  = QtWidgets.QPlainTextEdit(); self.log_in.setReadOnly(True); self.log_in.setMaximumBlockCount(2000)
        self.log_out = QtWidgets.QPlainTextEdit(); self.log_out.setReadOnly(True); self.log_out.setMaximumBlockCount(2000)
        l_lay.addWidget(l_title); l_lay.addWidget(self.log_in, 1)
        r_lay.addWidget(r_title); r_lay.addWidget(self.log_out, 1)
        splitter.addWidget(left); splitter.addWidget(right)
        splitter.setSizes([350, 350])
        outer.addWidget(splitter, 1)

        self.status = QtWidgets.QLabel("Idle"); outer.addWidget(self.status)

        self.cb_dev.currentIndexChanged.connect(self.on_cfg_change)
        for s in (self.sb_idle, self.sb_v, self.sb_h, self.sb_dead, self.sb_max, self.sb_hold, self.sb_click):
            s.valueChanged.connect(self.on_cfg_change)
        self.chk_mem.toggled.connect(self.on_cfg_change)

        self.apply_cfg()
        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.pump); self.timer.start(50)

        if "--autostart" in sys.argv and self.cfg.get("autostart", False):
            QtCore.QTimer.singleShot(400, self.start_remap)

    def apply_cfg(self):
        idx = 0
        for i,(n,v,p) in enumerate(self.keys):
            if n==self.cfg["device_name"] and v==self.cfg["vendor"] and p==self.cfg["product"]:
                idx=i; break
        self.cb_dev.setCurrentIndex(idx)
        self.sb_idle.setValue(self.cfg["scroll_idle"])
        self.sb_v.setValue(self.cfg["div_y"])
        self.sb_h.setValue(self.cfg["div_x"])
        self.sb_dead.setValue(self.cfg["deadzone"])
        self.sb_max.setValue(self.cfg["max_step"])
        self.sb_hold.setValue(self.cfg["hold_grace"])
        self.sb_click.setValue(self.cfg["click_gap"])
        self.chk_mem.setChecked(self.cfg.get("remember", True))
        self.chk_auto.setChecked(self.cfg.get("autostart", False))
        self.update_tip()

    def collect_cfg(self):
        i = max(0, self.cb_dev.currentIndex())
        n,v,p = self.keys[i] if self.keys else ("",0,0)
        return dict(
            device_name=n, vendor=v, product=p,
            scroll_idle=float(self.sb_idle.value()),
            div_y=float(self.sb_v.value()), div_x=float(self.sb_h.value()),
            deadzone=float(self.sb_dead.value()), max_step=int(self.sb_max.value()),
            hold_grace=float(self.sb_hold.value()),
            click_gap=float(self.sb_click.value()),
            remember=bool(self.chk_mem.isChecked()), autostart=bool(self.chk_auto.isChecked())
        )

    def on_cfg_change(self, *a):
        self.cfg = self.collect_cfg(); save_cfg(self.cfg); self.update_tip()

    def on_auto(self, on):
        self.cfg["autostart"]=bool(on); save_cfg(self.cfg)
        try: set_autostart(bool(on))
        except Exception as e: self.q_act.put(f"Autostart error: {e}")

    def start_remap(self):
        if self.remap and self.remap.is_running(): return
        self.cfg = self.collect_cfg(); save_cfg(self.cfg)
        if not self.cfg["device_name"]:
            self.q_act.put("No device selected."); return
        self.remap = RemapperScroll(
            self.cfg["device_name"], self.cfg["vendor"], self.cfg["product"],
            self.cfg["scroll_idle"], self.cfg["div_y"], self.cfg["div_x"],
            self.cfg["deadzone"], self.cfg["max_step"], self.cfg["hold_grace"], self.cfg["click_gap"],
            on_recv=self.q_in.put, on_act=self.q_act.put
        )
        self.remap.start()
        self.status.setText("Running"); self.act_start.setEnabled(False); self.act_stop.setEnabled(True)
        self.q_act.put(f"Starting: {self.cfg['device_name']}")

    def stop_remap(self):
        if self.remap: self.remap.stop()
        self.status.setText("Stopped"); self.act_start.setEnabled(True); self.act_stop.setEnabled(False)
        self.update_tip()

    def pump(self):
        pushed = False
        while True:
            try: msg = self.q_in.get_nowait()
            except queue.Empty: break
            self.log_in.appendPlainText(msg); pushed = True
        while True:
            try: msg = self.q_act.get_nowait()
            except queue.Empty: break
            self.log_out.appendPlainText(msg); pushed = True
        if pushed: self.update_tip()

    def update_tip(self):
        self.tray.setToolTip(
            f"{self.cfg.get('device_name','')} | idle={self.cfg.get('scroll_idle',0):.2f}s "
            f"v={self.cfg.get('div_y',0):.0f} h={self.cfg.get('div_x',0):.0f} "
            f"hold={self.cfg.get('hold_grace',0):.2f}s click={self.cfg.get('click_gap',0):.3f}s"
        )

    def toggle_visible(self): self.setVisible(not self.isVisible())
    def closeEvent(self, e): self.hide(); e.ignore()

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = Main(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
