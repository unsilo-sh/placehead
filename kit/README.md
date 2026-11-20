# placehead export kit

This kit prepares a placed design for terraine's placement headroom analysis. It runs on your
machine. It writes one file with no names from the design. That file is the only thing you send.

## Install

1. Unzip the kit into your Claude Code skills directory:

   ```bash
   unzip placehead-export.zip -d ~/.claude/skills/
   ```

2. Install the Python packages the tools need (Python 3.9 or later):

   ```bash
   python3 -m pip install pandas pyarrow
   ```

3. Start Claude Code in a directory that holds the design, or can read it. Then ask, for example:
   "Prepare this design for terraine's headroom analysis, and show me what leaves our site."

Claude Code loads `SKILL.md` and runs the workflow with you. You can also run the tools without
Claude Code. `SKILL.md` lists each command.

## For a security review

- `DATA.md` lists every field of the export, and what the obfuscation hides and does not hide.
- `tools/audit.py` checks an export against your own DEF, LEF and Liberty files, and lists what
  the export still shows, with your design's numbers.
- `tools/` and `vendor/` are short Python files with no network code. Read them, or ask Claude
  Code to explain any line.
- `SKILL.md` tells Claude Code not to read your design files or the key, and to read only the
  tools' reports and the export. Whatever Claude Code reads goes to your model provider, under
  your organization's terms with that provider.
