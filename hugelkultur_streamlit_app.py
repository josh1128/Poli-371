# app.py
# ------------------------------------------------------------
# Kigali 3D Mini-World (Streamlit + PyDeck, no API keys needed)
# - Real elevation via AWS Terrarium tiles
# - Satellite texture (Carto) draped on terrain
# - Parcel boundary, a dirt road, tiny "buildings", optional mounds
# - Interactive camera + layer controls
# ------------------------------------------------------------
import math
import numpy as np
import streamlit as st
import pydeck as pdk


st.set_page_config(page_title="Kigali 3D Mini-World", layout="wide")
st.title("🌍 Kigali 3D Mini-World (HOPE Rwanda area)")

# --- Site location (approx; Rwabutenge, Gahanga Sector, Kicukiro) ---
SITE_LAT, SITE_LON = -2.0120, 30.1400

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Camera")
zoom = st.sidebar.slider("Zoom", 10.0, 17.5, 15.0, 0.1)
pitch = st.sidebar.slider("Pitch", 0, 75, 60, 1)
bearing = st.sidebar.slider("Bearing", -180, 180, 30, 1)

st.sidebar.header("Layers")
show_boundary = st.sidebar.checkbox("Parcel boundary", True)
show_road = st.sidebar.checkbox("Dirt road", True)
show_buildings = st.sidebar.checkbox("Small buildings", True)
use_hugel = st.sidebar.checkbox("Hügelkultur mounds", False)

if use_hugel:
    mound_count = st.sidebar.slider("Mounds count", 4, 60, 20, 1)
    mound_radius_m = st.sidebar.slider("Mound radius (m)", 2, 12, 6, 1)
    years = st.sidebar.slider("Years (settling)", 0, 12, 3, 1)
else:
    mound_count, mound_radius_m, years = 0, 0, 0

# --- INITIAL VIEW ---
view = pdk.ViewState(
    latitude=SITE_LAT,
    longitude=SITE_LON,
    zoom=zoom,
    pitch=pitch,
    bearing=bearing,
)

# --- BASE TERRAIN (no API keys required) ---
# Uses satellite texture + Terrarium elevation tiles
terrain = pdk.Layer(
    "TerrainLayer",
    data=None,
    elevation_decoder={"rScaler": 256.0, "gScaler": 1.0, "bScaler": 1.0/256.0, "offset": -32768.0},
    texture="https://basemaps.cartocdn.com/rastertiles/satellite/{z}/{x}/{y}.png",
    elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
    wireframe=False,
    max_zoom=18,
    opacity=1.0,
)

layers = [terrain]

# --- HELPER: quick offsets in meters to lat/lon ---
def offset_meters(lat, lon, dx_m, dy_m):
    # dx east-west, dy north-south
    dlat = (dy_m / 111_320.0)
    dlon = (dx_m / (111_320.0 * math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon

# --- PARCEL BOUNDARY (rough polygon inspired by screenshot) ---
# Define polygon by offsets (meters) relative to site center
poly_offsets = [
    (-800, -800), (-700, +800), (+100, +900), (+900, +800),
    (+950, -200), (+700, -600), (+300, -500), (0, -700),
    (-300, -580), (-650, -650), (-800, -800)
]
boundary_coords = []
for dx, dy in poly_offsets:
    lat, lon = offset_meters(SITE_LAT, SITE_LON, dx, dy)
    boundary_coords.append([lon, lat])

if show_boundary:
    boundary = pdk.Layer(
        "PolygonLayer",
        data=[{"polygon": boundary_coords, "name": "Site"}],
        get_polygon="polygon",
        get_fill_color=[255, 140, 0, 40],
        get_line_color=[255, 140, 0, 220],
        line_width_min_pixels=2,
        stroked=True,
        filled=True,
        extruded=False,
        pickable=False,
    )
    layers.append(boundary)

# --- DIRT ROAD (simple polyline) ---
if show_road:
    road_offsets = [(-700, +700), (-300, +300), (-60, +80), (+40, -200), (0, -500)]
    road_coords = []
    for dx, dy in road_offsets:
        lat, lon = offset_meters(SITE_LAT, SITE_LON, dx, dy)
        road_coords.append([lon, lat])

    road = pdk.Layer(
        "PathLayer",
        data=[{"path": road_coords}],
        get_path="path",
        get_color=[180, 120, 60],
        width_scale=1,
        width_min_pixels=4,
        get_width=5,
        pickable=False,
    )
    layers.append(road)

# --- SMALL "BUILDINGS" as low columns near south edge ---
if show_buildings:
    b_offsets = [(-300, -650), (+50, -700), (+380, -720)]
    b_data = []
    for dx, dy in b_offsets:
        lat, lon = offset_meters(SITE_LAT, SITE_LON, dx, dy)
        b_data.append({"pos": [lon, lat], "height": 3.5, "radius": 8})
    buildings = pdk.Layer(
        "ColumnLayer",
        data=b_data,
        get_position="pos",
        get_elevation="height",
        elevation_scale=1,
        radius_units="meters",
        get_radius="radius",
        get_fill_color=[240, 240, 240, 200],
        pickable=False,
        extruded=True,
    )
    layers.append(buildings)

# --- HÜGELKULTUR MOUNDS (small cylinders) ---
if use_hugel and mound_count > 0:
    rng = np.random.default_rng(2025)
    # aging: mound height decays toward ~40% by year 10
    aging = float(np.exp(-years / 10.0) * 0.6 + 0.4)
    m_data = []
    for _ in range(mound_count):
        dx = rng.uniform(-200, +700)
        dy = rng.uniform(-200, +500)
        lat, lon = offset_meters(SITE_LAT, SITE_LON, dx, dy)
        height = rng.uniform(0.5, 1.2) * aging
        m_data.append({"pos": [lon, lat], "height": height, "radius": mound_radius_m})
    mounds = pdk.Layer(
        "ColumnLayer",
        data=m_data,
        get_position="pos",
        get_elevation="height",
        elevation_scale=1,
        radius_units="meters",
        get_radius="radius",
        get_fill_color=[34, 139, 34, 180],
        pickable=False,
        extruded=True,
    )
    layers.append(mounds)

# --- RENDER ---
deck = pdk.Deck(
    layers=layers,
    initial_view_state=view,
    map_provider="carto",          # no token needed
    map_style="satellite",
    tooltip={"text": "Kigali 3D mini-world"},
)
st.pydeck_chart(deck, use_container_width=True)

st.caption(
    "Notes: Terrain uses AWS Terrarium elevation tiles + Carto satellite imagery. "
    "Adjust Zoom/Pitch/Bearing for different angles. Boundary/road are illustrative."
)
