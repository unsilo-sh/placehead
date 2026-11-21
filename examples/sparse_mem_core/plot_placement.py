"""Draw a placement from def2graph's output.

Usage:
    python plot_placement.py --def sparse_mem_core_placed.def --graph demo/work/graph -o placement.png

Reads nodes.parquet (instance x/y in DEF units, width/height in um) and
summary.json (DEF units per um) from the def2graph output directory, and the
die outline from the DEF's DIEAREA.
"""
import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch, Rectangle

COLORS = {"memory": "#ff9a4d", "flop": "#ff6f4f", "comb": "#b8b8b8"}


def die_area(def_path):
    with open(def_path) as f:
        for line in f:
            m = re.match(r"\s*DIEAREA\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)", line)
            if m:
                return tuple(int(v) for v in m.groups())
    raise ValueError(f"no DIEAREA in {def_path}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--def", dest="def_path", required=True)
    ap.add_argument("--graph", required=True, help="def2graph output directory")
    ap.add_argument("-o", "--out", default="placement.png")
    args = ap.parse_args(argv)

    graph = Path(args.graph)
    summary = json.loads((graph / "summary.json").read_text())
    dbu = summary["dbu_per_micron"]
    nodes = pd.read_parquet(graph / "nodes.parquet")
    inst = nodes[nodes.ntype == "instance"].copy()
    ports = nodes[nodes.ntype == "port"]
    inst["x_um"], inst["y_um"] = inst.x / dbu, inst.y / dbu

    x0, y0, x1, y1 = (v / dbu for v in die_area(args.def_path))
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=1.5, ec="black"))

    # Std cells first, macros on top.
    for kind in ("comb", "flop", "memory"):
        sub = inst[inst.kind == kind]
        big = kind == "memory"
        for r in sub.itertuples():
            ax.add_patch(Rectangle((r.x_um, r.y_um), r.width, r.height, fc=COLORS[kind],
                                   ec="black" if big else "none", lw=1 if big else 0))
            if big:
                ax.text(r.x_um + r.width / 2, r.y_um + r.height / 2, r.name,
                        ha="center", va="center", fontsize=7, weight="bold")

    ax.scatter(ports.x / dbu, ports.y / dbu, s=6, c="#3b7dd8", marker="s", zorder=3)

    counts = inst.kind.value_counts()
    ax.legend(handles=[Patch(color=COLORS[k], label=f"{k} ({counts.get(k, 0)})") for k in COLORS]
              + [Patch(color="#3b7dd8", label=f"port ({len(ports)})")],
              loc="upper right", fontsize=8)
    ax.set_xlim(x0 - 20, x1 + 20)
    ax.set_ylim(y0 - 20, y1 + 20)
    ax.set_aspect("equal")
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    ax.set_title(f"{summary['design']}: {len(inst)} instances, "
                 f"{x1 - x0:g}x{y1 - y0:g} um die (from def2graph)")
    fig.tight_layout()
    fig.savefig(args.out, dpi=100)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
