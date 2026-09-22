#!/usr/bin/env bash
# Download, verify, and build LISFLOOD-FP 8 inside WSL2 — the exact steps
# used to build the toy 2-cell validation case in ASSUMPTIONS.md, so the
# build is reproducible rather than tribal knowledge from one session.
#
# Run from WSL (not from Windows/PowerShell):
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Purnendu/Aegir/scripts/model_build_lisflood.sh
#
# Everything this script creates lives under $HOME (the WSL filesystem),
# never under /mnt/c/ — see ASSUMPTIONS.md "LISFLOOD-FP obtained and built"
# for why (I/O performance; Windows/WSL path-translation overhead is real
# for the many small per-timestep files a hydraulic model run produces).
set -euo pipefail

ZENODO_URL="https://zenodo.org/records/13121102/files/LISFLOOD-FP-v8.2.zip?download=1"
EXPECTED_MD5="a0a607cf68078b56a9c50c7013cafa95"
EXPECTED_COMMIT="79ba7d380650ed9eec93656704e931ec2b89da6d"

SRC_DIR="$HOME/lisflood-fp/src"
ZIP_PATH="$SRC_DIR/LISFLOOD-FP-v8.2.zip"

mkdir -p "$SRC_DIR" "$HOME/lisflood-runs"

echo "== Checking build dependencies (apt) =="
REQUIRED_PKGS="build-essential cmake libnuma-dev libnetcdf-dev libnetcdf-c++4-dev"
MISSING=""
for pkg in $REQUIRED_PKGS; do
	dpkg -s "$pkg" >/dev/null 2>&1 || MISSING="$MISSING $pkg"
done
if [ -n "$MISSING" ]; then
	echo "Missing packages:$MISSING"
	echo "Install with: sudo apt-get update && sudo apt-get install -y$MISSING"
	exit 1
fi

echo "== Downloading LISFLOOD-FP v8.2 from Zenodo (DOI 10.5281/zenodo.13121102) =="
if [ ! -f "$ZIP_PATH" ]; then
	wget -q --show-progress -O "$ZIP_PATH" "$ZENODO_URL"
fi

ACTUAL_MD5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
if [ "$ACTUAL_MD5" != "$EXPECTED_MD5" ]; then
	echo "MD5 MISMATCH: got $ACTUAL_MD5, expected $EXPECTED_MD5 — aborting, do not build from an unverified download."
	exit 1
fi
echo "MD5 verified: $ACTUAL_MD5"

echo "== Extracting =="
cd "$SRC_DIR"
[ -d LISFLOOD-FP ] || unzip -q "$ZIP_PATH"

cd LISFLOOD-FP
ACTUAL_COMMIT=$(git rev-parse HEAD)
if [ "$ACTUAL_COMMIT" != "$EXPECTED_COMMIT" ]; then
	echo "WARNING: extracted source's HEAD commit ($ACTUAL_COMMIT) does not match the recorded commit ($EXPECTED_COMMIT) for the Zenodo v8.2 release — the release archive may have changed. Proceeding, but note this in any build record."
fi
echo "Building from commit: $ACTUAL_COMMIT"

echo "== Applying project patches (model/lisflood-patches/) =="
PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../model/lisflood-patches" && pwd)"
for patch in "$PATCH_DIR"/*.patch; do
	[ -e "$patch" ] || continue
	if git apply --reverse --check "$patch" 2>/dev/null; then
		echo "  $(basename "$patch") already applied, skipping"
	else
		echo "  applying $(basename "$patch")"
		git apply "$patch"
	fi
done

echo "== Configuring (CMake, Release, default config — NetCDF on, no CUDA on this machine) =="
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release

echo "== Building =="
cmake --build build -j"$(nproc)"

echo "== Verifying =="
./build/lisflood -v || true
echo
echo "Build complete: $SRC_DIR/LISFLOOD-FP/build/lisflood"
echo "Toolchain: $(gcc --version | head -1), $(cmake --version | head -1)"
