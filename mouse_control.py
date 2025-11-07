#!/usr/bin/env python3
import os, sys, json, threading, time, select, queue, traceback
from pathlib import Path
from evdev import InputDevice, UInput, ecodes as E, list_devices
from PyQt5 import QtWidgets, QtCore, QtGui

APP_NAME = "genius-remapper"
CFG_DIR = Path.home()/".config"/"genius-remapper"
CFG_DIR.mkdir(parents=True, exist_ok=True)
CFG_PATH = CFG_DIR/"config.json"
AUTOSTART_DIR = Path.home()/".config"/"autostart"
AUTOSTART_PATH = AUTOSTART_DIR/"genius-remapper.desktop"

DEFAULTS = dict(
    device_name="Genius Wireless Mouse",
    tap_window=0.20,
    scroll_idle=0.15,
    div_y=60.0,
    div_x=120.0,
    remember=True,
    autostart=False
)

def load_cfg():
    try:
        if CFG_PATH.exists():
            d = json.loads(CFG_PATH.read_text())
            return {**DEFAULTS, **d}
    except Exception:
        pass
    return dict(DEFAULTS)

def save_cfg(cfg):
    if not cfg.get("remember", True): return
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        CFG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

def set_autostart(enabled):
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    if enabled:
        exe = sys.executable or "python3"
        script = os.path.abspath(sys.argv[0])
        content = f"""[Desktop Entry]
Type=Application
Name=Genius Remapper
Exec={exe} {script} --autostart
X-GNOME-Autostart-enabled=true
"""
        AUTOSTART_PATH.write_text(content)
    else:
        if AUTOSTART_PATH.exists():
            AUTOSTART_PATH.unlink()

def list_pointer_names():
    seen = {}
    for path in list_devices():
        try:
            d = InputDevice(path)
            caps = d.capabilities().get(E.EV_REL, [])
            if E.REL_X in caps or E.REL_Y in caps or E.REL_WHEEL in caps:
                key = (d.name, d.info.vendor, d.info.product)
                seen[key] = True
        except Exception:
            continue
    items = [f"{name} (v={hex(v)} p={hex(p)})" for (name, v, p) in seen.keys()]
    items.sort()
    return items, list(seen.keys())

