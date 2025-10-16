# app.py
# ------------------------------------------------------------
# Interactive 3D Mini-World (Streamlit + Plotly)
# - Procedural terrain (no external data)
# - Kigali-like parcel boundary, road, simple buildings
# - Optional hügelkultur mounds with aging/settling
# - Rainfall + SCS-CN runoff quick calc
# ------------------------------------------------------------
import math
from typing import Tuple

import numpy as np
import plotly.graph_objects as go
import streamlit as st


# ---------- Helpers ----------
def make_grid(n: int, size_m: float) -> Tuple[np.ndarray, np.ndarray]:
    """Return X, Y coordinate grids from 0..size_m."""
    xs = np.linspace(0, size_m, n)
    ys = np.linspace(0, size_m, n)
    X, Y = np.meshgrid(xs, ys)
    return X, Y


def smooth_rand(n: int, k: float, seed: int) -> np.ndarray:
    """
    Fast 'soft' noise without extra deps: sum of a few sin/cos bases
    plus seeded randomness, then gentle blur via rolling mean.
    k controls hilliness scale (bigger = broader hills).
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 2 * np.pi, n)
    y = np.linspace(0, 2 * np.pi, n)
    X, Y = np.meshgrid(x, y)

    # A few smooth basis fields
    Z = (
        0.45 * np.sin(X / k + 0.7) * np.cos(Y / k + 1.3)
        + 0.35 * np.cos(1.7 * X / k) * np.sin(1.2 * Y / k)
        + 0.20 * np.sin(0.7 * X / k + 0.9) * np.sin(0.6 * Y / k + 0.4)
    )

    # Add a gentle random field and roll-mean blur
    R = rng.normal(0, 0.2, size=(n, n))
    R = (np.roll(R, 1, 0) + R + np.roll(R, -1, 0) + np.roll(R, 1, 1) + np.roll(R, -1, 1)) / 5.0
    Z = Z + 0.25 * R
    # Normalize 0..1
    Z = (Z - Z.min()) / (Z.max() - Z.min() + 1e-9)
    return Z


def add_gaussian_bump(Z: np.ndarray, cx: float, cy: float, amp: float, sigma: float) -> None:
    """Add a smooth hill (+) or trench (−) at center (cx, cy) in grid coords."""
    n = Z.shape[0]
    xs = np.linspace(0, 1, n)
    ys = np.linspace(0, 1, n)
    X, Y = np.meshgrid(xs, ys)
    Z += amp * np.exp(-(((X - cx) ** 2 + (Y - cy) ** 2) / (2 * sigma**2)))


def carve_polyline_trench(Z: np.ndarray, pts01: list, depth: float, width: float) -> None:
    """Lower elevation along a polyline (simple road/valley)."""
    n = Z.shape[0]
    xs = np.linspace(0, 1, n)
    ys = np.linspace(0, 1, n)
    X, Y = np.meshgrid(xs, ys)

    for (x0, y0), (x1, y1) in zip(pts01[:-1], pts01[1:]):
        # distance from each cell to the segment
        vx, vy = x1 - x0, y1 - y0
        wx, wy = X - x0, Y - y0
        c1 = vx * wx + vy * wy
        c2 = vx * vx + vy * vy + 1e-12
        t = np.clip(c1 / c2, 0, 1)
        projx = x0 + t * vx
        projy = y0 + t * vy
        d = np.sqrt((X - projx) ** 2 + (Y - projy) ** 2)
        Z -= depth * np.exp(-((d**2) / (2 * width**2)))


def polygon_boundary_xy(size_m: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Rough polygon inspired by the screenshot (world coordinates in meters).
    Returns closed loop.
    """
    # Coordinates in 0..1 then scale to meters
    poly01 = np.array([
        [0.15, 0.15],
        [0.18, 0.80],
        [0.55, 0.85],
        [0.88, 0.80],
        [0.90, 0.35],
        [0.80, 0.20],
        [0.65, 0.25],
        [0.50, 0.18],
        [0.35, 0.22],
        [0.20, 0.18],
        [0.15, 0.15],
    ])
    return poly01[:, 0] * size_m, poly01[:, 1] * size_m


def add_building_blocks(fig, size_m: float, ground_h: float):
    """Simple extruded 'buildings' as short prisms near the south edge."""
    bx = np.array([0.30, 0.33, 0.33, 0.30, 0.30]) * size_m
    by = np.array([0.18, 0.18, 0.22, 0.22, 0.18]) * size_m
    cx = np.array([0.55, 0.58, 0.58, 0.55, 0.55]) * size_m
    cy = np.array([0.17, 0.17, 0.21, 0.21, 0.17]) * size_m

    for xs, ys in [(bx, by), (cx, cy)]:
        fig.add_trace(
            go.Scatter3d(
                x=xs,
                y=ys,
                z=[ground_h, ground_h, ground_h + 3, ground_h + 3, ground_h],
                mode="lines",
                line=dict(width=6),
                name="Building",
                hoverinfo="skip",
                showlegend=False,
            )
        )


def scs_runoff_depth(P_mm: float, CN: float) -> float:
    """
    SCS-CN runoff (mm). P rainfall, CN 30..100.
    Q = (P - Ia)^2 / (P - Ia + S), where S = 25400/CN - 254 (mm), Ia ~ 0.2S.
    """
    S = 25400.0 / np.clip(CN, 1, 100) - 254.0
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    return ((P_mm - Ia) ** 2) / (P_mm - Ia + S)


# ---------- UI ----------
st.set_page_config(page_title="Kigali Mini-World (3D)", layout="wide")
st.title("🌍 Interactive 3D Mini-World (Kigali-inspired)")

left, right = st.columns([0.62, 0.38], gap="large")

