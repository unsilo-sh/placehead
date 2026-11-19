"""Placement headroom: how much shorter port-to-memory paths get with a few moves.

Usage:
    python headroom.py out/sparse_mem_core.graph.json --k 8 --ports 2 -o out/headroom.json

Paths: the wires in def2graph's cones from an input port, through gates, to a bank input pin,
and from a bank output pin, through gates, to an output port.

Scores, in um of wire:
  worst  the longest path
  total  the sum, over bank pins, of each pin's longest path

A placement is scored by the Manhattan distance between each path's two ends, which is
the shortest a placer could make it. With no limit on gate area, re-placed gates can always sit
on such routes, so a linear program over gate positions gives the same numbers (--check-lp).
"now" is the current placement with its gates where they are.

Moves:
  bank   relocate one bank to a legal spot, or change its orientation (N, FN, FS, S)
  port   move one bus's pins to a new place in the bottom edge's order; the other buses close
         up around it, in order, at the same pitch

Search: for each port budget P, the best port moves first (greedy), then up to K bank moves
(greedy), once to lower the worst path first and once to lower the total first.

Our choices, not the spec's: bank spacing GAP, die margin MARGIN, the keep-out above the pin
row PIN_KEEPOUT, the position grid STEP, the scores, and the search order.
"""
import argparse
import bisect
import itertools
import json
from collections import defaultdict

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

GAP, MARGIN, PIN_KEEPOUT, STEP = 15.0, 10.0, 20.0, 10.0
KEEPOUTS = []   # rectangles (x0, y0, x1, y1) no bank may overlap, e.g. an aisle kept for logic
ORIENTS = ("N", "FN", "FS", "S")
SIGNS = np.array([[1, 1], [1, -1], [-1, 1], [-1, -1]], float)


def flip(off, w, h, o):
    """Pin offsets (n, 2) of a bank placed N, moved to orientation o."""
    x, y = off[:, 0], off[:, 1]
    return np.stack({"N": (x, y), "FN": (w - x, y), "FS": (x, h - y), "S": (w - x, h - y)}[o], axis=1)


