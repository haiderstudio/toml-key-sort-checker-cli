#!/bin/sh
# Run the checker over each example file and show the result.
# The bad example fails on purpose, so each run is allowed to fail.
cd "$(dirname "$0")/.."
for f in examples/good.toml examples/bad.toml examples/edge.toml; do
  echo "== $f =="
  python3 src/toml_key_sort_checker.py "$f" || true
  echo
done
echo "== examples/ : the whole folder =="
python3 src/toml_key_sort_checker.py examples/ || true
