# placehead: placement headroom analysis

The test design is `sparse_mem_core`, copied from factory's `adapters/def2graph/examples/`.

## sparse_mem_core

A synthetic **16-bank sparse memory core** (loosely an AI-inference scratchpad
array) used to exercise def2graph's **memory-boundary** handling at scale. It is
*not* a faithful accelerator model — it's a connectivity scaffold that produces
the right graph structure: many memory macros reached from ports both
combinationally and through flops, with read data flowing back to output ports.

![placement](placement.png)

16 `fakeram45_64x32` SRAM banks (orange) placed in a 4×4 grid by OpenROAD, with
~1,210 Nangate45 std cells of glue logic.

## Files

| File | What it is |
|---|---|
| `gen.py` | Generator — emits the structural Verilog netlist (edit `NBANKS` to scale) |
| `sparse_mem_core.v` | Generated gate-level netlist (16 banks + 1,210 cells) |
| `place.tcl` | OpenROAD placement-only script (floorplan → manual macro grid → global/detailed place → `write_def`) |
| `sparse_mem_core_placed.def` | The placed DEF — ready-to-use def2graph input |
| `placement.png` | Floorplan figure above, drawn by `plot_placement.py` from def2graph's output |
| `plot_placement.py` | Draws the placement from def2graph's `nodes.parquet` and the DEF's `DIEAREA` |
| `make_graph_html.py`, `graph_template.html` | Build `graph.html`: def2graph's cones and every bank's wires on the placement, with pin positions from the LEF |
| `fetch_pdk.sh` | Downloads the Nangate45 and fakeram45 LEF and Liberty files into `pdk/` (not checked in) |

## Structure

- Registered address/write-data (`DFF`) fan out to all 16 banks → port→flop→mem paths.
- Combinational per-bank select/enable (`bank_sel` decode → `we`/`ce`) → port→mem paths.
- Masked OR-reduction read path to a **combinational** output (`rdata_c`, so output
  ports reach `mem_dout`) and a **registered** output (`rdata_r`).

## Reproduce

```bash
# 1. regenerate the netlist (optional; sparse_mem_core.v is included)
python3 gen.py

# 2. place it with OpenROAD (needs the Nangate45 PDK + fakeram45 LEF/LIB and an
#    openroad binary; this DEF was produced via the OpenROAD/test Nangate45 files).
#    Run place.tcl from a dir where Nangate45/*.lef|lib are visible, writing to /work.
openroad -exit place.tcl        # or inside a container, see place.tcl header
```

## Run def2graph on it

def2graph lives in factory, at `adapters/def2graph`. It needs `networkx`, `pandas` and `pyarrow`.

```bash
./fetch_pdk.sh
PYTHONPATH=/path/to/factory/adapters/def2graph python3 -m def2graph \
  --def sparse_mem_core_placed.def --lef pdk/*.lef --lib pdk/*.lib \
  --out out/sparse_mem --formats parquet json
python3 plot_placement.py --def sparse_mem_core_placed.def --graph out/sparse_mem -o placement.png
python3 make_graph_html.py --def sparse_mem_core_placed.def --lef pdk/*.lef --graph out/sparse_mem -o graph.html
```

Expected: `fakeram45_64x32` classified as **memory**, **16/16 banks** detected as
boundaries, and **624 memory endpoints**, each with its placement coordinate.
