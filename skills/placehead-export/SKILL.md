---
name: placehead-export
description: Export a placed design's graph for unsilo's placement analysis, with no design, IP or PDK names in it, and explain what the export holds. Use when the user wants to prepare a DEF for unsilo, check an export before it is sent, review what the export shows and what it leaves out, or read unsilo's results with the real names.
---

# placehead export

unsilo analyzes a client's placed design, with an analysis built for that client. For example,
one analysis estimates how much shorter the paths between a design's ports and its memories get
with a few moves. Every such analysis needs the graph under the design: which cell drives which,
the kind and size of each cell, and where each one sits. None needs a name from the design, its IP
or its PDK.

This skill is the method that gets unsilo that graph. It runs on the client's machine, in four
steps:

1. **Extract** the graph from the placed DEF, LEF and Liberty files.
2. **Obfuscate** it: replace every name with a meaningless token, and keep the key that maps
   tokens back to names on the client's side.
3. **Verify** that the export is the same graph, with only names, order and scale changed.
4. **Audit** the export against the design's own files, and list what it still shows.

The output is one file, which the client sends to unsilo. The same steps run the same way on
every design, so the client's security team can approve the method once.

You work in the client's own environment, with access to their design. Use it: find the right
input files, fix extraction problems, help choose the options, and answer questions about the
export from the code.

## Working rules

1. Only the export leaves the site. Do not send any file anywhere. The user sends the export
   through their own channel.
2. Keep `work/` with the design. It holds the real names and the key. Never put it in the
   export directory, or in a repository that is shared with unsilo.
3. Do not change the tools to make a check pass. The checks are what make the method safe to
   approve. If a check fails, stop, find the cause, and tell the user.
4. Answer questions about the export from the code, and cite `file:line`. The tools are short.

## Layout

| Path | Holds | Leaves the site? |
|---|---|---|
| `tools/extract.py` | Runs def2graph and make_graph_json.py on the design | No |
| `tools/def2graph/` | Reads DEF, LEF and Liberty, and traces each port's logic cone | No |
| `tools/make_graph_json.py` | Adds each pin's position from the LEF and each wire's two ends | No |
| `tools/obfuscate.py` | Replaces names with tokens and writes the key | No |
| `tools/verify.py` | Checks that the export is the same graph | No |
| `tools/audit.py` | Checks that the export holds no design names, and lists what it still shows | No |
| `tools/reveal.py` | Puts real names back into a file that unsilo returns | No |
| `DATA.md` | Every field of the export: what it holds, and why an analysis needs it | No |
| `viewer.html` | unsilo's cone viewer: draws a graph or an export on its floorplan, offline | No |
| `work/` (made by the tools) | The graph with real names, the key, and the roles file | **Never** |
| `export/` (made by the tools) | The export file only | **Yes, this one file** |

This skill is one directory of the placehead repository. The repository's `SECURITY.md` lists the
data-protection practices for a security team. A zip of the skill has a `VERSION` file that names
the commit it was built from.

## Setup

The tools need Python 3.9 or later, with pandas and pyarrow:

```bash
python3 -m pip install pandas pyarrow
```

The tools make no network connection. `tools/extract.py` is the only file that starts another
process: it runs def2graph and `make_graph_json.py`. `viewer.html` loads nothing from the web.

## Workflow

`$KIT` is this skill's base directory. Run each step from a directory beside the design, not from
inside the kit, so that `work/` and `export/` sit with the design. Show the user each tool's output.

1. **Find the inputs.**
   - The DEF must hold placement: its `COMPONENTS` are `PLACED` or `FIXED`. Routing is not read.
   - Give every LEF the design uses: the technology LEF, the standard-cell LEFs, and the LEF of
     each macro, such as SRAMs.
   - Give the Liberty files for the same cells. One corner is enough. The tools read only which
     cells are flops or memories, pin directions, and cell area.

