# hugelkultur_viz_app.py
# Streamlit app: DYNAMIC hügelkultur schematic with a real-rain time simulation (no graphs).
# - Time-stepped rain (steady/burst/pulsed)
# - Adjust total rainfall (mm), duration (min), and animation speed
# - Same single-screen schematic; no charts—just a picture that updates

import math
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
import time
import random

# ---------- App setup ----------
st.set_page_config(page_title="Dynamic Hügelkultur", layout="wide")
st.title("Dynamic Hügelkultur (No Graphs)")

# ---------- Sidebar controls ----------
st.sidebar.header("Rainfall & Catchment")
# New: realistic rain controls (total + duration + hyetograph shape)
total_rain_mm = st.sidebar.slider("Total storm rain (mm)", 5, 300, 80, 5)
duration_min  = st.sidebar.slider("Storm duration (minutes)", 5, 240, 40, 5)
rain_shape    = st.sidebar.selectbox("Rain shape", ["Steady", "Front-loaded burst", "Back-loaded burst", "Pulsed"])
randiness     = st.sidebar.slider("Intensity randomness (0–smooth, 1–chaotic)", 0.0, 1.0, 0.15, 0.05,
                                  help="Adds natural variability to the minute-by-minute intensity.")
A = st.sidebar.number_input("Contributing area (m²)", min_value=10.0, value=300.0, step=10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1, help="Higher CN ⇒ more runoff (e.g., compacted/roadside).")

st.sidebar.header("Mound: Size & Sponge")
mound_length = st.sidebar.number_inpu


