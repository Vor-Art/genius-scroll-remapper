#!/usr/bin/env python3
# mouse_remapper_core.py
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
    return sorted(seen.keys())

class RemapperScroll:
    def __init__(self, name, vendor, product,
                 scroll_idle=0.15, div_y=60.0, div_x=120.0,
                 deadzone=3.0, max_step=3, hold_grace=0.08,
                 virtual_name="Genius-Remapped Mouse",
                 on_recv=None, on_act=None):
        self.name, self.vendor, self.product = name, vendor, product
        self.scroll_idle = float(scroll_idle)
        self.div_y, self.div_x = float(div_y), float(div_x)
        self.deadzone = float(deadzone)
        self.max_step = int(max(1, max_step))
        self.hold_grace = float(hold_grace)
        self.virtual_name = virtual_name
        self.on_recv = on_recv or (lambda _msg: None)
        self.on_act  = on_act  or (lambda _msg: None)
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
            srcs = []
            for path in list_devices():
                d = InputDevice(path)
                if d.name == self.name and d.info.vendor == self.vendor and d.info.product == self.product:
                    rel = d.capabilities().get(E.EV_REL, [])
                    if E.REL_X in rel or E.REL_Y in rel or E.REL_WHEEL in rel or 11 in rel or 12 in rel:
                        srcs.append(d)
            if not srcs:
                self.on_act("No matching devices with EV_REL."); return

            for d in srcs: d.grab()
            self.on_act("Grabbed: " + ", ".join([d.path for d in srcs]))

            caps = {E.EV_KEY:[E.BTN_LEFT,E.BTN_RIGHT,E.BTN_MIDDLE,E.BTN_SIDE,E.BTN_EXTRA],
                    E.EV_REL:[E.REL_X,E.REL_Y,E.REL_WHEEL,E.REL_HWHEEL]}
            ui = UInput(caps, name=self.virtual_name, bustype=srcs[0].info.bustype,
                        vendor=self.vendor, product=self.product)
            self.on_act(f"Created virtual device: {self.virtual_name}")

            scrolling = False
            last_scroll = 0.0
            last_wheel_ts = 0.0
            ry = rx = 0.0

            def begin_scroll(ts):
                nonlocal scrolling, last_scroll, ry, rx
                last_scroll = ts
                if not scrolling:
                    scrolling = True
                    ry = rx = 0.0
                    self.on_act("[SCROLL START]")

            def end_scroll(tag):
                nonlocal scrolling, ry, rx
                if scrolling:
                    scrolling = False
                    ry = rx = 0.0
                    self.on_act(tag)

            def syn(): ui.syn()

            while not self._stop.is_set():
                fds = [d.fd for d in srcs]
                r,_,_ = select.select(fds, [], [], 0.01)
                now = time.time()

                if scrolling and (now - last_wheel_ts) > self.hold_grace:
                    end_scroll("[RELEASE]")

                if scrolling and now - last_scroll >= self.scroll_idle:
                    end_scroll("[SCROLL END]")

                if not r: continue
                for d in [s for s in srcs if s.fd in r]:
                    for ev in d.read():
                        if ev.type == E.EV_REL:
                            if ev.code in (E.REL_WHEEL, 11, 12):
                                self.on_recv(f"TICK code={ev.code} val={ev.value}")
                                last_wheel_ts = now
                                begin_scroll(now)
                                continue

                            if ev.code in (E.REL_X, E.REL_Y):
                                self.on_recv(f"MOVE {'X' if ev.code==E.REL_X else 'Y'} {ev.value}")
                                if scrolling:
                                    if ev.code == E.REL_Y:
                                        ry += ev.value
                                        if abs(ry) >= self.deadzone:
                                            out = int(ry / self.div_y)
                                            if out:
                                                out = max(-self.max_step, min(self.max_step, out))
                                                ui.write(E.EV_REL, E.REL_WHEEL, -out); syn()
                                                ry -= out * self.div_y
                                                last_scroll = now
                                                self.on_act(f"SCROLL V {out}")
                                    else:
                                        rx += ev.value
                                        if abs(rx) >= self.deadzone:
                                            out = int(rx / self.div_x)
                                            if out:
                                                out = max(-self.max_step, min(self.max_step, out))
                                                ui.write(E.EV_REL, E.REL_HWHEEL, out); syn()
                                                rx -= out * self.div_x
                                                last_scroll = now
                                                self.on_act(f"SCROLL H {out}")
                                    continue

                                ui.write(E.EV_REL, ev.code, ev.value); syn()

                        elif ev.type == E.EV_KEY:
                            self.on_recv(f"KEY code={ev.code} val={ev.value}")
                            ui.write(E.EV_KEY, ev.code, ev.value); syn()

        except Exception as e:
            self.on_act("ERROR: " + "".join(traceback.format_exception_only(type(e), e)).strip())
        finally:
            try:
                for d in locals().get("srcs", []):
                    try: d.ungrab()
                    except: pass
            finally:
                if "ui" in locals(): ui.close()