class Design:
    def __init__(self, g):
        self.g = g
        NI = self.NI = len(g["inst"])
        self.die = g["die"]
        self.name = name = lambda n: g["inst"][n][0] if n < NI else g["ports"][n - NI][0]
        SI = g["segInfo"]
        self.isgate = isgate = lambda n: n < NI and g["kinds"][g["inst"][n][1]] == "comb"
        self.banks = [i for i, r in enumerate(g["inst"]) if g["kinds"][r[1]] == "memory"]
        self.bpos = np.array([[g["inst"][b][2], g["inst"][b][3]] for b in self.banks])
        self.w, self.h = g["inst"][self.banks[0]][4], g["inst"][self.banks[0]][5]

        # Bank pin offsets, from the wire ends at each pin. All banks are placed N now.
        pin_xy = {}
        for k, s in enumerate(SI):
            q = g["segs"][k]
            pin_xy[(s[0], s[1])] = (q[0], q[1])
            pin_xy[(s[2], s[3])] = (q[2], q[3])
        b0 = self.banks[0]
        pins = sorted(p for (n, p) in pin_xy if n == b0)
        off = {p: np.array(pin_xy[(b0, p)]) - self.bpos[0] for p in pins}
        for bi, b in enumerate(self.banks):
            for p in pins:
                if (b, p) in pin_xy:
                    assert np.allclose(np.array(pin_xy[(b, p)]) - self.bpos[bi], off[p], atol=0.05), (b, p)

        # The ports each bank pin's paths reach, along cone wires through gates: back from an
        # input pin to input ports, forward from an output pin to output ports. def2graph lists
        # one endpoint pin per bank on a net, so its endpoint list would miss w_mask_in.
        fin, fout = defaultdict(list), defaultdict(list)
        for k, v in enumerate(g["segInCone"]):
            if v:
                fin[SI[k][2]].append(k)
                fout[SI[k][0]].append(k)

        def ports_of(b, p):
            found = set()
            for nbr, end, own_pin in ((fin, 0, 3), (fout, 2, 1)):
                seen, stack = set(), [(b, p)]
                while stack:
                    n, q = stack.pop()
                    for k in nbr[n]:
                        if q is not None and SI[k][own_pin] != q:
                            continue            # at the bank, only the wires on this pin
                        m = SI[k][end]
                        if m >= NI:
                            found.add(name(m))
                        elif isgate(m) and m not in seen:
                            seen.add(m)
                            stack.append((m, None))
            return frozenset(found)

        reach = {p: ports_of(b0, p) for p in pins}
        for b in self.banks[1:]:
            for p in pins:
                assert ports_of(b, p) == reach[p], f"{name(b)}.{p} reaches other ports than {name(b0)}.{p}"
        self.pins = [p for p in pins if reach[p]]          # bank pins on a cone path
        self.reach = [sorted(reach[p]) for p in self.pins]
        self.off = np.array([off[p] for p in self.pins])

        # Ports, grouped by bus in their left-to-right order on the bottom edge.
        self.ports = {p[0]: (p[2], p[3]) for p in g["ports"]}
        bus = lambda n: n.split("[")[0]
        order = sorted(self.ports, key=lambda n: self.ports[n][0])
        self.groups = []
        for n in order:
            if not self.groups or self.groups[-1][0] != bus(n):
                self.groups.append((bus(n), []))
            self.groups[-1][1].append(n)
        xs = [self.ports[n][0] for n in order]
        self.pitch = (xs[-1] - xs[0]) / (len(xs) - 1)
        self.x0, self.py = xs[0], self.ports[order[0]][1]

    # ---- state: bank positions and orientations, and the bus order on the bottom edge ----
    def initial(self):
        return {"pos": self.bpos.copy(), "orient": ["N"] * len(self.banks),
                "order": [b for b, _ in self.groups], "moves": []}

    def port_xy(self, order):
        members, xy, x = dict(self.groups), {}, self.x0
        for b in order:
            for n in members[b]:
                xy[n] = (x, self.py)
                x += self.pitch
        return xy

    # ---- scores ----
    def extremes(self, order):
        """Per bank pin and sign pair s: min over its ports of s . port. Then the longest straight
        line from a point P to those ports is max over s of (s . P - extreme[s])."""
        pxy = self.port_xy(order)
        return np.array([[min(s @ np.array(pxy[p]) for p in ports) for s in SIGNS] for ports in self.reach])

    def pin_worst(self, P, E):
        """P (..., pins, 2) pin positions -> (..., pins) longest straight line to the pin's ports."""
        return (P[..., None, :] * SIGNS).sum(-1).__sub__(E).max(-1)

    def bank_scores(self, st, E):
        out = []
        for b in range(len(self.banks)):
            v = self.pin_worst(st["pos"][b] + flip(self.off, self.w, self.h, st["orient"][b]), E)
            out.append((v.max(), v.sum()))
        return np.array(out)

    def detail(self, st):
        """Each bank's worst path, and the overall worst path's bank, pin, port and ends."""
        E = self.extremes(st["order"])
        pxy = self.port_xy(st["order"])
        bs = self.bank_scores(st, E)
        b = int(bs[:, 0].argmax())
        P = st["pos"][b] + flip(self.off, self.w, self.h, st["orient"][b])
        v = self.pin_worst(P, E)
        j = int(v.argmax())
        port = max(self.reach[j], key=lambda n: abs(pxy[n][0] - P[j][0]) + abs(pxy[n][1] - P[j][1]))
        return {"bank_worst": bs[:, 0].round(1).tolist(), "bank_total": bs[:, 1].round(1).tolist(),
                "worst_path": {"bank": self.name(self.banks[b]), "pin": self.pins[j], "port": port,
                               "length": round(float(v[j]), 1), "from": [round(c, 2) for c in pxy[port]],
                               "to": P[j].round(2).tolist()}}

    def geometry(self):
        side = {o: ("left" if flip(self.off, self.w, self.h, o)[:, 0].mean() < self.w / 2 else "right") for o in ORIENTS}
        return {"design": self.g["design"], "die": self.die, "bank_size": [self.w, self.h],
                "banks": [self.name(b) for b in self.banks], "start_pos": self.bpos.round(2).tolist(),
                "groups": [[b, len(m)] for b, m in self.groups], "pin_x0": self.x0, "pin_pitch": self.pitch,
                "pin_y": self.py, "pin_side": side, "bank_pins": len(self.pins)}

    def scores(self, st, E=None):
        bs = self.bank_scores(st, self.extremes(st["order"]) if E is None else E)
        return float(bs[:, 0].max()), float(bs[:, 1].sum())

    # ---- bank moves: one score grid for every bank, since all banks reach the same ports ----
    def grid_axes(self):
        x = np.arange(self.die[0] + MARGIN, self.die[2] - MARGIN - self.w + 1e-6, STEP)
        y = np.arange(self.die[1] + PIN_KEEPOUT, self.die[3] - MARGIN - self.h + 1e-6, STEP)
        return x, y

    def score_grid(self, E):
        x, y = self.grid_axes()
        X, Y = np.meshgrid(x, y)                                    # (ny, nx)
        C = np.stack([X, Y], -1)
        worst, total = {}, {}
        for o in ORIENTS:
            v = self.pin_worst(C[..., None, :] + flip(self.off, self.w, self.h, o), E)   # (ny, nx, pins)
            worst[o], total[o] = v.max(-1), v.sum(-1)
        return x, y, worst, total

    def blocked_by(self, x, y, pos):
        """Grid cells where a bank would come within GAP of a bank at pos."""
        bx = (x > pos[0] - self.w - GAP) & (x < pos[0] + self.w + GAP)
        by = (y > pos[1] - self.h - GAP) & (y < pos[1] + self.h + GAP)
        return by[:, None] & bx[None, :]

    def kept_out(self, x, y):
        """Grid cells where a bank would overlap a keep-out rectangle."""
        out = np.zeros((len(y), len(x)), bool)
        for x0, y0, x1, y1 in KEEPOUTS:
            out |= ((y + self.h > y0) & (y < y1))[:, None] & ((x + self.w > x0) & (x < x1))[None, :]
        return out

    def best_bank_move(self, st, objective, grid):
        x, y, gw, gt = grid
        bs = self.bank_scores(st, self.extremes(st["order"]))
        paint = [self.blocked_by(x, y, p) for p in st["pos"]]
        count = np.sum(paint, axis=0) + self.kept_out(x, y)
        best = None
        for b in range(len(self.banks)):
            free = (count - paint[b]) == 0
            worst_others = np.delete(bs[:, 0], b).max()
            total_others = bs[:, 1].sum() - bs[b, 1]
            for o in ORIENTS:
                w = np.where(free, np.maximum(gw[o], worst_others), np.inf)
                t = np.where(free, gt[o] + total_others, np.inf)
                a, c = (w, t) if objective == "worst" else (t, w)
                k = np.lexsort((c.ravel(), a.ravel()))[0]
                score = (float(a.ravel()[k]), float(c.ravel()[k]))
                if best is None or score < best[0]:
                    iy, ix = np.unravel_index(k, a.shape)
                    best = (score, b, np.array([x[ix], y[iy]]), o)
        return best

    def best_port_move(self, st, objective):
        best = None
        for b in st["order"]:
            rest = [g for g in st["order"] if g != b]
            for j in range(len(rest) + 1):
                order = rest[:j] + [b] + rest[j:]
                if order == st["order"]:
                    continue
                w, t = self.scores(dict(st, order=order))
                score = (w, t) if objective == "worst" else (t, w)
                if best is None or score < best[0]:
                    best = (score, b, j, order)
        return best

    # ---- the current gates, and the linear-program check ----
    def wire_scores(self, st, free_gates):
        """Longest path to or from each bank pin along cone wires, with gates where they are
        (free_gates False) or placed by a linear program (free_gates True)."""
        g, NI, SI = self.g, self.NI, self.g["segInfo"]
        pxy = self.port_xy(st["order"])
        bank_of = {b: bi for bi, b in enumerate(self.banks)}
        pin_ix = {p: j for j, p in enumerate(self.pins)}
        banks = set(self.banks)

        def fixed_xy(n, pin):
            if n >= NI:
                return pxy[self.name(n)]
            bi = bank_of[n]
            return tuple(st["pos"][bi] + flip(self.off, self.w, self.h, st["orient"][bi])[pin_ix[pin]])

        cone = [k for k, v in enumerate(g["segInCone"]) if v]
        out, inn = defaultdict(list), defaultdict(list)
        for k in cone:
            out[SI[k][0]].append(k)
            inn[SI[k][2]].append(k)

        def reach(starts, nbr, end):
            seen, stack = set(starts), list(starts)
            while stack:
                n = stack.pop()
                for k in nbr[n]:
                    m = SI[k][end]
                    if m not in seen:
                        seen.add(m)
                        if self.isgate(m):
                            stack.append(m)
            return seen

        in_ports = {NI + j for j, p in enumerate(g["ports"]) if p[1] == "I"}
        out_ports = {NI + j for j, p in enumerate(g["ports"]) if p[1] == "O"}
        ok = lambda n, ends: self.isgate(n) or n in ends
        fa, ba = reach(in_ports, out, 2), reach(banks, inn, 0)
        A = [k for k in cone if SI[k][0] in fa and SI[k][2] in ba and ok(SI[k][0], in_ports) and ok(SI[k][2], banks)
             and (SI[k][2] not in banks or SI[k][3] in pin_ix)]
        fb, bb = reach(banks, out, 2), reach(out_ports, inn, 0)
        B = [k for k in cone if SI[k][0] in fb and SI[k][2] in bb and ok(SI[k][0], banks) and ok(SI[k][2], out_ports)
             and (SI[k][0] not in banks or SI[k][1] in pin_ix)]
        gates = sorted({SI[k][e] for k in A + B for e in (0, 2) if self.isgate(SI[k][e])})
        gi = {n: j for j, n in enumerate(gates)}

        nv = 0
        def alloc(n):
            nonlocal nv
            s = nv; nv += n; return s
        X, Y, aA, dB = alloc(len(gates)), alloc(len(gates)), alloc(len(gates)), alloc(len(gates))
        sA = {(SI[k][2], SI[k][3]): None for k in A if SI[k][2] in banks}
        sB = {(SI[k][0], SI[k][1]): None for k in B if SI[k][0] in banks}
        for s in sA: sA[s] = alloc(1)
        for s in sB: sB[s] = alloc(1)
        wires = A + B
        EX, EY = alloc(len(wires)), alloc(len(wires))
        bounds = [(0, None)] * nv
        for j, n in enumerate(gates):
            if free_gates:
                bounds[X + j], bounds[Y + j] = (self.die[0], self.die[2]), (self.die[1], self.die[3])
            else:
                r = g["inst"][n]
                bounds[X + j] = (r[2] + r[4] / 2,) * 2
                bounds[Y + j] = (r[3] + r[5] / 2,) * 2

        rows, cols, vals, rhs = [], [], [], []
        def le(terms, b):
            for v, c in terms:
                rows.append(len(rhs)); cols.append(v); vals.append(c)
            rhs.append(b)
        A_set = set(A)
        for e, k in enumerate(wires):
            d, dp, s, sp = SI[k][:4]
            for axis, V, E in ((0, X, EX), (1, Y, EY)):
                td, cd = ([(V + gi[d], 1.0)], 0.0) if d in gi else ([], fixed_xy(d, dp)[axis])
                ts, cs = ([(V + gi[s], 1.0)], 0.0) if s in gi else ([], fixed_xy(s, sp)[axis])
                le(td + [(v, -c) for v, c in ts] + [(E + e, -1.0)], cs - cd)
                le([(v, -c) for v, c in td] + ts + [(E + e, -1.0)], cd - cs)
            if k in A_set:      # arrival(sink) >= arrival(driver) + wire
                le(([(aA + gi[d], 1.0)] if d in gi else []) + [(EX + e, 1.0), (EY + e, 1.0),
                   ((aA + gi[s]) if s in gi else sA[(s, sp)], -1.0)], 0.0)
            else:               # departure(driver) >= wire + departure(sink)
                le(([(dB + gi[s], 1.0)] if s in gi else []) + [(EX + e, 1.0), (EY + e, 1.0),
                   ((dB + gi[d]) if d in gi else sB[(d, dp)], -1.0)], 0.0)
        c = np.zeros(nv)
        for v in list(sA.values()) + list(sB.values()):
            c[v] = 1.0
        res = linprog(c, A_ub=coo_matrix((vals, (rows, cols)), shape=(len(rhs), nv)).tocsr(),
                      b_ub=np.array(rhs), bounds=bounds, method="highs")
        if res.status != 0:
            raise RuntimeError(res.message)
        v = [res.x[i] for i in list(sA.values()) + list(sB.values())]
        return float(max(v)), float(sum(v))


