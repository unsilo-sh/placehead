# Data protection

These practices apply to the placement graph export. Each one points to where you can check it.

- **Runs on your side.** The extraction tools run on your machine and make no network connections.
  They are short Python files in `skills/placehead-export/tools/`.
- **Minimum data.** The tools read only placement and connectivity. They never read timing, power,
  routing or RTL. By default, the export keeps only the logic paths that start at the chip's
  top-level pins and end at the first flip-flop or memory they reach. It also keeps the cells on
  those paths, the memories and the top-level pins. It drops every other wire, and any cell that
  is not on one of those paths.
- **No names leave your site.** Every design, cell, net, port and library name is replaced with a
  random token before export. If you choose, each top-level bus can carry a role from a fixed
  list, such as clock, address or read data. The audit rejects any word that is not on that list.
- **You hold the key.** Only your key maps tokens back to real names. It stays with you and is
  never sent to unsilo.
- **Checked before it is sent.** An audit tool compares the export against your own design files,
  and fails if any name from them appears. It also lists exactly what the export still shows.
- **One file, your channel.** A single file leaves your site, through your own approved channel.
- **Clear about what stays visible.** Obfuscation hides names, not structure: the floorplan shape,
  the connectivity and the cell sizes remain visible. Your team can review these before approving.

## Where to look

| Question | Answer in |
|---|---|
| What is in the export, field by field? | `skills/placehead-export/DATA.md` |
| What does the audit check? | `skills/placehead-export/tools/audit.py`, its first lines |
| How are names replaced? | `skills/placehead-export/tools/obfuscate.py` |
| What does unsilo compute from the export? | The analysis agreed for your engagement. `analysis/headroom.py` is an example |
| What does Claude Code read, if you use the skill? | `skills/placehead-export/SKILL.md`, "Rules for you, in this session" |

If you use Claude Code, anything it reads goes to your model provider, under your organization's
terms with that provider. The skill tells Claude Code not to read your design files, the key or the
roles file.
