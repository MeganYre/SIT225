"""
Live accelerometer X/Y/Z → smooth Plotly Dash.

Modes
-----
1) --demo   Replay python/data/accelerometer_xyz.csv (works without Cloud).
2) default  Connect to Arduino IoT Cloud (needs arduino_secrets.py filled in)
            and stream phone accelerometer variables into the smooth Dash API.

Uses run_smooth_dash() so peers can reuse the same smooth-update behaviour
for any continuous data source.
"""

from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
import traceback
from pathlib import Path

from smooth_dash import run_smooth_dash

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "accelerometer_xyz.csv"

# Shared live sample (updated by Cloud callbacks or CSV replay thread)
_lock = threading.Lock()
_latest: dict[str, float] | None = None


def set_latest(x: float, y: float, z: float) -> None:
    global _latest
    with _lock:
        _latest = {"x": float(x), "y": float(y), "z": float(z)}


def sample_fn() -> dict[str, float] | None:
    with _lock:
        return None if _latest is None else dict(_latest)


def start_csv_demo(path: Path, period_s: float = 0.05) -> None:
    """Replay combined CSV in a background thread (demo / marking without phone)."""

    def _loop() -> None:
        rows: list[tuple[float, float, float]] = []
        with path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 4:
                    continue
                try:
                    rows.append((float(row[1]), float(row[2]), float(row[3])))
                except ValueError:
                    continue
        if not rows:
            raise SystemExit(f"No usable rows in {path}")

        print(f"CSV demo: replaying {len(rows)} samples from {path.name}")
        i = 0
        while True:
            x, y, z = rows[i % len(rows)]
            set_latest(x, y, z)
            i += 1
            time.sleep(period_s)

    threading.Thread(target=_loop, daemon=True).start()


def start_arduino_cloud() -> None:
    """Background Arduino Cloud client → updates _latest on each axis write."""
    from arduino_iot_cloud import ArduinoCloudClient

    from arduino_secrets import DEVICE_ID, SECRET_KEY

    if "PASTE_YOUR" in DEVICE_ID or "PASTE_YOUR" in SECRET_KEY:
        raise SystemExit(
            "Fill in arduino_secrets.py, or run with --demo to use CSV replay."
        )

    # Cloud variable names on your Python Thing (synced to phone accel)
    var_x = "accelerometer_x"
    var_y = "accelerometer_y"
    var_z = "accelerometer_z"

    buf = {"x": None, "y": None, "z": None}

    def _try_publish() -> None:
        if buf["x"] is None or buf["y"] is None or buf["z"] is None:
            return
        set_latest(buf["x"], buf["y"], buf["z"])

    def on_x(client, value):
        buf["x"] = value
        _try_publish()

    def on_y(client, value):
        buf["y"] = value
        _try_publish()

    def on_z(client, value):
        buf["z"] = value
        _try_publish()

    def _run() -> None:
        print("Connecting to Arduino Cloud…")
        client = ArduinoCloudClient(
            device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY
        )
        client.register(var_x, value=None, on_write=on_x)
        client.register(var_y, value=None, on_write=on_y)
        client.register(var_z, value=None, on_write=on_z)
        client.start()

    threading.Thread(target=_run, daemon=True).start()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Smooth Dash accelerometer monitor")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Replay accelerometer_xyz.csv instead of Arduino Cloud",
    )
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--window", type=int, default=250, help="Sliding window size")
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=200,
        help="Dash poll interval (ms); lower = smoother, higher = less CPU thrash",
    )
    args = parser.parse_args(argv)

    if args.demo:
        if not CSV_PATH.exists():
            raise SystemExit(f"Missing {CSV_PATH}")
        start_csv_demo(CSV_PATH)
        title = "Smooth accelerometer (CSV demo)"
    else:
        start_arduino_cloud()
        title = "Smooth accelerometer (Arduino Cloud)"

    # Peer-facing API: any continuous source → smooth Dash
    run_smooth_dash(
        sample_fn,
        series=("x", "y", "z"),
        window_size=args.window,
        update_interval_ms=args.interval_ms,
        title=title,
        port=args.port,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exception(*sys.exc_info())
        raise
