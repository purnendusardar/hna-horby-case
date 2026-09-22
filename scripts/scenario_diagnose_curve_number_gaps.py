"""Diagnose the 29.4% of the AOI with no Curve Number: where the gap is
(map), whether each reason clusters or scatters (connected-component
labelling), and — for the one genuine data gap found — what NMD land-cover
classes it actually falls on.

Reads scripts/scenario_compute_curve_number.py's outputs, does not
recompute any of the CN/soil-group logic itself:
- web/data/scenario_curve_number_reason_grid.txt (one char per cell:
  K=ok, S=sealed, W=water, U=unmapped NMD class,
  N=no_soil_group/no polygon match, V=no_soil_group/matched a "Vatten"
  soil polygon, F=fallback-filled — see that script for the full legend).
- web/data/scenario_landcover.tif (for the NMD class breakdown of gap
  cells).

Output image is a plain stdlib-written PNG (struct + zlib, both stdlib —
no Pillow/matplotlib available on this machine, see ASSUMPTIONS.md), 4x
nearest-neighbour upscaled so isolated single-cell gaps are actually
visible at ~10 m native resolution.

Usage:
    python scripts/scenario_diagnose_curve_number_gaps.py
"""
import json
import pathlib
import struct
import zlib
from collections import deque

root = pathlib.Path(__file__).resolve().parents[1]
REASON_GRID_TXT = root / "web/data/scenario_curve_number_reason_grid.txt"
LANDCOVER_TIF = root / "web/data/scenario_landcover.tif"
LANDCOVER_CLASSES_JSON = root / "web/data/scenario_landcover_classes.json"
OUTPUT_PNG = root / "docs/curve_number_gaps.png"
OUTPUT_STATS = root / "docs/curve_number_gaps_stats.json"

SCALE = 4  # nearest-neighbour upscale factor for visibility

# Colorblind-safe (Okabe-Ito) palette. K (resolved) kept pale/unobtrusive;
# every gap reason gets a distinct, legible color.
COLORS = {
    "K": (245, 245, 245),  # resolved — pale background
    "S": (153, 153, 153),  # sealed — deliberate exclusion
    "W": (0, 114, 178),    # water — deliberate exclusion
    "N": (230, 159, 0),    # no soil polygon at all (coverage gap)
    "V": (213, 94, 0),     # matched a "Vatten" soil polygon (dataset disagreement) — the real gap
    "U": (204, 121, 167),  # unmapped NMD class
    "F": (213, 94, 0),     # fallback-filled — same color as V/N, it's the same cells post-fix
}


def read_reason_grid():
    lines = REASON_GRID_TXT.read_text(encoding="ascii").splitlines()
    return [list(line) for line in lines]


# --- Minimal stdlib TIFF reader (see scripts/scenario_compute_curve_number.py
# for the same reader; duplicated here rather than imported, matching this
# repo's self-contained-script convention). ---
def read_landcover_tiff(path):
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


