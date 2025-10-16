# app.py — Mini World Stormwater Simulator (HOPE Rwanda)
# - Grid-based hillside "world" (forests, ground, buildings/roads)
# - SCS-CN runoff per land cover + simple downhill flow routing
# - Adjustable forest/building coverage and soil condition
# - One-click animate loop for short storms

import time
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# -------------------- Page setup --------------------
st.set_page_config(page_title="Mini World – HOPE Rwanda Stormwater Simulator", layout="wide")
st.title("Mini World Stormwater Simulator – HOPE Rwanda")

with st.expander("About this demo"):
    st.markdown(
        """
This is a schematic mini-world: a small hillside draining downslope. Land cover drives how much rain becomes **runoff vs infiltration** using an SCS-Curve-Number style calculation. 
You can tweak cover ratios and storm size, then **simulate** to see where water concentrates (valleys/roads).

Context: HOPE Rwanda’s site in Rwabutenge (Gahanga, Kicukiro) experiences heavy rains and eroding roads; this tool explores how cover/roads affect water movement. :contentReference[oaicite:1]{index=1}
        """
    )

# -------------------- Sidebar controls --------------------
st.sidebar.header("World & Rain Controls")

# Grid size (kept modest for speed)
GRID_W = st.sidebar.slider("Grid width (cells)", 40, 120, 80, 10)
GRID_H = st.sidebar.slider("Grid height (cells)", 30, 100, 50, 10)

seed = st.sidebar.number_input("Random seed", value=42, step=1)
rng = np.random.default_rng(int(seed))

st.sidebar.subheader("Land cover mix")
forest_ratio = st.sidebar.slider("Forest share (%)", 0, 80, 35, 5) / 100.0
building_ratio = st.sidebar.slider("Buildings/roads share (%)", 0, 50, 10, 5) / 100.0
# Ground gets the remainder
ground_ratio = max(0.0, 1.0 - forest_ratio - building_ratio)

st.sidebar.subheader("Soil / antecedent condition")
soil_condition = st.sidebar.select_slider(
    "Antecedent moisture (dry ↔ wet)",
    options=["Dry", "Average", "Wet"],
    value="Average",
)

st.sidebar.subheader("Storm")
storm_mm = st.sidebar.slider("Total storm depth (mm)", 0, 1400, 120, 10)
steps = st.sidebar.slider("Animation steps", 1, 120, 30, 1)
step_duration = st.sidebar.slider("Step delay (ms)", 0, 150, 30, 5) / 1000.0

st.sidebar.subheader("Road pattern")
road_toggle = st.sidebar.checkbox("Include hillside road", value=True)

# -------------------- Build / cache a land-cover world --------------------
# Land cover codes: 0=forest, 1=ground, 2=building/road
def make_world(w, h, forest_r, build_r, road=True, rng=None):
    n = w * h
    forest_n = int(n * forest_r)
    build_n = int(n * build_r)
    ground_n = n - forest_n - build_n

    arr = np.array([0]*forest_n + [1]*ground_n + [2]*build_n, dtype=np.int8)
    rng.shuffle(arr)
    world = arr.reshape((h, w))

    if road:
        # Carve a simple diagonal road (impermeable) across the slope
        rr = np.linspace(5, h-6, num=6).astype(int)
        cc = np.linspace(3, w-4, num=6).astype(int)
        for r, c in zip(rr, cc):
            world[max(0,r-1):min(h,r+2), max(0,c-2):min(w,c+3)] = 2
    return world

@st.cache_data(show_spinner=False)
def cached_world(w, h, fr, br, road, seed):
    return make_world(w, h, fr, br, road, np.random.default_rng(int(seed)))

world = cached_world(GRID_W, GRID_H, forest_ratio, building_ratio, road_toggle, seed)

# -------------------- Slope / elevation model --------------------
# A simple tilted plane with a small valley at bottom to collect flow.
y = np.linspace(1.0, 0.0, GRID_H).reshape(-1, 1)      # downslope (top -> bottom)
x = np.linspace(0.0, 1.0, GRID_W).reshape(1, -1)
elev = 0.70 * y + 0.05 * np.cos(4*np.pi*x) * (1.0 - y)  # gentle undulations + valley tendency

# -------------------- Curve Numbers (by cover & moisture) --------------------
# Baseline (AMC II / "Average") CNs; tweak by moisture.
CN_base = {
    0: 60,   # forest
    1: 75,   # mixed bare/grass ground
    2: 95,   # buildings/roads (impervious)
}

moisture_adj = {
    "Dry": -5,       # drier soil -> slightly lower CN
    "Average": 0,
    "Wet": +5,       # wetter soil -> slightly higher CN
}

CN_map = np.zeros_like(world, dtype=float)
for cls, base in CN_base.items():
    CN_map[world == cls] = base + moisture_adj[soil_condition]
CN_map = np.clip(CN_map, 30, 98)  # bounds for sanity

# Convert CN to S (potential max retention) in mm
# S = 25400/CN - 254    (CN in [30,100))
S_map = (25400.0 / CN_map) - 254.0
Ia_map = 0.20 * S_map  # initial abstraction

# -------------------- Helpers: runoff per step & routing --------------------
def scs_runoff(P_mm, S, Ia):
    # Vectorized SCS runoff (mm) for depth P
    # Q = ((P - Ia)^2)/(P - Ia + S) if P>Ia else 0
    excess = P_mm - Ia
    Q = np.where(excess > 0.0, (excess**2) / (excess + S), 0.0)
    return Q

