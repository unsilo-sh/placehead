#!/bin/sh
# Download the Nangate45 and fakeram45 LEF and Liberty files this design uses,
# from OpenROAD's test/Nangate45 directory, into pdk/.
set -e
cd "$(dirname "$0")"
mkdir -p pdk
base=https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD/master/test/Nangate45
for f in Nangate45_tech.lef Nangate45_stdcell.lef Nangate45_typ.lib fakeram45_64x32.lef fakeram45_64x32.lib fakeram45_1024x32.lef fakeram45_1024x32.lib; do
  curl -fsSL "$base/$f" -o "pdk/$f"
done
