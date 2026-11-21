"""Write a graph JSON (format placehead-graph/1): def2graph's port cones on the placement.

Usage (extract.py runs it):
    python make_graph_json.py --def design.def --lef *.lef --graph work/graph -o work/graph.json

def2graph decides what is in each cone (cones.json, nodes.parquet). This script
adds geometry: each pin's position from its cell's LEF pin shape and the cell's
placement and orientation, and each wire as a straight segment from the pin
that drives a net to each pin it feeds. The DEF has no routing, so a wire's
length is the Manhattan distance between its two pins: a lower bound on a route.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

KINDS = ["comb", "flop", "memory"]


def read_lef(paths):
    """Per macro: (width, height) and {pin: (direction, (x, y) centre of its first shape)}."""
    macros = {}
    for path in paths:
        text = Path(path).read_text()
        for mm in re.finditer(r"^MACRO\s+(\S+)(.*?)^END\s+\1\b", text, re.S | re.M):
            name, body = mm.groups()
            size = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", body)
            pins = {}
            for pm in re.finditer(r"^\s*PIN\s+(\S+)\s*$", body, re.M):
                pname = pm.group(1)
                # Pin names hold brackets (addr_in[0]), so find the END line as plain text.
                end = re.search(r"^\s*END\s+" + re.escape(pname) + r"\s*$", body[pm.end():], re.M)
                pbody = body[pm.end():pm.end() + end.start()] if end else ""
                d = re.search(r"DIRECTION\s+(\S+)", pbody)
                r = re.search(r"RECT\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)", pbody)
                if r:
                    x0, y0, x1, y1 = map(float, r.groups())
                    pins[pname] = (d.group(1) if d else "INPUT", ((x0 + x1) / 2, (y0 + y1) / 2))
            macros[name] = ((float(size.group(1)), float(size.group(2))) if size else (0, 0), pins)
    return macros


def orient(x, y, w, h, o):
    """A point in a cell's LEF frame, moved to its placed frame (origin at the placed lower-left)."""
    return {"N": (x, y), "S": (w - x, h - y), "FN": (w - x, y), "FS": (x, h - y),
            "W": (h - y, x), "E": (y, w - x), "FW": (y, x), "FE": (h - y, w - x)}[o]


