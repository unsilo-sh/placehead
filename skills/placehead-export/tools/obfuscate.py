"""Replace every design name in a graph JSON with a token, and write the key that undoes it.

Usage:
    python obfuscate.py work/graph.json --key work/key.json -o export/design.export.json
        [--profile cones|full] [--scale 1|random|FACTOR]

The input is the graph JSON that extract.py writes (format placehead-graph/1). It holds real names.
The output holds no name from the design. Only the output leaves your site. The key stays with you.

What changes:
  names     instances, nets, ports, cell types, pins and the design name become tokens (common.py).
            A port keeps its bit index, so a bus stays a bus: addr[3] becomes ob7[3].
  order     instances, ports, cell types and wires are shuffled, so list order does not show the
            sort order of the real names.
  geometry  coordinates move so that the die's lower-left corner is (0, 0). With --scale, every
            coordinate and length is also multiplied by one factor, kept in the key.
  profile   cones (the default) keeps only the wires inside the port cones, the cells on them,
            every memory and every port. full keeps every wire and every cell.
  roles     opt-in, with --roles: each bus you list gets a role from a fixed list (common.ROLES),
            such as read_data. The export holds the role, never the bus's real name.
            --roles-template work/roles.json writes a file to fill in, then stops. It holds the
            real bus names, so keep it in work/.

What does not change: which cell connects to which, the kind of each cell (comb, flop, memory),
cell sizes and positions relative to each other, and path lengths (times the scale).
"""
import argparse
import hashlib
import json
import os
import random
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import GRAPH_FORMAT, KEY_FORMAT, ROLES, load_json, split_bit


def write_roles_template(g, path):
    """One entry per bus: its direction, its width, and an empty role to fill in."""
    buses = {}
    for name, d, *_ in g["ports"]:
        b = buses.setdefault(split_bit(name)[0], {"direction": d, "width": 0, "role": ""})
        b["width"] += 1
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({
        "about": "Set each role to one of 'allowed', or leave it empty to send no role for that bus. "
                 "This file holds real bus names: keep it on your side.",
        "allowed": list(ROLES), "buses": dict(sorted(buses.items()))}, indent=1))
    print(f"wrote {path}: {len(buses)} buses. Fill in the roles, then run with --roles {path}.")


