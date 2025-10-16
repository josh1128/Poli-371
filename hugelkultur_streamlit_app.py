# permeable_pavement_app.py
# Robust Streamlit app for permeable pavement visualization + stormwater balance
# (All computations live inside one function to avoid NameErrors from ordering.)

import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

# ---------- Page ----------
st.set_page_config(page_title="Permeable Pavements – Visualize & Simulate", layout="wide")
st.title("🧱 Permeable Pavements – Visualize & Simulate")

PAVEMENT_PRESETS = {
    "Porous asphalt":        {"k_mm_hr": 3000.0, "t_cm": 5.0,  "note": "Avoid over-compaction; preserve surface voids."},
    "Pervious concrete":     {"k_mm_hr": 2000.0, "t_cm": 12.0, "note": "Place/finish quickly; do not over-trowel."},
    "PICP (interlocking)":   {"k_mm_hr": 1200.0, "t_cm": 8.0,  "note": "Keep joints full of clean stone; vacuum as needed."},
}

# ---------- Sidebar inputs ----------
st.sidebar.header("Storm & Site")
P_mm   = st.sidebar.slider("Storm depth (mm)", 5, 1400, 80, 5)
T_hr   = st.sidebar.slider("Storm duration (hours)", 1.0, 48.0, 6.0, 0.5)
A_m2   = st.sidebar.number_input("Contributing area (m²)", 10.0, 100000.0, 400.0, 10.0)

st.sidebar.header("Pavement Type & Surface")
ptype  = st.sidebar.selectbox("Pavement type", list(PAVEMENT_PRESETS.keys()))
preset = PAVEMENT_PRESETS[ptype]
k_clean = st.sidebar.number_input("Clean surface permeability (mm/hr)", 100.0, 10000.0, float(preset["k_mm_hr"]), 100.0)
clog_pct = st.sidebar.slider("Clogging level (0% = clean, 80% = very clogged)", 0, 80, 10, 5)
surface_t_cm = st.sidebar.number_input("Surface thickness (cm)", 3.0, 50.0, float(preset["t_cm"]), 1.0)

st.sidebar.header("Reservoir Layers")
choker_t_cm = st.sidebar.slider("Choker layer thickness (cm)", 2, 5, 3)
base_t_cm   = st.sidebar.slider("Base reservoir thickness (cm)", 5, 25, 10)
sub_t_cm    = st.sidebar.slider("Subbase reservoir thickness (cm)", 10, 60, 25)
base_void   = st.sidebar.slider("Base void ratio (0–0.5)", 0.10, 0.50, 0.30, 0.01)
sub_void    = st.sidebar.slider("Subbase void ratio (0–0.5)", 0.10, 0.50, 0.35, 0.01)

st.sidebar.header("Soils & Underdrain")
soil_ksat = st.sidebar.number_input("Soil Ksat (mm/hr)", 0.5, 200.0, 10.0, 0.5)
use_drain = st.sidebar.checkbox("Include underdrain", value=False)
drain_Lps = st.sidebar.number_input("Underdrain capacity (L/s)", 0.0, 100.0, 2.0, 0.5) if use_drain else 0.0

st.sidebar.header("Conservatism & Losses")
edge_losses_pct = st.sidebar.slider("Edge/maintenance losses (%)", 0, 20, 5, 1)
storage_sf = st.sidebar.slider("Storage safety factor (0.8–1.2)", 0.8, 1.2, 1.0, 0.05)

# ---------- Helpers ----------
def mm_to_m(x): return x / 1000.0
def cm_to_m(x): return x / 100.0
def L_to_m3(x): return x / 1000.0

# ---------- Core calculation (single function so variables are always defined) ----------
def compute_balance(P_mm, T_hr, A_m2, k_clean, clog_pct, base_t_cm, sub_t_cm, base_void, sub_void,
                    soil_ksat, use_drain, drain_Lps, edge_losses_pct, storage_sf):
    # Effective surface permeability (clogging reduces capacity)
    k_eff_mm_hr = k_clean * (1.0 - clog_pct / 100.0)

    # Incoming rainfall (effective after small losses)
    rain_m3 = mm_to_m(P_mm) * A_m2
    rain_m3_eff = rain_m3 * (1.0 - edge_losses_pct / 100.0)

    # Surface infiltration capacity during event
    surf_cap_m3 = mm_to_m(k_eff_mm_hr * T_hr) * A_m2

    # Reservoir storage
    storage_m3 = storage_sf * (
        A_m2 * cm_to_m(base_t_cm) * base_void +
        A_m2 * cm_to_m(sub_t_cm)  * sub_void
    )

    # Soil exfiltration during event
    soil_exfil_m3 = mm_to_m(soil_ksat * T_hr) * A_m2

    # Underdrain outflow during event
    drain_m3 = L_to_m3(drain_Lps * 3600.0 * T_hr) if use_drain and drain_Lps > 0 else 0.0

    # What can pass surface during storm
    infiltr_through_surface_m3 = min(rain_m3_eff, surf_cap_m3)

    # Downstream of surface, how much can be handled during storm?
    handle_during_event_m3 = soil_exfil_m3 + drain_m3 + storage_m3

    # Overflow from reservoir (during event)
    overflow_m3 = max(0.0, infiltr_through_surface_m3 - handle_during_event_m3)

    # End-of-storm stored (cannot be negative, cannot exceed storage)
    stored_end_m3 = min(storage_m3, max(0.0, infiltr_through_surface_m3 - (soil_exfil_m3 + drain_m3)))

    # Surface-rejected water (never got through surface during event)
    surface_reject_m3 = max(0.0, rain_m3_eff - surf_cap_m3)

    # Total runoff = surface reject + overflow
    runoff_m3 = surface_reject_m3 + overflow_m3

    # Mass balance nudge
    err = rain_m3_eff - (runoff_m3 + soil_exfil_m3 + drain_m3 + stored_end_m3)
    if abs(err) > 1e-6:
        stored_end_m3 = max(0.0, stored_end_m3 + err)

    return {
        "k_eff_mm_hr": k_eff_mm_hr,
        "rain_m3_eff": rain_m3_eff,
        "surf_cap_m3": surf_cap_m3,
        "storage_m3": storage_m3,
        "soil_exfil_m3": soil_exfil_m3,
        "drain_m3": drain_m3,
        "infiltr_through_surface_m3": infiltr_through_surface_m3,
        "overflow_m3": overflow_m3,
        "stored_end_m3": stored_end_m3,
        "surface_reject_m3": surface_reject_m3,
        "runoff_m3": runoff_m3,
    }

