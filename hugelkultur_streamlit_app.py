# app.py
# Streamlit 3D Rwanda mini-environment (pydeck + Mapbox Terrain)
# Features:
# - 3D terrain with satellite texture (TerrainLayer)
# - Adjustable terrain exaggeration, zoom, pitch, bearing
# - Region presets across Rwanda
# - Points of interest with labels + tooltips
# - Graceful prompt if no Mapbox token is supplied

import os
import streamlit as st
import pydeck as pdk
import pandas as pd

st.set_page_config(page_title="Rwanda 3D Mini Environment", layout="wide")
st.title("🇷🇼 Rwanda — 3D Interactive Mini Environment")

# ----------------------------
# Mapbox token handling
# ----------------------------
# Priority: secrets -> env -> sidebar
default_token = st.secrets.get("MAPBOX_API_KEY", os.getenv("MAPBOX_API_KEY", ""))

with st.sidebar:
    st.header("🔑 Mapbox Access")
    token = st.text_input("Mapbox token (kept local to your session)", value=default_token, type="password")
    if token:
        os.environ["MAPBOX_API_KEY"] = token  # pydeck reads this env var

# If no token, explain and stop early
if not os.environ.get("MAPBOX_API_KEY"):
    st.warning(
        "A Mapbox token is required for 3D terrain + satellite imagery.\n\n"
        "Add MAPBOX_API_KEY to `.streamlit/secrets.toml` or paste it in the sidebar.\n\n"
        "➡ Get a free token at mapbox.com."
    )
    st.stop()

# ----------------------------
# Presets & POIs
# ----------------------------
PRESETS = {
    "Kigali (City)": {"lat": -1.9577, "lon": 30.1127, "zoom": 9.5, "pitch": 60, "bearing": 20},
    "Volcanoes National Park": {"lat": -1.4734, "lon": 29.5360, "zoom": 10.5, "pitch": 65, "bearing": 310},
    "Lake Kivu (Gisenyi–Kibuye)": {"lat": -2.1120, "lon": 29.2570, "zoom": 9.0, "pitch": 60, "bearing": 10},
    "Nyungwe Forest": {"lat": -2.4800, "lon": 29.2000, "zoom": 10.0, "pitch": 65, "bearing": 350},
    "Akagera (Savanna East)": {"lat": -1.6200, "lon": 30.7000, "zoom": 9.5, "pitch": 60, "bearing": 30},
}

POIS = pd.DataFrame([
    {"name": "Kigali City", "lat": -1.9577, "lon": 30.1127, "elev_m": 1567, "desc": "Capital; rolling highlands"},
    {"name": "Mt. Karisimbi", "lat": -1.4639, "lon": 29.4433, "elev_m": 4507, "desc": "Highest peak in Rwanda"},
    {"name": "Lake Kivu", "lat": -2.0420, "lon": 29.3510, "elev_m": 1460, "desc": "Rift valley lake"},
    {"name": "Nyungwe Forest", "lat": -2.4800, "lon": 29.2000, "elev_m": 2500, "desc": "Montane rainforest"},
    {"name": "Akagera Park", "lat": -1.6200, "lon": 30.7000, "elev_m": 1350, "desc": "Eastern savanna & wetlands"},
])

# ----------------------------
# Sidebar controls
# ----------------------------
with st.sidebar:
    st.header("🗺️ View Controls")

    preset = st.selectbox("Region preset", list(PRESETS.keys()), index=0)
    base = PRESETS[preset]

    st.subheader("Terrain & Camera")
    exaggeration = st.slider("Terrain vertical exaggeration", 1.0, 8.0, 2.5, 0.1)
    zoom = st.slider("Zoom", 6.0, 13.0, float(base["zoom"]), 0.1)
    pitch = st.slider("Pitch (tilt)", 0, 80, int(base["pitch"]), 1)
    bearing = st.slider("Bearing (compass)", 0, 359, int(base["bearing"]), 1)

    st.subheader("Labels")
    show_pois = st.checkbox("Show points of interest", value=True)
    label_size = st.slider("Label size", 10, 32, 18, 1)

    st.subheader("Visual Options")
    wireframe = st.checkbox("Wireframe overlay", value=False)
    shading = st.checkbox("Enable realistic lighting", value=True)

