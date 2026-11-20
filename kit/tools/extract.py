"""Read a placed design and write its graph JSON. Everything this writes holds real names: keep it.

Usage:
    python extract.py --def design.def --lef tech.lef cells.lef sram.lef --lib cells.lib sram.lib \
        --work work/

It runs two programs from vendor/, on this machine only:
  def2graph          reads the DEF, LEF and Liberty files and traces each port's logic cone to the
                     flops and memories it reaches. Writes work/graph/ (parquet and JSON).
  make_graph_json.py adds each pin's position from the LEF and each wire's two ends. Writes
                     work/graph.json.

The DEF needs placement. Routing is not read. Liberty is read only to tell flops, memories and
other cells apart, and for cell area.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--def", dest="def_path", required=True)
    ap.add_argument("--lef", nargs="+", required=True)
    ap.add_argument("--lib", nargs="+", required=True)
    ap.add_argument("--work", required=True, help="a directory that stays on your side")
    args = ap.parse_args(argv)

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(VENDOR))
    run = lambda cmd: subprocess.run([sys.executable, *cmd], env=env, check=True)

    # -q: def2graph prints no design names, only progress counts.
    run(["-m", "def2graph", "--def", args.def_path, "--lef", *args.lef, "--lib", *args.lib,
         "--out", str(work / "graph"), "--formats", "parquet", "json", "-q"])
    run([str(VENDOR / "make_graph_json.py"), "--def", args.def_path, "--lef", *args.lef,
         "--graph", str(work / "graph"), "-o", str(work / "graph.json")])
    print(f"wrote {work / 'graph.json'}. It holds real names: obfuscate it, and do not send it.")


if __name__ == "__main__":
    main()
