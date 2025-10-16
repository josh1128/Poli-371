# app.py
# HOPE Rwanda – "World" Simulator (Streamlit, no Matplotlib/Folium)
# Tabs: Overview • World Simulator • Bundles • Map
# Deps: streamlit, numpy, pandas (pydeck comes with Streamlit)

import time
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="HOPE Rwanda – World Simulator", layout="wide")
st.title("🌍 HOPE Rwanda – Interactive World Simulator")

# ============== Helpers ==============
def scs_runoff_depth_mm(P, CN):
    """SCS-CN runoff depth (mm) from total event depth P."""
    S = 25400.0 / CN - 254.0  # mm
    Ia = 0.2 * S
    if P <= Ia:
        return 0.0
    return ((P - Ia) ** 2) / (P + 0.8 * S)

def mm_to_m3(mm, area_m2):
    return (mm / 1000.0) * area_m2

def hyetograph(total_mm, duration_min, shape="Triangular", peak_at=0.4):
    t = np.arange(duration_min, dtype=float)
    if shape == "Uniform":
        i = np.ones_like(t) * (total_mm / duration_min)
    elif shape == "Front-loaded":
        x = np.linspace(0, 3, duration_min); w = np.exp(-x); i = w / w.sum() * total_mm
    elif shape == "Back-loaded":
        x = np.linspace(0, 3, duration_min); w = np.exp(-x[::-1]); i = w / w.sum() * total_mm
    else:
        peak_idx = max(1, int(peak_at * (duration_min - 1)))
        up = np.linspace(0, 1, peak_idx + 1)
        down = np.linspace(1, 0, duration_min - peak_idx - 1)
        shape_arr = np.concatenate([up, down]) if down.size else up
        i = shape_arr / shape_arr.sum() * total_mm
    return i

def incremental_runoff_series(intensities_mm, CN):
    cum = np.cumsum(intensities_mm)
    Q_tot = np.array([scs_runoff_depth_mm(P, CN) for P in cum])
    inc = np.diff(np.concatenate([[0.0], Q_tot]))
    inc[inc < 0] = 0.0
    return inc, Q_tot