def read_def(def_path):
    """Die area (DEF units) and {net: [(instance or 'PIN', pin)]} for signal nets."""
    die, nets = None, defaultdict(list)
    in_nets, net = False, None
    conn = re.compile(r"\(\s*(\S+)\s+(\S+)\s*\)")
    with open(def_path) as f:
        for line in f:
            if die is None:
                m = re.match(r"\s*DIEAREA\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)", line)
                if m:
                    die = [int(v) for v in m.groups()]
            if re.match(r"\s*NETS\s+\d+", line):
                in_nets = True
                continue
            if re.match(r"\s*END\s+NETS", line):
                in_nets = False
            if not in_nets:
                continue
            m = re.match(r"\s*-\s+(\S+)", line)
            if m:
                net = m.group(1)
            nets[net].extend(conn.findall(line.split("+")[0]))
    if die is None:
        raise ValueError(f"no DIEAREA in {def_path}")
    return die, nets


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--def", dest="def_path", required=True)
    ap.add_argument("--lef", nargs="+", required=True)
    ap.add_argument("--graph", required=True, help="def2graph output directory")
    ap.add_argument("-o", "--out", default="graph.json")
    args = ap.parse_args(argv)
    sys.setrecursionlimit(20000)

    g = Path(args.graph)
    summary = json.loads((g / "summary.json").read_text())
    dbu = summary["dbu_per_micron"]
    cones = json.loads((g / "cones.json").read_text())["ports"]
    nodes = pd.read_parquet(g / "nodes.parquet")
    lef = read_lef(args.lef)
    die, nets = read_def(args.def_path)

    inst = nodes[nodes.ntype == "instance"].sort_values("name").reset_index(drop=True)
    ports = nodes[nodes.ntype == "port"].sort_values("name").reset_index(drop=True)
    cells = sorted(inst.cell.unique())
    idx = {f"I:{n}": i for i, n in enumerate(inst.name)}
    idx.update({f"P:{n}": len(inst) + i for i, n in enumerate(ports.name)})
    kind = dict(zip(inst.name, inst.kind))
    placed = {r.name: (r.cell, r.x / dbu, r.y / dbu, r.orient) for r in inst.itertuples()}
    port_at = {r.name: (r.x / dbu, r.y / dbu, r.direction) for r in ports.itertuples()}

    def um(v):
        return round(float(v) / dbu, 3)

    # ---- pins: position and direction ----
    def pin_xy(i, p):
        if i == "PIN":
            x, y, _ = port_at[p]
            return x, y
        cell, x, y, o = placed[i]
        (w, h), pins = lef[cell]
        px, py = orient(*pins[p][1], w, h, o)
        return x + px, y + py

    def drives(i, p):
        if i == "PIN":
            return port_at[p][2] == "INPUT"
        return lef[placed[i][0]][1][p][0] == "OUTPUT"

    def node_of(i, p):
        return f"P:{p}" if i == "PIN" else f"I:{i}"

    # ---- wires: one segment from a net's driver pin to each pin it feeds ----
    segs, seg_net, fanout, fanin = [], [], defaultdict(list), {}
    for net, conns in nets.items():
        conns = [(i, p) for i, p in conns if i == "PIN" or (i in placed and p in lef[placed[i][0]][1])]
        drv = [c for c in conns if drives(*c)]
        if len(drv) != 1:
            continue
        d = drv[0]
        for s in conns:
            if s == d:
                continue
            (x1, y1), (x2, y2) = pin_xy(*d), pin_xy(*s)
            k = len(segs)
            segs.append([round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)])
            seg_net.append((net, d, s, abs(x1 - x2) + abs(y1 - y2)))
            fanout[d].append(k)
            fanin[s] = k

    # ---- bus wires: the bit of a bus each net carries ----
    # A net carries bit n when its name ends in [n], or when the plain gate driving it
    # gets bit n and no other bit on its inputs (an inverter, a masking AND, an OR tree).
    # A gate that mixes bits (a decoder) drives a net that carries no bit.
    def bit_of(name):
        m = re.search(r"\[(\d+)\]$", name)
        return int(m.group(1)) if m else None

    drv_of = {}
    for net, conns in nets.items():
        for c in conns:
            if (c[0] == "PIN" or (c[0] in placed and c[1] in lef[placed[c[0]][0]][1])) and drives(*c):
                drv_of[net] = c
    pin_net = {c: net for net, conns in nets.items() for c in conns}
    net_bit = {}

    def carries(net):
        if net in net_bit:
            return net_bit[net]
        net_bit[net] = None
        b = bit_of(net)
        d = drv_of.get(net)
        if b is None and d is not None and d[0] != "PIN" and kind.get(d[0]) == "comb":
            ins = {carries(pin_net[(d[0], p)]) for p, (dr, _) in lef[placed[d[0]][0]][1].items()
                   if dr != "OUTPUT" and (d[0], p) in pin_net}
            ins.discard(None)
            b = ins.pop() if len(ins) == 1 else None
        net_bit[net] = b
        return b

    def cell_pins(i, out):
        return [(i, p) for p, (dr, _) in lef[placed[i][0]][1].items()
                if (dr == "OUTPUT") == out and (i, p) in (fanout if out else fanin)]

    # ---- cones: which wires def2graph's cone holds, and each endpoint's path length ----
    data_cones = {}
    in_any_cone = set()
    for name, c in cones.items():
        members = set(c["nodes"])
        segs_in = [k for k, (net, d, s, _) in enumerate(seg_net)
                   if f"N:{net}" in members and node_of(*d) in members and node_of(*s) in members]
        in_any_cone.update(segs_in)
        segset = set(segs_in)
        memo = {}

        # Longest wire length along the cone's wires, through plain gates only.
        if c["direction"] == "INPUT":
            def length(pin):           # from the top-level pin to `pin`
                if pin in memo:
                    return memo[pin]
                i, p = pin
                if i == "PIN" and p == name:
                    best = 0.0
                elif not drives(i, p):
                    k = fanin.get(pin)
                    best = length(seg_net[k][1]) + seg_net[k][3] if k in segset else float("-inf")
                elif kind.get(i) == "comb":
                    best = max([length(q) for q in cell_pins(i, False)], default=float("-inf"))
                else:
                    best = float("-inf")
                memo[pin] = best
                return best
        else:
            def length(pin):           # from `pin` to the top-level pin
                if pin in memo:
                    return memo[pin]
                i, p = pin
                if i == "PIN" and p == name:
                    best = 0.0
                elif drives(i, p):
                    best = max([length(seg_net[k][2]) + seg_net[k][3] for k in fanout.get(pin, []) if k in segset],
                               default=float("-inf"))
                elif kind.get(i) == "comb":
                    best = max([length(q) for q in cell_pins(i, True)], default=float("-inf"))
                else:
                    best = float("-inf")
                memo[pin] = best
                return best

        ends = []
        for e in c["endpoints"]:
            key = ("P:" if e["type"] == "port" else "I:") + e["instance"]
            if key not in idx:
                continue
            pin = ("PIN", e["instance"]) if e["type"] == "port" else (e["instance"], e["pin"])
            try:
                L = length(pin)
            except KeyError:
                L = float("-inf")
            ends.append([idx[key], e["pin"] or "", e["type"], e["depth"], round(L, 2) if L > float("-inf") else None])
        data_cones[name] = {"d": c["direction"][0], "m": sorted({idx[n] for n in members if n in idx}),
                            "s": segs_in, "e": ends, "depth": c["max_depth"]}

    # ---- banks: every wire into and out of each memory, back to a flop or top-level pin ----
    banks = {}
    for b in sorted(n for n, k in kind.items() if k == "memory"):
        pins = lef[placed[b][0]][1]
        seg_in, seg_out = set(), set()

        def back(pin):                  # wires that feed `pin`
            k = fanin.get(pin)
            if k is None or k in seg_in:
                return
            seg_in.add(k)
            i, _ = seg_net[k][1]
            if i != "PIN" and kind.get(i) == "comb":
                for q in cell_pins(i, False):
                    back(q)

        def fwd(pin):                   # wires `pin` feeds
            for k in fanout.get(pin, []):
                if k in seg_out:
                    continue
                seg_out.add(k)
                i, _ = seg_net[k][2]
                if i != "PIN" and kind.get(i) == "comb":
                    for q in cell_pins(i, True):
                        fwd(q)

        groups = defaultdict(lambda: [0, 0])
        for p, (dr, _) in pins.items():
            pin = (b, p)
            if pin not in fanin and pin not in fanout:
                continue                # power, or unconnected
            back(pin) if dr != "OUTPUT" else fwd(pin)
            k = fanin.get(pin) if dr != "OUTPUT" else (fanout.get(pin) or [None])[0]
            grp = groups[p.split("[")[0]]
            grp[0] += 1
            grp[1] += k in in_any_cone
        banks[b] = {"pins": sum(v[0] for v in groups.values()), "reached": sum(v[1] for v in groups.values()),
                    "groups": dict(sorted(groups.items())), "in": sorted(seg_in), "out": sorted(seg_out)}

    data = {
        "format": "placehead-graph/1",
        "design": summary["design"],
        "die": [um(v) for v in die],
        "kinds": KINDS,
        "cells": cells,
        "inst": [[r.name, KINDS.index(r.kind), um(r.x), um(r.y), round(float(r.width), 3),
                  round(float(r.height), 3), cells.index(r.cell)] for r in inst.itertuples()],
        "ports": [[r.name, r.direction[0], um(r.x), um(r.y)] for r in ports.itertuples()],
        "segs": segs,
        "segInCone": [int(k in in_any_cone) for k in range(len(segs))],
        # A bus wire carries one bit of a bus, or lands on a pin that is one bit of a bus.
        "segBus": [int(carries(net) is not None or bit_of(d[1]) is not None or bit_of(s[1]) is not None)
                   for net, d, s, L in seg_net],
        # Per wire: driver node, driver pin, sink node, sink pin, net, length (um).
        "segInfo": [[idx[node_of(*d)], d[1], idx[node_of(*s)], s[1], net, round(L, 2)]
                    for net, d, s, L in seg_net],
        "cones": data_cones,
        "banks": banks,
        "summary": {"flop_endpoints": summary["cell_boundaries"]["flop_endpoints_total"],
                    "memory_endpoints": summary["cell_boundaries"]["memory_endpoints_total"],
                    "nets": summary["graph_stats"]["signal_nets"]},
    }
    blob = json.dumps(data, separators=(",", ":"))
    Path(args.out).write_text(blob)
    print(f"wrote {args.out} ({len(blob) // 1024} KB), {len(segs)} wires")


if __name__ == "__main__":
    main()
