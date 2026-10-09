#!/usr/bin/env python3
"""Render one PNG with a small views/clones chart per repo, stacked vertically.

  traffic_chart.py <data_dir> <out.png>

Covers the last 30 days ending yesterday (UTC). Repos are ordered by total
activity; each chart has its own y-scale so quiet repos still show their shape.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DAYS = 30
ROW_HEIGHT = 1.15  # inches per repo
VIEWS, CLONES = "#2a78d6", "#eb6834"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"


def load(data_dir, keys):
    index = json.loads((data_dir / "index.json").read_text())
    repos = []
    for name in index["repos"]:
        path = data_dir / "repos" / f"{name}.json"
        if not path.exists():
            continue
        d = json.loads(path.read_text())
        views = [d["views"].get(k, {}).get("count", 0) for k in keys]
        clones = [d["clones"].get(k, {}).get("count", 0) for k in keys]
        repos.append((name, views, clones))
    repos.sort(key=lambda r: (-(sum(r[1]) + sum(r[2])), r[0]))
    return index["owner"], repos


def render(data_dir, out):
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    days = [end - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]
    owner, repos = load(data_dir, [d.isoformat() for d in days])
    if not repos:
        sys.exit("no repo data to plot")

    height = len(repos) * ROW_HEIGHT + 0.8
    fig, axes = plt.subplots(len(repos), 1, figsize=(7.0, height), dpi=150, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    x = range(DAYS)

    for ax, (name, views, clones) in zip(axes.flat, repos):
        ax.set_facecolor(SURFACE)
        ax.plot(x, views, color=VIEWS, lw=1.6, solid_joinstyle="round")
        ax.plot(x, clones, color=CLONES, lw=1.6, solid_joinstyle="round")
        top = max(max(views), max(clones), 1)
        ax.set_ylim(0, top * 1.15)
        ax.set_yticks([0, top], ["", str(top)])  # hide "0": it collides with the first date label
        ax.set_xticks([0, DAYS - 1], [days[0].strftime("%m/%d"), days[-1].strftime("%m/%d")])
        ax.set_xlim(0, DAYS - 1)
        ax.tick_params(colors=MUTED, labelsize=7, length=0, pad=2)
        ax.grid(axis="y", color=GRID, lw=0.6)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.set_title(name, loc="left", fontsize=8.5, color=INK, fontweight="bold", pad=3)
        ax.set_title(f"views {sum(views)} / clones {sum(clones)}", loc="right", fontsize=7, color=INK2, pad=3)

    fig.suptitle(f"{owner} traffic — last {DAYS} days to {end} (UTC)", x=0.01, ha="left",
                 fontsize=11, color=INK, fontweight="bold")
    fig.legend(handles=[plt.Line2D([], [], color=VIEWS, lw=2, label="Views"),
                        plt.Line2D([], [], color=CLONES, lw=2, label="Clones")],
               loc="upper right", ncol=2, frameon=False, fontsize=8, labelcolor=INK2)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.55 / height), h_pad=0.8)
    fig.savefig(out, facecolor=SURFACE)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: traffic_chart.py <data_dir> <out.png>")
    render(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"saved {sys.argv[2]}")
