"""Convert a LISFLOOD-FP water-depth ASCII grid (.wd) plus its DEM into a
triangulated water-surface mesh, per the brief's web-asset spec (§5):
"3D water surface (maximum): .glb, Draco-compressed. Triangulate wet
cells from maximum water surface elevation, decimate, colour vertices by
depth, alpha about 0.7."

This script builds a valid, uncompressed glTF 2.0 binary (.glb) — pure
stdlib (json + struct), no external 3D library. Decimation here means
"wet cells only, one quad per cell, no attempt at mesh simplification
beyond that" — a real but coarse decimation, not the polygon-reduction
algorithm a dedicated tool would run; see ASSUMPTIONS.md "Where the pilot
chain breaks" for why Draco compression itself is NOT applied here.

Wet-surface elevation per cell = DEM (ground) + water depth (so the mesh
sits at the actual water surface, not at the ground). Only cells with
depth >= 5 cm are meshed (matches the depth-PNG transparency threshold).
Vertex colour: same pale-blue -> dark-blue ramp as
scripts/model_convert_depth_to_png.py, alpha ~0.7 (179/255) throughout,
per the brief's own value.

Usage:
    python scripts/model_convert_depth_to_mesh.py <wd_file> <dem_file> <output_glb>
"""
import base64
import json
import struct
import sys

TRANSPARENT_BELOW_M = 0.05
DEPTH_CLAMP_M = 2.0
ALPHA = 179  # ~0.7 * 255, per brief

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


def depth_color(depth):
    frac = min(depth, DEPTH_CLAMP_M) / DEPTH_CLAMP_M
    r = round(COLOR_SHALLOW[0] + frac * (COLOR_DEEP[0] - COLOR_SHALLOW[0])) / 255
    g = round(COLOR_SHALLOW[1] + frac * (COLOR_DEEP[1] - COLOR_SHALLOW[1])) / 255
    b = round(COLOR_SHALLOW[2] + frac * (COLOR_DEEP[2] - COLOR_SHALLOW[2])) / 255
    return (r, g, b, ALPHA / 255)


def build_mesh(wd, dem):
    """One quad (2 triangles) per wet cell, local XY in metres from the
    grid origin (not georeferenced — glTF has no native CRS; a real web
    front-end would re-anchor this the same way the brief's terrain
    already is, via Cesium's own tiling)."""
    positions, colors, indices = [], [], []
    ncols, nrows, cs = wd["ncols"], wd["nrows"], wd["cellsize"]
    wet = 0
    for row in range(nrows):
        for col in range(ncols):
            depth = wd["grid"][row][col]
            if depth == wd["nodata"] or depth < TRANSPARENT_BELOW_M:
                continue
            ground = dem["grid"][row][col]
            if ground == dem["nodata"]:
                continue
            wet += 1
            z = ground + depth
            x0, x1 = col * cs, (col + 1) * cs
            y0, y1 = row * cs, (row + 1) * cs  # +row = further south; fine for a standalone mesh
            base = len(positions)
            for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                positions.append((x, y, z))
                colors.append(depth_color(depth))
            indices += [base, base + 1, base + 2, base, base + 2, base + 3]
    return positions, colors, indices, wet


def write_glb(path, positions, colors, indices):
    pos_bytes = b"".join(struct.pack("<fff", *p) for p in positions)
    color_bytes = b"".join(struct.pack("<ffff", *c) for c in colors)
    idx_bytes = b"".join(struct.pack("<I", i) for i in indices)

    def pad4(b):
        return b + b"\x00" * ((4 - len(b) % 4) % 4)

    pos_bytes_p, color_bytes_p, idx_bytes_p = pad4(pos_bytes), pad4(color_bytes), pad4(idx_bytes)
    pos_offset = 0
    color_offset = len(pos_bytes_p)
    idx_offset = color_offset + len(color_bytes_p)
    bin_chunk = pos_bytes_p + color_bytes_p + idx_bytes_p

    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]

    gltf = {
        "asset": {"version": "2.0", "generator": "scripts/model_convert_depth_to_mesh.py (Aegir pilot pipeline, uncompressed — see ASSUMPTIONS.md)"},
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "COLOR_0": 1},
            "indices": 2,
            "mode": 4,
        }]}],
        "buffers": [{"byteLength": len(bin_chunk)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_offset, "byteLength": len(pos_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": color_offset, "byteLength": len(color_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": idx_offset, "byteLength": len(idx_bytes), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3",
             "min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]},
            {"bufferView": 1, "componentType": 5126, "count": len(colors), "type": "VEC4"},
            {"bufferView": 2, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}, "alphaMode": "BLEND"}],
    }
    json_bytes = json.dumps(gltf).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)  # glTF pads JSON chunk with spaces

    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(json_bytes) + 8 + len(bin_chunk))
    json_chunk_header = struct.pack("<II", len(json_bytes), 0x4E4F534A)
    bin_chunk_header = struct.pack("<II", len(bin_chunk), 0x004E4942)

    with open(path, "wb") as f:
        f.write(header + json_chunk_header + json_bytes + bin_chunk_header + bin_chunk)


def main():
    if len(sys.argv) != 4:
        sys.exit("Usage: python scripts/model_convert_depth_to_mesh.py <wd_file> <dem_file> <output_glb>")
    wd_path, dem_path, glb_path = sys.argv[1], sys.argv[2], sys.argv[3]
    wd = read_ascii_grid(wd_path)
    dem = read_ascii_grid(dem_path)
    positions, colors, indices, wet = build_mesh(wd, dem)
    if wet == 0:
        print("No wet cells >= 5 cm depth — nothing to mesh.")
        return
    write_glb(glb_path, positions, colors, indices)
    print(f"Wrote {glb_path}: {wet} wet cells, {len(positions)} vertices, {len(indices)//3} triangles "
          f"(UNCOMPRESSED — no Draco, see ASSUMPTIONS.md)")


if __name__ == "__main__":
    main()
