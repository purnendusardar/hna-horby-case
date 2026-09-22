"""Convert a LISFLOOD-FP water-depth ASCII grid (.wd) into a depth PNG,
per the brief's web-asset spec (§5): "PNG, legend colour ramp, transparent
below 5 cm".

Reads the SAME 6-line positional ASCII-grid header as every other input
in this pipeline (ncols, nrows, xllcorner, yllcorner, cellsize,
NODATA_value) — see ASSUMPTIONS.md "Where the pilot chain breaks" for why
that header shape matters. Writes an RGBA PNG (stdlib struct+zlib, same
minimal writer as scripts/scenario_diagnose_curve_number_gaps.py, extended
to 4 channels for the alpha/transparency requirement).

Colour ramp: pale blue (shallow) -> dark blue (deep), clamped at
DEPTH_CLAMP_M for legibility (brief gives no exact ramp, only "legend
colour ramp" — clamp value and exact hues are this script's own choice,
not specified elsewhere). Cells below 5 cm are fully transparent (alpha=0),
matching the brief's transparency threshold exactly, not approximated.

Usage:
    python scripts/model_convert_depth_to_png.py <wd_file> <output_png>
"""
import struct
import sys
import zlib

TRANSPARENT_BELOW_M = 0.05
DEPTH_CLAMP_M = 2.0

# Pale blue -> dark blue, linearly interpolated by clamped depth fraction.
COLOR_SHALLOW = (173, 216, 230)
COLOR_DEEP = (8, 48, 107)


def read_ascii_grid(path):
    with open(path, "r", encoding="ascii") as f:
        ncols = int(f.readline().split()[1])
        nrows = int(f.readline().split()[1])
        xllcorner = float(f.readline().split()[1])
        yllcorner = float(f.readline().split()[1])
        cellsize = float(f.readline().split()[1])
        nodata = float(f.readline().split()[1])
        grid = []
        for _ in range(nrows):
            grid.append([float(v) for v in f.readline().split()])
    return {"ncols": ncols, "nrows": nrows, "xllcorner": xllcorner, "yllcorner": yllcorner,
            "cellsize": cellsize, "nodata": nodata, "grid": grid}


def write_png_rgba(path, width, height, pixel_fn):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            r, g, b, a = pixel_fn(x, y)
            raw += bytes((r, g, b, a))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # colour type 6 = RGBA
    idat = zlib.compress(bytes(raw), 9)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def depth_to_rgba(depth, nodata):
    if depth == nodata or depth < TRANSPARENT_BELOW_M:
        return (0, 0, 0, 0)
    frac = min(depth, DEPTH_CLAMP_M) / DEPTH_CLAMP_M
    r = round(COLOR_SHALLOW[0] + frac * (COLOR_DEEP[0] - COLOR_SHALLOW[0]))
    g = round(COLOR_SHALLOW[1] + frac * (COLOR_DEEP[1] - COLOR_SHALLOW[1]))
    b = round(COLOR_SHALLOW[2] + frac * (COLOR_DEEP[2] - COLOR_SHALLOW[2]))
    return (r, g, b, 255)


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python scripts/model_convert_depth_to_png.py <wd_file> <output_png>")
    wd_path, png_path = sys.argv[1], sys.argv[2]
    grid_data = read_ascii_grid(wd_path)
    grid = grid_data["grid"]
    nodata = grid_data["nodata"]

    max_depth = max((v for row in grid for v in row if v != nodata), default=0.0)
    wet_cells = sum(1 for row in grid for v in row if v != nodata and v >= TRANSPARENT_BELOW_M)

    def pixel_fn(x, y):
        return depth_to_rgba(grid[y][x], nodata)

    write_png_rgba(png_path, grid_data["ncols"], grid_data["nrows"], pixel_fn)
    print(f"Wrote {png_path}: {grid_data['ncols']}x{grid_data['nrows']}, "
          f"max depth {max_depth:.3f} m, {wet_cells} cells >= {TRANSPARENT_BELOW_M} m")


if __name__ == "__main__":
    main()
