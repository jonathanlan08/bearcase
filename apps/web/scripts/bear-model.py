"""Sculpt the BearCase bear (public/models/bear.glb): a low-poly sitting bear from fused signed-distance primitives,
meshed by marching cubes and simplified to ~2,600 triangles. Run with: uv venv .bear && uv pip install --python .bear/bin/python numpy scikit-image trimesh fast-simplification && .bear/bin/python scripts/bear-model.py
The same shapes translate to a Blender metaball rig if the mark is ever re-sculpted by hand.
Units: metres-ish; bear is ~1.9 tall, sits at origin with feet on y=0. +Z faces the camera."""
import numpy as np, trimesh
from skimage import measure
import fast_simplification as fs

def sphere(p, c, r): return np.linalg.norm(p - c, axis=-1) - r
def ellipsoid(p, c, rad):
    q = (p - c) / rad
    k0 = np.linalg.norm(q, axis=-1); k1 = np.linalg.norm(q / rad, axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)
def capsule(p, a, b, r):
    pa = p - a; ba = b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
    return np.linalg.norm(pa - np.outer(h, ba), axis=-1) - r
def smin(a, b, k=0.12):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)

def bear(p):
    d = ellipsoid(p, np.array([0, 0.80, 0.0]), np.array([0.62, 0.78, 0.55]))          # body, upright
    d = smin(d, ellipsoid(p, np.array([0, 0.95, 0.30]), np.array([0.42, 0.45, 0.30])), 0.2)  # belly
    d = smin(d, sphere(p, np.array([0, 1.58, 0.16]), 0.38), 0.10)                       # head
    d = smin(d, ellipsoid(p, np.array([0, 1.50, 0.50]), np.array([0.20, 0.16, 0.18])), 0.06)  # snout
    for sx in (-1, 1):
        d = smin(d, sphere(p, np.array([sx * 0.27, 1.90, 0.05]), 0.13), 0.04)           # ears
        d = smin(d, capsule(p, np.array([sx * 0.50, 1.25, 0.10]), np.array([sx * 0.62, 0.62, 0.42]), 0.14), 0.08)  # arms
        d = smin(d, capsule(p, np.array([sx * 0.42, 0.40, 0.15]), np.array([sx * 0.46, 0.14, 0.62]), 0.19), 0.10)  # legs out front
        d = smin(d, ellipsoid(p, np.array([sx * 0.47, 0.13, 0.70]), np.array([0.20, 0.13, 0.22])), 0.05)          # feet
    d = np.maximum(d, -p[..., 1])  # flat underside at y=0
    return d

n = 120
xs = np.linspace(-1.1, 1.1, n); ys = np.linspace(-0.05, 2.2, n); zs = np.linspace(-1.0, 1.2, n)
X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
P = np.stack([X, Y, Z], -1).reshape(-1, 3)
D = bear(P).reshape(n, n, n)
verts, faces, _, _ = measure.marching_cubes(D, level=0.0, spacing=(xs[1]-xs[0], ys[1]-ys[0], zs[1]-zs[0]))
verts += np.array([xs[0], ys[0], zs[0]])
print("raw", len(verts), len(faces))
v2, f2 = fs.simplify(verts.astype(np.float32), faces.astype(np.int64), target_count=2600, agg=7)
m = trimesh.Trimesh(v2, f2, process=True)
m.fix_normals()
m.visual = trimesh.visual.ColorVisuals(m, vertex_colors=np.tile([38, 43, 50, 255], (len(m.vertices), 1)))
print("final", len(m.vertices), len(m.faces), "bounds", m.bounds.round(2).tolist(), "watertight", m.is_watertight)
m.export(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "public" / "models" / "bear.glb"))
import os; print("bytes", os.path.getsize(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "public" / "models" / "bear.glb")))
