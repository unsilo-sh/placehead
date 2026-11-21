"""Shared by the kit's tools: the token grammar, the export schema, and a scan of design files.

Nothing here opens a network connection or writes outside the paths it is given.
"""
import gzip
import json
import re

GRAPH_FORMAT = "placehead-graph/1"
KEY_FORMAT = "placehead-key/1"

# Every name in an export is a token: a two-letter prefix, a number, and for bus bits the bit index.
#   oi  instance        on  net           oc  cell type (library cell or macro)
#   ob  port, or bus    op  pin of a cell type
TOKEN = re.compile(r"^o[ibcnp]\d+(\[\d+\])?$")
TOKEN_ANY = re.compile(r"o[ibcnp]\d+")

# Every other string the export may hold. Each one is a word of the format, not of the design.
SCHEMA_WORDS = {
    # format and design label
    GRAPH_FORMAT, "design",
    # top-level keys
    "format", "die", "kinds", "cells", "inst", "ports", "segs", "segInCone", "segBus", "segInfo",
    "cones", "banks", "summary",
    # cone, bank and summary keys
    "d", "m", "s", "e", "depth", "pins", "reached", "groups", "in", "out",
    "flop_endpoints", "memory_endpoints", "nets",
    # the optional key for bus roles (its values are checked against ROLES, not here)
    "roles",
    # values: cell kinds, endpoint types, port directions, and the empty pin of a port endpoint
    "comb", "flop", "memory", "port", "I", "O", "",
}

TOP_KEYS = {"format", "design", "die", "kinds", "cells", "inst", "ports", "segs", "segInCone",
            "segBus", "segInfo", "cones", "banks", "summary"}
OPTIONAL_KEYS = {"roles"}

# Opt-in: the role of a bus, from this fixed list only (unsilo's list; ask to extend it).
# The export holds the role in "roles", keyed by bus token, and never the bus's real name.
ROLES = ("clock", "reset", "address", "write_data", "read_data", "write_enable", "chip_enable",
         "select", "other")


def split_bit(name):
    """'addr[3]' -> ('addr', '[3]'), 'clk' -> ('clk', ''). Only the last [n] is a bit index."""
    m = re.match(r"^(.*?)(\[\d+\])$", name)
    return (m.group(1), m.group(2)) if m else (name, "")


def strings(obj, path="$"):
    """Every string in a JSON value, keys included, with the path where it sits."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield path + ".<key>", k
            yield from strings(v, f"{path}.{k}" if not TOKEN.match(k) else f"{path}.<token>")
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v, path + "[]")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def _open(path):
    with open(path, "rb") as f:
        gz = f.read(2) == b"\x1f\x8b"
    return gzip.open(path, "rt", errors="replace") if gz else open(path, errors="replace")


def design_names(def_paths=(), lef_paths=(), lib_paths=()):
    """The names a design's own files define, by source, read line by line.

    DEF: the design, its ports, instances, the cells they use, and nets.
    LEF: macros, their pins, sites and layers.  Liberty: libraries, cells and pins.
    """
    found = {}

    def add(kind, name):
        name = name.strip('"').lstrip("\\")
        if name:
            found.setdefault(kind, set()).add(name)
            base = split_bit(name)[0]       # addr[3] also names the bus addr
            if base != name:
                found.setdefault(kind + " bus", set()).add(base)

    for p in def_paths:
        section = None
        with _open(p) as f:
            for line in f:
                m = re.match(r"\s*(DESIGN)\s+(\S+)", line)
                if m and section is None:
                    add("def design", m.group(2))
                m = re.match(r"\s*(COMPONENTS|PINS|NETS|SPECIALNETS)\s+\d+", line)
                if m:
                    section = m.group(1)
                    continue
                if re.match(r"\s*END\s+(COMPONENTS|PINS|NETS|SPECIALNETS)", line):
                    section = None
                    continue
                m = re.match(r"\s*-\s+(\S+)(?:\s+(\S+))?", line)
                if not m:
                    continue
                if section == "COMPONENTS":
                    add("def instance", m.group(1))
                    if m.group(2):
                        add("def cell", m.group(2))
                elif section == "PINS":
                    add("def port", m.group(1))
                elif section in ("NETS", "SPECIALNETS"):
                    add("def net", m.group(1))
    for p in lef_paths:
        with _open(p) as f:
            for line in f:
                m = re.match(r"\s*(MACRO|PIN|SITE|LAYER)\s+(\S+)\s*$", line)
                if m:
                    add("lef " + m.group(1).lower(), m.group(2))
    for p in lib_paths:
        with _open(p) as f:
            for line in f:
                for m in re.finditer(r"\b(library|cell|pin|bus|bundle)\s*\(\s*\"?([^\s\")]+)\"?\s*\)", line):
                    add("lib " + m.group(1), m.group(2))
    return found
