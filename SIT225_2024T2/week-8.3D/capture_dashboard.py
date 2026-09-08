"""
D6 — Live accelerometer windows + webcam snapshots on Plotly Dash.

Every WINDOW_SECONDS of phone accelerometer data:
  1. Build an X/Y/Z graph for that window
  2. Capture a laptop webcam frame (OpenCV)
  3. Show graph + image on the Dash dashboard
  4. Save matching files: {seq}_{yyyymmddHHMMss}.csv and .jpg

Modes
-----
  python capture_dashboard.py          # Arduino IoT Cloud (needs arduino_secrets.py)
  python capture_dashboard.py --demo   # Replay data/accelerometer_xyz.csv (no phone)

Why 10-second windows
---------------------
Long enough for one clear gesture (wave / shake / idle) in front of the camera,
short enough to collect many balanced samples in a 30+ minute session.
"""

from __future__ import annotations

import argparse
import base64
import csv
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, no_update

ROOT = Path(__file__).resolve().parent
CAPTURE_DIR = ROOT / "captures"
DEMO_CSV = ROOT / "data" / "accelerometer_xyz.csv"

# Default Cloud variable names (must match your Arduino IoT Cloud Python Thing)
VAR_X = "accelerometer_x"
VAR_Y = "accelerometer_y"
VAR_Z = "accelerometer_z"


@dataclass
class Sample:
    t: float
    x: float
    y: float
    z: float


@dataclass
class SharedState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    buffer: list[Sample] = field(default_factory=list)
    window_start: float | None = None
    seq: int = 0
    # Latest completed window for Dash
    figure: go.Figure | None = None
    image_b64: str | None = None
    status: str = "Waiting for accelerometer data..."
    last_stem: str = ""
    # Webcam (opened once, reused)
    camera: cv2.VideoCapture | None = None


STATE = SharedState()


def _ensure_dirs() -> None:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)


def _next_seq() -> int:
    """Continue sequence from highest existing N_*.csv in captures/."""
    existing = list(CAPTURE_DIR.glob("*_*.csv"))
    nums: list[int] = []
    for p in existing:
        try:
            nums.append(int(p.name.split("_", 1)[0]))
        except ValueError:
            continue
    return (max(nums) + 1) if nums else 1


def _open_camera(index: int = 0) -> cv2.VideoCapture:
    cam = cv2.VideoCapture(index, cv2.CAP_DSHOW)  # CAP_DSHOW helps on Windows
    if not cam.isOpened():
        cam.release()
        cam = cv2.VideoCapture(index)
    if not cam.isOpened():
        raise SystemExit(
            f"Could not open webcam (index={index}). "
            "Close other apps using the camera and try again."
        )
    # Warm up a few frames so exposure settles
    for _ in range(5):
        cam.read()
        time.sleep(0.05)
    return cam


def _capture_jpg(path: Path) -> bytes:
    with STATE.lock:
        cam = STATE.camera
    if cam is None or not cam.isOpened():
        raise RuntimeError("Webcam is not open")

    ok, frame = cam.read()
    if not ok or frame is None:
        raise RuntimeError("Failed to read webcam frame")

    # BGR → RGB for correct colours when encoding / Dash display
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("Failed to encode JPEG")
    data = buf.tobytes()
    path.write_bytes(data)
    return data


def _save_csv(path: Path, samples: list[Sample]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_unix", "x", "y", "z"])
        for s in samples:
            writer.writerow([f"{s.t:.6f}", s.x, s.y, s.z])


def _make_figure(samples: list[Sample], title: str) -> go.Figure:
    if not samples:
        fig = go.Figure()
        fig.update_layout(title=title)
        return fig

    t0 = samples[0].t
    xs = [s.t - t0 for s in samples]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=[s.x for s in samples], mode="lines", name="X"))
    fig.add_trace(go.Scatter(x=xs, y=[s.y for s in samples], mode="lines", name="Y"))
    fig.add_trace(go.Scatter(x=xs, y=[s.z for s in samples], mode="lines", name="Z"))
    fig.update_layout(
        title=title,
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis_title="Seconds into window",
        yaxis_title="Acceleration",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=420,
    )
    return fig


def finalise_window(samples: list[Sample]) -> None:
    """Save CSV + JPG and publish dashboard snapshot for one completed window."""
    if len(samples) < 2:
        with STATE.lock:
            STATE.status = f"Skipped short window ({len(samples)} samples)"
        return

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    with STATE.lock:
        seq = STATE.seq
        STATE.seq += 1

    stem = f"{seq}_{ts}"
    csv_path = CAPTURE_DIR / f"{stem}.csv"
    jpg_path = CAPTURE_DIR / f"{stem}.jpg"

    _save_csv(csv_path, samples)
    try:
        jpg_bytes = _capture_jpg(jpg_path)
        b64 = base64.b64encode(jpg_bytes).decode("ascii")
        img_ok = True
    except Exception as exc:  # noqa: BLE001 — keep session alive if camera glitches
        b64 = None
        img_ok = False
        print(f"[warn] Webcam capture failed for {stem}: {exc}")

    fig = _make_figure(samples, title=f"Window {stem} ({len(samples)} samples)")

    with STATE.lock:
        STATE.figure = fig
        STATE.image_b64 = b64
        STATE.last_stem = stem
        if img_ok:
            STATE.status = (
                f"Saved {stem}.csv + .jpg | samples={len(samples)} | "
                f"duration~{samples[-1].t - samples[0].t:.1f}s"
            )
        else:
            STATE.status = f"Saved {stem}.csv (image FAILED) | samples={len(samples)}"

    print(STATE.status, flush=True)


