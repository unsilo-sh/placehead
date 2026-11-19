"""Build graph.html, an interactive view of def2graph's port cones on the placement.

Usage:
    python make_graph_html.py --def sparse_mem_core_placed.def --graph out/sparse_mem -o graph.html

Reads nodes.parquet, cones.json and summary.json from the def2graph output
directory, and DIEAREA and each macro's signal pins from the DEF. Writes the
page from graph_template.html with the data inlined.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

KINDS = ["comb", "flop", "memory"]


def read_def(def_path, macros):
    """Die area (DEF units) and, per macro instance, each pin its signal nets connect and that net."""
    die, pins = None, defaultdict(dict)
    in_nets, net = False, None
    pin_re = re.compile(r"\(\s*(\S+)\s+(\S+)\s*\)")
    with open(def_path) as f:
        for line in f:
            if die is None:
                m = re.match(r"\s*DIEAREA\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)", line)
                if m:
                    die = [int(v) for v in m.groups()]
            if re.match(r"\s*NETS\s+\d+", line):
                in_nets = True
            elif re.match(r"\s*END\s+NETS", line):
                in_nets = False
            elif in_nets:
                m = re.match(r"\s*-\s+(\S+)", line)
                if m:
                    net = m.group(1)
                for inst, pin in pin_re.findall(line):
                    if inst in macros:
                        pins[inst][pin] = net
    if die is None:
        raise ValueError(f"no DIEAREA in {def_path}")
    return die, pins


def pin_group(pin):
    return pin.split("[")[0]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--def", dest="def_path", required=True)
    ap.add_argument("--graph", required=True, help="def2graph output directory")
    ap.add_argument("-o", "--out", default="graph.html")
    ap.add_argument("--template", default=str(Path(__file__).with_name("graph_template.html")))
    args = ap.parse_args(argv)

    g = Path(args.graph)
    summary = json.loads((g / "summary.json").read_text())
    dbu = summary["dbu_per_micron"]
    cones = json.loads((g / "cones.json").read_text())["ports"]
    nodes = pd.read_parquet(g / "nodes.parquet")

    inst = nodes[nodes.ntype == "instance"].sort_values("name").reset_index(drop=True)
    ports = nodes[nodes.ntype == "port"].sort_values("name").reset_index(drop=True)
    cells = sorted(inst.cell.unique())
    # One index space: instances first, then ports.
    idx = {f"I:{n}": i for i, n in enumerate(inst.name)}
    idx.update({f"P:{n}": len(inst) + i for i, n in enumerate(ports.name)})

    macros = set(inst[inst.kind == "memory"].name)
    die, macro_pins = read_def(args.def_path, macros)

    def um(v):
        return round(float(v) / dbu, 3)

    data_inst = [[r.name, KINDS.index(r.kind), um(r.x), um(r.y), round(float(r.width), 3),
                  round(float(r.height), 3), cells.index(r.cell)] for r in inst.itertuples()]
    data_ports = [[r.name, r.direction[0], um(r.x), um(r.y)] for r in ports.itertuples()]

    data_cones = {}
    cone_nets = set()
    for name, c in cones.items():
        drivers, sinks = defaultdict(list), defaultdict(list)
        for a, b in c["edges"]:
            if b.startswith("N:"):
                drivers[b].append(a)
            elif a.startswith("N:"):
                sinks[a].append(b)
        wires = sorted({(idx[d], idx[s]) for net in drivers.keys() | sinks.keys()
                        for d in drivers.get(net, []) for s in sinks.get(net, [])
                        if d in idx and s in idx})
        members = sorted({idx[n] for n in c["nodes"] if n in idx})
        cone_nets.update(n[2:] for n in c["nodes"] if n.startswith("N:"))
        ends = []
        for e in c["endpoints"]:
            key = ("I:" if e["type"] != "port" else "P:") + e["instance"]
            if key not in idx:
                continue
            ends.append([idx[key], e["pin"], e["type"], e["depth"]])
        data_cones[name] = {"d": c["direction"][0], "m": members, "w": [list(w) for w in wires],
                            "e": ends, "depth": c["max_depth"]}

    banks = {}
    for b in sorted(macros):
        # A pin is inside a cone when its net is. def2graph lists one endpoint
        # pin per instance on a net, so its endpoints undercount.
        allp = macro_pins.get(b, {})
        got = {p for p, n in allp.items() if n in cone_nets}
        groups = defaultdict(lambda: [0, 0])
        for p in allp:
            groups[pin_group(p)][0] += 1
            groups[pin_group(p)][1] += p in got
        banks[b] = {"pins": len(allp), "reached": len(got),
                    "groups": {k: v for k, v in sorted(groups.items())}}

    data = {
        "design": summary["design"],
        "die": [um(v) for v in die],
        "kinds": KINDS,
        "cells": cells,
        "inst": data_inst,
        "ports": data_ports,
        "cones": data_cones,
        "banks": banks,
        "summary": {"flop_endpoints": summary["cell_boundaries"]["flop_endpoints_total"],
                    "memory_endpoints": summary["cell_boundaries"]["memory_endpoints_total"],
                    "nets": summary["graph_stats"]["signal_nets"]},
    }
    blob = json.dumps(data, separators=(",", ":"))
    Path(args.out).with_name("graph_data.json").write_text(blob)
    html = (Path(args.template).read_text().replace("/*__DATA__*/null", blob)
            .replace("__DESIGN__", summary["design"]))
    Path(args.out).write_text(html)
    print(f"wrote {args.out} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