# ============== Sidebar: "world" parameters ==============
with st.sidebar:
    st.header("World Setup")
    # Site scale knobs (simple abstractions so it stays lightweight)
    area_roads_m2 = st.number_input("Road catchment draining to weak spots (m²)", 500.0, 100000.0, 6000.0, 100.0)
    base_CN = st.slider("Base Curve Number (dirt/unpaved)", 70, 95, 85, 1)
    slope = st.selectbox("Slope condition", ["Low", "Moderate", "Steep"], index=1)
    slope_factor = {"Low": 0.95, "Moderate": 1.00, "Steep": 1.05}[slope]

    st.header("Storm")
    P_total = st.slider("Storm total (mm)", 20, 200, 80, 5)
    dur = st.slider("Storm duration (min)", 10, 240, 90, 5)
    shape = st.selectbox("Hyetograph shape", ["Triangular", "Uniform", "Front-loaded", "Back-loaded"])
    peak_at = st.slider("Triangular peak position", 0.2, 0.8, 0.4, 0.05)

    st.header("Solutions (from HOPE docs)")
    # Rainwater Harvesting (rooftops) — storage & overflow routing
    harv_on = st.toggle("Rainwater Harvesting", True)
    if harv_on:
        roof_area_m2 = st.number_input("Rooftop area (m²)", 0.0, 20000.0, 800.0, 10.0)
        tank_size_L = st.number_input("Tank size (L)", 100.0, 20000.0, 1000.0, 50.0)
        n_tanks = st.number_input("# of tanks", 0, 1000, 16, 1)
        first_flush_mm = st.slider("First-flush skim (mm)", 0, 5, 2, 1)
    else:
        roof_area_m2 = 0.0; tank_size_L = 0.0; n_tanks = 0; first_flush_mm = 0

    # Hügelkultur — distributed storage that intercepts road flow
    hug_on = st.toggle("Hügelkultur beds", True)
    if hug_on:
        n_beds = st.number_input("# beds", 0, 400, 40, 1)
        bed_len = st.number_input("Bed length (m)", 1.0, 50.0, 6.0, 0.5)
        bed_wid = st.number_input("Bed width (m)", 0.5, 5.0, 1.2, 0.1)
        core_depth = st.number_input("Core thickness (m)", 0.1, 2.0, 0.6, 0.05)
        core_por = st.slider("Core porosity (void fraction)", 0.2, 0.8, 0.5, 0.05)
        edge_loss = st.slider("Edge losses (fraction)", 0.0, 0.5, 0.15, 0.05)
        hug_intercept_share = st.slider("Share of road runoff intercepted (%)", 0, 80, 30, 5) / 100.0
    else:
        n_beds=0; bed_len=0; bed_wid=0; core_depth=0; core_por=0; edge_loss=0; hug_intercept_share=0

    # Vetiver — CN reduction + extra infiltration
    vet_on = st.toggle("Vetiver Grass", True)
    if vet_on:
        vet_CN = st.slider("Vetiver CN reduction (points)", 0, 12, 4, 1)
        vet_extra_infil = st.slider("Extra infiltration on remaining runoff (%)", 0, 40, 12, 1) / 100.0
    else:
        vet_CN=0; vet_extra_infil=0.0

    # Permeable Pavements — weighted CN + direct infiltration on permeable patch
    pp_on = st.toggle("Permeable Pavements", True)
    if pp_on:
        pp_frac = st.slider("Fraction of roads converted", 0.0, 1.0, 0.25, 0.05)
        pp_CN = st.slider("CN reduction on permeable area (points)", 0, 20, 8, 1)
        pp_direct = st.slider("Direct infiltration on permeable area (%)", 0, 90, 40, 5) / 100.0
    else:
        pp_frac=0.0; pp_CN=0; pp_direct=0.0

# ============== Build storm & CN ==============
inten = hyetograph(P_total, dur, shape, peak_at)
cumP = np.cumsum(inten)

CN_eff = base_CN
if vet_on:
    CN_eff = max(30, CN_eff - vet_CN)
if pp_on and pp_frac > 0:
    CN_perm = max(30, CN_eff - pp_CN)
    CN_eff = (1 - pp_frac) * CN_eff + pp_frac * CN_perm
CN_eff *= slope_factor

inc_Q_mm, cum_Q_mm = incremental_runoff_series(inten, CN_eff)
rain_on_perm_mm = inten * (pp_frac if pp_on else 0.0)
pp_direct_infil_mm = rain_on_perm_mm * (pp_direct if pp_on else 0.0)

inc_Q_m3 = mm_to_m3(inc_Q_mm, area_roads_m2)
pp_direct_infil_m3 = mm_to_m3(pp_direct_infil_mm, area_roads_m2)
runoff_after_pp_m3 = np.maximum(0.0, inc_Q_m3 - pp_direct_infil_m3)
vetiver_extra_infil_m3 = runoff_after_pp_m3 * (vet_extra_infil if vet_on else 0.0)
effective_runoff_m3_series = np.maximum(0.0, runoff_after_pp_m3 - vetiver_extra_infil_m3)

# Rainwater harvesting (separate: roofs)
if harv_on:
    P_eff_roof = max(0.0, P_total - first_flush_mm)
    roof_yield_m3 = mm_to_m3(P_eff_roof, roof_area_m2)
    tank_cap_m3 = (tank_size_L * n_tanks) / 1000.0
    roof_captured_m3 = min(roof_yield_m3, tank_cap_m3)
    roof_overflow_m3 = max(0.0, roof_yield_m3 - roof_captured_m3)
else:
    roof_yield_m3 = 0.0; roof_captured_m3 = 0.0; roof_overflow_m3 = 0.0