def push_sample(x: float, y: float, z: float, window_s: float) -> None:
    """Append one sample; when the window duration elapses, finalise and reset."""
    now = time.time()
    sample = Sample(t=now, x=float(x), y=float(y), z=float(z))

    to_finalise: list[Sample] | None = None
    with STATE.lock:
        if STATE.window_start is None:
            STATE.window_start = now
        STATE.buffer.append(sample)
        elapsed = now - STATE.window_start
        if elapsed >= window_s:
            to_finalise = list(STATE.buffer)
            STATE.buffer.clear()
            STATE.window_start = now

    if to_finalise is not None:
        # Finalise outside the lock (I/O + camera)
        finalise_window(to_finalise)


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


def start_csv_demo(path: Path, period_s: float, window_s: float) -> None:
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

        print(f"Demo: replaying {len(rows)} samples from {path.name} every {period_s}s")
        i = 0
        while True:
            x, y, z = rows[i % len(rows)]
            push_sample(x, y, z, window_s)
            i += 1
            time.sleep(period_s)

    threading.Thread(target=_loop, daemon=True).start()


def start_arduino_cloud(window_s: float) -> None:
    from arduino_iot_cloud import ArduinoCloudClient

    from arduino_secrets import DEVICE_ID, SECRET_KEY

    if "PASTE_YOUR" in DEVICE_ID or "PASTE_YOUR" in SECRET_KEY:
        raise SystemExit(
            "Fill in arduino_secrets.py (copy from arduino_secrets.example.py), "
            "or run with --demo."
        )

    buf = {"x": None, "y": None, "z": None}

    def _try_push() -> None:
        if buf["x"] is None or buf["y"] is None or buf["z"] is None:
            return
        push_sample(buf["x"], buf["y"], buf["z"], window_s)

    def on_x(client, value):
        buf["x"] = value
        _try_push()

    def on_y(client, value):
        buf["y"] = value
        _try_push()

    def on_z(client, value):
        buf["z"] = value
        _try_push()

    def _run() -> None:
        print("Connecting to Arduino IoT Cloud...")
        client = ArduinoCloudClient(
            device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY
        )
        client.register(VAR_X, value=None, on_write=on_x)
        client.register(VAR_Y, value=None, on_write=on_y)
        client.register(VAR_Z, value=None, on_write=on_z)
        client.start()

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Dash UI
# ---------------------------------------------------------------------------


def create_app(poll_ms: int) -> Dash:
    empty = go.Figure()
    empty.update_layout(
        title="Waiting for first window...",
        template="plotly_white",
        height=420,
    )

    app = Dash(__name__)
    app.title = "D6 Accel + Webcam"
    app.layout = html.Div(
        style={
            "fontFamily": "Segoe UI, sans-serif",
            "padding": "16px",
            "maxWidth": "1100px",
            "margin": "0 auto",
        },
        children=[
            html.H2("D6 — Accelerometer window + activity image"),
            html.P(
                "Every completed time window: graph updates, webcam snaps, "
                "and matching CSV/JPG files are written under captures/."
            ),
            html.Div(id="status", style={"marginBottom": "12px", "color": "#333"}),
            dcc.Graph(id="window-graph", figure=empty),
            html.H4("Latest webcam capture"),
            html.Img(
                id="webcam-image",
                style={
                    "maxWidth": "100%",
                    "border": "1px solid #ccc",
                    "borderRadius": "4px",
                },
            ),
            dcc.Interval(id="tick", interval=poll_ms, n_intervals=0),
        ],
    )

    @app.callback(
        Output("window-graph", "figure"),
        Output("webcam-image", "src"),
        Output("status", "children"),
        Input("tick", "n_intervals"),
        prevent_initial_call=False,
    )
    def _on_tick(_n: int):
        with STATE.lock:
            fig = STATE.figure
            b64 = STATE.image_b64
            status = STATE.status

        if fig is None:
            return no_update, no_update, status

        src = f"data:image/jpeg;base64,{b64}" if b64 else ""
        return fig, src, status

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="D6 accel windows + webcam Dash")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Replay data/accelerometer_xyz.csv instead of Arduino Cloud",
    )
    parser.add_argument(
        "--window-seconds",
        type=float,
        default=10.0,
        help="Seconds of data per saved graph/image pair (default 10)",
    )
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--camera", type=int, default=0, help="Webcam device index")
    parser.add_argument(
        "--demo-period",
        type=float,
        default=0.05,
        help="Seconds between demo CSV samples",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=500,
        help="How often Dash refreshes the latest window/image",
    )
    args = parser.parse_args(argv)

    _ensure_dirs()
    with STATE.lock:
        STATE.seq = _next_seq()
        STATE.camera = _open_camera(args.camera)

    print(f"Captures -> {CAPTURE_DIR}")
    print(f"Next sequence number -> {STATE.seq}")
    print(f"Window length -> {args.window_seconds}s")

    if args.demo:
        if not DEMO_CSV.exists():
            raise SystemExit(f"Missing {DEMO_CSV}")
        start_csv_demo(DEMO_CSV, args.demo_period, args.window_seconds)
        print("Mode: DEMO (CSV replay). Use real Cloud mode for the assessment run.")
    else:
        start_arduino_cloud(args.window_seconds)
        print("Mode: Arduino IoT Cloud")

    app = create_app(args.poll_ms)
    print(f"Dashboard -> http://127.0.0.1:{args.port}")
    try:
        app.run(host="127.0.0.1", port=args.port, debug=False)
    finally:
        with STATE.lock:
            if STATE.camera is not None:
                STATE.camera.release()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exception(*sys.exc_info())
        raise
