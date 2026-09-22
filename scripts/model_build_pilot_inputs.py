"""Build the non-DEM LISFLOOD-FP inputs for the pilot pipeline-validation
run (Manning's n grid, spatially-uniform rainfall time series) — the DEM
itself is fetched/reprojected separately (Copernicus GLO-30 placeholder;
see ASSUMPTIONS.md "Pilot pipeline run" and scripts/model_stage_and_run.sh).

Every input this script writes shares the EXACT grid header (287x273,
cellsize 9.996932063502381 m, xllcorner/yllcorner matching
web/data/scenario_landcover.tif) — LISFLOOD-FP's ASCII-grid readers are
fixed positional parsers (see ASSUMPTIONS.md "Where the pilot chain
breaks"): every grid fed to one run MUST agree on ncols/nrows/cellsize or
inputs silently misalign.

Manning's n: brief §4.6 values (channel 0.035, sealed 0.015, grass 0.035,
forest 0.10), assigned per NMD class via web/data/scenario_landcover.tif
(reusing the same stdlib TIFF reader as scripts/scenario_compute_curve_number.py)
and web/data/scenario_landcover_classes.json's sealed/pervious/water kind.
Forest NMD classes (111-128) get 0.10; every other pervious/water class
gets 0.035 (grass and channel share the same brief-given value, so water
cells default to it too — there is no separate delineated channel mask in
this project yet); sealed cells get 0.015.

Rainfall: LISFLOOD-FP's simpler "rainfall <file>" keyword — a spatially
UNIFORM, temporally-varying time series (mm/hr, LoadTimeSeries format) —
not the full spatially-varying "dynamicrainfile" NetCDF option. This is a
deliberate pilot-run simplification, not a capability gap (NetCDF
rainfall was confirmed supported in ASSUMPTIONS.md's doc-capability
check): building the CN-based per-cell effective-rainfall NetCDF grid is
real follow-on work, scoped out of this pipeline-validation pass to keep
it testable end-to-end today. Source: docs/hyetographs/hyetograph_40mm.csv
(scripts/scenario_generate_hyetographs.py's alternating-block storm,
already generated — nothing new computed here).

Usage:
    python scripts/model_build_pilot_inputs.py <run_dir>
"""
import csv
import pathlib
import struct
import sys

root = pathlib.Path(__file__).resolve().parents[1]
LANDCOVER_TIF = root / "web/data/scenario_landcover.tif"
LANDCOVER_CLASSES_JSON = root / "web/data/scenario_landcover_classes.json"
HYETOGRAPH_CSV = root / "docs/hyetographs/hyetograph_40mm.csv"

# Must match scripts/scenario_compute_curve_number.py's grid exactly.
CELLSIZE = 9.996932063502381
NODATA = -9999

MANNING_FOREST = 0.10
MANNING_GRASS_OR_CHANNEL = 0.035
MANNING_SEALED = 0.015

FOREST_NMD_VALUES = {111, 112, 113, 114, 115, 116, 117, 118, 121, 123, 124, 125, 126, 127, 128}


def read_landcover_tiff(path):
    import json
    data = path.read_bytes()
    endian = "<" if data[0:2] == b"II" else ">"
    ifd_offset = struct.unpack(endian + "I", data[4:8])[0]
    n_entries = struct.unpack(endian + "H", data[ifd_offset:ifd_offset + 2])[0]
    tags = {}
    p = ifd_offset + 2
    type_sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8}
    type_fmt = {1: "B", 3: "H", 4: "I", 11: "f", 12: "d"}
    for _ in range(n_entries):
        tag, typ, count, value_bytes = struct.unpack(endian + "HHI4s", data[p:p + 12])
        size = type_sizes.get(typ, 1) * count
        raw = value_bytes[:size] if size <= 4 else data[struct.unpack(endian + "I", value_bytes)[0]:][:size]
        if typ in type_fmt:
            tags[tag] = struct.unpack(endian + type_fmt[typ] * count, raw)
        p += 12
    width, height = tags[256][0], tags[257][0]
    strip_offsets, strip_byte_counts = tags[273], tags[279]
    pixels = bytearray()
    for off, nbytes in zip(strip_offsets, strip_byte_counts):
        pixels.extend(data[off:off + nbytes])
    n_pixels = width * height
    values = struct.unpack(endian + "H" * n_pixels, bytes(pixels[:n_pixels * 2]))
    return {"grid": [values[r * width:(r + 1) * width] for r in range(height)], "width": width, "height": height}


def build_manning_grid(out_path):
    import json
    lc = read_landcover_tiff(LANDCOVER_TIF)
    kind_by_value = {c["value"]: c["kind"] for c in json.loads(LANDCOVER_CLASSES_JSON.read_text(encoding="utf-8"))["classes"]}

    with out_path.open("w", encoding="ascii") as f:
        f.write(f"ncols        {lc['width']}\n")
        f.write(f"nrows        {lc['height']}\n")
        f.write("xllcorner    414832.632369\n")
        f.write("yllcorner    6189108.715862\n")
        f.write(f"cellsize     {CELLSIZE}\n")
        f.write(f"NODATA_value {NODATA}\n")
        for row in lc["grid"]:
            vals = []
            for value in row:
                if value in FOREST_NMD_VALUES:
                    n = MANNING_FOREST
                elif kind_by_value.get(value) == "sealed":
                    n = MANNING_SEALED
                else:
                    n = MANNING_GRASS_OR_CHANNEL
                vals.append(str(n))
            f.write(" ".join(vals) + "\n")
    print(f"Wrote {out_path}")


def build_rainfall_series(out_path):
    rows = list(csv.DictReader(HYETOGRAPH_CSV.open(encoding="utf-8")))
    with out_path.open("w", encoding="ascii") as f:
        f.write("Rainfall time series - scripts/scenario_generate_hyetographs.py's 40mm design storm, spatially uniform (pilot simplification, see module docstring)\n")
        f.write(f"{len(rows) + 1} minutes\n")
        for r in rows:
            f.write(f"{r['intensity_mm_per_h']} {r['t_start_min']}\n")
        f.write(f"0.0 {rows[-1]['t_end_min']}\n")
    print(f"Wrote {out_path} ({len(rows) + 1} points, 0-{rows[-1]['t_end_min']} min)")


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/model_build_pilot_inputs.py <run_dir>")
    run_dir = pathlib.Path(sys.argv[1])
    run_dir.mkdir(parents=True, exist_ok=True)
    build_manning_grid(run_dir / "pipelinetest_horby_pilot.n")
    build_rainfall_series(run_dir / "pipelinetest_horby_pilot.rain")


if __name__ == "__main__":
    main()
