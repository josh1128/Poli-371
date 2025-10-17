
# app: design_simulator_app.py
# Visually appealing Streamlit interface for comparing water-design interventions
# - No heavy dependencies; runs without SWMM
# - Uses Plotly for charts and Folium for map (optional)
# - Clean, modern UI with tabs, metric cards, and scenario snapshots

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# Optional map (doesn't break if not present)
try:
    import folium
    from streamlit_folium import st_folium
    HAS_MAP = True
except Exception:
    HAS_MAP = False

# -------------------- Page & Theme --------------------
st.set_page_config(page_title="Water Design Simulator", layout="wide")
st.markdown(
    '''
    <style>
        :root { --card-bg: rgba(255,255,255,0.65); }
        .metric-card {
            background: var(--card-bg);
            border: 1px solid rgba(0,0,0,0.06);
            border-radius: 16px;
            padding: 18px 16px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }
        .pill {
            display:inline-block;padding:4px 10px;border-radius:999px;
            background:rgba(0,0,0,0.06);font-size:12px;margin-right:6px;
        }
        .footnote { color:#666; font-size:12px; }
        .section-title { font-weight:700; font-size:1.05rem; margin-bottom:0.6rem; }
        .glass {
            background: linear-gradient(135deg, rgba(255,255,255,0.55), rgba(255,255,255,0.2));
            border:1px solid rgba(255,255,255,0.4);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            border-radius: 20px; padding: 14px;
        }
    </style>
    ''',
    unsafe_allow_html=True
)

# Header with gradient
st.markdown(
    '''
    <div style="border-radius:20px;padding:26px;margin-bottom:14px;
        background: radial-gradient(1300px 300px at 0% -10%,
          rgba(99,102,241,0.25), transparent 50%),
          radial-gradient(800px 300px at 100% 0%,
          rgba(16,185,129,0.25), transparent 40%),
          linear-gradient(180deg, #0f172a 0%, #111827 100%);">
      <div style="display:flex;align-items:center;gap:18px;">
        <div style="width:46px;height:46px;border-radius:12px;background:#10b981;
            display:flex;align-items:center;justify-content:center;font-weight:800;color:white;">
          WD
        </div>
        <div>
          <div style="color:#e5e7eb;font-size:13px;letter-spacing:.08em">INTERACTIVE DECISION TOOL</div>
          <div style="color:white;font-weight:800;font-size:24px;line-height:1.1;margin-top:2px">
            Water Design Simulator
          </div>
          <div style="color:#a7f3d0;font-size:13px;margin-top:6px;">Compare rainwater tanks, vetiver strips,
            hügelkultur mounds, and permeable pavement—visually.</div>
        </div>
      </div>
    </div>
    ''',
    unsafe_allow_html=True
)

# -------------------- Data classes --------------------
@dataclass
class ScenarioInputs:
    storm_mm: float
    area_m2: float
    slope_pct: float
    base_cn: int
    tank_m3: float
    vetiver_rows: int
    hugel_len_m: float
    hugel_height_m: float
    pav_area_m2: float
    years: int

@dataclass
class ScenarioOutputs:
    rainfall_m3: float
    runoff_m3: float
    captured_m3: float
    peak_proxy_lps: float
    erosion_index: float

# -------------------- Simplified hydrology --------------------
def scs_runoff_depth(P: float, CN: int) -> float:
    """Return runoff depth (mm) using SCS-CN; handles low-P gracefully."""
    S = (25400 / CN) - 254  # mm
    Ia = 0.2 * S
    if P <= Ia:
        return 0.0
    return ((P - Ia)**2) / (P - Ia + S)

def tank_capture(P_m3: float, tank_m3: float) -> Tuple[float, float]:
    captured = min(P_m3, tank_m3)
    overflow = max(0.0, P_m3 - tank_m3)
    return captured, overflow

def hugel_storage_m3(length_m: float, height_m: float, years: int) -> float:
    # Simple triangular cross-section; porosity ~ 55% initial, decay 5%/yr
    width_m = height_m * 1.8
    cross_area = 0.5 * width_m * height_m  # m2
    volume = cross_area * length_m  # m3
    porosity0 = 0.55
    decay = 0.05 * years
    effective_porosity = max(0.25, porosity0 * (1 - decay))
    return volume * effective_porosity

def permeable_pavement_effect(area_m2: float) -> Dict[str, float]:
    # Reduce CN and add shallow storage
    cn_delta = 8 if area_m2 > 0 else 0
    storage_m3 = 0.08 * area_m2 / 1000  # 80 mm reservoir equivalent
    return {"cn_delta": cn_delta, "storage_m3": storage_m3}

