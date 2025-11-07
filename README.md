# Genius Mouse Scroll Remapper

A tiny two-file helper that remaps the Genius Wireless Mouse middle touch surface into a smooth scroll-only pad while still letting you trigger a middle-click through smart tick detection. The GUI is written in PyQt5 and wraps the `RemapperScroll` core which uses `evdev` + `uinput`.

## Requirements

```bash
sudo apt update
sudo apt install python3 python3-pip python3-evdev python3-pyqt5
```

> **Note:** You should add yourself to the `input` group to run app without `sudo`:
>
> ```bash
> sudo usermod -aG input "$USER"
> echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/90-uinput.rules
> sudo udevadm control --reload-rules && sudo udevadm trigger
> ```
> Sign out/in afterwards.

## Running the App

```bash
python3 mouse_remapper_app.py
```

1. Pick your Genius mouse from the dropdown (it lists all pointer devices with relative axes).
2. Tune scroll speed, deadzone, hold grace, and click-gap values.
3. Click **Start** to grab the physical mouse and spawn the virtual one (`Genius-Remapped Mouse`).
4. Logs on the right show raw events and emitted actions; use them to verify MMB detection (`MMB CLICK`).

The tray icon tooltip mirrors your active parameters, and the “Start with system” checkbox writes a `.desktop` file under `~/.config/autostart` so the remapper launches automatically after login.

## Adding it to the Ubuntu application menu

Run the provided helper to copy the icon, create a `.desktop` file under `~/.local/share/applications`, and refresh the desktop database:

```bash
./install_desktop_entry.sh
```

The script grabs the absolute path to `mouse_remapper_app.py`, writes `~/.local/share/applications/genius-remapper.desktop`, and installs `assets/genius_remapper.svg` as `~/.local/share/icons/genius-remapper.svg`. After it finishes, search for “Genius Mouse Scroll Remapper” in *Show Applications* and pin it if desired.

## Troubleshooting

- **No devices listed** – Try to run `sudo python3 mouse_remapper_app.py`; If there are devices, ensure your user belongs to the `input` group (log out/in after adding). The launcher runs the app without `sudo`, so the `/dev/input/event*` files must be accessible to your user.
- **Virtual scroll stutters** – Lower `div_y` / `div_x` or increase `deadzone`.
- **Middle-click doesn’t trigger** – Increase the click gap toward `0.06` seconds if your firmware emits sparse ticks.

Happy scrolling!
