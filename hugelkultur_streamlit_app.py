# app.py — 3D Interactive Mini World (HOPE Rwanda)
# - Realistic synthetic terrain (fractal noise + southward slope)
# - Land cover: forests, ground, buildings/roads that follow terrain logic
# - Hydrology: SCS-CN runoff + simple D8 routing (toy model)
# - 3D interactive Plotly surface (drag/zoom) + water overlay
# - Fixes: "near_road" neighborhood growth; settlement_score normalized as NumPy array

import math
import time
import numpy as np
import streamlit as st
import plotly.graph_objects as go

# -------------------- Page setup --------------------
st.set_page_config(page_title="3D Mini World – HOPE Rwanda", layout="wide")
st.title("3D Mini World – HOPE Rwanda (Stormwater)")

with st.expander("About this simulator"):
    st.markdown(
        """
A schematic hillslope inspired by Kigali’s terrain. It generates terrain, places roads/buildings and forests
based on slope/elevation, and simulates storm **runoff vs infiltration** per cell (SCS-CN) with a simple **downhill routing**.
Use it for **relative comparisons** (e.g., more forest, fewer roads) — not for engineering design.
        """
    )

# -------------------- Sidebar controls --------------------
st.sidebar.header("World & realism")
W = st.sidebar.slider("Width (cells)", 80, 220, 140, 10)
H = st.sidebar.slider("Height (cells)", 60, 180, 110, 10)
seed = st.sidebar.number_input("Random seed", value=7, step=1)

relief = st.sidebar.slider("Relief (vertical range)", 0.4, 1.8, 1.0, 0.05)
roughness = st.sidebar.slider("Terrain roughness (octaves)", 1, 7, 4, 1)
slope_bias = st.sidebar.slider("Southward slope bias", 0.10, 1.00, 0.55, 0.05)
valley_focus = st.sidebar.slider("Valley emphasis", 0.00, 1.00, 0.35, 0.05)

st.sidebar.header("Land cover")
forest_share = st.sidebar.slider("Target forest share (%)", 10, 80, 40, 5) / 100.0
build_share  = st.sidebar.slider("Target buildings/roads share (%)", 5, 35, 12, 1) / 100.0

st.sidebar.header("Soil moisture (affects CN)")
soil_state = st.sidebar.select_slider("Antecedent moisture", ["Dry", "Average", "Wet"], value="Average")

st.sidebar.header("Road network")
curvy = st.sidebar.slider("Road curviness", 0.0, 1.0, 0.55, 0.05)
spurs = st.sidebar.slider("Side roads (count)", 0, 6, 3, 1)

st.sidebar.header("Storm & animation")
storm_mm = st.sidebar.slider("Total storm depth (mm)", 0, 1400, 180, 10)
steps = st.sidebar.slider("Animation steps", 10, 180, 60, 5)
frame_delay = st.sidebar.slider("Frame delay (ms)", 0, 120, 25, 5) / 1000.0

rng = np.random.default_rng(int(seed))

# -------------------- Terrain synthesis --------------------
def fbm_noise(h, w, octaves=4, persistence=0.5, lacunarity=2.0, rng=None):
    """Fractal Brownian Motion using tiled blurred noise (fast & dependency-free)."""
    base = np.zeros((h, w), dtype=float)
    for o in range(octaves):
        freq = lacunarity ** o
        sh = max(2, int(h / freq))
        sw = max(2, int(w / freq))
        n = rng.normal(0, 1, size=(sh, sw))
        up = np.kron(n, np.ones((math.ceil(h/sh), math.ceil(w/sw))))
        up = up[:h, :w]
        base += (persistence ** o) * up
    base = (base - base.min()) / (base.max() - base.min() + 1e-9)
    return base