class RemapperWorker(QtCore.QObject):
    debug = QtCore.pyqtSignal(str)
    started = QtCore.pyqtSignal(bool)
    stopped = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self._thr = None
        self._stop = threading.Event()

    def start(self, name, vendor, product, tap_window, scroll_idle, div_y, div_x):
        self.stop()
        self._stop.clear()
        self._thr = threading.Thread(
            target=self._run,
            args=(name, vendor, product, tap_window, scroll_idle, div_y, div_x),
            daemon=True
        )
        self._thr.start()

    def stop(self):
        if self._thr and self._thr.is_alive():
            self._stop.set()
            self._thr.join(timeout=1.0)
        self._thr = None
        self.stopped.emit()

    def _run(self, name, vendor, product, tap_window, scroll_idle, div_y, div_x):
        try:
            srcs = []
            for path in list_devices():
                d = InputDevice(path)
                if d.name == name and d.info.vendor == vendor and d.info.product == product:
                    srcs.append(d)
            if not srcs:
                self.debug.emit("No matching devices.")
                self.started.emit(False)
                return

            # Choose nodes that have REL events
            good = []
            for d in srcs:
                caps = d.capabilities().get(E.EV_REL, [])
                if (E.REL_X in caps or E.REL_Y in caps or E.REL_WHEEL in caps or 11 in caps or 12 in caps):
                    good.append(d)
            if not good:
                self.debug.emit("Found devices, but none with EV_REL.")
                self.started.emit(False)
                return

            for d in good:
                d.grab()
            self.debug.emit("Grabbed: " + ", ".join([g.path for g in good]))

            caps = {
                E.EV_KEY: [E.BTN_LEFT, E.BTN_RIGHT, E.BTN_MIDDLE, E.BTN_SIDE, E.BTN_EXTRA],
                E.EV_REL: [E.REL_X, E.REL_Y, E.REL_WHEEL, E.REL_HWHEEL],
            }
            ui = UInput(caps, name="Genius-Remapped Mouse", bustype=good[0].info.bustype,
                        vendor=vendor, product=product)
            self.debug.emit("Created virtual device: Genius-Remapped Mouse")
            self.started.emit(True)

            state = "IDLE"
            t0 = 0.0
            acc_x = 0.0
            acc_y = 0.0
            last_move = 0.0

            def syn(): ui.syn()
            def mmb():
                self.debug.emit("[MMB]")
                ui.write(E.EV_KEY, E.BTN_MIDDLE, 1); syn()
                ui.write(E.EV_KEY, E.BTN_MIDDLE, 0); syn()

            while not self._stop.is_set():
                fds = [d.fd for d in good]
                r,_,_ = select.select(fds, [], [], 0.01)

                now = time.time()
                if state == "PENDING" and now - t0 >= tap_window:
                    mmb(); state = "IDLE"
                if state == "SCROLL" and now - last_move >= scroll_idle:
                    self.debug.emit("[SCROLL END]")
                    state = "IDLE"

                if not r: continue

                for d in [s for s in good if s.fd in r]:
                    for ev in d.read():
                        if ev.type == E.EV_REL:
                            if ev.code in (E.REL_WHEEL, 11, 12):
                                if state == "IDLE":
                                    state = "PENDING"; t0 = time.time()
                                    self.debug.emit("[PENDING]")
                                continue
                            if ev.code in (E.REL_X, E.REL_Y):
                                if state == "PENDING":
                                    state = "SCROLL"
                                    self.debug.emit("[SCROLL START]")
                                if state == "SCROLL":
                                    if ev.code == E.REL_Y:
                                        out = int(-(acc_y + ev.value)/div_y)
                                        acc_y = (acc_y + ev.value) + out*div_y
                                        if out:
                                            self.debug.emit(f"[V {out}]")
                                            ui.write(E.EV_REL, E.REL_WHEEL, out); syn()
                                    else:
                                        out = int((acc_x + ev.value)/div_x)
                                        acc_x = (acc_x + ev.value) - out*div_x
                                        if out:
                                            self.debug.emit(f"[H {out}]")
                                            ui.write(E.EV_REL, E.REL_HWHEEL, out); syn()
                                    last_move = time.time()
                                    continue
                                ui.write(E.EV_REL, ev.code, ev.value); syn()
                        elif ev.type == E.EV_KEY:
                            ui.write(E.EV_KEY, ev.code, ev.value); syn()

            for d in good:
                try: d.ungrab()
                except: pass
            ui.close()
        except Exception as e:
            self.debug.emit("ERROR: " + "".join(traceback.format_exception_only(type(e), e)).strip())
            self.started.emit(False)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Genius Remapper")
        self.setMinimumSize(520, 420)
        self.cfg = load_cfg()

        self.worker = RemapperWorker()
        self.worker.debug.connect(self.on_debug)
        self.worker.started.connect(self.on_started)
        self.worker.stopped.connect(self.on_stopped)

        self.tray = QtWidgets.QSystemTrayIcon(self)
        icon = QtGui.QIcon.fromTheme("input-mouse")
        if icon.isNull():
            pm = QtGui.QPixmap(16,16); pm.fill(QtGui.QColor("#4caf50"))
            icon = QtGui.QIcon(pm)
        self.tray.setIcon(icon)
        m = QtWidgets.QMenu()
        self.act_show = m.addAction("Show/Hide", self.toggle_visible)
        self.act_start = m.addAction("Start", self.start_remap)
        self.act_stop  = m.addAction("Stop", self.stop_remap)
        m.addSeparator()
        self.act_quit = m.addAction("Quit", QtWidgets.qApp.quit)
        self.tray.setContextMenu(m)
        self.tray.show()

        self.build_ui()
        self.populate_devices()
        self.apply_cfg_to_ui()

        if "--autostart" in sys.argv and self.cfg.get("autostart", False):
            QtCore.QTimer.singleShot(500, self.start_remap)

    def build_ui(self):
        w = QtWidgets.QWidget(); self.setCentralWidget(w)
        lay = QtWidgets.QVBoxLayout(w)

        form = QtWidgets.QFormLayout()
        self.cb_device = QtWidgets.QComboBox()
        form.addRow("Device:", self.cb_device)

        self.sb_tap = QtWidgets.QDoubleSpinBox(); self.sb_tap.setRange(0.05, 1.0); self.sb_tap.setSingleStep(0.05); self.sb_tap.setSuffix(" s")
        self.sb_idle = QtWidgets.QDoubleSpinBox(); self.sb_idle.setRange(0.05, 1.0); self.sb_idle.setSingleStep(0.05); self.sb_idle.setSuffix(" s")
        self.sb_v = QtWidgets.QDoubleSpinBox(); self.sb_v.setRange(5.0, 400.0); self.sb_v.setSingleStep(5.0)
        self.sb_h = QtWidgets.QDoubleSpinBox(); self.sb_h.setRange(5.0, 400.0); self.sb_h.setSingleStep(5.0)
        form.addRow("Tap Window:", self.sb_tap)
        form.addRow("Scroll Idle:", self.sb_idle)
        form.addRow("Vertical speed (↓ faster):", self.sb_v)
        form.addRow("Horizontal speed:", self.sb_h)

        lay.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start"); self.btn_start.clicked.connect(self.start_remap)
        self.btn_stop  = QtWidgets.QPushButton("Stop");  self.btn_stop.clicked.connect(self.stop_remap)
        btns.addWidget(self.btn_start); btns.addWidget(self.btn_stop)
        lay.addLayout(btns)

        self.cb_remember = QtWidgets.QCheckBox("Remember last config")
        self.cb_autostart = QtWidgets.QCheckBox("Start with system")
        self.cb_autostart.toggled.connect(self.on_autostart_toggled)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(self.cb_remember); hl.addWidget(self.cb_autostart); hl.addStretch(1)
        lay.addLayout(hl)

        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(1000)
        lay.addWidget(self.log, 1)

        self.status = QtWidgets.QLabel("Idle"); lay.addWidget(self.status)

        self.cb_device.currentIndexChanged.connect(self.on_ui_change)
        for s in (self.sb_tap, self.sb_idle, self.sb_v, self.sb_h, self.cb_remember):
            s.valueChanged.connect(self.on_ui_change) if hasattr(s, "valueChanged") else s.toggled.connect(self.on_ui_change)

    def populate_devices(self):
        items, keys = list_pointer_names()
        self._dev_keys = keys
        self.cb_device.clear()
        if not items:
            self.cb_device.addItem("(no pointer devices found)")
        else:
            for it in items: self.cb_device.addItem(it)

    def apply_cfg_to_ui(self):
        # select device by name
        idx = 0
        for i, (name, v, p) in enumerate(self._dev_keys):
            if name == self.cfg.get("device_name"):
                idx = i; break
        self.cb_device.setCurrentIndex(idx)
        self.sb_tap.setValue(self.cfg["tap_window"])
        self.sb_idle.setValue(self.cfg["scroll_idle"])
        self.sb_v.setValue(self.cfg["div_y"])
        self.sb_h.setValue(self.cfg["div_x"])
        self.cb_remember.setChecked(self.cfg.get("remember", True))
        self.cb_autostart.setChecked(self.cfg.get("autostart", False))

    def collect_cfg_from_ui(self):
        i = max(0, self.cb_device.currentIndex())
        name, v, p = self._dev_keys[i] if self._dev_keys else ("", 0, 0)
        d = dict(
            device_name=name,
            tap_window=float(self.sb_tap.value()),
            scroll_idle=float(self.sb_idle.value()),
            div_y=float(self.sb_v.value()),
            div_x=float(self.sb_h.value()),
            remember=bool(self.cb_remember.isChecked()),
            autostart=bool(self.cb_autostart.isChecked()),
        )
        return d, (name, v, p)

    def on_ui_change(self, *a):
        self.cfg, _ = self.collect_cfg_from_ui()
        save_cfg(self.cfg)
        self.tray.setToolTip(f"{self.cfg['device_name']} | tap={self.cfg['tap_window']:.2f}s idle={self.cfg['scroll_idle']:.2f}s")

    def on_autostart_toggled(self, on):
        self.cfg["autostart"] = bool(on)
        save_cfg(self.cfg)
        try:
            set_autostart(on)
        except Exception as e:
            self.on_debug(f"Autostart error: {e}")

    def start_remap(self):
        self.cfg, key = self.collect_cfg_from_ui()
        save_cfg(self.cfg)
        name, v, p = key
        if not name:
            self.on_debug("No device selected."); return
        self.on_debug(f"Starting on: {name} v={hex(v)} p={hex(p)}")
        self.worker.start(name, v, p, self.cfg["tap_window"], self.cfg["scroll_idle"], self.cfg["div_y"], self.cfg["div_x"])
        self.status.setText("Starting…")

    def stop_remap(self):
        self.worker.stop()
        self.status.setText("Stopped")

    def on_started(self, ok):
        self.status.setText("Running" if ok else "Failed")
        self.act_start.setEnabled(not ok); self.act_stop.setEnabled(True)

    def on_stopped(self):
        self.act_start.setEnabled(True); self.act_stop.setEnabled(False)
        self.tray.setToolTip("Idle")

    def on_debug(self, s):
        self.log.appendPlainText(s)
        self.tray.setToolTip(s)

    def toggle_visible(self):
        self.setVisible(not self.isVisible())

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