# Hügelkultur storage & interception
if hug_on:
    hug_core_vol = n_beds * bed_len * bed_wid * core_depth
    hug_storage_m3 = hug_core_vol * core_por * (1 - edge_loss)
    hug_intercepted_m3 = min(hug_storage_m3, np.sum(effective_runoff_m3_series) * hug_intercept_share)
    hug_overflow_m3 = max(0.0, np.sum(effective_runoff_m3_series) * hug_intercept_share - hug_intercepted_m3)
else:
    hug_storage_m3=0.0; hug_intercepted_m3=0.0; hug_overflow_m3=0.0

# Combine to final "world" runoff arriving at weak spots
baseline_CN_with_slope = base_CN * slope_factor
baseline_Q_mm_total = scs_runoff_depth_mm(P_total, baseline_CN_with_slope)
baseline_runoff_m3_total = mm_to_m3(baseline_Q_mm_total, area_roads_m2)

solutions_runoff_m3 = np.sum(effective_runoff_m3_series) \
                      - hug_intercepted_m3 + hug_overflow_m3 \
                      + roof_overflow_m3  # rooftop overflow joins ground system

solutions_runoff_m3 = max(0.0, solutions_runoff_m3)

reduction_ratio = 1.0 - (solutions_runoff_m3 / (baseline_runoff_m3_total + 1e-9))
road_protection = (
    40 * max(0.0, reduction_ratio)
    + 20 * (1.0 if vet_on else 0.0)
    + 20 * (pp_frac if pp_on else 0.0)
    + 20 * (min(1.0, hug_intercepted_m3 / (hug_storage_m3 + 1e-9)) if hug_on else 0.0)
)
road_protection = float(np.clip(road_protection, 0, 100))

# ============== Tabs ==============
tab1, tab2, tab3, tab4 = st.tabs(["Overview", "World Simulator", "Bundles", "Map"])

with tab1:
    st.subheader("What this world simulates")
    st.markdown(
        """
- **Storm engine:** choose storm size, duration, and temporal pattern; we compute SCS-CN runoff.
- **Four feasible levers:** Rainwater Harvesting, Hügelkultur, Vetiver, Permeable Pavements.
- **World outputs:** baseline vs. after-solutions runoff, storage captured, and a **Road Protection Score**.
- **Design intent from HOPE docs:** reduce erosion & runoff, **store water** for reuse, and keep solutions easy to implement/maintain. 
        """
    )
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Baseline runoff (m³)", f"{baseline_runoff_m3_total:,.1f}")
    k2.metric("Runoff after solutions (m³)", f"{solutions_runoff_m3:,.1f}")
    k3.metric("Water captured in tanks (m³)", f"{roof_captured_m3:,.1f}")
    k4.metric("Road Protection Score", f"{road_protection:.0f}/100")

    st.divider()
    # Distribution chart
    dist = pd.DataFrame(
        {
            "Volume (m³)": {
                "Remaining runoff": float(solutions_runoff_m3),
                "Permeable direct infiltration": float(np.sum(pp_direct_infil_m3)),
                "Vetiver extra infiltration": float(np.sum(vetiver_extra_infil_m3)),
                "Hügel intercepted": float(hug_intercepted_m3),
                "Tanks (rooftops)": float(roof_captured_m3),
            }
        }
    )
    st.subheader("Where the water goes")
    st.bar_chart(dist)

