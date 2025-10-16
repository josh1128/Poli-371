# permeable_pavement_app.py
# Streamlit: Permeable Pavement Visualizer & Stormwater Simulator
# - Choose porous asphalt, pervious concrete, or PICP
# - Adjust storm depth/duration, area, slope, clogging, soil Ksat, layer thickness/voids
# - Toggle underdrain and size its capacity
# - Live water balance KPIs + bar chart
# - Cross-section drawing of layers that updates with inputs

import math
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

# -------------------- Page setup --------------------
st.set_page_config(page_title="Permeable Pavements – Visualize & Simulate", layout="wide")
st.title("🧱 Permeable Pavements – Visualize & Simulate")

st.caption(
    "Interactive demo for HOPE Rwanda: explore how porous asphalt, pervious concrete, "
    "or permeable interlocking concrete pavers (PICP) handle rainfall by storing, infiltrating, "
    "and draining water through layered stone reservoirs to the soil below."
)

# -------------------- Defaults by pavement type --------------------
PAVEMENT_PRESETS = {
    "Porous asphalt": {
        "surface_perm_mm_hr": 3_000,  # idealized clean surface permeability
        "surface_thick_cm": 5,
        "notes": "Porous asphalt relies on voids in the asphalt mix; avoid over-compaction."
    },
    "Pervious concrete": {
        "surface_perm_mm_hr": 2_000,
        "surface_thick_cm": 12,
        "notes": "Place/finish quickly; do not over-trowel the surface."
    },
    "Permeable interlocking concrete pavers (PICP)": {
        "surface_perm_mm_hr": 1_200,
        "surface_thick_cm": 8,
        "notes": "Infiltration occurs through joint stone between pavers; keep joints clean."
    },
}

# -------------------- Sidebar controls --------------------
st.sidebar.header("Storm & Site")

P = st.sidebar.slider("Storm depth (mm)", min_value=5, max_value=1400, value=80, step=5)
T = st.sidebar.slider("Storm duration (hours)", min_value=0.25, max_value=48.0, value=6.0, step=0.25)
A = st.sidebar.number_input("Contributing area (m²)", min_value=10.0, value=400.0, step=10.0)
slope = st.sidebar.slider("Surface slope (%)", 0.0, 12.0, 2.0, 0.5)

st.sidebar.header("Pavement Type & Surface")
ptype = st.sidebar.selectbox("Pavement type", list(PAVEMENT_PRESETS.keys()))
preset = PAVEMENT_PRESETS[ptype]

# Allow overrides
surface_perm = st.sidebar.number_input(
    "Clean surface permeability (mm/hr)",
    min_value=100.0, value=float(preset["surface_perm_mm_hr"]), step=100.0
)
clog = st.sidebar.slider("Clogging level (0% = clean, 80% = very clogged)", 0, 80, 10, 5)
surface_thick_cm = st.sidebar.number_input(
    "Surface thickness (cm)", min_value=3.0, value=float(preset["surface_thick_cm"]), step=1.0
)

st.sidebar.header("Reservoir Layers")
choker_thick_cm = st.sidebar.slider("Choker/bedding layer thickness (cm)", 2, 5, 3)
base_thick_cm   = st.sidebar.slider("Base reservoir thickness (cm)", 5, 25, 10)
subbase_thick_cm= st.sidebar.slider("Subbase reservoir thickness (cm)", 10, 60, 25)
base_void = st.sidebar.slider("Base void ratio (0–0.5)", 0.10, 0.50, 0.30, 0.01)
sub_void  = st.sidebar.slider("Subbase void ratio (0–0.5)", 0.10, 0.50, 0.35, 0.01)

st.sidebar.header("Soils & Underdrain")
soil_ksat = st.sidebar.number_input("Soil saturated hydraulic conductivity (mm/hr)", min_value=0.5, value=10.0, step=0.5)
underdrain_on = st.sidebar.checkbox("Include underdrain", value=False)
if underdrain_on:
    drain_capacity_lps = st.sidebar.number_input("Underdrain capacity (L/s)", min_value=0.5, value=2.0, step=0.5)
else:
    drain_capacity_lps = 0.0

st.sidebar.header("Conservatism & Extras")
edge_losses = st.sidebar.slider("Edge/maintenance/construction losses (%)", 0, 20, 5, 1)
safety_factor = st.sidebar.slider("Storage safety factor (0.8–1.2)", 0.8, 1.2, 1.0, 0.05)

