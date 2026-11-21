---
name: placehead-export
description: Prepare a placed design for terraine's placement headroom analysis, and explain exactly what data leaves your site. Use when the user wants to export a DEF for terraine, check an export for sensitive data, review what the obfuscation hides and what it does not, or read terraine's results with the real names.
---

# placehead export kit

terraine's placement headroom analysis estimates how much shorter the paths between a design's
ports and its memories can get with a few moves. It needs the placed design's connectivity and
geometry. It does not need any name from the design.

This kit runs on the design owner's machine. It reads the design, replaces every name with a
meaningless token, checks the result, and writes one file to send to terraine. The key that maps
tokens back to names stays with the owner. Your job is to run the kit with the user and to answer
their questions about what the file holds. Their security team may ask these questions too.

## Rules for you, in this session

These rules apply because anything you read or print in this session goes to the model provider.

1. Do not read the design files (DEF, LEF, Liberty) or anything in `work/`, including `key.json`
   and `roles.json`. Run the tools on them and read only what the tools print.
2. You may read the export file and all of the kit's code. The export is the data that leaves the
   site, so reading it shows nothing new.
3. Do not use `audit.py --show` unless the user asks for it. Before you use it, tell the user that
   it prints real names into this session.
4. Do not send any file anywhere. The user sends the export through their own approved channel.
5. Do not change the kit's code to make a check pass. If a check fails, stop and tell the user.
6. Answer questions about data handling from the code, and cite `file:line`. Do not rely on this
   file alone. The tools are short, so read them.

## Layout

| Path | Holds | Leaves the site? |
|---|---|---|
| `tools/extract.py` | Runs def2graph and make_graph_json.py on the design | No |
| `tools/make_graph_json.py` | Adds each pin's position from the LEF and each wire's two ends | No |
| `tools/obfuscate.py` | Replaces names with tokens and writes the key | No |
| `tools/verify.py` | Checks that the export is the same design with only names, order and scale changed | No |
| `tools/audit.py` | Checks that the export holds no design names, and lists what it still shows | No |
| `tools/reveal.py` | Puts real names back into a file that terraine returns | No |
| `tools/def2graph/` | Reads DEF, LEF and Liberty, and traces each port's logic cone | No |
| `DATA.md` | Every field of the export: what it holds, and why the analysis needs it | No |
| `viewer.html` | terraine's cone viewer: draws an export on its floorplan, offline | No |
| `work/` (made by the tools) | The design's graph with real names, and the key | **Never** |
| `export/` (made by the tools) | The export file only | **Yes, this one file** |

This skill is one directory of the placehead repository, `skills/placehead-export/`. The
repository's `SECURITY.md` summarizes the data-protection practices for a security team. A zip
of the skill has a `VERSION` file that names the commit it was built from.

## Setup

The tools need Python 3.9 or later, with pandas and pyarrow:

```bash
python3 -m pip install pandas pyarrow
```

The tools make no network connection. To confirm this, search the code for network modules:

```bash
grep -rnE "socket|urllib|http|requests" $KIT/tools
```

The search finds no network code. The only subprocess call is in `tools/extract.py`. It starts
def2graph and `make_graph_json.py`. `viewer.html` loads no fonts, scripts or styles from the web. Its
one `fetch` reads `graph.json` beside the page, which fails when the page is opened from disk.

## Workflow

`$KIT` is this skill's base directory. Run each step from a project directory the user picks, not from
inside the kit, so `work/` and `export/` sit with the design. Give the user each tool's output.

1. **Extract.** Use the design's placed DEF, all its LEF files, and its Liberty files:

   ```bash
   python3 $KIT/tools/extract.py --def design.def --lef tech.lef cells.lef sram.lef --lib cells.lib sram.lib --work work
   ```

   This writes `work/graph/` and `work/graph.json`. Both hold real names.

2. **Obfuscate.** Ask the user which options to use before you run this step. See "Options" below.

   ```bash
   python3 $KIT/tools/obfuscate.py work/graph.json --key work/key.json -o export/design.export.json
   ```

   If the user opts in to bus roles, write the roles file first. Then add `--roles` to the command:

   ```bash
   python3 $KIT/tools/obfuscate.py work/graph.json --roles-template work/roles.json
   python3 $KIT/tools/obfuscate.py work/graph.json --roles work/roles.json --key work/key.json -o export/design.export.json
   ```

   The user fills in `work/roles.json`. It holds the real bus names, so do not read it unless the
   user tells you to, and tell them that the bus names then enter this session.

3. **Verify.** This shows that the analysis sees the same design:

   ```bash
   python3 $KIT/tools/verify.py work/graph.json export/design.export.json --key work/key.json
   ```

4. **Audit.** Give it the same design files as step 1:

   ```bash
   python3 $KIT/tools/audit.py export/design.export.json --key work/key.json \
       --def design.def --lef tech.lef cells.lef sram.lef --lib cells.lib sram.lib --json work/audit.json
   ```

   Check 3 reads the design's own files and searches the export for every name they define. This
   check does not trust the obfuscator.

5. **Review.** Go through the audit's "What the export still shows" list with the user. Each item
   is data the security team must accept. `DATA.md` explains each item. To show the user the
   export as terraine sees it, have them open `viewer.html` in a browser and pick the export
   with **Open graph file**. The page reads the file in the browser and sends it nowhere.

6. **Send.** The user sends `export/design.export.json` and its sha256 from the audit report.
   Nothing else leaves the site.

7. **Read the results.** terraine returns results that name tokens. Put the real names back:

   ```bash
   python3 $KIT/tools/reveal.py headroom.json --key work/key.json -o work/headroom.revealed.json
   ```

## Options

Explain these choices to the user, and let them decide. The defaults are terraine's choices, not
fixed rules.

- `--profile headroom` (default) keeps only what the headroom analysis reads: the wires inside the
  port cones, the cells on them, every memory and every port. `--profile full` keeps every wire.
  The full profile also lets terraine draw the wires outside the cones.
- `--scale 1` (default) keeps lengths in um. `--scale random` multiplies every coordinate and
  length by one secret factor between 0.5 and 2, kept in the key. This hides the absolute die size
  and cell heights. It gives limited protection: terraine's analysis uses spacing rules in um, so the
  user must tell terraine the factor, or terraine's results will be inexact. Ratios between sizes
  stay visible at any scale.
- `--roles` (opt-in, off by default) sends a role for each bus the user chooses, from a fixed list:
  clock, reset, address, write_data, read_data, write_enable, chip_enable, select, other. The
  export holds the role, never the bus's real name. Roles make terraine's results easier to read.
  The audit lists the roles that leave the site, and fails on any other word.

## Questions users ask

Answer from the code. These pointers say where to look.

- *What leaves the site?* One JSON file. `DATA.md` lists every field. `audit.py` check 1 fails
  on any key that the format does not have.
- *Can terraine get the names back?* Not from the export. Tokens are numbers in a random order,
  not hashes of names, so there is nothing to guess against (`obfuscate.py`, the `shuffled` and
  `*_tok` lines). Only the key maps them back, and the key stays in `work/`.
- *What can terraine still learn?* The structure and the floorplan: counts, sizes, positions,
  and which cell drives which. The audit lists these items with this design's numbers.
  Say this plainly. Obfuscation hides names, not structure.
- *Is the design's process or library visible?* No library, cell or process name is in the file.
  At scale 1, cell heights are in um, and a reader can match a row height to a known library.
- *Does anything run on terraine's side before the file arrives?* No. The kit runs only here.