@st.cache_data(show_spinner=False)
def build_terrain(h, w, octaves, slope_bias, valley_focus, relief, seed):
    rng = np.random.default_rng(int(seed))
    fbm = fbm_noise(h, w, octaves=octaves, persistence=0.55, lacunarity=2.0, rng=rng)
    south = np.linspace(1.0, 0.0, h).reshape(-1, 1)               # southward tilt (top high → bottom low)
    x = np.linspace(0, 1, w)[None, :]
    ridges = 0.15 * np.cos(4 * np.pi * x)                         # gentle E-W undulations
    base = (slope_bias * south + (1.0 - slope_bias) * fbm + ridges)
    val = fbm_noise(h, w, octaves=max(1, octaves-1), persistence=0.65, rng=rng)
    elev = base - valley_focus * val
    elev = (elev - elev.min()) / (elev.max() - elev.min() + 1e-9)
    elev = elev ** 1.1                                             # skew for deeper basins
    elev = elev * relief
    return elev

elev = build_terrain(H, W, roughness, slope_bias, valley_focus, relief, seed)

# -------------------- Land cover placement --------------------
def place_roads(elev, curviness=0.6, n_spurs=3, rng=None):
    H, W = elev.shape
    road = np.zeros((H, W), dtype=bool)
    # main curvy polyline at ~1/3 from top
    r = int(H * (0.30 + 0.1 * rng.random()))
    c = 0
    drift = 0
    while c < W:
        road[max(0, r-1):min(H, r+2), max(0, c-2):min(W, c+3)] = True
        drift += rng.normal(0, curviness*0.8)
        r = int(np.clip(r + np.tanh(drift), 2, H-3))
        c += 2
    # side spurs generally downhill
    for _ in range(n_spurs):
        c0 = rng.integers(low=int(W*0.1), high=int(W*0.9))
        rows_with_road = np.where(road[:, c0])[0]
        if rows_with_road.size == 0:
            continue
        r0 = int(rows_with_road[0])
        r = r0; c = c0
        length = rng.integers(low=int(H*0.15), high=int(H*0.35))
        for _ in range(length):
            road[max(0, r-1):min(H, r+2), max(0, c-1):min(W, c+2)] = True
            win = elev[max(0,r-1):min(H,r+2), max(0,c-1):min(W,c+2)]
            rr, cc = np.unravel_index(np.argmin(win), win.shape)
            r = int(np.clip((r-1)+rr, 1, H-2))
            c = int(np.clip((c-1)+cc, 1, W-2))
    return road

rng_local = np.random.default_rng(int(seed))
road_mask = place_roads(elev, curvy, spurs, rng_local)

# Buildings cluster near roads & gentle slopes
slope_mag = np.hypot(*np.gradient(elev))
gentle = (slope_mag < np.percentile(slope_mag, 60))

# --- FIXED: grow road neighborhood safely (no logical_and.reduce with scalars) ---
near = np.zeros_like(road_mask, dtype=bool)
near[:-1, :] |= road_mask[1:, :]
near[1:,  :] |= road_mask[:-1, :]
near[:, :-1] |= road_mask[:, 1:]
near[:, 1:]  |= road_mask[:, :-1]
near_road = road_mask | near

settlement_score = gentle.astype(float) * 0.6 + near_road.astype(float) * 1.2
settlement_score += 0.3 * fbm_noise(H, W, octaves=2, persistence=0.7, rng=rng_local)
# --- FIXED: ensure NumPy array before normalization ---
settlement_score = np.asarray(settlement_score, dtype=float)
settlement_score = (settlement_score - settlement_score.min()) / (settlement_score.ptp() + 1e-9)

target_build = int(W*H*build_share)
buildings = np.zeros((H, W), dtype=bool)
idx = np.dstack(np.unravel_index(np.argsort(settlement_score.ravel())[::-1], (H, W)))[0]
for r, c in idx:
    if target_build <= 0:
        break
    rr = slice(max(0, r-1), min(H, r+2))
    cc = slice(max(0, c-1), min(W, c+2))
    add = (~buildings[rr, cc]) & (settlement_score[rr, cc] > 0.55)
    if add.any():
        buildings[rr, cc] = True
        target_build -= int(add.sum())