# -------------------- Helper calculations --------------------
def mm_to_m(mm): return mm / 1000.0
def cm_to_m(cm): return cm / 100.0
def m3_to_L(m3): return m3 * 1000.0
def L_to_m3(L): return L / 1000.0

# Effective surface conductivity reduced by clogging:
# Simple model: k_eff = k_clean * (1 - clog%)
k_eff = surface_perm * (1.0 - clog / 100.0)  # mm/hr

# Storm volumes
rain_depth_m = mm_to_m(P)    # m
rain_vol_m3  = rain_depth_m * A  # m³ total on contributing area

# Losses (e.g., construction tracking fines, imperfect connectivity)
rain_vol_m3_eff = rain_vol_m3 * (1.0 - edge_losses / 100.0)

# Infiltration capacity through surface during the event (m³):
surface_cap_mm = k_eff * T  # mm over the event
surface_cap_m  = mm_to_m(surface_cap_mm)  # m water column
surface_cap_m3 = surface_cap_m * A        # m³

# Reservoir storage capacity (m³):
base_storage_m3    = A * cm_to_m(base_thick_cm) * base_void
subbase_storage_m3 = A * cm_to_m(subbase_thick_cm) * sub_void
storage_m3 = safety_factor * (base_storage_m3 + subbase_storage_m3)

# Soil exfiltration during event (m³):
soil_exfil_mm = soil_ksat * T  # mm event
soil_exfil_m3 = mm_to_m(soil_exfil_mm) * A

# Underdrain discharge during event (m³):
drain_m3 = 0.0
if underdrain_on and drain_capacity_lps > 0:
    drain_m3 = L_to_m3(drain_capacity_lps * 3600.0 * T)

# -------------------- Water balance logic --------------------
# 1) Rain hits surface; limited by surface infiltration capacity during event.
infil_through_surface_m3 = min(rain_vol_m3_eff, surface_cap_m3)

# 2) What reaches reservoir: (infiltrated water)
to_reservoir_m3 = infiltr_through_surface_m3

# 3) From reservoir, water can:
#    - be stored up to storage_m3
#    - exfiltrate to soil during event up to soil_exfil_m3
#    - leave via underdrain up to drain_m3
#    Any excess above (storage + exfil + drain) during the event overflows.
capacity_during_event_m3 = storage_m3 + soil_exfil_m3 + drain_m3
overflow_m3 = max(0.0, to_reservoir_m3 - capacity_during_event_m3)

# 4) End-of-storm stored volume (cannot be negative):
stored_end_m3 = min(storage_m3, max(0.0, to_reservoir_m3 - (soil_exfil_m3 + drain_m3)))

# 5) “Runoff” here = water that could not pass surface during the event + overflow from reservoir
surface_rejected_m3 = max(0.0, rain_vol_m3_eff - surface_cap_m3)
runoff_m3 = surface_rejected_m3 + overflow_m3

# 6) Accountability check (small rounding differences possible)
balance_err = rain_vol_m3_eff - (runoff_m3 + soil_exfil_m3 + drain_m3 + stored_end_m3)
if abs(balance_err) > 1e-6:
    # Nudge stored volume to balance
    stored_end_m3 = max(0.0, stored_end_m3 + balance_err)

# -------------------- UI Layout --------------------
left, right = st.columns([1.1, 0.9])