with tab2:
    st.subheader("Live storm playback")
    # Play/pause
    if "playing" not in st.session_state: st.session_state.playing = False
    if "t_idx" not in st.session_state: st.session_state.t_idx = 0
    c1, c2, c3, c4 = st.columns([1,1,1,2])
    if c1.button("▶️ Play"): st.session_state.playing = True
    if c2.button("⏸️ Pause"): st.session_state.playing = False
    if c3.button("⏮️ Reset"): st.session_state.playing = False; st.session_state.t_idx = 0
    speed = c4.slider("Speed (sim minutes / second)", 1, 20, 6, 1)

    # Advance clock
    if st.session_state.playing:
        time.sleep(1/12)  # small tick
        st.session_state.t_idx += speed
        if st.session_state.t_idx >= dur:
            st.session_state.t_idx = dur - 1
            st.session_state.playing = False
        st.experimental_rerun()

    t = min(int(st.session_state.t_idx), dur - 1)
    live = pd.DataFrame(
        {
            "Rain (mm)": np.cumsum(inten)[:t+1],
            "Runoff (mm, SCS w/ solutions)": np.cumsum(inc_Q_mm)[:t+1],
        }
    )
    lc1, lc2 = st.columns(2)
    with lc1:
        st.markdown(f"**Minute:** {t+1}/{dur}")
        st.line_chart(pd.DataFrame({"mm/min": inten[:t+1]}), height=220)
        st.caption("Rainfall intensity")
    with lc2:
        st.line_chart(live, height=220)
        st.caption("Cumulative rain vs. cumulative SCS runoff")

    st.divider()
    this_min = pd.DataFrame(
        [
            ("Rain this minute (mm)", inten[t]),
            ("Incremental runoff (mm)", inc_Q_mm[t]),
            ("Permeable direct infil (m³)", float(pp_direct_infil_m3[t])),
            ("Vetiver extra infil (m³)", float(vetiver_extra_infil_m3[t])),
        ], columns=["Metric", "Value"]
    )
    st.dataframe(this_min, hide_index=True, use_container_width=True)

with tab3:
    st.subheader("One-click bundles")
    st.caption("Pre-set combinations inspired by the design doc. Toggle to load, then fine-tune in the sidebar.")
    bcol1, bcol2, bcol3, bcol4 = st.columns(4)
    if bcol1.button("A) Tanks + Hügel"):
        st.session_state.update({
            'harv_on': True, 'hug_on': True,
        })
        st.info("Loaded: Rainwater Harvesting + Hügelkultur. Increase tank count & bed size for bigger impact.")
    if bcol2.button("B) Hügel + Vetiver"):
        st.session_state.update({
            'hug_on': True, 'vet_on': True,
        })
        st.info("Loaded: Hügelkultur + Vetiver. Stabilize slopes and store water in wood cores.")
    if bcol3.button("C) Permeable + Vetiver"):
        st.session_state.update({
            'pp_on': True, 'vet_on': True,
        })
        st.info("Loaded: Permeable Pavement + Vetiver. Keep surfaces draining and slopes rooted.")
    if bcol4.button("D) All Four"):
        st.session_state.update({
            'harv_on': True, 'hug_on': True, 'pp_on': True, 'vet_on': True
        })
        st.info("Loaded: Integrated system (tanks + hügel + vetiver + permeable).")

    st.markdown(
        """
**Reading the outputs:**  
- **Road Protection Score** blends runoff reduction plus stability effects from vetiver, permeable share, and how much hügel storage is actually used.  
- Use **storm sliders** to stress-test big events (e.g., 120–160 mm).
        """
    )

with tab4:
    st.subheader("Optional map (enter coordinates)")
    st.caption("No external map libs needed. Enter a center point; we’ll show markers for key features you define.")
    lat = st.number_input("Center latitude", value=-1.95, format="%.6f")
    lon = st.number_input("Center longitude", value=30.100000, format="%.6f")
    # Simple points table the team can extend with actual GPS from the docs
    pts = pd.DataFrame(
        [
            {"name": "Access road junction", "lat": lat, "lon": lon},
            {"name": "Proposed hügel zone", "lat": lat+0.003, "lon": lon+0.003},
            {"name": "Tank cluster", "lat": lat-0.003, "lon": lon-0.003},
        ]
    )
    st.map(pts[["lat","lon"]], size=80)
    st.dataframe(pts, hide_index=True, use_container_width=True)
