"""Check that an export is the same design as its graph JSON, with only names, order and scale changed.

Usage:
    python verify.py work/graph.json export/design.export.json --key work/key.json

It maps each export token back through the key and compares every cell, port, wire and path length
with the graph JSON. If they match, an analysis of the export gives the same result as an analysis
of the real design, in export units. It prints counts only, no names.
"""
import argparse
import sys

from common import load_json, split_bit


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("graph")
    ap.add_argument("export")
    ap.add_argument("--key", required=True)
    args = ap.parse_args(argv)
    g, x, key = load_json(args.graph), load_json(args.export), load_json(args.key)

    s, (ox, oy) = key["scale"], key["offset"]
    tol = 0.002 + 1e-6 * s
    near = lambda a, b: a is None and b is None or (a is not None and b is not None and abs(a - b) <= tol)
    X, Y, L = (lambda v: (v - ox) * s), (lambda v: (v - oy) * s), (lambda v: None if v is None else v * s)
    problems = []

    def check(ok, what):
        if not ok:
            problems.append(what)

    # nodes: export index -> graph index
    gi = {r[0]: i for i, r in enumerate(g["inst"])}
    NI, XI = len(g["inst"]), len(x["inst"])
    gp = {p[0]: NI + j for j, p in enumerate(g["ports"])}
    port_real = lambda t: key["bus"][split_bit(t)[0]] + split_bit(t)[1]
    node = {}
    for j, r in enumerate(x["inst"]):
        i = gi[key["inst"][r[0]]]
        node[j] = i
        o = g["inst"][i]
        check(x["kinds"][r[1]] == g["kinds"][o[1]], "instance kind")
        check(key["cell"][x["cells"][r[6]]] == g["cells"][o[6]], "instance cell type")
        check(all(near(a, b) for a, b in zip(r[2:6], [X(o[2]), Y(o[3]), L(o[4]), L(o[5])])), "instance geometry")
    for j, p in enumerate(x["ports"]):
        n = gp[port_real(p[0])]
        node[XI + j] = n
        o = g["ports"][n - NI]
        check(p[1] == o[1] and near(p[2], X(o[2])) and near(p[3], Y(o[3])), "port")
    check(len(x["ports"]) == len(g["ports"]), "port count")

    def pin_real(n, t):
        if n >= XI:
            return port_real(t)
        if not t:
            return t
        cell, base = key["pin"][split_bit(t)[0]]
        check(cell == g["cells"][g["inst"][node[n]][6]], "pin belongs to another cell type")
        return base + split_bit(t)[1]

    # wires: match each export wire to the graph wire with the same ends and net
    gseg = {}
    for k, si in enumerate(g["segInfo"]):
        gseg[(si[0], si[1], si[2], si[3], si[4])] = k
    xseg = {}
    for j, si in enumerate(x["segInfo"]):
        k = gseg.get((node[si[0]], pin_real(si[0], si[1]), node[si[2]], pin_real(si[2], si[3]), key["net"][si[4]]))
        if k is None:
            problems.append("wire not in the graph")
            continue
        xseg[j] = k
        q, o = x["segs"][j], g["segs"][k]
        check(near(q[0], X(o[0])) and near(q[1], Y(o[1])) and near(q[2], X(o[2])) and near(q[3], Y(o[3])),
              "wire geometry")
        check(near(si[5], L(g["segInfo"][k][5])), "wire length")
        check(x["segInCone"][j] == g["segInCone"][k] and x["segBus"][j] == g["segBus"][k], "wire flags")
    want = {k for k in range(len(g["segs"])) if key["profile"] == "full" or g["segInCone"][k]}
    check(set(xseg.values()) == want, f"the export holds other wires than profile {key['profile']} keeps")

    # cones: same endpoints and path lengths per port
    check(len(x["cones"]) == len(g["cones"]), "cone count")
    for t, c in x["cones"].items():
        o = g["cones"][port_real(t)]
        ends = sorted((node[e[0]], pin_real(e[0], e[1]) if e[2] != "port" else "", e[2], e[3], e[4])
                      for e in c["e"])
        kept = sorted((e[0], e[1] or "", e[2], e[3], L(e[4])) for e in o["e"] if e[0] in set(node.values()))
        check(len(ends) == len(kept) and all(a[:4] == b[:4] and near(a[4], b[4]) for a, b in zip(ends, kept)),
              "cone endpoints or path lengths")
        check(c["d"] == o["d"] and c["depth"] == o["depth"], "cone direction or depth")
        check(sorted(xseg[k] for k in c["s"]) == sorted(k for k in o["s"] if k in want), "cone wires")

    # banks
    check(len(x["banks"]) == len(g["banks"]), "memory count")
    for t, b in x["banks"].items():
        o = g["banks"][key["inst"][t]]
        groups = {key["pin"][p][1]: v for p, v in b["groups"].items()}
        check(groups == o["groups"] and b["pins"] == o["pins"] and b["reached"] == o["reached"], "memory pins")
        check(sorted(xseg[k] for k in b["in"]) == sorted(k for k in o["in"] if k in want), "memory wires in")
        check(sorted(xseg[k] for k in b["out"]) == sorted(k for k in o["out"] if k in want), "memory wires out")

    # roles: only the ones the key recorded, each on a bus of the export
    check(x.get("roles", {}) == key.get("roles", {}), "roles differ from the key's")
    check(all(t in key["bus"] for t in x.get("roles", {})), "a role names a bus not in the key")

    print(f"compared {len(x['inst'])} instances, {len(x['ports'])} ports, {len(xseg)} wires, "
          f"{len(x['cones'])} cones, {len(x['banks'])} memories (profile {key['profile']}, scale {s:g})")
    if problems:
        from collections import Counter
        for what, n in Counter(problems).most_common():
            print(f"  FAIL {n} x {what}")
        sys.exit(1)
    print("PASS: same cells, ports, wires, cones and path lengths. Only names, order and scale differ.")


if __name__ == "__main__":
    main()
