"""
Interactive annotation helper for D6 captures.

Opens a small Dash UI: browse each JPG, pick a label, write annotations.csv.

Labels (edit ACTIVITY_NAMES to match your session):
  0 = no-activity
  1 = waving
  2 = shaking

Usage:
  python annotate.py
  Then open http://127.0.0.1:8051
"""

from __future__ import annotations

import argparse
import base64
import csv
from pathlib import Path

from dash import Dash, Input, Output, State, dcc, html

ROOT = Path(__file__).resolve().parent
CAPTURE_DIR = ROOT / "captures"
ANNOTATIONS_PATH = ROOT / "annotations.csv"

# Change these names to your real activities for the report
ACTIVITY_NAMES = {
    0: "no-activity",
    1: "waving",
    2: "shaking",
}


def list_images() -> list[Path]:
    return sorted(CAPTURE_DIR.glob("*_*.jpg"), key=lambda p: p.name)


def load_existing() -> dict[str, int]:
    if not ANNOTATIONS_PATH.exists():
        return {}
    out: dict[str, int] = {}
    with ANNOTATIONS_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("filename") or row.get("file")
            label = row.get("label") or row.get("activity")
            if name is None or label is None:
                continue
            try:
                out[name] = int(label)
            except ValueError:
                continue
    return out


def save_annotations(mapping: dict[str, int]) -> None:
    with ANNOTATIONS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "label"])
        for name in sorted(mapping.keys(), key=_sort_key):
            writer.writerow([name, mapping[name]])


def _sort_key(name: str) -> tuple[int, str]:
    try:
        return int(name.split("_", 1)[0]), name
    except ValueError:
        return 10**9, name


def create_app() -> Dash:
    images = list_images()
    labels = load_existing()

    app = Dash(__name__)
    app.title = "D6 Annotate"

    if not images:
        app.layout = html.Div(
            [
                html.H2("No images found"),
                html.P(f"Run capture_dashboard.py first. Expected folder: {CAPTURE_DIR}"),
            ],
            style={"fontFamily": "Segoe UI, sans-serif", "padding": "24px"},
        )
        return app

    # Shared mutable store via a simple module-level dict updated in callbacks
    store = {"labels": labels, "index": 0}

    options = [
        {"label": f"{k} — {v}", "value": k} for k, v in ACTIVITY_NAMES.items()
    ]

    app.layout = html.Div(
        style={
            "fontFamily": "Segoe UI, sans-serif",
            "padding": "16px",
            "maxWidth": "900px",
            "margin": "0 auto",
        },
        children=[
            html.H2("Annotate activity images"),
            html.P(
                "Look at the photo (and optionally the matching CSV pattern later). "
                "Choose a label, then Next. Save writes annotations.csv."
            ),
            html.Div(id="meta", style={"marginBottom": "8px"}),
            html.Img(
                id="img",
                style={
                    "maxWidth": "100%",
                    "border": "1px solid #ccc",
                    "borderRadius": "4px",
                },
            ),
            html.Div(
                style={"marginTop": "12px", "display": "flex", "gap": "12px", "alignItems": "center"},
                children=[
                    dcc.RadioItems(
                        id="label",
                        options=options,
                        value=0,
                        inline=True,
                    ),
                ],
            ),
            html.Div(
                style={"marginTop": "12px", "display": "flex", "gap": "8px"},
                children=[
                    html.Button("Previous", id="prev", n_clicks=0),
                    html.Button("Next", id="next", n_clicks=0),
                    html.Button("Save annotations.csv", id="save", n_clicks=0),
                ],
            ),
            html.Div(id="msg", style={"marginTop": "12px", "color": "#064"}),
            dcc.Store(id="idx", data=0),
        ],
    )

    def _img_src(path: Path) -> str:
        return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode(
            "ascii"
        )

    @app.callback(
        Output("img", "src"),
        Output("meta", "children"),
        Output("label", "value"),
        Output("idx", "data"),
        Output("msg", "children"),
        Input("prev", "n_clicks"),
        Input("next", "n_clicks"),
        Input("save", "n_clicks"),
        State("idx", "data"),
        State("label", "value"),
        prevent_initial_call=False,
    )
    def _nav(prev_c, next_c, save_c, idx, label_val):
        from dash import ctx

        idx = int(idx or 0)
        msg = ""
        triggered = ctx.triggered_id

        # Persist current label before moving / saving
        if triggered in ("prev", "next", "save") and images:
            name = images[idx].name
            store["labels"][name] = int(label_val)

        if triggered == "prev":
            idx = max(0, idx - 1)
        elif triggered == "next":
            idx = min(len(images) - 1, idx + 1)
        elif triggered == "save":
            save_annotations(store["labels"])
            msg = f"Wrote {ANNOTATIONS_PATH} ({len(store['labels'])} rows)"

        path = images[idx]
        current = store["labels"].get(path.name, 0)
        labelled = sum(1 for p in images if p.name in store["labels"])
        meta = (
            f"{idx + 1} / {len(images)} — {path.name} | "
            f"labelled {labelled}/{len(images)} | "
            f"CSV twin: {path.with_suffix('.csv').name}"
        )
        return _img_src(path), meta, current, idx, msg

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8051)
    args = parser.parse_args()
    app = create_app()
    print(f"Annotator -> http://127.0.0.1:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