# ---------- Left: Cross-section + notes ----------
with left:
    st.subheader("Cross-section (not to scale)")
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Layer heights (normalized to figure)
    # We'll map cm directly to relative heights for an intuitive visual
    surf_h   = surface_thick_cm
    chok_h   = choker_thick_cm
    base_h   = base_thick_cm
    sub_h    = subbase_thick_cm
    total_h  = surf_h + chok_h + base_h + sub_h
    # Normalize:
    def nh(x): return x / total_h

    y0 = 0.0
    layers = [
        ("Subbase reservoir", sub_h, (0.85, 0.92, 1.00), f"Void≈{sub_void:.2f}"),
        ("Base reservoir",   base_h, (0.80, 0.87, 0.98), f"Void≈{base_void:.2f}"),
        ("Choker/Bedding",   chok_h, (0.92, 0.92, 0.92), "Uniform stone"),
        (ptype,              surf_h, (0.75, 0.75, 0.75), f"k≈{k_eff:.0f} mm/hr (eff.)"),
    ]

    for name, h_cm, color, note in layers:
        h = nh(h_cm)
        rect = plt.Rectangle((0.1, y0), 0.8, h, facecolor=color, edgecolor="black")
        ax.add_patch(rect)
        ax.text(0.5, y0 + h/2, f"{name}\n{h_cm:.0f} cm\n{note}",
                ha="center", va="center", fontsize=9)
        y0 += h

    # Underdrain icon (if any)
    if underdrain_on:
        ax.plot([0.15, 0.85], [0.05, 0.05], lw=6)
        ax.text(0.5, 0.02, f"Underdrain (~{drain_capacity_lps:.1f} L/s capacity)", ha="center", va="bottom", fontsize=9)

    # Soil label
    ax.text(0.5, -0.02, f"Soil (Ksat≈{soil_ksat:.1f} mm/hr)", ha="center", va="top", fontsize=10)

    st.pyplot(fig)

    with st.expander("Construction & O&M tips (summary)"):
        st.markdown(
            f"""
- **Keep fines out** during construction; protect layers from mud contamination to prevent clogging.  
- **{ptype}**: {preset['notes']}  
- **Subgrade**: Avoid over-compaction; enable infiltration to native soils.  
- **Maintenance**: Routine sweeping/vacuuming of surface (esp. joints for PICP) to reduce clogging; keep gutters/edges clean.  
- **Steeper sites**: Consider terraced subgrades and/or underdrains to control internal flow down slope.
"""
        )

# ---------- Right: KPIs + bar chart ----------
with right:
    st.subheader("Event Water Balance (end of storm)")

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Rain volume", f"{rain_vol_m3_eff:,.1f} m³")
    kpi2.metric("Runoff/Overflow", f"{runoff_m3:,.1f} m³")
    kpi3.metric("Stored in reservoir", f"{stored_end_m3:,.1f} m³")

    kpi4, kpi5, kpi6 = st.columns(3)
    kpi4.metric("Exfiltrated to soil", f"{soil_exfil_m3:,.1f} m³")
    kpi5.metric("Underdrain outflow", f"{drain_m3:,.1f} m³")
    kpi6.metric("Surface k (eff.)", f"{k_eff:,.0f} mm/hr")

    st.markdown("---")

    # Bar chart
    labels = ["Runoff", "Stored", "Soil Exfiltration", "Underdrain"]
    values = [runoff_m3, stored_end_m3, soil_exfil_m3, drain_m3]

    fig2, ax2 = plt.subplots(figsize=(6.6, 3.5))
    ax2.bar(labels, values)
    ax2.set_ylabel("Volume (m³)")
    ax2.set_title("Where did the stormwater go?")
    for idx, v in enumerate(values):
        ax2.text(idx, v + max(values)*0.02 if max(values) > 0 else 0.02, f"{v:.1f}", ha="center", va="bottom", fontsize=9)
    st.pyplot(fig2)

# -------------------- Explanations --------------------
with st.expander("How this simulation works"):
    st.markdown(
        """
**Surface infiltration** is limited by the pavement's effective permeability over the storm duration.  
That water enters the **stone reservoirs** (base + subbase), which have storage based on thickness × area × void ratio.  
During the storm, water can **exfiltrate to soil** (limited by soil Ksat) and, if present, **drain out** via an underdrain (limited by its capacity).  
If incoming water exceeds the sum of **surface capacity + soil exfiltration + drain + storage**, the excess appears as **runoff/overflow**.
"""
    )

with st.expander("Which sliders to tweak for lower vs higher runoff?"):
    st.markdown(
        """
- **To lower runoff**: decrease *clogging*, increase *storm duration* (same depth), increase *base/subbase thickness* or *void ratios*, increase *soil Ksat*, and/or enable a higher-capacity *underdrain*.  
- **To increase runoff** (stress test): increase *clogging*, shorten *storm duration* (same depth), reduce *reservoir thickness/voids*, turn off or shrink the *underdrain*, and/or lower *soil Ksat*.
"""
    )

with st.expander("Notes on suitability for HOPE Rwanda’s narrow access roads"):
    st.markdown(
        """
Permeable pavements are best in **low-speed, low-traffic** areas like small access roads and parking pads.  
They combine **drivable surface + stormwater management** in a compact footprint—useful where right-of-way is tight or slopes are present.  
For steeper hills, use **terraced subgrades** and consider **underdrains** to manage internal flow downslope.
"""
    )
