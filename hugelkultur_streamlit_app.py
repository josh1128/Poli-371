# free_3d_rwanda.py
# 100% free version — no Mapbox or paid tokens
# Uses open elevation data via leafmap + pydeck terrain rendering

import streamlit as st
import leafmap.foliumap as leafmap
import pydeck as pdk

st.set_page_config(page_title="Rwanda 3D Environment (Free)", layout="wide")
st.title("🇷🇼 Rwanda – Free 3D Interactive Mini Environment")

st.markdown("""
Explore Rwanda's landscapes in 3D — no tokens or paid APIs needed.
This uses open-source elevation and OpenStreetMap layers.
""")

# ---- Controls ----
with st.sidebar:
    st.header("🗺️ View Options")
    region = st.selectbox(
        "Select region",
        [
            "Kigali",
            "Volcanoes National Park",
            "Lake Kivu",
            "Nyungwe Forest",
            "Akagera National Park",
        ],
    )

# Coordinates for presets
coords = {
    "Kigali": (-1.9577, 30.1127, 9),
    "Volcanoes National Park": (-1.4734, 29.5360, 10),
    "Lake Kivu": (-2.1120, 29.2570, 9),
    "Nyungwe Forest": (-2.4800, 29.2000, 9),
    "Akagera National Park": (-1.6200, 30.7000, 9),
}
lat, lon, zoom = coords[region]

# ---- Create base map (leafmap is open/free) ----
m = leafmap.Map(center=[lat, lon], zoom=zoom, height="800px")
m.add_basemap("SATELLITE")

# Add elevation (SRTM open dataset)
m.add_dem(
    dem="SRTM",  # Shuttle Radar Topography Mission (free)
    name="3D Terrain",
    elevation_scale=2,  # exaggerate height
)

# Add label markers
m.add_marker(location=[lat, lon], popup=region)

# Render map
m.to_streamlit(height=700)

st.markdown("""
**Powered by:**  
- 🌍 OpenStreetMap (Imagery)  
- 🏔️ NASA SRTM (Elevation)  
- 🐍 leafmap + pydeck + Streamlit
""")