def bus_moves(start, order):
    """The fewest port moves from start to order: buses minus the longest run already in start's order."""
    run = []
    for p in (start.index(b) for b in order):
        i = bisect.bisect_left(run, p)
        run[i:i + 1] = [p]
    return len(order) - len(run)


def all_orders(D):
    """Every bus order, with each bank mirrored in place whichever way scores best for it
    (lowest worst path, then lowest total; N on a tie). Banks stay where they are.
    Returns the orders no other order beats on both scores: (order, orientation per bank)."""
    st = D.initial()
    start = [b for b, _ in D.groups]
    nb = len(D.banks)
    pins = np.stack([np.stack([st["pos"][b] + flip(D.off, D.w, D.h, o) for b in range(nb)]) for o in ORIENTS])
    rows = []
    for order in itertools.permutations(start):
        v = D.pin_worst(pins, D.extremes(list(order)))              # (orients, banks, pins)
        w, t = v.max(2), v.sum(2)
        pick = np.lexsort((t, w), axis=0)[0]                         # per bank, an orientation index
        ar = np.arange(nb)
        rows.append((float(w[pick, ar].max()), float(t[pick, ar].sum()), list(order), [ORIENTS[i] for i in pick]))
    rows.sort(key=lambda r: (r[0], r[1]))
    front, best_t = [], float("inf")
    for r in rows:
        if r[1] < best_t - 1e-6:
            best_t = r[1]
            front.append((r[2], r[3]))
    return front, len(rows)


