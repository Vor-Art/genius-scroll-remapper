#!/usr/bin/env python3
# mouse_remapper.py
import time, select, threading, traceback
from evdev import InputDevice, UInput, ecodes as E, list_devices

def list_pointer_candidates():
    seen = {}
    for path in list_devices():
        try:
            d = InputDevice(path)
            rel = d.capabilities().get(E.EV_REL, [])
            if E.REL_X in rel or E.REL_Y in rel or E.REL_WHEEL in rel or 11 in rel or 12 in rel:
                seen[(d.name, d.info.vendor, d.info.product)] = True
        except Exception:
            pass
    return sorted(seen.keys())  # list of (name, vendor, product)

class Remapper:
    def __init__(self, name, vendor, product, tap_window=0.20, scroll_idle=0.15,
                 div_y=60.0, div_x=120.0, virtual_name="Genius-Remapped Mouse", on_debug=None):
        self.name, self.vendor, self.product = name, vendor, product
        self.tap_window, self.scroll_idle = float(tap_window), float(scroll_idle)
        self.div_y, self.div_x = float(div_y), float(div_x)
        self.virtual_name = virtual_name
        self.on_debug = on_debug or (lambda _msg: None)
        self._thr = None
        self._stop = threading.Event()

    def start(self):
        self.stop()
        self._stop.clear()
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self):
        if self._thr and self._thr.is_alive():
            self._stop.set()
            self._thr.join(timeout=1.0)
        self._thr = None

    def is_running(self):
        return bool(self._thr and self._thr.is_alive())

    def _run(self):
        try:
            # gather all matching event nodes with relative caps
            srcs = []
            for path in list_devices():
                d = InputDevice(path)
                if d.name == self.name and d.info.vendor == self.vendor and d.info.product == self.product:
                    rel = d.capabilities().get(E.EV_REL, [])
                    if E.REL_X in rel or E.REL_Y in rel or E.REL_WHEEL in rel or 11 in rel or 12 in rel:
                        srcs.append(d)
            if not srcs:
                self.on_debug("No matching devices with EV_REL.")
                return

            for d in srcs: d.grab()
            self.on_debug("Grabbed: " + ", ".join([d.path for d in srcs]))

            caps = {
                E.EV_KEY: [E.BTN_LEFT, E.BTN_RIGHT, E.BTN_MIDDLE, E.BTN_SIDE, E.BTN_EXTRA],
                E.EV_REL: [E.REL_X, E.REL_Y, E.REL_WHEEL, E.REL_HWHEEL],
            }
            ui = UInput(caps, name=self.virtual_name, bustype=srcs[0].info.bustype,
                        vendor=self.vendor, product=self.product)
            self.on_debug(f"Created virtual device: {self.virtual_name}")

            state = "IDLE"
            t0 = 0.0
            acc_x = acc_y = 0.0
            last_move = 0.0

            def syn(): ui.syn()
            def mmb():
                self.on_debug("[MMB]")
                ui.write(E.EV_KEY, E.BTN_MIDDLE, 1); syn()
                ui.write(E.EV_KEY, E.BTN_MIDDLE, 0); syn()

            while not self._stop.is_set():
                fds = [d.fd for d in srcs]
                r,_,_ = select.select(fds, [], [], 0.01)

                now = time.time()
                if state == "PENDING" and now - t0 >= self.tap_window:
                    mmb(); state = "IDLE"
                if state == "SCROLL" and now - last_move >= self.scroll_idle:
                    self.on_debug("[SCROLL END]")
                    state = "IDLE"

                if not r: continue
                for d in [s for s in srcs if s.fd in r]:
                    for ev in d.read():
                        if ev.type == E.EV_REL:
                            # wheel tick = trigger; swallow it
                            if ev.code in (E.REL_WHEEL, 11, 12):
                                if state == "IDLE":
                                    state = "PENDING"; t0 = time.time()
                                    self.on_debug("[PENDING]")
                                continue
                            if ev.code in (E.REL_X, E.REL_Y):
                                if state == "PENDING":
                                    state = "SCROLL"
                                    self.on_debug("[SCROLL START]")
                                if state == "SCROLL":
                                    if ev.code == E.REL_Y:
                                        out = int(-(acc_y + ev.value)/self.div_y)
                                        acc_y = (acc_y + ev.value) + out*self.div_y
                                        if out:
                                            self.on_debug(f"[V {out}]")
                                            ui.write(E.EV_REL, E.REL_WHEEL, out); syn()
                                    else:
                                        out = int((acc_x + ev.value)/self.div_x)
                                        acc_x = (acc_x + ev.value) - out*self.div_x
                                        if out:
                                            self.on_debug(f"[H {out}]")
                                            ui.write(E.EV_REL, E.REL_HWHEEL, out); syn()
                                    last_move = time.time()
                                    continue
                                # normal motion passthrough when not scrolling
                                ui.write(E.EV_REL, ev.code, ev.value); syn()
                        elif ev.type == E.EV_KEY:
                            ui.write(E.EV_KEY, ev.code, ev.value); syn()

        except Exception as e:
            self.on_debug("ERROR: " + "".join(traceback.format_exception_only(type(e), e)).strip())
        finally:
            try:
                for d in locals().get("srcs", []):
                    try: d.ungrab()
                    except: pass
            finally:
                if "ui" in locals(): ui.close()