# ----------------------------
# Terrain Layer (deck.gl)
# ----------------------------
# Mapbox TerrainRGB as elevation source + Mapbox Satellite for texture
# (Requires MAPBOX_API_KEY)
terrain_layer = pdk.Layer(
    "TerrainLayer",
    data=None,  # tile-based
    elevation_data="mapbox://mapbox.terrain-rgb",
    texture="mapbox://mapbox.satellite",
    elevation_decoder={"rScaler": 6553.6, "gScaler": 25.6, "bScaler": 0.1, "offset": -10000},
    operation="terrain+draw",
    visible=True,
    wireframe=wireframe,
    # deck.gl prop name is 'material', but pydeck exposes via 'material' dict on Layer
    # We'll keep default PBR; lighting controlled via LightingEffect below
)

# Points of Interest (scatter) + Labels (text)
layers = [terrain_layer]

if show_pois:
    poi_scatter = pdk.Layer(
        "ScatterplotLayer",
        data=POIS,
        get_position=["lon", "lat"],
        get_radius=150,
        pickable=True,
        get_fill_color=[255, 255, 255],
        get_line_color=[0, 0, 0],
        line_width_min_pixels=1,
        stroked=True,
        filled=True,
        opacity=0.8,
    )
    poi_labels = pdk.Layer(
        "TextLayer",
        data=POIS,
        get_position=["lon", "lat"],
        get_text="name",
        get_size=label_size,
        get_color=[255, 255, 255],
        get_angle=0,
        get_text_anchor='"middle"',
        get_alignment_baseline='"top"',
        billboard=True,
        pickable=False,
        outline_color=[0, 0, 0],
        outline_width=4,
    )
    layers += [poi_scatter, poi_labels]

# Lighting (optional but makes mountains look more real)
effects = None
if shading:
    ambient = pdk.types.LightSpecification(
        "ambient", color=[255, 255, 255], intensity=1.0
    )
    dir1 = pdk.types.LightSpecification(
        "directional",
        color=[255, 255, 240],
        intensity=2.0,
        direction=[-1, -0.8, -0.2],  # azimuth/elevation-ish
    )
    dir2 = pdk.types.LightSpecification(
        "directional",
        color=[200, 210, 255],
        intensity=1.2,
        direction=[0.8, 0.2, -0.2],
    )
    effects = pdk.types.LightingEffect(ambient, dir1, dir2)

# ----------------------------
# Deck & View
# ----------------------------
view_state = pdk.ViewState(
    latitude=base["lat"],
    longitude=base["lon"],
    zoom=zoom,
    pitch=pitch,
    bearing=bearing,
)

tooltip = {
    "html": "<b>{name}</b><br/>Elevation: {elev_m} m<br/>{desc}",
    "style": {"backgroundColor": "rgba(0,0,0,0.7)", "color": "white"}
}

r = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    map_provider="mapbox",  # use Mapbox for the TerrainLayer texture
    map_style=None,  # None because TerrainLayer supplies satellite texture
    effects=[effects] if effects else None,
    tooltip=tooltip,
)

# Display
st.pydeck_chart(r)

# ----------------------------
# Mini helper / tips
# ----------------------------
with st.expander("💡 Tips & Notes"):
    st.markdown(
        """
- Drag to rotate, scroll to zoom. Increase **Pitch** for dramatic relief.  
- Use **Terrain vertical exaggeration** to emphasize mountains/valleys.  
- Toggle **Wireframe** to see the mesh.  
- If terrain looks flat: zoom in/out or increase pitch/exaggeration.  
- Want your own markers? Replace the `POIS` table with your locations.
        """
    )
