# app.py — Realistic Mini World (HOPE Rwanda)
# Terrain: fractal Brownian motion + southward slope
# Lighting: hillshade
# Land cover: forests follow terrain; buildings cluster around curvy roads
# Hydrology: SCS-CN infiltration/runoff per cover + simple D8 routing
# Animation: falling raindrop overlay while ponding accumulates

import time
import math
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# -------------------- Page setup --------------------
st.set_page_config(page_title="Realistic Mini World – HOPE Rwanda", layout="wide")
st.title("Realistic Mini World – HOPE Rwanda (Stormwater)")

with st.expander("What you're seeing"):
    st.markdown(
        """
A synthetic but realistic **hillside near Kigali**: terrain is generated with fractal noise and lit with hillshade.
Land cover is placed where it typically occurs (forest mid/high slope; roads along gentler contours with clustered buildings).
Choose a storm and watch **rainfall, runoff routing, and ponding** in valleys/roads. Use it for **relative scenario** comparisons.
        """
    )

# -------------------- Sidebar controls --------------------
st.sidebar.header("World settings")
W = st.sidebar.slider("Width (cells)", 80, 200, 140, 10)
H = st.sidebar.slider("Height (cells)", 60, 160, 110, 10)
seed = st.sidebar.number_input("Random seed", value=7, step=1)

st.sidebar.subheader("Terrain realism")
relief = st.sidebar.slider("Relief (vertical range)", 0.4, 1.6, 1.0, 0.05)
roughness = st.sidebar.slider("Terrain roughness (fBm octaves)", 1, 7, 4, 1)
slope_bias = st.sidebar.slider("Southward slope bias", 0.1, 1.0, 0.55, 0.05)
valley_focus = st.sidebar.slider("Valley emphasis", 0.0, 1.0, 0.35, 0.05)

st.sidebar.subheader("Land cover composition")
forest_share = st.sidebar.slider("Target forest share (%)", 10, 80, 40, 5) / 100.0
build_share = st.sidebar.slider("Target buildings/roads share (%)", 5, 35, 12, 1) / 100.0
# ground = remainder

st.sidebar.subheader("Soil moisture (affects CN)")
soil_state = st.sidebar.select_slider("Antecedent moisture", ["Dry", "Average", "Wet"], value="Average")

st.sidebar.subheader("Road network")
curvy = st.sidebar.slider("Road curviness", 0.0, 1.0, 0.55, 0.05)
spurs = st.sidebar.slider("Side roads (count)", 0, 6, 3, 1)

st.sidebar.subheader("Storm & animation")
storm_mm = st.sidebar.slider("Total storm depth (mm)", 0, 1400, 180, 10)
steps = st.sidebar.slider("Animation steps", 10, 180, 60, 5)
delay = st.sidebar.slider("Frame delay (ms)", 0, 120, 25, 5) / 1000.0
raindrops = st.sidebar.slider("Visible raindrops (x100)", 0, 30, 10, 1) * 100

rng = np.random.default_rng(int(seed))

# -------------------- Terrain synthesis (fBm noise + plane) --------------------
def fbm_noise(h, w, octaves=4, persistence=0.5, lacunarity=2.0, rng=None):
    """Fractal Brownian Motion using summed blurred white-noise (fast & dependency-free)."""
    base = np.zeros((h, w), dtype=float)
    for o in range(octaves):
        freq = lacunarity ** o
        # downsampled noise then resize via tile/repeat (cheap "blur")
        sh = max(2, int(h / freq))
        sw = max(2, int(w / freq))
        n = rng.normal(0, 1, size=(sh, sw))
        # simple nearest upsample:
        up = np.kron(n, np.ones((math.ceil(h/sh), math.ceil(w/sw))))
        up = up[:h, :w]
        base += (persistence ** o) * up
    # normalize 0-1
    base = (base - base.min()) / (base.max() - base.min() + 1e-9)
    return base

@st.cache_data(show_spinner=False)
def build_terrain(h, w, octaves, slope_bias, valley_focus, relief, seed):
    rng = np.random.default_rng(int(seed))
    fbm = fbm_noise(h, w, octaves=octaves, persistence=0.55, lacunarity=2.0, rng=rng)
    # southward slope (top high → bottom low)
    south = np.linspace(1.0, 0.0, h).reshape(-1, 1)
    # gentle east-west undulations
    x = np.linspace(0, 1, w)[None, :]
    ridges = 0.15 * np.cos(4 * np.pi * x)
    base = (slope_bias * south + (1.0 - slope_bias) * fbm + ridges)
    # emphasize valleys by subtracting smoothed fbm
    val = fbm_noise(h, w, octaves=max(1, octaves-1), persistence=0.65, rng=rng)
    elev = base - valley_focus * val
    # normalize and scale relief
    elev = (elev - elev.min()) / (elev.max() - elev.min() + 1e-9)
    elev = elev ** 1.1  # slight skew for more realistic basins
    elev = elev * relief
    return elev

