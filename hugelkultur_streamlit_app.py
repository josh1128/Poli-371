
import math
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="Hügelkultur Dynamics – HOPE Rwanda", layout="wide")

st.title("Hügelkultur Dynamics – HOPE Rwanda")
st.caption("Explore how mound size, wood porosity, and decomposition affect water storage and runoff over time.")

with st.expander("About this tool"):
    st.markdown("""
This dashboard models a **hügelkultur mound** as a sponge-like volume that **declines over time**
due to decomposition and settling. It uses a simple SCS Curve Number runoff estimate for a single storm,
then compares runoff volume to the mound's storage in each year.
            
**Notes drawn from your brief:**  
- Hügel beds are raised mounds of **wood + plant debris** topped with soil/compost.  
- They **retain water** like a sponge and **shrink** over several years as wood decomposes.  
- Typical mound **height ~ 5–6 ft (1.5–1.8 m)**; hardwoods like alder, birch, oak perform well.  
- Maintenance includes **adding soil/compost** as the mound settles.
""")

# ===================
# Sidebar Controls
# ===================
st.sidebar.header("Rainfall & Catchment")
P = st.sidebar.slider("Storm rainfall P (mm)", 10, 200, 60, 5)
A = st.sidebar.number_input("Contributing area A (m²)", min_value=10.0, value=500.0, step=10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1,
                       help="Higher CN = more runoff (e.g., compacted surfaces near roads).")

