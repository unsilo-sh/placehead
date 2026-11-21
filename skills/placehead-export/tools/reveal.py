"""Put the real names back into a file that unsilo sends you, such as headroom results.

Usage:
    python reveal.py results.json --key work/key.json -o results.revealed.json

Each token (oi12, ob3[7], op5, ...) in the file becomes the real name it stands for. A pin token
becomes cell/pin. Numbers stay as they are: if the export used --scale, divide lengths by the key's
scale for um. Run it on your side only. The output holds real names, so do not send it back.
"""
import argparse
import re
from pathlib import Path

from common import load_json

TOK = re.compile(r"\bo([ibcnp])(\d+)\b")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", help="any text file: JSON, CSV, a report")
    ap.add_argument("--key", required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    key = load_json(args.key)
    table = {"i": key["inst"], "b": key["bus"], "c": key["cell"], "n": key["net"],
             "p": {t: f"{c}/{p}" for t, (c, p) in key["pin"].items()}}
    unknown = set()

    def sub(m):
        t = m.group(0)
        real = table[m.group(1)].get(t)
        if real is None:
            unknown.add(t)
            return t
        return real

    text = TOK.sub(sub, Path(args.file).read_text())
    Path(args.out).write_text(text)
    print(f"wrote {args.out}")
    if key["scale"] != 1:
        print(f"lengths are in export units: divide by {key['scale']} for um")
    if unknown:
        print(f"{len(unknown)} tokens are not in this key (another export's key?)")


if __name__ == "__main__":
    main()