2. **Extract.**

   ```bash
   python3 $KIT/tools/extract.py --def design.def --lef tech.lef cells.lef sram.lef --lib cells.lib sram.lib --work work
   ```

   This writes `work/graph/` and `work/graph.json`. If a LEF or Liberty file is missing, the step
   fails, or `unknown_cells` in `work/graph/summary.json` is more than 0.

3. **Choose the options** with the user. See "Options" below.

4. **Obfuscate.**

   ```bash
   python3 $KIT/tools/obfuscate.py work/graph.json --key work/key.json -o export/design.export.json
   ```

   For bus roles, write the roles file, fill it in, then add `--roles`:

   ```bash
   python3 $KIT/tools/obfuscate.py work/graph.json --roles-template work/roles.json
   python3 $KIT/tools/obfuscate.py work/graph.json --roles work/roles.json --key work/key.json -o export/design.export.json
   ```

   You can propose a role for each bus from its name, direction and width. Confirm the roles
   with the user before you run the second command.

5. **Verify.**

   ```bash
   python3 $KIT/tools/verify.py work/graph.json export/design.export.json --key work/key.json
   ```

6. **Audit.** Give it the same design files as step 2:

   ```bash
   python3 $KIT/tools/audit.py export/design.export.json --key work/key.json \
       --def design.def --lef tech.lef cells.lef sram.lef --lib cells.lib sram.lib --json work/audit.json
   ```

   Check 3 reads the design's own files and searches the export for every name they define, so it
   does not depend on the obfuscator. If a check fails, `--show` prints the strings that failed.

7. **Review.** Go through the audit's "What the export still shows" list with the user. These are
   the items the client approves. `DATA.md` explains each one. To see the export as unsilo sees
   it, open `viewer.html` in a browser and pick the export with **Open graph file**.

8. **Send.** The user sends `export/design.export.json` and the sha256 from the audit report.

9. **Read the results.** unsilo's results name tokens. Put the real names back:

   ```bash
   python3 $KIT/tools/reveal.py results.json --key work/key.json -o work/results.revealed.json
   ```

## Options

The defaults are unsilo's choices, not fixed rules. Explain each choice, and let the user decide.

- `--profile cones` (default) keeps only the wires inside the port cones, the cells on them,
  every memory and every port. `--profile full` keeps every wire and every cell. unsilo tells the
  client which profile their analysis needs. Use `cones` unless unsilo asked for `full`.
- `--scale 1` (default) keeps lengths in um. `--scale random` multiplies every coordinate and
  length by one secret factor between 0.5 and 2, kept in the key. This hides the absolute die size
  and cell heights, but ratios between sizes stay visible. An analysis may use spacing rules in
  um, so the client must then tell unsilo the factor, or the results will be inexact.
- `--roles` (opt-in) gives each bus the user chooses a role from a fixed list: clock, reset,
  address, write_data, read_data, write_enable, chip_enable, select, other. The export holds the
  role, never the bus's real name. Roles make unsilo's results easier to read. The audit lists
  the roles in the export, and fails on any other word.

## Questions users ask

Answer from the code. These pointers say where to look.

- *What leaves the site?* One JSON file. `DATA.md` lists every field. `audit.py` check 1 fails on
  any key that the format does not have.
- *Can unsilo get the names back?* Not from the export. Tokens are numbers in a random order, not
  hashes of names, so there is nothing to guess against (`obfuscate.py`, the `shuffled` and
  `*_tok` lines). Only the key maps them back, and the key stays in `work/`.
- *What can unsilo still learn?* The structure and the floorplan: counts, sizes, positions, and
  which cell drives which. The audit lists these items with this design's numbers. Say this
  plainly: obfuscation hides names, not structure.
- *Is the process or library visible?* No library, cell or process name is in the file. At scale
  1, cell heights are in um, and a reader can match a row height to a known library.
- *Does anything run on unsilo's side before the file arrives?* No. The method runs only here.