st.sidebar.header("Mound Geometry & Properties")
mound_length = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 15.0, 1.0)
mound_width = st.sidebar.number_input("Mound base width (m)", 0.5, 10.0, 2.0, 0.5)
mound_height0 = st.sidebar.number_input("Initial mound height (m)", 0.3, 3.0, 1.5, 0.1)
wood_porosity = st.sidebar.slider("Effective porosity of wood core (0–1)", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("Decomposition / Settling")
half_life_years = st.sidebar.slider("Wood volume half-life (years)", 1, 15, 6, 1,
                                    help="Time for wood storage capacity to halve due to decomposition.")
settling_frac_extra = st.sidebar.slider("Extra settling over 5y (%)", 0, 50, 15, 5,
                                        help="Additional storage loss not due to decomposition (soil collapse, compaction).")

years = st.sidebar.slider("Years to simulate", 1, 30, 12, 1)

# ===================
# Helper functions
# ===================
def scs_runoff_mm(P_mm, CN):
    """SCS runoff (mm) from storm depth P (mm)."""
    S = (25400 / CN) - 254  # potential max retention (mm)
    Ia = 0.2 * S            # initial abstraction (mm)
    if P_mm <= Ia:
        return 0.0
    Q = ((P_mm - Ia) ** 2) / (P_mm - Ia + S)
    return max(Q, 0.0)

def mound_initial_storage_m3(length_m, width_m, height_m, porosity):
    """Approximate sponge-like storage from triangular cross-section times length and porosity."""
    cross_area = 0.5 * width_m * height_m
    bulk_vol = cross_area * length_m
    return bulk_vol * porosity

def decay_series(initial_value, half_life, years, extra_settling_frac_5y=0.0):
    """Exponential decay with a linear extra-settling loss applied over first 5 years."""
    t = np.arange(0, years+1, 1)
    lam = math.log(2) / half_life
    decay_vals = initial_value * np.exp(-lam * t)
    extra = np.zeros_like(t, dtype=float)
    if years > 0 and extra_settling_frac_5y > 0:
        frac = extra_settling_frac_5y / 100.0
        ramp_years = min(5, years)
        ramp = np.linspace(0, frac * initial_value, ramp_years + 1)
        extra[:ramp_years+1] = ramp
        if years > ramp_years:
            extra[ramp_years+1:] = frac * initial_value
    values = decay_vals - extra
    values[values < 0] = 0.0
    return values

# ===================
# Core calculations
# ===================
Q_mm = scs_runoff_mm(P, CN)          # runoff depth in mm
runoff_m3 = Q_mm / 1000.0 * A        # event runoff volume (m³)

initial_storage_m3 = mound_initial_storage_m3(mound_length, mound_width, mound_height0, wood_porosity)
storage_time_series = decay_series(initial_storage_m3, half_life_years, years, settling_frac_extra)
intercepted_series = np.minimum(storage_time_series, runoff_m3)

# ===================
# Layout: two columns
# ===================
col1, col2 = st.columns([1,1])

with col1:
    st.subheader("Event Runoff & Initial Storage")
    m1, m2, m3 = st.columns(3)
    m1.metric("Runoff depth Q (mm)", f"{Q_mm:.1f}")
    m2.metric("Event runoff (m³)", f"{runoff_m3:.1f}")
    m3.metric("Initial mound storage (m³)", f"{initial_storage_m3:.1f}")
    st.caption("Runoff based on SCS CN method; storage from triangular mound × porosity.")

    st.subheader("Storage Decline Over Time")
    fig1, ax1 = plt.subplots(figsize=(6,3.5))
    ax1.plot(np.arange(0, years+1), storage_time_series, linewidth=2)
    ax1.set_xlabel("Year")
    ax1.set_ylabel("Mound Storage (m³)")
    st.pyplot(fig1)

with col2:
    st.subheader("Interception of This Storm Over Time")
    fig2, ax2 = plt.subplots(figsize=(6,3.5))
    ax2.plot(np.arange(0, years+1), intercepted_series, linewidth=2)
    ax2.set_xlabel("Year")
    ax2.set_ylabel("Intercepted Volume (m³)")
    st.pyplot(fig2)

st.markdown("---")

# ===================
# Schematic (simple)
# ===================
st.subheader("Schematic (Not to Scale)")
st.caption("Adjust mound size and porosity to see how the schematic annotations change.")

fig3, ax3 = plt.subplots(figsize=(8, 3))
# Draw ground
ax3.plot([0, 10], [2, 2], linewidth=3)
# Mound as triangle
height = max(mound_height0, 0.1)
width = max(mound_width, 0.5)
left = 5 - width/2
right = 5 + width/2
ax3.fill([left, 5, right], [2, 2+height, 2], alpha=0.6)
# Raindrops icons at top
for x in np.linspace(1, 9, 10):
    ax3.text(x, 4.9, "💧", ha="center", va="center", fontsize=9)
# Infiltration arrows
for x in np.linspace(left+0.2, right-0.2, 4):
    ax3.annotate("", xy=(x, 2.1), xytext=(x, 2+height*0.7),
                 arrowprops=dict(arrowstyle="-|>", lw=1.8))
# Labels
ax3.text(5, 2+height*0.85, "mulch + soil", ha="center", fontsize=9)
ax3.text(5, 2+height*0.45, "wood/organic core\n('sponge')", ha="center", fontsize=9)
ax3.axis("off")
st.pyplot(fig3)

# ===================
# Notes Panel (from your brief)
# ===================
st.markdown("---")
st.subheader("Your Notes (embedded)")
st.markdown("""
**What it is**  
- Raised beds of **rotten logs and plant debris** (composting wood) topped with compost/soil.  
- Typical mound **~5–6 ft high (≈1.5–1.8 m)**.  
- **Materials:** logs, branches, leaves, straw, cardboard, grass clippings, manure, compost.  
- **Best wood species:** alder, apple, birch, cottonwood, maple, oak, poplar, dry willow (hardwoods).  
- **Good crops:** cucumbers, legumes, melons, potatoes, squashes.

**Considerations**  
- Hügel beds **shrink over years** (wood shrinkage, decomposition, settling).  
- Steeper sides = harder to plant (seeds may wash).  
- Build in **fall** for spring planting.

**Maintenance**  
- **Top up soil** as mound shrinks.  
- Add **compost** before each planting season.

**Benefits**  
- More mass → **more water retention**.  
- Wood **stores rainwater** and releases it later.  
- Soil becomes **self-tilling** over time as wood breaks down.  
- Captures **surface runoff** (acts like a sponge).  
- **Slows runoff**, helps reduce erosion (including near dirt roads).  
- Generally **inexpensive**, can be **planted immediately**.

**Design tips**  
- **In-ground** hügel beds catch more runoff (but need more tools).  
- **Borders** (wood/brick/stone) keep the top layer from washing away.
""")

# Footer
st.markdown("---")
st.caption("Educational model for planning discussions. For engineering design, consult local standards and expert review.")