elev = build_terrain(H, W, roughness, slope_bias, valley_focus, relief, seed)

# -------------------- Hillshade (terrain lighting) --------------------
def hillshade(elevation, azimuth_deg=315, altitude_deg=45, cellsize=1.0):
    az = np.deg2rad(azimuth_deg)
    alt = np.deg2rad(altitude_deg)
    # gradients
    gy, gx = np.gradient(elevation, cellsize)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)  # y points down in image coords
    hs = (np.sin(alt) * np.cos(slope) +
          np.cos(alt) * np.sin(slope) * np.cos(az - aspect))
    hs = np.clip(hs, 0, 1)
    return hs

shade = hillshade(elev, azimuth_deg=320, altitude_deg=38)

# -------------------- Land cover placement --------------------
# 0=forest, 1=ground, 2=buildings/roads
def place_roads(h, w, curviness=0.6, n_spurs=3, rng=None):
    road = np.zeros((h, w), dtype=bool)
    # main curvy polyline at ~1/3 from top
    r = int(h * (0.30 + 0.1 * rng.random()))
    c = 0
    drift = 0
    while c < w:
        road[max(0, r-1):min(h, r+2), max(0, c-2):min(w, c+3)] = True
        # wander up/down with memory
        drift += rng.normal(0, curviness*0.8)
        r = int(np.clip(r + np.tanh(drift), 2, h-3))
        c += 2
    # side spurs dropping downhill
    for _ in range(n_spurs):
        c0 = rng.integers(low=int(w*0.1), high=int(w*0.9))
        r0 = np.argmax(road[:, c0])  # where main road exists
        if r0 == 0 and not road[0, c0]:
            continue
        r = r0; c = c0
        length = rng.integers(low=int(h*0.15), high=int(h*0.35))
        for _ in range(length):
            road[max(0, r-1):min(h, r+2), max(0, c-1):min(w, c+2)] = True
            # go generally downhill; adjust toward lower neighbor of elev
            window = elev[max(0,r-1):min(h,r+2), max(0,c-1):min(w,c+2)]
            rr, cc = np.unravel_index(np.argmin(window), window.shape)
            r = int(np.clip((r-1)+rr, 1, h-2))
            c = int(np.clip((c-1)+cc, 1, w-2))
    return road

rng_local = np.random.default_rng(int(seed))
road_mask = place_roads(H, W, curvy, spurs, rng_local)

# Buildings cluster near roads & gentle slopes
slope_mag = np.hypot(*np.gradient(elev))
gentle = (slope_mag < np.percentile(slope_mag, 60))
near_road = road_mask | (np.logical_and.reduce([
    np.pad(road_mask[1:, :], ((0,1),(0,0)), constant_values=False),
    np.pad(road_mask[:-1, :], ((1,0),(0,0)), constant_values=False) == False, # just to mix neighbors
    True
]) == True)  # keeping simple; we just bias around roads

settlement_score = gentle.astype(float) * 0.6 + road_mask.astype(float) * 1.2
settlement_score += 0.3 * fbm_noise(H, W, octaves=2, persistence=0.7, rng=rng_local)
settlement_score = (settlement_score - settlement_score.min()) / (settlement_score.ptp() + 1e-9)

target_build = int(W*H*build_share)
buildings = np.zeros((H, W), dtype=bool)
idx = np.dstack(np.unravel_index(np.argsort(settlement_score.ravel())[::-1], (H, W)))[0]
for r, c in idx:
    if target_build <= 0:
        break
    # place a small blocky footprint
    rr = slice(max(0, r-1), min(H, r+2))
    cc = slice(max(0, c-1), min(W, c+2))
    add = (~buildings[rr, cc]) & (settlement_score[rr, cc] > 0.55)
    if add.any():
        buildings[rr, cc] = True
        target_build -= int(add.sum())

# Forest prefers mid/high elevation and non-steep areas
forest_score = (elev - elev.min()) / (elev.ptp() + 1e-9)
forest_score *= (1.0 - np.clip(slope_mag / slope_mag.max(), 0, 1)) ** 0.4
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

# Ground = everything else
ground = ~(forest | buildings | road_mask)

# Land cover map: 0=forest, 1=ground, 2=build/road
world = np.full((H, W), 1, dtype=np.int8)
world[forest] = 0
world[buildings | road_mask] = 2

