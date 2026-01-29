#!/bin/bash
for f in ./1x1/*.mxl; do
  echo "Converting $f → ${f%.mxl}.krn"
  python3 -m converter21 -f musicxml -t humdrum "$f" "${f%.mxl}.krn"
done
