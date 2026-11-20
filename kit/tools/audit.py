"""Check an export before it leaves your site, and list what a reader can still learn from it.

Usage:
    python audit.py export/design.export.json
        [--def design.def --lef a.lef ... --lib a.lib ...] [--key work/key.json] [--show] [--json report.json]

Checks:
  1 schema   the file has only the keys of the format, and its values have the types they should.
  2 strings  every string in the file is a token (oi12, ob3[7], ...) or a word of the format
             (common.SCHEMA_WORDS). Any other string FAILS, because it may be a real name.
  3 names    with --def/--lef/--lib: no name your design files define appears in the file,
             whole or inside a longer string. This check does not trust check 2 or the obfuscator.
  4 files    nothing else sits beside the export: no key, no graph JSON, no design file.

Then it lists what the export still shows: sizes, counts, geometry and connectivity.

The report names no real design names. --show prints up to 20 of them for each failed check. Use it
only on a screen you trust: anything printed in a Claude Code session goes to the model provider.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from common import (GRAPH_FORMAT, KEY_FORMAT, SCHEMA_WORDS, TOKEN, TOP_KEYS, design_names,
                    load_json, strings)


class Report:
    def __init__(self, show):
        self.show, self.results, self.lines = show, [], []

    def check(self, name, ok, detail, examples=()):
        self.results.append({"check": name, "pass": bool(ok), "detail": detail})
        self.say(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        if not ok and self.show:
            for ex in list(examples)[:20]:
                self.say(f"         {ex}")

    def say(self, line=""):
        self.lines.append(line)
        print(line)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def schema_problems(g):
    """Wrong keys and wrong types, as (where, what) pairs. Names are not checked here."""
    bad = []
    extra = set(g) - TOP_KEYS
    missing = TOP_KEYS - set(g)
    bad += [(f"$.{k}", "key not in the format") for k in sorted(extra)]
    bad += [(f"$.{k}", "key missing") for k in sorted(missing)]
    if missing:
        return bad

    def rows(field, n, types):
        for j, r in enumerate(g[field]):
            if not isinstance(r, list) or len(r) != n or not all(t(v) for t, v in zip(types, r)):
                bad.append((f"$.{field}[{j}]", "row has the wrong shape"))
                return

    s, num = (lambda v: isinstance(v, str)), is_num
    idx = lambda v: isinstance(v, int) and not isinstance(v, bool)
    rows("inst", 7, [s, idx, num, num, num, num, idx])
    rows("ports", 4, [s, s, num, num])
    rows("segs", 4, [num] * 4)
    rows("segInfo", 6, [idx, s, idx, s, s, lambda v: v is None or num(v)])
    for f in ("segInCone", "segBus"):
        if len(g[f]) != len(g["segs"]) or any(v not in (0, 1) for v in g[f]):
            bad.append((f"$.{f}", "not one 0 or 1 per wire"))
    if not (isinstance(g["die"], list) and len(g["die"]) == 4 and all(map(num, g["die"]))):
        bad.append(("$.die", "not four numbers"))
    for k, c in g["cones"].items():
        if set(c) != {"d", "m", "s", "e", "depth"}:
            bad.append((f"$.cones.<token>", "cone keys not in the format"))
            break
    for k, b in g["banks"].items():
        if set(b) != {"pins", "reached", "groups", "in", "out"}:
            bad.append((f"$.banks.<token>", "bank keys not in the format"))
            break
    if set(g["summary"]) != {"flop_endpoints", "memory_endpoints", "nets"}:
        bad.append(("$.summary", "summary keys not in the format"))
    return bad


def residual(g, key, say):
    """What a reader of the export can still learn. Numbers only, in export units."""
    kinds = g["kinds"]
    by_kind = Counter(kinds[r[1]] for r in g["inst"])
    cell_kind = {}
    for r in g["inst"]:
        cell_kind.setdefault(r[6], (kinds[r[1]], r[4], r[5]))
    buses = Counter(TOKEN.match(p[0]) and p[0].split("[")[0] for p in g["ports"])
    widths = sorted(buses.values(), reverse=True)
    W, H = g["die"][2] - g["die"][0], g["die"][3] - g["die"][1]
    comb_h = sorted({round(h, 3) for k, w, h in cell_kind.values() if k != "memory"})
    mems = {(round(w, 3), round(h, 3)) for k, w, h in cell_kind.values() if k == "memory"}
    edges = Counter()
    for p in g["ports"]:
        x, y = p[2], p[3]
        edges[min((y - g["die"][1], "bottom"), (g["die"][3] - y, "top"),
                  (x - g["die"][0], "left"), (g["die"][2] - x, "right"))[1]] += 1
    scale = key.get("scale") if key else None
    unit = "um" if scale == 1 else ("export units (um times the key's scale)" if key else
                                    "export units (um, unless --scale was used)")

    say("What the export still shows (decide whether each item is acceptable):")
    say(f"  - Die size: {W:g} x {H:g} {unit}.")
    say(f"  - Instances: {len(g['inst'])} ({', '.join(f'{n} {k}' for k, n in sorted(by_kind.items()))}),"
        f" of {len(g['cells'])} cell types.")
    say(f"  - Memories: {by_kind.get('memory', 0)}, in {len(mems)} sizes: "
        + ", ".join(f"{w:g} x {h:g}" for w, h in sorted(mems)) + f" {unit}.")
    say(f"  - Standard-cell heights: {', '.join(f'{h:g}' for h in comb_h[:6])}"
        f"{' ...' if len(comb_h) > 6 else ''} {unit}. With scale 1, a reader may match the row "
        "height to a known library or process node.")
    say(f"  - Ports: {len(g['ports'])} in {len(buses)} buses (widths {', '.join(map(str, widths[:12]))}"
        f"{' ...' if len(widths) > 12 else ''}), on edges: "
        + ", ".join(f"{n} {e}" for e, n in edges.most_common()) + ". Port order along each edge is visible.")
    say(f"  - Nets: {g['summary']['nets']}. Wires: {len(g['segs'])}, each with both end points and its length.")
    say("  - Connectivity: which cell drives which. With cell sizes and kinds, a reader can rebuild the"
        " gate-level structure of the cones, but not its names or logic functions.")
    say("  - Placement: the position of every exported cell, so the floorplan picture is visible.")
    say("Not in the export: any name from the design, logic functions, timing, power, routing, layers,"
        " RTL, and the library and process names.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export")
    ap.add_argument("--def", dest="defs", nargs="+", default=[])
    ap.add_argument("--lef", nargs="+", default=[])
    ap.add_argument("--lib", nargs="+", default=[])
    ap.add_argument("--key", help="the key from obfuscate.py: checks the file is the one it wrote")
    ap.add_argument("--show", action="store_true", help="print offending strings (may be real names)")
    ap.add_argument("--json", help="also write the report as JSON")
    args = ap.parse_args(argv)

    path = Path(args.export)
    blob = path.read_bytes()
    R = Report(args.show)
    R.say(f"Audit of {path.name}: {len(blob) // 1024} KB, sha256 {hashlib.sha256(blob).hexdigest()}")
    try:
        g = json.loads(blob)
    except ValueError as e:
        R.check("json", False, f"not JSON ({e})")
        sys.exit(1)
    if not isinstance(g, dict) or g.get("format") != GRAPH_FORMAT:
        R.check("format", False, f"not a {GRAPH_FORMAT} file")
        sys.exit(1)

    key = None
    if args.key:
        key = load_json(args.key)
        if key.get("format") != KEY_FORMAT:
            sys.exit(f"error: {args.key} is not a key file")
        R.check("key", key["export_sha256"] == hashlib.sha256(blob).hexdigest(),
                "the file is the one obfuscate.py wrote with this key"
                if key["export_sha256"] == hashlib.sha256(blob).hexdigest()
                else "the file changed after obfuscate.py wrote it, or the key is for another file")

    # 1 schema
    bad = schema_problems(g)
    R.check("1 schema", not bad, "only the keys and value types of the format" if not bad
            else f"{len(bad)} problems", [f"{w}: {m}" for w, m in bad])

    # 2 strings
    all_strings = list(strings(g))
    odd = [(p, s) for p, s in all_strings if s not in SCHEMA_WORDS and not TOKEN.match(s)]
    kinds = Counter(s[:2] for _, s in all_strings if TOKEN.match(s))
    R.check("2 strings", not odd,
            f"{len(all_strings)} strings: {sum(kinds.values())} tokens "
            f"({', '.join(f'{n} {k}' for k, n in sorted(kinds.items()))}), the rest format words"
            if not odd else f"{len(odd)} strings are neither tokens nor format words; they may be real names",
            [f"{p}: {s!r}" for p, s in odd])

    # 3 names from the design files
    if args.defs or args.lef or args.lib:
        names = design_names(args.defs, args.lef, args.lib)
        total = sum(len(v) for v in names.values())
        index = {}
        for kind, vs in names.items():
            for v in vs:
                index.setdefault(v, kind)
        found = Counter()
        hits = []
        for p, s in all_strings:
            if s in SCHEMA_WORDS:
                continue
            # every piece of s, 3 characters or longer, looked up among the design's names
            for i in range(len(s)):
                for j in range(i + 3, len(s) + 1):
                    k = index.get(s[i:j])
                    if k:
                        found[k] += 1
                        hits.append(f"{p}: {s!r} holds {k} {s[i:j]!r}")
        R.check("3 names", not found,
                f"none of the {total} names in the design files appears in the export"
                if not found else "names from the design files appear in the export: "
                + ", ".join(f"{n} x {k}" for k, n in found.most_common()), hits)
        R.say("         names read: " + ", ".join(f"{len(v)} {k}" for k, v in sorted(names.items())))
        R.say("         (names shorter than 3 characters, such as pin A, are not checked)")
    else:
        R.say("  [SKIP] 3 names: give --def, --lef and --lib to check against the design's own files")

    # 4 what sits beside the export
    others = sorted(p.name for p in path.parent.iterdir() if p != path and p.name != ".DS_Store")
    R.check("4 files", not others,
            "the export directory holds only this file" if not others
            else f"{len(others)} other files sit beside the export: " + ", ".join(others))

    R.say()
    residual(g, key, R.say)
    ok = all(r["pass"] for r in R.results)
    R.say()
    R.say("RESULT: " + ("PASS. Nothing in the file is a name from the design." if ok else
                        "FAIL. Do not send this file. Run with --show on a trusted screen to see why."))
    if args.json:
        Path(args.json).write_text(json.dumps({"file": path.name, "sha256": hashlib.sha256(blob).hexdigest(),
                                               "pass": ok, "checks": R.results}, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