# Forest prefers mid/high elevation & non-steep, away from roads/buildings
forest_score = (elev - elev.min()) / (elev.ptp() + 1e-9)
forest_score *= (1.0 - np.clip(slope_mag / (slope_mag.max() + 1e-9), 0, 1)) ** 0.4
forest_score *= (1.0 - buildings.astype(float))
forest_score *= (1.0 - road_mask.astype(float)*0.9)
forest_score += 0.25 * fbm_noise(H, W, octaves=2, persistence=0.6, rng=rng_local)
forest_score = (forest_score - forest_score.min()) / (forest_score.ptp() + 1e-9)

target_forest = int(W*H*forest_share)
forest = np.zeros((H, W), dtype=bool)
idx2 = np.dstack(np.unravel_index(np.argsort(forest_score.ravel())[::-1], (H, W)))[0]
count = 0
for r, c in idx2:
    if count >= target_forest:
        break
    if not buildings[r, c] and not road_mask[r, c]:
        forest[r, c] = True
        count += 1

# Ground = remainder
ground = ~(forest | buildings | road_mask)

# Land cover map (0=forest, 1=ground, 2=build/road)
world = np.full((H, W), 1, dtype=np.int8)
world[forest] = 0
world[buildings | road_mask] = 2

# -------------------- SCS-CN runoff --------------------
CN_base = {  # AMC II baseline
    0: 60,  # forest
    1: 78,  # mixed ground
    2: 95,  # impervious (roads/roofs)
}
moisture_adj = {"Dry": -5, "Average": 0, "Wet": +5}

CN = np.zeros_like(world, dtype=float)
for k, v in CN_base.items():
    CN[world == k] = v + moisture_adj[soil_state]
CN = np.clip(CN, 30, 98)
S = 25400.0 / CN - 254.0   # mm
Ia = 0.2 * S

def scs_runoff(P, S, Ia):
    ex = P - Ia
    return np.where(ex > 0, (ex**2) / (ex + S), 0.0)

# -------------------- Simple D8 routing --------------------
def route_d8(Q_mm, elev, iters=1):
    H, W = Q_mm.shape
    acc = Q_mm.copy()
    for _ in range(iters):
        moved = np.zeros_like(acc)
        for r in range(H):
            for c in range(W):
                z0 = elev[r, c]
                rmin, cmin, zmin = r, c, z0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr = r + dr; cc = c + dc
                        if 0 <= rr < H and 0 <= cc < W:
                            z = elev[rr, cc]
                            if z < zmin:
                                zmin = z; rmin = rr; cmin = cc
                if (rmin, cmin) != (r, c):
                    moved[rmin, cmin] += acc[r, c] * 0.88  # 88% flows
                    acc[r, c] *= 0.12                      # 12% ponds/roughness
        acc += moved
    return acc

# -------------------- 3D figure builder --------------------
def cover_colorscale():
    # Discrete mapping: 0=forest (green), 1=ground (tan), 2=road/build (dark gray)
    return [
        [0.00, "rgb(32,128,32)"],   [0.33, "rgb(32,128,32)"],   # forest
        [0.33, "rgb(194,176,138)"], [0.66, "rgb(194,176,138)"], # ground
        [0.66, "rgb(45,45,48)"],    [1.00, "rgb(45,45,48)"],    # roads/buildings
    ]