def vetiver_effect(rows: int, slope_pct: float) -> Dict[str, float]:
    # Roughness & micro-terracing: reduce CN by up to ~10, reduce erosion proxy
    cn_delta = min(10, rows * 3)
    erosion_factor = max(0.6, 1 - rows * 0.1)  # 0.6 minimum
    # Slight peak attenuation proxy
    peak_factor = max(0.7, 1 - rows * 0.05)
    return {"cn_delta": cn_delta, "erosion_factor": erosion_factor, "peak_factor": peak_factor}

def compute_scenario(x: ScenarioInputs) -> ScenarioOutputs:
    A = x.area_m2
    # Adjust CN with design effects
    cn = x.base_cn
    # Permeable pavement
    pav = permeable_pavement_effect(x.pav_area_m2)
    cn = max(30, cn - pav["cn_delta"])  # lower CN means more infiltration
    pav_storage = pav["storage_m3"]
    # Vetiver rows
    vet = vetiver_effect(x.vetiver_rows, x.slope_pct)
    cn = max(30, cn - vet["cn_delta"])

    # Baseline runoff depth and volume
    runoff_mm = scs_runoff_depth(x.storm_mm, cn)
    rainfall_m3 = x.storm_mm / 1000.0 * A
    runoff_m3 = runoff_mm / 1000.0 * A

    # Storage cascade: tank -> hügel -> permeable base
    tank_inflow = rainfall_m3 * 0.35  # assume 35% of site is rooftops
    tank_cap, tank_over = tank_capture(tank_inflow, x.tank_m3)

    hugel_cap = hugel_storage_m3(x.hugel_len_m, x.hugel_height_m, x.years)
    hugel_inflow = max(0.0, runoff_m3 - tank_cap)  # what reaches ground features
    hugel_used = min(hugel_inflow, hugel_cap)

    pav_used = min(max(0.0, runoff_m3 - tank_cap - hugel_used), pav_storage)

    captured_total = tank_cap + hugel_used + pav_used
    final_runoff = max(0.0, runoff_m3 - captured_total)

    # Simple peak and erosion proxies
    peak_proxy = (final_runoff * 1000) / 3600.0  # L/s from m3 over ~1h
    peak_proxy *= vet["peak_factor"]
    erosion_index = final_runoff * (x.slope_pct / 5) * vet["erosion_factor"]
    return ScenarioOutputs(rainfall_m3, final_runoff, captured_total, peak_proxy, erosion_index)

# -------------------- Sidebar controls --------------------
st.sidebar.header("Scenario Controls")
st.sidebar.caption("Tweak inputs and compare scenarios in real time.")

colA, colB = st.sidebar.columns(2)
storm_mm = colA.slider("Storm depth (mm)", 10, 1400, 120, step=10)
area_m2 = colB.number_input("Site area (m²)", min_value=100.0, value=2500.0, step=50.0)

col1, col2 = st.sidebar.columns(2)
slope_pct = col1.slider("Avg slope (%)", 0, 30, 6, step=1)
base_cn = col2.slider("Baseline CN", 55, 90, 78, step=1)

st.sidebar.markdown("---")
st.sidebar.subheader("Design Levers")
tank_m3 = st.sidebar.slider("Tank volume (m³)", 0.0, 100.0, 12.0, step=1.0)
vetiver_rows = st.sidebar.slider("Vetiver rows", 0, 6, 2, step=1)
hugel_len_m = st.sidebar.slider("Hügelkultur length (m)", 0.0, 200.0, 40.0, step=5.0)
hugel_height_m = st.sidebar.slider("Hügelkultur height (m)", 0.2, 2.0, 0.8, step=0.1)
pav_area_m2 = st.sidebar.slider("Permeable pavement area (m²)", 0.0, float(area_m2), 120.0, step=10.0)
years = st.sidebar.slider("Years since installation", 0, 15, 2, step=1)

# -------------------- Tabs --------------------
t1, t2, t3, t4 = st.tabs(["Overview", "Scenario Builder", "Map (optional)", "Report"])

