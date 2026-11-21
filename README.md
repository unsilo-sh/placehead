# placehead: placement headroom analysis

placehead estimates how much shorter the paths between a chip's top-level pins and its memories
can get with a few placement moves: moving a bus's pins along the die edge, or mirroring a memory
in place. It reports the headroom as the longest path and the total path length, before and after
each move.

The analysis needs a placed design's connectivity and geometry. It does not need any name from the
design. So the design owner extracts a graph on their own machine, removes every name from it, and
sends terraine only that graph.

## How we work together

| Step | Who | Where | What |
|---|---|---|---|
| 1. Extract | Partner | Partner's machine | Read the placed DEF, LEF and Liberty files into a graph |
| 2. Obfuscate | Partner | Partner's machine | Replace every name with a random token, and move the die to (0, 0). The key stays with the partner |
| 3. Verify and audit | Partner | Partner's machine | Check that the export is the same design, and that no name from the design files is in it |
| 4. Send | Partner | Partner's channel | Send one file, `design.export.json`, and its sha256 hash |
| 5. Analyze | terraine | terraine | Run `analysis/headroom.py` on the export |
| 6. Return | terraine | terraine's channel | Send the results. They name tokens, not real names |
| 7. Reveal | Partner | Partner's machine | Put the real names back into the results with the key |

Steps 1 to 4 are one Claude Code skill, `skills/placehead-export/`. Claude Code runs the tools with
you and answers questions about what the export holds. You can also run the tools without Claude
Code.

## For the partner

Read `SECURITY.md` first. It lists the data-protection practices for your security team.

1. Install the Python packages (Python 3.9 or later):

   ```bash
   python3 -m pip install pandas pyarrow
   ```

2. Install the skill for Claude Code:

   ```bash
   cp -R skills/placehead-export ~/.claude/skills/
   ```

3. Try it on the synthetic design first. It runs steps 1 to 3 on a design with no secrets:

   ```bash
   examples/sparse_mem_core/run_demo.sh
   ```

4. Start Claude Code in a directory that can read your design, and ask, for example:
   "Prepare this design for terraine's headroom analysis, and show me what leaves our site."

`skills/placehead-export/SKILL.md` lists each command if you run the tools by hand.
`skills/placehead-export/DATA.md` describes every field of the export.

Run the tools outside this repository, or keep their output in the ignored directories `work/`
and `export/`. `.gitignore` keeps keys, roles files and exports out of git.

## Repository layout

| Path | Holds | Runs at |
|---|---|---|
| `SECURITY.md` | Data-protection practices, for a security review | |
| `skills/placehead-export/` | The skill: extract, obfuscate, verify, audit and reveal tools, the vendored def2graph reader, the field list and an offline viewer | Partner |
| `analysis/` | The headroom analysis and its results viewer. It is here so you can see what terraine computes from your export | terraine |
| `examples/sparse_mem_core/` | A synthetic 48-memory design, to try the skill on | Either |
| `scripts/` | `package.sh` zips the skill for a partner who does not clone the repository. `vendor_def2graph.sh` refreshes the vendored reader | terraine |

## Viewers

Both viewers are single HTML files that load nothing from the web. Open one in a browser and pick a
file with its open button. The file stays in the browser.

- `skills/placehead-export/viewer.html` draws an export, or a graph with real names, on its
  floorplan: each port's logic cone, and each memory's wires.
- `analysis/headroom_viewer.html` draws headroom results: every variant tried, its cost, and the
  moves from today's placement to it.
