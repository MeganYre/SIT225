"""
Reusable smooth Plotly Dash live monitor.

Why not redraw every N samples?
  Rebuilding a full figure each batch causes a visible jump. This module
  streams points with Dash/Plotly `extendData`, which appends to existing
  traces and drops older points with a sliding window (`maxPoints`).
  Users see a continuous scrolling line instead of a hard graph swap.

Public API
----------
run_smooth_dash(sample_fn, ...)
    Peer-friendly entry point. Pass a zero-arg function that returns the
    latest sample as a dict, e.g. {"x": 0.1, "y": 0.2, "z": 9.8}, or None
    when nothing new is available. Series names must match dict keys.

create_smooth_dash_app(sample_fn, ...)
    Same behaviour, but returns the Dash app so you can customise layout
    or run it yourself.

Design justification
--------------------
- sample_fn keeps data acquisition out of the UI layer (Cloud, CSV, serial…).
- series + window_size + update_interval_ms are the only knobs peers need.
- extendData avoids full figure replacement; window_size caps memory/CPU.
- sample_fn may read shared state updated by another thread (e.g. Arduino Cloud).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from dash import Dash, Input, Output, dcc, html, no_update
import plotly.graph_objects as go

SampleFn = Callable[[], Mapping[str, float] | None]


def create_smooth_dash_app(
    sample_fn: SampleFn,
    *,
    series: Sequence[str] = ("x", "y", "z"),
    window_size: int = 250,
    update_interval_ms: int = 200,
    title: str = "Smooth live monitor",
) -> Dash:
    """
    Build a Dash app that smoothly streams continuous series via extendData.

    Parameters
    ----------
    sample_fn:
        Called on each interval tick. Return a mapping of series_name -> value,
        or None / incomplete mapping to skip this tick (no visual glitch).
    series:
        Ordered series keys to plot (must match sample_fn keys).
    window_size:
        Max points kept per trace (sliding window).
    update_interval_ms:
        How often Dash polls sample_fn (smaller = smoother, more CPU).
    title:
        Page / figure title.
    """
    if window_size < 2:
        raise ValueError("window_size must be >= 2")
    if update_interval_ms < 10:
        raise ValueError("update_interval_ms must be >= 10")
    if not series:
        raise ValueError("series must not be empty")

    series = tuple(series)
    colours = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b")

    fig = go.Figure()
    for i, name in enumerate(series):
        fig.add_trace(
            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name=name.upper() if len(name) == 1 else name,
                line=dict(width=2, color=colours[i % len(colours)]),
            )
        )
    fig.update_layout(
        title=title,
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis_title="Time",
        yaxis_title="Value",
        uirevision="smooth-live",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=520,
    )

    app = Dash(__name__)
    app.title = title
    app.layout = html.Div(
        style={
            "fontFamily": "Segoe UI, sans-serif",
            "padding": "16px",
            "maxWidth": "1100px",
            "margin": "0 auto",
        },
        children=[
            html.H2(title),
            html.P(
                "Streaming via Plotly extendData (sliding window) — "
                "no full graph redraw every N samples."
            ),
            dcc.Graph(id="smooth-live-graph", figure=fig),
            dcc.Interval(
                id="smooth-live-tick",
                interval=update_interval_ms,
                n_intervals=0,
            ),
            html.Div(
                id="smooth-live-status",
                style={"marginTop": "8px", "color": "#555"},
            ),
        ],
    )

    @app.callback(
        Output("smooth-live-graph", "extendData"),
        Output("smooth-live-status", "children"),
        Input("smooth-live-tick", "n_intervals"),
        prevent_initial_call=False,
    )
    def _on_tick(_n: int) -> tuple[Any, str]:
        sample = sample_fn()
        if not sample:
            return no_update, "Waiting for data…"

        try:
            values = [float(sample[name]) for name in series]
        except (KeyError, TypeError, ValueError):
            return no_update, "Incomplete sample — skipped"

        t = time.time()
        extend = {
            "x": [[t] for _ in series],
            "y": [[v] for v in values],
        }
        trace_indices = list(range(len(series)))
        status = " | ".join(
            f"{name}={val:.3f}" for name, val in zip(series, values)
        )
        # (data, traces, maxPoints) → Plotly drops oldest points for a smooth scroll
        return (extend, trace_indices, window_size), status

    return app


def run_smooth_dash(
    sample_fn: SampleFn,
    *,
    series: Sequence[str] = ("x", "y", "z"),
    window_size: int = 250,
    update_interval_ms: int = 200,
    title: str = "Smooth live monitor",
    host: str = "127.0.0.1",
    port: int = 8050,
    debug: bool = False,
) -> None:
    """
    Peer API: start a smooth live Dash monitor for any continuous data source.

    Example
    -------
    latest = {"x": 0.0, "y": 0.0, "z": 9.8}

    def sample():
        return dict(latest)  # updated elsewhere from sensors / Cloud

    run_smooth_dash(sample, series=("x", "y", "z"), window_size=300)
    """
    app = create_smooth_dash_app(
        sample_fn,
        series=series,
        window_size=window_size,
        update_interval_ms=update_interval_ms,
        title=title,
    )
    print(f"Smooth Dash running at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
