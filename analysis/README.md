# analysis

unsilo runs this code on a partner's export. It reads only the export, so its results name
tokens, not real names. The partner puts the real names back with `reveal.py` and their key.

## headroom.py

`headroom.py` estimates how much shorter the paths between top-level pins and memories get with a
few moves. A path runs from an input port, through logic cells, to a memory input pin, or from a
memory output pin, through logic cells, to an output port.

It scores a placement in two ways:

- **worst:** the longest path.
- **total:** the sum, over memory pins, of each pin's longest path.

Each path's length is the Manhattan distance (|dx| + |dy|) between its two ends. This is the
shortest a placer could make it. With no limit on the area for logic cells, re-placed cells can
always sit on such a route. `--check-lp` confirms this with a linear program over cell positions.

The moves:

- **port move:** take one bus's pins out of the order along the die edge and put them in another
  place. The other buses close up around it, at the same pitch.
- **memory move:** mirror a memory in place (orientations N, FN, FS, S), or move it to a legal spot.

For each port budget, it makes the best port moves, then up to K memory moves, greedily.
`--orders` also scores every order of the buses, with each memory mirrored its best way.

```bash
python3 analysis/headroom.py design.export.json --k 48 --ports 2 --orders \
    --keepout X0,Y0,X1,Y1 -o out/headroom.json
```

`--keepout X0,Y0,X1,Y1` (repeatable) reserves a rectangle no memory may overlap, for example a
channel kept for logic. The memory spacing, die margin, pin keep-out and grid step are unsilo's
choices, at the top of the file.

The results (format `placehead-headroom/2`) hold every variant tried. Each variant names its
parent, the variant one move before it, so any variant traces back to today's placement.

## headroom_viewer.html

The viewer draws the results: each variant's cost against the number of moves from today, or worst
path against total. Click a variant to see its moves and its floorplan. Open the page in a browser
and pick a results file.

## Limits

- **Bounds, not placements.** Scores are lower bounds on wire length, not routed lengths. A real
  placer run on the best variants would measure the real gain.
- **No area for logic.** A move does not account for the area the logic cells need. A memory move
  can take space that logic cells use today.

## Results on the synthetic design

On `examples/sparse_mem_core`, with the memory array fixed and the channel between its halves kept
for logic, port moves give most of the headroom. Two bus moves shorten the worst path by 24% and
the total by 29%. Mirroring memories adds a few percent.