res = compute_balance(
    P_mm, T_hr, A_m2, k_clean, clog_pct,
    base_t_cm, sub_t_cm, base_void, sub_void,
    soil_ksat, use_drain, drain_Lps, edge_losses_pct, storage_sf
)

# ---------- Layout ----------
left, right = st.columns([1.1, 0.9])

with left:
    st.subheader("Cross-section (not to scale)")
    # Build a simple cross-section; matplotlib only, no fancy libs
    fig, ax = plt.subplots(figsize=(6.4, 5.0))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    surf_h = surface_t_cm
    chok_h = choker_t_cm
    base_h = base_t_cm
    sub_h  = sub_t_cm
    total  = surf_h + chok_h + base_h + sub_h
    nh = lambda x: x / total

    y = 0.0
    layers = [
        ("Subbase reservoir", sub_h, (0.85, 0.92, 1.00), f"Void ≈ {sub_void:.2f}"),
        ("Base reservoir",    base_h, (0.80, 0.87, 0.98), f"Void ≈ {base_void:.2f}"),
        ("Choker/Bedding",    chok_h, (0.92, 0.92, 0.92), "Uniform stone"),
        (ptype,               surf_h, (0.75, 0.75, 0.75), f"k(eff) ≈ {res['k_eff_mm_hr']:.0f} mm/hr"),
    ]
    for name, h_cm, color, note in layers:
        h = nh(h_cm)
        ax.add_patch(plt.Rectangle((0.1, y), 0.8, h, facecolor=color, edgecolor="black"))
        ax.text(0.5, y + h/2, f"{name}\n{h_cm:.0f} cm\n{note}", ha="center", va="center", fontsize=9)
        y += h

    if use_drain and drain_Lps > 0:
        ax.plot([0.15, 0.85], [0.05, 0.05], lw=6)  # drain pipe
        ax.text(0.5, 0.02, f"Underdrain (~{drain_Lps:.1f} L/s)", ha="center", va="bottom", fontsize=9)

    ax.text(0.5, -0.02, f"Soil (Ksat ≈ {soil_ksat:.1f} mm/hr)", ha="center", va="top", fontsize=10)
    st.pyplot(fig)

    with st.expander("Construction & O&M tips"):
        st.markdown(
            f"- Keep fines/mud out of layers during construction to prevent clogging.\n"
            f"- **{ptype}**: {preset['note']}\n"
            f"- Avoid over-compacting subgrade; enable infiltration.\n"
            f"- Routine sweeping/vacuuming (esp. PICP joints) keeps the surface open.\n"
            f"- On steeper sites, terrace subgrades and consider an underdrain."
        )

with right:
    st.subheader("Event Water Balance")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rain volume (eff.)", f"{res['rain_m3_eff']:.1f} m³")
    c2.metric("Runoff / Overflow", f"{res['runoff_m3']:.1f} m³")
    c3.metric("Stored at end", f"{res['stored_end_m3']:.1f} m³")

    c4, c5, c6 = st.columns(3)
    c4.metric("Exfiltrated to soil", f"{res['soil_exfil_m3']:.1f} m³")
    c5.metric("Underdrain outflow", f"{res['drain_m3']:.1f} m³")
    c6.metric("Surface k (eff.)", f"{res['k_eff_mm_hr']:.0f} mm/hr")

    st.markdown("---")
    labels = ["Runoff", "Stored", "Soil Exfiltration", "Underdrain"]
    values = [res["runoff_m3"], res["stored_end_m3"], res["soil_exfil_m3"], res["drain_m3"]]

    fig2, ax2 = plt.subplots(figsize=(6.6, 3.6))
    ax2.bar(labels, values)
    ax2.set_ylabel("Volume (m³)")
    ax2.set_title("Where did the stormwater go?")
    vmax = max(values) if max(values) > 0 else 1.0
    for i, v in enumerate(values):
        ax2.text(i, v + 0.02 * vmax, f"{v:.1f}", ha="center", va="bottom", fontsize=9)
    st.pyplot(fig2)

with st.expander("How to get LOWER vs HIGHER runoff"):
    st.markdown(
        "- **Lower runoff**: decrease *Clogging*; increase *storm duration*; increase *Base/Subbase thickness* or *void ratios*; increase *Soil Ksat*; add or upsize *Underdrain*.\n"
        "- **Higher runoff (stress test)**: increase *Clogging*; shorten *storm duration*; reduce *reservoir thickness/voids*; turn off or shrink *Underdrain*; lower *Soil Ksat*."
    )