def read_roles(path, g):
    """{real bus name: role} for the buses with a role. Stops on an unknown bus or role."""
    buses = load_json(path).get("buses", {})
    real = {split_bit(p[0])[0] for p in g["ports"]}
    roles = {}
    for bus, rec in buses.items():
        role = rec.get("role", "") if isinstance(rec, dict) else rec
        if not role:
            continue
        if bus not in real:
            sys.exit(f"error: {path} names a bus that is not in the design")
        if role not in ROLES:
            sys.exit(f"error: {path} has a role that is not in the allowed list: {', '.join(ROLES)}")
        roles[bus] = role
    return roles


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("graph", help="graph JSON from extract.py (holds real names)")
    ap.add_argument("--roles-template", help="write a roles file to fill in, then stop")
    ap.add_argument("--roles", help="opt-in: a filled-in roles file; the export carries each bus's role")
    ap.add_argument("--key", help="where to write the key (keep it; never send it)")
    ap.add_argument("-o", "--out", help="the export file to write")
    ap.add_argument("--profile", choices=["cones", "full"], default="cones")
    ap.add_argument("--scale", default="1", help="1 (default), random (0.5 to 2), or a factor")
    ap.add_argument("--seed", type=int, help="fixed shuffle, for tests only: anyone with the seed "
                                             "can undo the shuffle, not the names")
    args = ap.parse_args(argv)

    if args.roles_template:
        g = load_json(args.graph)
        if g.get("format") != GRAPH_FORMAT:
            sys.exit(f"error: {args.graph} is not a {GRAPH_FORMAT} file")
        return write_roles_template(g, args.roles_template)
    if not (args.key and args.out):
        ap.error("--key and -o are required")
    out, key_path = Path(args.out).resolve(), Path(args.key).resolve()
    if key_path.parent == out.parent:
        sys.exit("error: write the key outside the export directory, so it is not sent by mistake")

    raw = Path(args.graph).read_bytes()
    g = json.loads(raw)
    if g.get("format") != GRAPH_FORMAT:
        sys.exit(f"error: {args.graph} is not a {GRAPH_FORMAT} file")
    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    scale = (round(rng.uniform(0.5, 2.0), 4) if args.scale == "random" else float(args.scale))
    ox, oy = g["die"][0], g["die"][1]

    NI = len(g["inst"])
    kinds, cells = g["kinds"], g["cells"]
    is_port = lambda n: n >= NI

    # ---- what to keep ----
    nseg = len(g["segs"])
    keep_seg = [k for k in range(nseg) if args.profile == "full" or g["segInCone"][k]]
    keep_node = set(range(NI, NI + len(g["ports"])))
    keep_node |= {i for i, r in enumerate(g["inst"]) if kinds[r[1]] == "memory"}
    if args.profile == "full":
        keep_node |= set(range(NI))
    for k in keep_seg:
        keep_node |= {g["segInfo"][k][0], g["segInfo"][k][2]}

    # ---- new order and new indices ----
    def shuffled(xs):
        xs = list(xs)
        rng.shuffle(xs)
        return xs

    insts = shuffled(i for i in range(NI) if i in keep_node)
    ports = shuffled(range(NI, NI + len(g["ports"])))
    node_new = {n: j for j, n in enumerate(insts)}
    node_new.update({n: len(insts) + j for j, n in enumerate(ports)})
    segs = shuffled(keep_seg)
    seg_new = {k: j for j, k in enumerate(segs)}

    used_cells = sorted({g["inst"][i][6] for i in insts})
    cell_order = shuffled(used_cells)
    cell_new = {c: j for j, c in enumerate(cell_order)}

    # ---- tokens ----
    inst_tok = {i: f"oi{node_new[i]}" for i in insts}
    buses = shuffled(sorted({split_bit(g["ports"][n - NI][0])[0] for n in ports}))
    bus_tok = {b: f"ob{j}" for j, b in enumerate(buses)}

    def port_tok(name):
        base, bit = split_bit(name)
        return bus_tok[base] + bit

    pin_keys = set()                    # (cell index, pin base) for every pin the export names
    for k in segs:
        d, dp, s, sp = g["segInfo"][k][:4]
        for n, p in ((d, dp), (s, sp)):
            if not is_port(n):
                pin_keys.add((g["inst"][n][6], split_bit(p)[0]))
    for c in g["cones"].values():
        for e in c["e"]:
            if e[2] != "port" and e[1] and e[0] in keep_node:
                pin_keys.add((g["inst"][e[0]][6], split_bit(e[1])[0]))
    for b, rec in g["banks"].items():
        cell = next(r[6] for r in g["inst"] if r[0] == b)
        pin_keys |= {(cell, p) for p in rec["groups"]}
    pin_tok = {pk: f"op{j}" for j, pk in enumerate(shuffled(sorted(pin_keys)))}

    def pin(n, p):
        if is_port(n):
            return port_tok(g["ports"][n - NI][0])
        if not p:
            return p
        base, bit = split_bit(p)
        return pin_tok[(g["inst"][n][6], base)] + bit

    nets = shuffled(sorted({g["segInfo"][k][4] for k in segs}))
    net_tok = {n: f"on{j}" for j, n in enumerate(nets)}

    # A token must never equal a real name: a reader could not tell the two apart.
    real = {r[0] for r in g["inst"]} | {p[0] for p in g["ports"]} | set(cells) | set(nets)
    real |= {split_bit(p[0])[0] for p in g["ports"]} | {b for (_, b) in pin_keys}
    toks = set(inst_tok.values()) | set(bus_tok.values()) | set(net_tok.values()) | set(pin_tok.values())
    toks |= {f"oc{j}" for j in range(len(cell_order))}
    clash = toks & real
    if clash:
        sys.exit(f"error: {len(clash)} tokens equal real names in this design. Tell unsilo.")

    # ---- geometry ----
    X = lambda x: round((x - ox) * scale, 3)
    Y = lambda y: round((y - oy) * scale, 3)
    L = lambda v: None if v is None else round(v * scale, 3)

    data = {
        "format": GRAPH_FORMAT,
        "design": "design",
        "die": [X(g["die"][0]), Y(g["die"][1]), X(g["die"][2]), Y(g["die"][3])],
        "kinds": kinds,
        "cells": [f"oc{j}" for j in range(len(cell_order))],
        "inst": [[inst_tok[i], r[1], X(r[2]), Y(r[3]), L(r[4]), L(r[5]), cell_new[r[6]]]
                 for i in insts for r in [g["inst"][i]]],
        "ports": [[port_tok(p[0]), p[1], X(p[2]), Y(p[3])] for n in ports for p in [g["ports"][n - NI]]],
        "segs": [[X(q[0]), Y(q[1]), X(q[2]), Y(q[3])] for k in segs for q in [g["segs"][k]]],
        "segInCone": [g["segInCone"][k] for k in segs],
        "segBus": [g["segBus"][k] for k in segs],
        "segInfo": [[node_new[d], pin(d, dp), node_new[s], pin(s, sp), net_tok[net], L(ln)]
                    for k in segs for d, dp, s, sp, net, ln in [g["segInfo"][k]]],
    }

    cones = {}
    for name, c in g["cones"].items():
        cones[port_tok(name)] = {
            "d": c["d"],
            "m": sorted(node_new[n] for n in c["m"] if n in node_new),
            "s": sorted(seg_new[k] for k in c["s"] if k in seg_new),
            "e": sorted([[node_new[e[0]], pin(e[0], e[1]) if e[2] != "port" else "", e[2], e[3], L(e[4])]
                         for e in c["e"] if e[0] in node_new], key=lambda e: (e[0], e[1])),
            "depth": c["depth"],
        }
    data["cones"] = dict(sorted(cones.items()))

    banks = {}
    for b, rec in g["banks"].items():
        i = next(j for j, r in enumerate(g["inst"]) if r[0] == b)
        cell = g["inst"][i][6]
        banks[inst_tok[i]] = {
            "pins": rec["pins"], "reached": rec["reached"],
            "groups": dict(sorted((pin_tok[(cell, p)], v) for p, v in rec["groups"].items())),
            "in": sorted(seg_new[k] for k in rec["in"] if k in seg_new),
            "out": sorted(seg_new[k] for k in rec["out"] if k in seg_new),
        }
    data["banks"] = dict(sorted(banks.items()))
    data["summary"] = {"flop_endpoints": g["summary"]["flop_endpoints"],
                       "memory_endpoints": g["summary"]["memory_endpoints"],
                       "nets": len(nets) if args.profile == "cones" else g["summary"]["nets"]}
    roles = read_roles(args.roles, g) if args.roles else {}
    if roles:
        data["roles"] = dict(sorted((bus_tok[b], r) for b, r in roles.items()))

    blob = json.dumps(data, separators=(",", ":")).encode()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)

    key = {
        "format": KEY_FORMAT,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graph_sha256": hashlib.sha256(raw).hexdigest(),
        "export_sha256": hashlib.sha256(blob).hexdigest(),
        "profile": args.profile, "scale": scale, "offset": [ox, oy],
        "design": g["design"],
        "inst": {inst_tok[i]: g["inst"][i][0] for i in insts},
        "bus": {t: b for b, t in bus_tok.items()},
        "cell": {f"oc{j}": cells[c] for j, c in enumerate(cell_order)},
        "pin": {t: [cells[c], p] for (c, p), t in pin_tok.items()},
        "net": {t: n for n, t in net_tok.items()},
        "roles": data.get("roles", {}),
    }
    key_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(key, f)

    print(f"wrote {out} ({len(blob) // 1024} KB, sha256 {key['export_sha256'][:12]})")
    print(f"  profile {args.profile}: {len(insts)} of {NI} instances, {len(segs)} of {nseg} wires, "
          f"{len(ports)} ports, {len(nets)} nets")
    print(f"  scale {'1 (lengths in um)' if scale == 1 else 'kept in the key'}")
    print(f"  roles: {len(roles)} of {len(buses)} buses carry a role" if args.roles else "  roles: none sent")
    print(f"wrote key {key_path} (mode 600). Keep it. Do not send it.")


if __name__ == "__main__":
    main()