def route_downhill(Q_mm, elev, iters=1):
    """Very simple flow accumulator that pushes water one cell to its lowest neighbor (D8) per iter."""
    H, W = Q_mm.shape
    acc = Q_mm.copy()
    for _ in range(iters):
        moved = np.zeros_like(acc)
        for r in range(H):
            for c in range(W):
                # Find lowest neighbor including staying put
                r0, c0 = r, c
                rmin, cmin = r0, c0
                zmin = elev[r0, c0]
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r0 + dr, c0 + dc
                        if 0 <= rr < H and 0 <= cc < W:
                            if elev[rr, cc] < zmin:
                                zmin = elev[rr, cc]; rmin, cmin = rr, cc
                # Move a portion if a downhill cell exists
                if (rmin, cmin) != (r0, c0):
                    moved[rmin, cmin] += acc[r0, c0] * 0.85  # 85% flows, 15% ponds/friction
                    acc[r0, c0] *= 0.15
        acc += moved
    return acc

# -------------------- Visualization --------------------
def render(world, water_mm, title=""):
    # Base colors per land cover
    # forest=green, ground=tan, road/buildings=dark
    palette = np.array([
        [0.20, 0.55, 0.20],  # forest
        [0.76, 0.69, 0.50],  # ground
        [0.25, 0.25, 0.28],  # buildings/roads
    ])
    base_rgb = palette[world]

    # Water overlay (blue intensity by depth)
    # Normalize water depth for display
    vmax = max(1.0, np.percentile(water_mm, 95))
    water_norm = np.clip(water_mm / vmax, 0.0, 1.0)

    overlay = base_rgb.copy()
    blue = np.zeros_like(base_rgb)
    blue[..., 2] = 1.0  # pure blue channel
    alpha = (water_norm * 0.85)[..., None]  # up to 85% overlay where very wet
    img = (1 - alpha) * overlay + alpha * blue

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(img, origin="upper", interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=13)
    # Legend proxy
    handles = [
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=palette[0], label="Forest"),
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=palette[1], label="Ground"),
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=palette[2], label="Buildings/Road"),
        plt.Line2D([0],[0], marker="s", linestyle="None", markersize=10, color=[0.3,0.3,1.0], label="More water"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True)
    st.pyplot(fig, clear_figure=True)
    plt.close(fig)

# -------------------- Simulation --------------------
colA, colB = st.columns([2, 1])

with colB:
    st.markdown("### Actions")
    do_sim = st.button("Simulate once")
    do_anim = st.button("Animate storm")

with colA:
    # Precompute per-step rainfall
    storm_series = np.linspace(0, storm_mm, num=max(steps, 1))
    prev = 0.0

    # Start with dry
    ponded = np.zeros_like(S_map)

    if do_sim or do_anim:
        if do_sim:
            # Single step = full storm
            inc = storm_mm
            Q = scs_runoff(inc, S_map, Ia_map)
            infil = np.clip(inc - Q, 0.0, None)

            routed = route_downhill(Q, elev, iters=2)
            ponded = routed

            render(world, ponded, title=f"Runoff & Ponding (storm={storm_mm} mm, soil={soil_condition})")

            st.info(
                f"Infiltration (mean): {infil.mean():.1f} mm | "
                f"Runoff (mean): {Q.mean():.1f} mm | "
                f"Max ponded: {ponded.max():.1f} mm"
            )

        if do_anim:
            ph = st.empty()
            bar = st.progress(0)
            accum = np.zeros_like(S_map)

            for i, total in enumerate(storm_series, start=1):
                inc = total - prev
                prev = total

                Q = scs_runoff(inc, S_map, Ia_map)
                routed = route_downhill(Q, elev, iters=1)
                accum += routed

                with ph.container():
                    render(world, accum, title=f"Animated storm step {i}/{len(storm_series)}")

                bar.progress(int(100 * i / len(storm_series)))
                time.sleep(step_duration)

            st.success(
                f"Done. Mean runoff this storm: {(accum.mean()):.1f} mm (display shows ponding/concentration)."
            )
    else:
        render(world, np.zeros_like(S_map), title="Initial world (no storm yet)")
        st.caption(
            "Blue intensifies where water concentrates. Adjust land cover shares and storm depth, then click **Simulate** or **Animate storm**."
        )

# -------------------- Diagnostics panel --------------------
with st.expander("Diagnostics & assumptions"):
    c_forest = (world == 0).mean()*100
    c_ground = (world == 1).mean()*100
    c_build  = (world == 2).mean()*100
    st.write(f"Land cover: Forest ~{c_forest:.1f}%, Ground ~{c_ground:.1f}%, Buildings/Roads ~{c_build:.1f}%")
    st.write("CN (min/mean/max):",
             f"{CN_map.min():.0f} / {CN_map.mean():.0f} / {CN_map.max():.0f}")
    st.write("Notes:")
    st.markdown(
        """
- Schematic slope only; no real DEM here. Lower rows represent downslope/valley.
- Curve Numbers approximate mixed soils/cover; buildings/roads assumed near-impervious.
- Routing is a simple “push downhill” toy model; it’s good for intuition, not design.
- Use this to compare **relative** effects: more forest (lower CN) → more infiltration; more impervious → more runoff.
        """
    )

