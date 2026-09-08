"""
Step 7–8 analysis: compare no-activity / activity 1 / activity 2 patterns.

Reads annotations.csv + matching captures/*.csv, prints summary stats, and
writes comparison plots under graphs/.

Usage:
  python analyse_activities.py
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
CAPTURE_DIR = ROOT / "captures"
ANNOTATIONS_PATH = ROOT / "annotations.csv"
GRAPH_DIR = ROOT / "graphs"

ACTIVITY_NAMES = {
    0: "no-activity",
    1: "waving",
    2: "shaking",
}


def load_annotations(path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("filename") or ""
            # Accept jpg or csv stem
            if name.endswith(".jpg"):
                stem = name[:-4]
            elif name.endswith(".csv"):
                stem = name[:-4]
            else:
                stem = Path(name).stem
            rows.append((stem, int(row["label"])))
    return rows


def load_window(csv_path: Path) -> np.ndarray:
    """Return Nx3 array of x,y,z."""
    xs, ys, zs = [], [], []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            xs.append(float(row["x"]))
            ys.append(float(row["y"]))
            zs.append(float(row["z"]))
    if not xs:
        return np.zeros((0, 3))
    return np.column_stack([xs, ys, zs])


def window_features(xyz: np.ndarray) -> dict[str, float]:
    if xyz.size == 0:
        return {
            "std_x": 0.0,
            "std_y": 0.0,
            "std_z": 0.0,
            "std_mag": 0.0,
            "range_mag": 0.0,
            "mean_mag": 0.0,
        }
    mag = np.linalg.norm(xyz, axis=1)
    return {
        "std_x": float(np.std(xyz[:, 0])),
        "std_y": float(np.std(xyz[:, 1])),
        "std_z": float(np.std(xyz[:, 2])),
        "std_mag": float(np.std(mag)),
        "range_mag": float(np.ptp(mag)),
        "mean_mag": float(np.mean(mag)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--annotations",
        type=Path,
        default=ANNOTATIONS_PATH,
        help="Path to annotations.csv",
    )
    args = parser.parse_args()

    if not args.annotations.exists():
        raise SystemExit(
            f"Missing {args.annotations}. Label images with: python annotate.py"
        )

    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    annotations = load_annotations(args.annotations)
    by_label: dict[int, list[tuple[str, dict[str, float], np.ndarray]]] = defaultdict(
        list
    )

    for stem, label in annotations:
        csv_path = CAPTURE_DIR / f"{stem}.csv"
        if not csv_path.exists():
            print(f"[skip] no CSV for {stem}")
            continue
        xyz = load_window(csv_path)
        feats = window_features(xyz)
        by_label[label].append((stem, feats, xyz))

    if not by_label:
        raise SystemExit("No labelled windows with matching CSVs found.")

    # --- Console summary ---
    print("\n=== Per-class feature means (use in report) ===\n")
    feature_keys = ["std_x", "std_y", "std_z", "std_mag", "range_mag", "mean_mag"]
    class_means: dict[int, dict[str, float]] = {}

    for label in sorted(by_label.keys()):
        items = by_label[label]
        name = ACTIVITY_NAMES.get(label, f"label_{label}")
        means = {
            k: float(np.mean([it[1][k] for it in items])) for k in feature_keys
        }
        class_means[label] = means
        print(f"{label} ({name}) — n={len(items)}")
        for k in feature_keys:
            print(f"  {k:10s}: {means[k]:.4f}")
        print()

    # --- Contrast text helpers ---
    print("=== Suggested contrasts for the report ===\n")
    pairs = [(0, 1), (0, 2), (1, 2)]
    for a, b in pairs:
        if a not in class_means or b not in class_means:
            continue
        na = ACTIVITY_NAMES.get(a, str(a))
        nb = ACTIVITY_NAMES.get(b, str(b))
        da = class_means[a]["std_mag"]
        db = class_means[b]["std_mag"]
        ra = class_means[a]["range_mag"]
        rb = class_means[b]["range_mag"]
        print(
            f"{na} vs {nb}: "
            f"std_mag {da:.3f} vs {db:.3f}; "
            f"range_mag {ra:.3f} vs {rb:.3f}"
        )
    print()

    # --- Bar chart of std_mag ---
    labels_present = sorted(class_means.keys())
    names = [ACTIVITY_NAMES.get(i, str(i)) for i in labels_present]
    stds = [class_means[i]["std_mag"] for i in labels_present]
    ranges = [class_means[i]["range_mag"] for i in labels_present]

    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].bar(names, stds, color=["#4c78a8", "#f58518", "#54a24b"][: len(names)])
    ax[0].set_title("Mean magnitude std (motion intensity)")
    ax[0].set_ylabel("std(|a|)")
    ax[1].bar(names, ranges, color=["#4c78a8", "#f58518", "#54a24b"][: len(names)])
    ax[1].set_title("Mean magnitude range")
    ax[1].set_ylabel("max(|a|)-min(|a|)")
    fig.tight_layout()
    out_bar = GRAPH_DIR / "class_feature_comparison.png"
    fig.savefig(out_bar, dpi=140)
    plt.close(fig)
    print(f"Wrote {out_bar}")

    # --- Example traces (up to 3 windows per class) ---
    fig, axes = plt.subplots(
        len(labels_present), 3, figsize=(12, 3.2 * len(labels_present)), squeeze=False
    )
    for row, label in enumerate(labels_present):
        items = by_label[label][:3]
        name = ACTIVITY_NAMES.get(label, str(label))
        for col in range(3):
            ax = axes[row][col]
            if col >= len(items):
                ax.axis("off")
                continue
            stem, _feats, xyz = items[col]
            t = np.arange(len(xyz))
            ax.plot(t, xyz[:, 0], label="x", linewidth=1)
            ax.plot(t, xyz[:, 1], label="y", linewidth=1)
            ax.plot(t, xyz[:, 2], label="z", linewidth=1)
            ax.set_title(f"{name}: {stem}")
            if col == 0:
                ax.set_ylabel("accel")
            if row == 0 and col == 0:
                ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    out_ex = GRAPH_DIR / "example_windows_by_class.png"
    fig.savefig(out_ex, dpi=140)
    plt.close(fig)
    print(f"Wrote {out_ex}")

    print(
        "\nInterpretation tip:\n"
        "  no-activity -> low std/range (nearly flat lines).\n"
        "  waving -> larger rhythmic swings, often on 1-2 axes.\n"
        "  shaking -> higher frequency / noisier / larger std than waving.\n"
        "Use ambiguous images + these patterns together when re-checking labels."
    )


if __name__ == "__main__":
    main()