# -------------------- SCS-CN setup --------------------
CN_base = {  # AMC II
    0: 60,  # forest
    1: 78,  # mixed ground (grass/bare)
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
    Q = np.where(ex > 0, (ex**2) / (ex + S), 0.0)
    return Q

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
                    moved[rmin, cmin] += acc[r, c] * 0.88  # flows
                    acc[r, c] *= 0.12                      # local ponding/roughness
        acc += moved
    return acc

# -------------------- Visualization --------------------
# Color ramps: terrain (brown/green) + hillshade
def terrain_rgb(elev, shade):
    # base colormap: green lowlands to brown ridges
    low = np.array([0.73, 0.83, 0.66])  # light green
    mid = np.array([0.52, 0.72, 0.48])  # green
    high = np.array([0.59, 0.52, 0.42]) # brown
    e = (elev - elev.min()) / (elev.ptp() + 1e-9)
    base = np.where(e[..., None] < 0.5,
                    low*(1-2*e[...,None]) + mid*(2*e[...,None]),
                    mid*(1-2*(e[...,None]-0.5)) + high*(2*(e[...,None]-0.5)))
    # apply hillshade
    shade = (0.55 + 0.45*shade)[..., None]  # keep some ambient
    img = np.clip(base * shade, 0, 1)
    return img

def overlay_cover(img, world):
    # forest tint
    forest_tint = np.array([0.10, 0.35, 0.10])
    ground_tint = np.array([0.60, 0.53, 0.38])
    road_tint   = np.array([0.16, 0.16, 0.18])

    out = img.copy()
    # gentle alpha per class
    out[world == 0] = 0.75*out[world == 0] + 0.25*forest_tint
    out[world == 1] = 0.90*out[world == 1] + 0.10*ground_tint
    out[world == 2] = 0.55*out[world == 2] + 0.45*road_tint
    return out

def draw_frame(pond_mm, drop_xy=None, title=""):
    # base terrain
    img = terrain_rgb(elev, shade)
    img = overlay_cover(img, world)

    # water overlay (blue by depth)
    vmax = max(1.0, np.percentile(pond_mm, 98))
    water_alpha = np.clip(pond_mm / vmax, 0, 1) * 0.9
    blue = np.zeros_like(img); blue[..., 2] = 1.0
    img = (1 - water_alpha[..., None]) * img + water_alpha[..., None] * blue

    fig, ax = plt.subplots(figsize=(11.5, 7.2))
    ax.imshow(img, origin="upper", interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])

    # raindrops (cosmetic)
    if drop_xy is not None and len(drop_xy[0]) > 0:
        ax.scatter(drop_xy[0], drop_xy[1], s=6, marker='|', linewidths=0.5)

    ax.set_title(title, fontsize=13)
    # Legend
    handles = [
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=[0.10,0.35,0.10], label="Forest"),
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=[0.60,0.53,0.38], label="Ground"),
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=[0.16,0.16,0.18], label="Buildings/Roads"),
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=[0.3,0.3,1.0], label="More water"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True)
    st.pyplot(fig, clear_figure=True)
    plt.close(fig)

# -------------------- Simulation controls --------------------
colA, colB = st.columns([2.2, 1.0])

with colB:
    st.markdown("### Actions")
    run_once = st.button("Simulate full storm")
    animate = st.button("Animate rainfall")

with colA:
    # precompute step rain
    series = np.linspace(0, storm_mm, num=max(1, steps))
    prev = 0.0
    pond = np.zeros_like(elev)

    if run_once:
        inc = storm_mm
        Q = scs_runoff(inc, S, Ia)  # per-cell runoff (mm)
        routed = route_d8(Q, elev, iters=3)
        pond = routed
        infil = np.clip(inc - Q, 0, None)

        draw_frame(pond, title=f"Full storm: {storm_mm} mm (soil={soil_state})")
        st.info(f"Mean infiltration: {infil.mean():.1f} mm | "
                f"Mean runoff: {Q.mean():.1f} mm | "
                f"Max ponded: {pond.max():.1f} mm")

    elif animate:
        placeholder = st.empty()
        progress = st.progress(0)
        pond = np.zeros_like(elev)

        # initialize raindrops
        xdrop = rng.integers(0, W, size=raindrops)
        ydrop = rng.integers(0, H, size=raindrops)

        for i, total in enumerate(series, start=1):
            inc = total - prev
            prev = total
            # physics: fresh step runoff then routing/accumulation
            Q = scs_runoff(inc, S, Ia)
            routed = route_d8(Q, elev, iters=1)
            pond += routed

            # update drops (falling top->bottom; recycle)
            if raindrops > 0:
                ydrop = ydrop + rng.integers(1, 3, size=raindrops)
                ydrop = np.where(ydrop >= H, 0, ydrop)
                xdrop = (xdrop + rng.integers(-1, 2, size=raindrops)) % W

            with placeholder.container():
                draw_frame(pond, (xdrop, ydrop),
                           title=f"Step {i}/{len(series)} – accumulated ponding")

            progress.progress(int(100 * i / len(series)))
            time.sleep(delay)

        st.success(f"Done. Mean runoff this storm: {pond.mean():.1f} mm (map shows where it concentrates).")

    else:
        draw_frame(pond, title="Terrain & land cover (no storm yet)")
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
- Hillshade gives realistic relief; no real DEM is used (keeps the app dependency-free).
- Curve Numbers approximate cover behavior; buildings/roads treated as near-impervious.
- Routing is a simplified D8 flow; good for intuition, not for engineering design.
- Use for **relative comparisons** (e.g., more forest or rerouted roads).
        """
    )
