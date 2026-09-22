#!/usr/bin/env bash
# Stage a LISFLOOD-FP run's inputs from the Windows repo into the WSL
# filesystem, run the model there, then copy results back.
#
# This is the ONLY script that touches /mnt/c/ during a model run. Every
# other step — the actual simulation, all of LISFLOOD-FP's per-timestep
# I/O — happens entirely under $HOME/lisflood-runs/ (the WSL/ext4
# filesystem), never under /mnt/c/. See ASSUMPTIONS.md "Windows Python for
# preprocessing, WSL for execution" for why: /mnt/c/ is a 9p network-style
# mount from WSL's point of view, and LISFLOOD-FP writes many small files
# per run (one .wd/.elev pair per saveint step) — doing that over /mnt/c/
# is measurably slower and is exactly the I/O pattern this split avoids.
#
# Run from WSL:
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Purnendu/Aegir/scripts/model_stage_and_run.sh <run_name>
#
# Expects Windows-side inputs already prepared at:
#   model/inputs/<run_name>/<run_name>.par   (and everything it references:
#   DEM, .bci, .bdy, .n, rainfall .nc — all paths inside the .par file must
#   be relative, since they get copied as a whole directory into WSL)
#
# Writes results back to:
#   model/outputs/<run_name>/
set -euo pipefail

if [ $# -ne 1 ]; then
	echo "Usage: $0 <run_name>" >&2
	exit 1
fi
RUN_NAME="$1"

REPO_WIN="/mnt/c/Purnendu/Aegir"
INPUT_DIR="$REPO_WIN/model/inputs/$RUN_NAME"
OUTPUT_DIR="$REPO_WIN/model/outputs/$RUN_NAME"
LISFLOOD_BIN="$HOME/lisflood-fp/src/LISFLOOD-FP/build/lisflood"
RUN_DIR="$HOME/lisflood-runs/$RUN_NAME"

if [ ! -d "$INPUT_DIR" ]; then
	echo "No inputs at $INPUT_DIR — nothing to stage." >&2
	exit 1
fi
if [ ! -x "$LISFLOOD_BIN" ]; then
	echo "lisflood binary not found at $LISFLOOD_BIN — run scripts/model_build_lisflood.sh first." >&2
	exit 1
fi
PAR_FILE="$INPUT_DIR/$RUN_NAME.par"
if [ ! -f "$PAR_FILE" ]; then
	echo "Expected parameter file not found: $PAR_FILE" >&2
	exit 1
fi

echo "== Staging inputs: $INPUT_DIR -> $RUN_DIR (WSL filesystem) =="
rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR"
cp -r "$INPUT_DIR"/. "$RUN_DIR"/
mkdir -p "$RUN_DIR/results"

echo "== Running lisflood ($RUN_NAME.par) entirely under \$HOME =="
cd "$RUN_DIR"
"$LISFLOOD_BIN" -v "$RUN_NAME.par" 2>&1 | tee run.log

echo "== Copying results back: $RUN_DIR/results -> $OUTPUT_DIR =="
mkdir -p "$OUTPUT_DIR"
cp -r "$RUN_DIR/results"/. "$OUTPUT_DIR"/
cp "$RUN_DIR/run.log" "$OUTPUT_DIR/run.log"

echo "Done. Results at $OUTPUT_DIR (Windows: model\\outputs\\$RUN_NAME\\)"
echo "Run working directory kept at $RUN_DIR for inspection/debugging — not deleted automatically."