with right:
    st.subheader("World & Environment")
    seed = st.slider("Random seed", 0, 9999, 2025, 1)
    size_m = st.slider("World size (m)", 150, 500, 320, 10)
    n = st.slider("Grid resolution", 60, 160, 120, 10)
    hilliness = st.slider("Hilliness scale", 6, 30, 16)
    road_depth = st.slider("Road/valley depth (m)", 0.0, 3.0, 1.2, 0.1)
    show_boundary = st.checkbox("Show parcel boundary", True)
    show_buildings = st.checkbox("Show small buildings", True)

    st.subheader("Hügelkultur (optional)")
    use_hugel = st.checkbox("Add hügelkultur mounds", False)
    mound_cover = st.slider("Mound coverage (%)", 0, 50, 20, 1)
    mound_height = st.slider("Initial mound height (m)", 0.0, 1.5, 0.6, 0.1)
    years = st.slider("Years (settling/decomposition)", 0, 12, 3, 1)
    # Simple aging curve: height decays to ~40% by year 10
    aging_factor = float(np.exp(-years / 10.0) * 0.6 + 0.4)

    st.subheader("Rain & Runoff (SCS-CN)")
    P = st.slider("Storm rainfall (mm)", 10, 1400, 120, 10)
    CN = st.slider("Curve Number (higher = more runoff)", 55, 95, 80)

# ---------- Terrain ----------
X, Y = make_grid(n, size_m)
Z0 = smooth_rand(n, k=hilliness, seed=seed)  # 0..1
# Scale to meters (relief ~ 10 m)
Z = 2 + 8 * Z0

# Add a few gentle hills/valleys so it feels 'Rwandan hills'
add_gaussian_bump(Z, 0.25, 0.65, +2.3, 0.12)
add_gaussian_bump(Z, 0.75, 0.55, +1.8, 0.16)
add_gaussian_bump(Z, 0.50, 0.30, -1.4, 0.18)

# Carve a curvy dirt road / drainage swale roughly north-south
road = [(0.18, 0.80), (0.35, 0.60), (0.48, 0.48), (0.52, 0.38), (0.50, 0.22)]
if road_depth > 0:
    carve_polyline_trench(Z, road, depth=road_depth, width=0.02)

# Optional hügelkultur mounds dotted inside boundary area
if use_hugel and mound_height > 0 and mound_cover > 0:
    rng = np.random.default_rng(seed + 99)
    num = int(12 + mound_cover * 0.6)
    for _ in range(num):
        cx, cy = rng.uniform(0.22, 0.85), rng.uniform(0.22, 0.78)
        h = mound_height * (0.6 + 0.4 * rng.random()) * aging_factor
        s = rng.uniform(0.012, 0.028)
        add_gaussian_bump(Z, cx, cy, +h, s)

# ---------- 3D Figure ----------
fig = go.Figure()

fig.add_trace(
    go.Surface(
        x=X,
        y=Y,
        z=Z,
        colorscale="Earth",
        showscale=False,
        lighting=dict(ambient=0.4, diffuse=0.6, fresnel=0.1, specular=0.2, roughness=0.8),
        lightposition=dict(x=3000, y=2000, z=8000),
        hovertemplate="x:%{x:.1f} m<br>y:%{y:.1f} m<br>z:%{z:.2f} m<extra></extra>",
        name="Terrain",
        opacity=0.98,
    )
)

# Boundary polyline
bx, by = polygon_boundary_xy(size_m)
if show_boundary:
    fig.add_trace(
        go.Scatter3d(
            x=bx, y=by, z=np.full_like(bx, Z.mean() + 0.2),
            mode="lines",
            line=dict(width=6),
            name="Boundary",
            hoverinfo="skip",
            showlegend=False,
        )
    )

# Road line on top for visibility
rx = np.array([p[0] for p in road]) * size_m
ry = np.array([p[1] for p in road]) * size_m
rz = np.interp(rx, X[0], Z[int(0.5 * n)])  # rough overlay height
fig.add_trace(
    go.Scatter3d(
        x=rx, y=ry, z=rz + 0.15,
        mode="lines",
        line=dict(width=8),
        name="Road / Swale",
        hoverinfo="skip",
        showlegend=False,
    )
)

# Simple 'buildings'
if show_buildings:
    add_building_blocks(fig, size_m=size_m, ground_h=float(np.percentile(Z, 30)))

fig.update_scenes(
    xaxis_title="East (m)", yaxis_title="North (m)", zaxis_title="Elevation (m)",
    aspectmode="data",
)

fig.update_layout(
    margin=dict(l=0, r=0, t=0, b=0),
    scene_camera=dict(
        eye=dict(x=1.8, y=1.6, z=1.2),
        up=dict(x=0, y=0, z=1),
    ),
)

with left:
    st.plotly_chart(fig, use_container_width=True)

# ---------- Metrics ----------
# Quick runoff calc and volumes
Q_mm = scs_runoff_depth(P, CN)
A_m2 = size_m * size_m
runoff_m3 = Q_mm / 1000.0 * A_m2
rain_m3 = P / 1000.0 * A_m2
retained_m3 = max(rain_m3 - runoff_m3, 0.0)

m1, m2, m3 = st.columns(3)
m1.metric("Rain volume", f"{rain_m3:,.0f} m³", f"{P} mm")
m2.metric("Runoff (SCS-CN)", f"{runoff_m3:,.0f} m³", f"CN {CN}")
m3.metric("Retained/Infiltrated", f"{retained_m3:,.0f} m³",
          ("Hügel on" if use_hugel else "Hügel off"))

st.caption(
    "Tip: Reduce **CN** (more permeable soil/cover) and/or raise mound coverage to see retention increase. "
    "Use the **Years** slider to visualize how aging/settling lowers mound height over time."
)

