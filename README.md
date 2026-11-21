# placehead: placement analysis on an obfuscated graph

placehead lets a design owner share a placed design with unsilo for analysis, without sharing any
name from the design. The owner extracts a graph of the placement on their own machine, removes
every name from it, and sends unsilo only that graph.

unsilo builds the analysis for each client, around that client's design and questions. Placement
analysis needs a design's connectivity and geometry, not its names, so one export format serves
every analysis. `analysis/headroom.py` is an example: it estimates how much shorter the paths
between top-level pins and memories get with a few placement moves.

## How we work together

| Step | Who | Where | What |
|---|---|---|---|
| 1. Extract | Partner | Partner's machine | Read the placed DEF, LEF and Liberty files into a graph |
| 2. Obfuscate | Partner | Partner's machine | Replace every name with a random token, and move the die to (0, 0). The key stays with the partner |
| 3. Verify and audit | Partner | Partner's machine | Check that the export is the same design, and that no name from the design files is in it |
| 4. Send | Partner | Partner's channel | Send one file, `design.export.json`, and its sha256 hash |
| 5. Analyze | unsilo | unsilo | Run the analysis built for this client on the export |
| 6. Return | unsilo | unsilo's channel | Send the results. They name tokens, not real names |
| 7. Reveal | Partner | Partner's machine | Put the real names back into the results with the key |

Steps 1 to 4 are one agent skill, `skills/placehead-export/`. `SKILL.md` holds the workflow: each
command, each check, and the rules for which files may be read in an agent session. `DATA.md`
describes every field of the export.

## For the partner

Read `SECURITY.md` first. It lists the data-protection practices for your security team.

1. Install the Python packages (Python 3.9 or later):

   ```bash
   python3 -m pip install pandas pyarrow
   ```

2. Install the skill. For Claude Code:

   ```bash
   cp -R skills/placehead-export ~/.claude/skills/
   ```

3. Run the workflow on the synthetic design. It runs steps 1 to 3 on a design with no secrets:

   ```bash
   examples/sparse_mem_core/run_demo.sh
   ```

4. Run the workflow on your design, from a directory that can read it. With the skill installed,
   an agent session can start from a request such as: "Prepare this design for unsilo's placement
   analysis, and show me what leaves our site."

Keep the workflow's output outside this repository, or in the ignored directories `work/` and
`export/`. `.gitignore` keeps keys, roles files and exports out of git.

## Repository layout

| Path | Holds | Runs at |
|---|---|---|
| `SECURITY.md` | Data-protection practices, for a security review | |
| `skills/placehead-export/` | The skill: extract, obfuscate, verify, audit and reveal tools, the def2graph reader, the field list and an offline viewer | Partner |
| `analysis/` | An example analysis, `headroom.py`, and its results viewer. It shows the kind of work unsilo does on an export | unsilo |
| `examples/sparse_mem_core/` | A synthetic 48-memory design, to try the skill on | Either |
| `scripts/` | `package.sh` zips the skill for a partner who does not clone the repository | unsilo |

## Viewers

Both viewers are single HTML files that load nothing from the web. Open one in a browser and pick a
file with its open button. The file stays in the browser.

- `skills/placehead-export/viewer.html` draws an export, or a graph with real names, on its
  floorplan: each port's logic cone, and each memory's wires.
- `analysis/headroom_viewer.html` draws the example analysis's results: every variant tried, its cost, and the
  moves from today's placement to it.