# -------------------- Overview --------------------
with t1:
    st.markdown("<div class='section-title'>Snapshot</div>", unsafe_allow_html=True)
    inputs = ScenarioInputs(storm_mm, area_m2, slope_pct, base_cn, tank_m3, vetiver_rows, hugel_len_m, hugel_height_m, pav_area_m2, years)
    out = compute_scenario(inputs)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.metric("Rainfall (m³)", f"{out.rainfall_m3:,.1f}")
        st.caption("From storm depth × site area")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.metric("Captured (m³)", f"{out.captured_m3:,.1f}")
        st.caption("Tank + Hügel + Pavement storage used")
        st.markdown("</div>", unsafe_allow_html=True)
    with c3:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.metric("Runoff (m³)", f"{out.runoff_m3:,.1f}")
        st.caption("Residual outflow after interventions")
        st.markdown("</div>", unsafe_allow_html=True)
    with c4:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.metric("Peak proxy (L/s)", f"{out.peak_proxy_lps:,.1f}")
        st.caption("Indicative; lower is safer for roads")
        st.markdown("</div>", unsafe_allow_html=True)

    # Donut chart for partitioning
    labels = ["Captured", "Runoff"]
    values = [max(out.captured_m3, 0.0001), max(out.runoff_m3, 0.0001)]
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.6)])
    fig.update_layout(margin=dict(l=10,r=10,t=10,b=10), height=320)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div class='footnote'>Note: This is a planning-level tool using SCS-CN and simple storage assumptions; calibrate before final decisions.</div>", unsafe_allow_html=True)

# -------------------- Scenario Builder --------------------
with t2:
    st.markdown("<div class='section-title'>Compare Baseline vs. Current Settings</div>", unsafe_allow_html=True)

    # Build baseline (no interventions)
    base_inputs = ScenarioInputs(storm_mm, area_m2, slope_pct, base_cn, 0.0, 0, 0.0, 0.2, 0.0, 0)
    base_out = compute_scenario(base_inputs)

    df = pd.DataFrame({
        "Metric": ["Captured (m³)", "Runoff (m³)", "Peak proxy (L/s)", "Erosion index"],
        "Baseline": [base_out.captured_m3, base_out.runoff_m3, base_out.peak_proxy_lps, base_out.erosion_index],
        "Scenario": [out.captured_m3, out.runoff_m3, out.peak_proxy_lps, out.erosion_index]
    })

    # Bars
    m = ["Captured (m³)", "Runoff (m³)", "Peak proxy (L/s)", "Erosion index"]
    fig2 = go.Figure()
    fig2.add_bar(x=m, y=df["Baseline"], name="Baseline")
    fig2.add_bar(x=m, y=df["Scenario"], name="Scenario")
    fig2.update_layout(barmode='group', margin=dict(l=10,r=10,t=10,b=10), height=360)
    st.plotly_chart(fig2, use_container_width=True)

    # Quick hints
    with st.expander("💡 Tuning tips"):
        st.markdown("""
        - **Cut runoff fast:** increase **Tank volume**, **Hügel length/height**, and **Permeable area**.
        - **Protect roads (steep areas):** add **Vetiver rows** to attenuate peaks and erosion.
        - **Long-term:** move **Years** slider up to see storage loss from hügelkultur aging.
        """)

# -------------------- Map --------------------
with t3:
    if HAS_MAP:
        st.markdown("<div class='section-title'>Locate interventions (mock coordinates)</div>", unsafe_allow_html=True)
        m = folium.Map(location=[-1.95, 30.12], zoom_start=12)
        folium.Marker([-1.95, 30.12], tooltip="Site").add_to(m)
        st_folium(m, width=None, height=420)
        st.caption("Replace with your site lat/lon and layer roads/plots as needed.")
    else:
        st.info("Map dependencies not installed. Add 'folium' and 'streamlit-folium' to requirements.txt to enable the map tab.")

# -------------------- Report --------------------
with t4:
    st.markdown("<div class='section-title'>Scenario Summary</div>", unsafe_allow_html=True)
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Inputs**")
        st.json({
            "storm_mm": storm_mm, "area_m2": area_m2, "slope_pct": slope_pct, "base_cn": base_cn,
            "tank_m3": tank_m3, "vetiver_rows": vetiver_rows,
            "hugel_len_m": hugel_len_m, "hugel_height_m": hugel_height_m,
            "pav_area_m2": pav_area_m2, "years": years
        })
    with cols[1]:
        st.markdown("**Outputs**")
        st.json({
            "rainfall_m3": round(out.rainfall_m3, 2),
            "captured_m3": round(out.captured_m3, 2),
            "runoff_m3": round(out.runoff_m3, 2),
            "peak_proxy_lps": round(out.peak_proxy_lps, 2),
            "erosion_index": round(out.erosion_index, 3)
        })

    st.download_button(
        "⬇️ Download results (CSV)",
        data=pd.DataFrame([{
            **vars(ScenarioInputs(storm_mm, area_m2, slope_pct, base_cn, tank_m3, vetiver_rows, hugel_len_m, hugel_height_m, pav_area_m2, years)),
            **{k: v for k, v in vars(out).items()}
        }]).to_csv(index=False).encode('utf-8'),
        file_name="scenario_results.csv",
        mime="text/csv"
    )

    st.markdown("---")
    st.caption("Export this CSV and attach it to your memo or slides.")

