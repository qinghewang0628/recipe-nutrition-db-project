#!/usr/bin/env python3
"""Render docs/figures/timings.{png,svg} from docs/evidence/scale_timings.csv.

Every number comes from the evidence file written by scale/run_experiment.py,
nothing is retyped, so the figure cannot disagree with the tables in
docs/scale_experiment.md.  Requires matplotlib (dev-time only: the committed
PNG/SVG is what the report uses).

    python3 tools/plot_timings.py
"""
import csv
import sys

try:
    import matplotlib
except ImportError:  # pragma: no cover
    sys.exit("matplotlib is required: python3 -m pip install matplotlib")

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SRC = "docs/evidence/scale_timings.csv"
TARGETS = ["docs/figures/timings.png", "docs/figures/timings.svg"]
TIERS = [("small", "x1 - 10k recipes"), ("medium", "x5 - 50k recipes"),
         ("large", "x20 - 200k recipes")]
QUERIES = ["q1", "q2", "q3"]
NO_IDX, WITH_IDX = "#b03a2e", "#1f6f78"
BOTTOM = 0.4  # bars start here so a log axis can still show 0.6 ms


def load():
    with open(SRC, newline="", encoding="utf-8") as fh:
        return {(r["tier"], r["query"]): r for r in csv.DictReader(fh)}


def fmt(value):
    return f"{value:.2f}" if value < 10 else f"{value:,.0f}"


def main():
    data = load()
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.5), sharey=True)
    width, offset = 0.36, 0.02
    x = np.arange(len(QUERIES))
    for ax, (tier, label) in zip(axes, TIERS):
        noidx = [float(data[(tier, q)]["noindex_median_ms"]) for q in QUERIES]
        indexed = [float(data[(tier, q)]["indexed_median_ms"]) for q in QUERIES]
        left, right = x - width / 2 - offset, x + width / 2 + offset
        ax.bar(left, noidx, width, bottom=BOTTOM, color=NO_IDX,
               label="without the secondary indexes")
        ax.bar(right, indexed, width, bottom=BOTTOM, color=WITH_IDX,
               label="with them")
        for xi, value, colour in ([(a, b, NO_IDX) for a, b in zip(left, noidx)]
                                  + [(a, b, WITH_IDX) for a, b in zip(right, indexed)]):
            ax.text(xi, value + BOTTOM, fmt(value), ha="center", va="bottom",
                    fontsize=8, color=colour)
        for i, q in enumerate(QUERIES):
            ratio = float(data[(tier, q)]["speedup"])
            top = max(noidx[i], indexed[i])
            ax.text(x[i], top * 2.3, "tie" if ratio < 1.05 else f"x{ratio:.1f}",
                    ha="center", fontsize=10, fontweight="bold", color="#333333")
        ax.set_xticks(x, QUERIES)
        ax.set_title(label, fontsize=10)
        ax.set_yscale("log")
        ax.set_ylim(BOTTOM, 30000)
        ax.grid(axis="y", ls=":", color="#bbbbbb", lw=0.7)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("median wall-clock time per query (ms, log scale)")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, 0.98))
    fig.suptitle("Effect of the four secondary indexes at three data volumes",
                 fontsize=12)
    fig.text(0.5, 0.012,
             "Median of 12 runs; both series keep every primary key. Bars start at "
             "0.4 ms so the log axis can show sub-millisecond queries. "
             "'tie' = the index does not pay at x1.",
             ha="center", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.045, 1, 0.94))
    for target in TARGETS:
        fig.savefig(target, dpi=200 if target.endswith(".png") else None)
    print("wrote " + ", ".join(TARGETS))


if __name__ == "__main__":
    main()
