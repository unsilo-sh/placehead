# vendor

`def2graph/` is terraine's DEF/LEF/Liberty reader. It traces each top-level port's logic cone to
the flops and memories it reaches. `tools/extract.py` runs it. It is a copy, without its plotting
module, of `adapters/def2graph` in terraine's factory repository at commit 38e7d68.
`scripts/vendor_def2graph.sh` refreshes the copy.

It needs pandas and pyarrow. It opens no network connection.