class Tree:
    """Every variant tried, each with its parent: the variant one move before it. Today is variant 0.
    A variant reached twice keeps its first parent; each path that reached it is named in "via"."""

    def __init__(self, D):
        self.D, self.vs, self.ix = D, [], {}
        self.add(D.initial(), None, "today", None)

    @staticmethod
    def key(st):
        return (tuple(st["order"]), tuple(st["orient"]), tuple(np.round(st["pos"], 1).ravel()))

    def add(self, st, parent, move, via):
        k = self.key(st)
        if k in self.ix:
            v = self.vs[self.ix[k]]
            if via and via not in v["via"]:
                v["via"].append(via)
            return v["id"]
        w, t = self.D.scores(st)
        v = {"id": len(self.vs), "parent": parent, "move": move,
             "depth": 0 if parent is None else self.vs[parent]["depth"] + 1,
             "worst": w, "total": t, "via": [via] if via else [],
             "pos": st["pos"].round(2).tolist(), "orient": list(st["orient"]), "order": list(st["order"]),
             **self.D.detail(st)}
        self.ix[k] = v["id"]
        self.vs.append(v)
        return v["id"]


def bank_move_text(D, st, b, pos, o):
    name = D.name(D.banks[b])
    if np.allclose(pos, st["pos"][b]):
        return f"mirror: {name} to {o}"
    return f"bank: {name} to ({pos[0]:.0f}, {pos[1]:.0f}) {o}"