def write_png(path, width, height, pixel_fn):
    """pixel_fn(x, y) -> (r, g, b). Writes an 8-bit RGB PNG, stdlib only."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type: None
        for x in range(width):
            r, g, b = pixel_fn(x, y)
            raw += bytes((r, g, b))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    path.write_bytes(png)


def connected_components(grid, target_chars, height, width):
    """4-connectivity flood fill over cells whose char is in target_chars.
    Returns a list of component sizes, largest first."""
    visited = [[False] * width for _ in range(height)]
    sizes = []
    for r0 in range(height):
        for c0 in range(width):
            if visited[r0][c0] or grid[r0][c0] not in target_chars:
                continue
            size = 0
            q = deque([(r0, c0)])
            visited[r0][c0] = True
            while q:
                r, c = q.popleft()
                size += 1
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < height and 0 <= nc < width and not visited[nr][nc] and grid[nr][nc] in target_chars:
                        visited[nr][nc] = True
                        q.append((nr, nc))
            sizes.append(size)
    sizes.sort(reverse=True)
    return sizes


def main():
    reason_grid = read_reason_grid()
    height = len(reason_grid)
    width = len(reason_grid[0])

    counts = {}
    for row in reason_grid:
        for ch in row:
            counts[ch] = counts.get(ch, 0) + 1
    total = height * width

    print(f"Reason-grid cell counts ({width}x{height}={total} total): {counts}")

    # Clustering: connected components per gap reason (post-fallback grid
    # still marks the ORIGINAL reason, e.g. 'V', not 'F' twice — see
    # scenario_compute_curve_number.py; F cells are the same cells as
    # N/V, just also fallback-filled, so cluster on the original reason).
    cluster_stats = {}
    for code in ("S", "W", "N", "V", "U"):
        if counts.get(code, 0) == 0:
            continue
        sizes = connected_components(reason_grid, {code}, height, width)
        top5 = sizes[:5]
        singleton_pct = round(100 * sum(1 for s in sizes if s == 1) / len(sizes), 1) if sizes else 0
        cluster_stats[code] = {
            "total_cells": sum(sizes),
            "num_components": len(sizes),
            "largest_component": sizes[0] if sizes else 0,
            "top5_components": top5,
            "pct_of_cells_in_largest_component": round(100 * sizes[0] / sum(sizes), 1) if sizes else 0,
            "pct_of_components_that_are_singleton_cells": singleton_pct,
        }
        pattern = "CLUSTERED" if cluster_stats[code]["pct_of_cells_in_largest_component"] > 50 else \
                  ("SCATTERED" if singleton_pct > 50 else "MIXED")
        print(f"  {code}: {sum(sizes)} cells in {len(sizes)} component(s), largest={sizes[0]}, "
              f"{cluster_stats[code]['pct_of_cells_in_largest_component']}% of cells in the largest one, "
              f"{singleton_pct}% of components are lone single cells -> {pattern}")
        cluster_stats[code]["pattern"] = pattern

    # NMD class breakdown for the genuine gap reasons (N, V) — what land
    # cover is actually under these gap cells.
    gap_class_breakdown = {}
    if counts.get("N", 0) or counts.get("V", 0):
        lc = read_landcover_tiff(LANDCOVER_TIF)
        legend = {c["value"]: c["name"] for c in json.loads(LANDCOVER_CLASSES_JSON.read_text(encoding="utf-8"))["classes"]}
        for code in ("N", "V"):
            if counts.get(code, 0) == 0:
                continue
            class_counts = {}
            for r in range(height):
                for c in range(width):
                    if reason_grid[r][c] == code:
                        v = lc["grid"][r][c]
                        class_counts[v] = class_counts.get(v, 0) + 1
            gap_class_breakdown[code] = {
                f"{v} ({legend.get(v, '?')})": n for v, n in sorted(class_counts.items(), key=lambda kv: -kv[1])
            }
            print(f"  NMD classes under '{code}' gap cells: {gap_class_breakdown[code]}")

    print(f"== Rendering map ({width*SCALE}x{height*SCALE} px) ==")

    def pixel_fn(x, y):
        row, col = y // SCALE, x // SCALE
        return COLORS.get(reason_grid[row][col], (255, 0, 255))  # magenta = unexpected code, should never show

    OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    write_png(OUTPUT_PNG, width * SCALE, height * SCALE, pixel_fn)

    stats = {
        "grid_size": {"width": width, "height": height},
        "cell_counts_by_reason_code": counts,
        "legend": {
            "K": "resolved (CN assigned)", "S": "sealed (deliberate exclusion)",
            "W": "water (deliberate exclusion)", "N": "no soil polygon match at all (coverage gap)",
            "V": "matched a 'Vatten' soil polygon under pervious NMD land (dataset disagreement)",
            "U": "NMD class not in NMD_TO_TR55 mapping",
        },
        "clustering": cluster_stats,
        "nmd_class_breakdown_of_gap_cells": gap_class_breakdown,
        "map_image": "docs/curve_number_gaps.png",
        "map_scale": f"{SCALE}x nearest-neighbour upscale from native ~10 m cells",
    }
    OUTPUT_STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PNG}")
    print(f"Wrote {OUTPUT_STATS}")


if __name__ == "__main__":
    main()