def make_3d_figure(elev, world, pond_mm=None, title=""):
    H, W = elev.shape
    z_base = elev.copy()
    cover_idx = world.astype(float) / 2.0  # 0, 0.5, 1.0
    x = np.arange(W); y = np.arange(H)

    fig = go.Figure()

    # Base surface (terrain + cover colors)
    fig.add_trace(go.Surface(
        x=x, y=y, z=z_base,
        surfacecolor=cover_idx,
        colorscale=cover_colorscale(),
        cmin=0.0, cmax=1.0,
        showscale=False,
        lighting=dict(ambient=0.4, diffuse=0.7, specular=0.2, roughness=0.8),
        lightposition=dict(x=200, y=100, z=300),
        name="Terrain"
    ))

    # Water overlay (semi-transparent)
    if pond_mm is not None:
        pond_norm = pond_mm / (np.percentile(pond_mm, 98) + 1e-9)
        z_water = z_base + 0.02 * relief + 0.20 * pond_norm * (relief / 1.0)
        z_water = np.where(pond_mm > 1e-6, z_water, np.nan)
        fig.add_trace(go.Surface(
            x=x, y=y, z=z_water,
            colorscale=[[0, "rgb(70,120,255)"], [1, "rgb(70,120,255)"]],
            showscale=False,
            opacity=0.55,
            name="Water"
        ))

    fig.update_layout(
        title=title,
        scene=dict(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            aspectmode="data"
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        height=720
    )
    return fig

# -------------------- UI: actions --------------------
colA, colB = st.columns([2.2, 1.0])
with colB:
    st.markdown("### Actions")
    run_once = st.button("Simulate full storm")
    animate = st.button("Animate rainfall")

with colA:
    if run_once:
        inc = storm_mm
        Q = scs_runoff(inc, S, Ia)       # per-cell runoff (mm)
        routed = route_d8(Q, elev, iters=3)
        pond = routed
        infil = np.clip(inc - Q, 0, None)

        fig = make_3d_figure(elev, world, pond_mm=pond,
                             title=f"Full storm: {storm_mm} mm (soil={soil_state})")
        st.plotly_chart(fig, use_container_width=True)
        st.info(f"Mean infiltration: {infil.mean():.1f} mm | "
                f"Mean runoff: {Q.mean():.1f} mm | "
                f"Max ponded: {pond.max():.1f} mm")

    elif animate:
        placeholder = st.empty()
        progress = st.progress(0)
        series = np.linspace(0, storm_mm, num=max(1, steps))
        prev = 0.0
        pond = np.zeros_like(elev)

        for i, total in enumerate(series, start=1):
            inc = total - prev
            prev = total
            Q = scs_runoff(inc, S, Ia)
            routed = route_d8(Q, elev, iters=1)
            pond += routed

            fig = make_3d_figure(elev, world, pond_mm=pond,
                                 title=f"Step {i}/{len(series)} – accumulated ponding")
            placeholder.plotly_chart(fig, use_container_width=True)
            progress.progress(int(100 * i / len(series)))
            time.sleep(frame_delay)

        st.success(f"Done. Mean runoff this storm: {pond.mean():.1f} mm (map shows where it concentrates).")

    else:
        fig = make_3d_figure(elev, world, pond_mm=None, title="Terrain & land cover (no storm yet)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Tip: increase **forest share** or reduce **buildings/roads** to see more infiltration and less concentration in valleys/roads.")

# -------------------- Diagnostics --------------------
with st.expander("Diagnostics & assumptions"):
    pct_forest = (world==0).mean()*100
    pct_ground = (world==1).mean()*100
    pct_build  = (world==2).mean()*100
    st.write(f"Land cover: forest {pct_forest:.1f}%, ground {pct_ground:.1f}%, buildings/roads {pct_build:.1f}%")
    st.write(f"CN stats (min/mean/max): {CN.min():.0f} / {CN.mean():.0f} / {CN.max():.0f}")
    st.markdown(
        """
**Notes**
- 3D surface is synthetic but terrain-informed; hill direction and valleys are realistic.
- Curve Numbers: forest < ground < roads/buildings for infiltration capacity.
- Routing is a simplified D8 flow; use results for intuition and scenario comparison.
        """
    )