def search(D, tree, objective, port_budget, k):
    """Greedy: the best port moves first, then up to k bank moves. Adds each variant to the tree."""
    st, at = D.initial(), 0
    via = f"search: lower the {'worst path' if objective == 'worst' else 'total'} first, up to {port_budget} port move{'s' if port_budget != 1 else ''}"
    key = lambda s: s if objective == "worst" else s[::-1]
    path = [0]
    for _ in range(port_budget):
        mv = D.best_port_move(st, objective)
        if mv is None or mv[0] >= key(D.scores(st)):
            break
        _, b, j, st["order"] = mv
        at = tree.add(st, at, f"port: {b} pins to place {j + 1} of {len(st['order'])}", via)
        path.append(at)
    grid = D.score_grid(D.extremes(st["order"]))
    for _ in range(k):
        mv = D.best_bank_move(st, objective, grid)
        if mv is None or mv[0] >= key(D.scores(st)):
            break
        _, b, pos, o = mv
        if np.allclose(pos, st["pos"][b], atol=1.0):
            pos = st["pos"][b].copy()      # the grid's nearest point to where the bank is: a mirror in place
        text = bank_move_text(D, st, b, pos, o)
        st["pos"][b], st["orient"][b] = pos, o
        at = tree.add(st, at, text, via)
        path.append(at)
    return {"via": via, "path": path}


