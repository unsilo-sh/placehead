# What the export holds

The export is one JSON file in format `placehead-graph/1`. This page lists every field. `audit.py`
check 1 fails on any key that is not in this list. Check 2 fails on any string that is not a token
or a word of the format.

## Tokens

Every name from the design becomes a token. A token is a two-letter prefix and a number.

| Prefix | Stands for | Example |
|---|---|---|
| `oi` | an instance (a cell or a memory) | `oi1514` |
| `ob` | a port, or a bus of ports. A bus bit keeps its index. | `ob3[7]` |
| `oc` | a cell type (a library cell or a memory macro) | `oc2` |
| `op` | a pin of one cell type. A bus pin keeps its index. | `op41[12]` |
| `on` | a net | `on988` |

The numbers come from a random shuffle. They are not hashes of the names, so a reader cannot test
a guessed name against a token. The key in `work/key.json` is the only map back to the names.
`obfuscate.py` stops if any token equals a real name in the design.

A bus keeps its bit indices because the analysis moves a bus's pins as a group. So a reader can see
that `ob3` has 32 bits. A reader cannot see that it was named `rdata`.

## Fields

Units are um, times the scale if `--scale` was used. The die's lower-left corner is at (0, 0).

| Field | Holds | The analysis uses it to |
|---|---|---|
| `format` | `placehead-graph/1` | read the file |
| `design` | the word `design`, never the design's name | label the page |
| `die` | die corners: `[0, 0, width, height]` | draw the floorplan and bound moves |
| `kinds` | `["comb", "flop", "memory"]` | name the three cell kinds |
| `cells` | one token per cell type | tell cell types apart |
| `inst` | per instance: token, kind, x, y, width, height, cell type | place memories and the cells on paths |
| `ports` | per port: token, direction (`I` or `O`), x, y | place path ends, and move buses |
| `segs` | per wire: x and y of both ends | measure wire lengths |
| `segInCone` | per wire: 1 if it is in a port's logic cone | pick the paths the analysis scores |
| `segBus` | per wire: 1 if it carries a bus bit | let the viewer hide other wires |
| `segInfo` | per wire: driver index and pin, sink index and pin, net token, length | follow paths from cell to cell |
| `cones` | per port token: direction, member cells, wires, endpoints (cell, pin, kind, depth, path length), depth | score each port's paths |
| `banks` | per memory token: pin counts per pin group, and its input and output wires | score each memory's paths |
| `summary` | counts: flop endpoints, memory endpoints, nets | show totals |
| `roles` | opt-in only: per bus token, a role from the fixed list below | label buses in results |

A "cone" starts at a port and follows logic cells until it reaches a flop or a memory. A wire is a
straight line from the pin that drives a net to a pin the net feeds. The design is placed, not
routed, so no routes are in the file.

## Bus roles (opt-in)

By default, the export gives no hint of what a bus does. With `--roles`, the owner gives each
chosen bus one role from this list:

`clock`, `reset`, `address`, `write_data`, `read_data`, `write_enable`, `chip_enable`, `select`,
`other`

The export then holds, for example, `"roles": {"ob3": "read_data"}`. The bus's real name stays in
the key. The audit fails on any role that is not on the list, and lists the roles it found. The
roles file that the owner fills in holds the real bus names, so it stays in `work/`.

## Profiles

- `headroom` (default): keeps the wires inside the cones, the cells on them, every memory and
  every port. `summary.nets` counts only the nets in the file.
- `full`: keeps every wire and every cell, and the design's total net count.

## What the export still shows

Obfuscation hides names. It does not hide structure. The audit lists these items with your
design's numbers:

- the die size (at scale 1)
- the number of instances of each kind, of cell types, of nets and of wires
- the sizes of the memories and cells (at scale 1, a reader can match a row height to a known
  library or process)
- the ports: how many, their bus widths, their directions, and their order along each edge
- with `--roles`: the role of each bus the owner chose
- the placement of each exported cell, so the floorplan is visible
- the connectivity: which cell drives which. A reader can rebuild the gate-level structure of the
  cones, but not the names or the logic functions.

## Not in the export

- no name from the design: instances, nets, ports, buses, cell types, pins, the design itself
- no library, macro, process or tool name
- no logic function, timing, power, routing or layer data
- no RTL, and no file paths from the user's machine

## Look at the export

Open `viewer.html` in a browser and pick the export with **Open graph file**. The page draws it as
unsilo sees it: tokens in place of names. It reads the file in the browser and sends it nowhere.

## unsilo's choices

These are unsilo's choices, not rules of any standard. The owner can ask for others.

- the token prefixes, and keeping bus bit indices
- the list of bus roles
- the `headroom` profile as the default
- the scale range for `--scale random`, 0.5 to 2
- rounding to 0.001 um