def order_path(D, tree, order, orient, via):
    """A path from today to a bus order and its mirrors: one bus move at a time, each the move toward
    the order that scores best, then one mirror at a time, best first."""
    st, at, path = D.initial(), 0, [0]
    while bus_moves(order, st["order"]):
        best = None
        for b in st["order"]:
            rest = [g for g in st["order"] if g != b]
            for j in range(len(rest) + 1):
                o = rest[:j] + [b] + rest[j:]
                if bus_moves(order, o) < bus_moves(order, st["order"]):
                    sc = D.scores(dict(st, order=o))
                    if best is None or sc < best[0]:
                        best = (sc, b, j, o)
        _, b, j, st["order"] = best
        at = tree.add(st, at, f"port: {b} pins to place {j + 1} of {len(order)}", via)
        path.append(at)
    todo = [b for b in range(len(D.banks)) if orient[b] != st["orient"][b]]
    while todo:
        def after(b):
            t = list(st["orient"]); t[b] = orient[b]
            return D.scores(dict(st, orient=t))
        b = min(todo, key=after)
        todo.remove(b)
        text = bank_move_text(D, st, b, st["pos"][b], orient[b])
        st["orient"][b] = orient[b]
        at = tree.add(st, at, text, via)
        path.append(at)
    return {"via": via, "path": path}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("--k", type=int, default=8, help="most bank moves")
    ap.add_argument("--ports", type=int, default=2, help="most port moves")
    ap.add_argument("--check-lp", action="store_true", help="also place the gates by a linear program")
    ap.add_argument("--orders", action="store_true",
                    help="also score every bus order, banks mirrored in place, and add a path to each best one (about a minute for 8 buses)")
    ap.add_argument("--keepout", action="append", default=[], metavar="X0,Y0,X1,Y1",
                    help="a rectangle no bank may overlap, in um; repeat for more")
    ap.add_argument("-o", "--out", default="out/headroom.json")
    args = ap.parse_args(argv)
    KEEPOUTS[:] = [tuple(float(v) for v in k.split(",")) for k in args.keepout]

    D = Design(json.load(open(args.graph)))
    st0 = D.initial()
    base = {"line": dict(zip(("worst", "total"), D.scores(st0))),
            "now": dict(zip(("worst", "total"), D.wire_scores(st0, free_gates=False)))}
    if args.check_lp:
        base["lp"] = dict(zip(("worst", "total"), D.wire_scores(st0, free_gates=True)))
    print(f"{len(D.pins)} pins per bank on cone paths; {len(D.banks)} banks")
    for k, v in base.items():
        print(f"current, {k:5s}: worst {v['worst']:6.0f} um, total {v['total'] / 1000:7.1f} mm")

    tree, paths = Tree(D), []
    for objective in ("worst", "total"):
        for p in range(args.ports + 1):
            paths.append(search(D, tree, objective, p, args.k))
    if args.orders:
        front, n = all_orders(D)
        print(f"scored {n} bus orders; {len(front)} no other order beats on both scores")
        for order, orient in front:
            paths.append(order_path(D, tree, order, orient, f"best bus order: {' '.join(order)}"))
    for pth in paths:
        v = tree.vs[pth["path"][-1]]
        print(f"{pth['via']}: {len(pth['path']) - 1} moves, worst {v['worst']:6.0f} um, total {v['total'] / 1000:7.1f} mm")
    print(f"{len(tree.vs)} variants")
    json.dump({"format": "placehead-headroom/2", "geometry": D.geometry(),
               "settings": {"GAP": GAP, "MARGIN": MARGIN, "PIN_KEEPOUT": PIN_KEEPOUT, "STEP": STEP, "KEEPOUTS": KEEPOUTS},
               "pins": D.pins, "base": base, "variants": tree.vs, "paths": paths}, open(args.out, "w"), separators=(",", ":"))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
