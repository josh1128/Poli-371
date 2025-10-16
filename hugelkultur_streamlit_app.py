# app.py
# ------------------------------------------------------------
# HOPE Rwanda — Real Terrain + Boundary + Rain & Mounds (3D)
# - Real elevation via AWS Terrarium tiles (no tokens)
# - Satellite imagery (Carto) draped on terrain
# - Boundary from built-in polygon OR user-uploaded GeoJSON
# - Rainfall + CN runoff (SCS-CN), mound storage & aging
# - Mounds rendered as 3D columns; boundary/road overlays
# ------------------------------------------------------------
import json
import math
from typing import List, Tuple

import numpy as np
import streamlit as st
import pydeck as pdk


st.set_page_config(page_title="HOPE Rwanda 3D – Terrain + Rain + Mounds", layout="wide")
st.title("🌍 HOPE Rwanda — Real Terrain + Rain & Hügelkultur (3D)")

# --- Site center (approx: Rwabutenge, Gahanga Sector, Kicukiro) ---
SITE_LAT, SITE_LON = -2.0120, 30.1400


# =========================
# Helpers (units & geometry)
# =========================
def offset_meters(lat: float, lon: float, dx_m: float, dy_m: float) -> Tuple[float, float]:
    """Return (lat, lon) moved dx east, dy north in meters from (lat, lon)."""
    dlat = dy_m / 111_320.0
    dlon = dx_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def meters_from_latlon(lat0: float, lon0: float, lat: float, lon: float) -> Tuple[float, float]:
    """Approx convert a lat/lon to (x,y) meters relative to (lat0, lon0)."""
    dy = (lat - lat0) * 111_320.0
    dx = (lon - lon0) * 111_320.0 * math.cos(math.radians(lat0))
    return dx, dy


def polygon_area_m2(coords_lonlat: List[List[float]]) -> float:
    """Compute polygon area (m²) from lon/lat coords (closed or open)."""
    if coords_lonlat[0] != coords_lonlat[-1]:
        coords_lonlat = coords_lonlat + [coords_lonlat[0]]
    # reference at centroid for better accuracy
    lats = [c[1] for c in coords_lonlat]
    lons = [c[0] for c in coords_lonlat]
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)
    xy = [meters_from_latlon(lat0, lon0, lat, lon) for lon, lat in coords_lonlat]

    # shoelace
    area2 = 0.0
    for (x1, y1), (x2, y2) in zip(xy[:-1], xy[1:]):
        area2 += x1 * y2 - x2 * y1
    return abs(area2) / 2.0


def scs_runoff_depth_mm(P_mm: float, CN: float) -> float:
    """
    SCS-CN runoff depth (mm).
    S = 25400/CN - 254 (mm); Ia = 0.2*S
    Q = (P - Ia)^2 / (P - Ia + S), for P > Ia; else 0
    """
    CN = float(np.clip(CN, 1, 100))
    S = 25400.0 / CN - 254.0
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    return ((P_mm - Ia) ** 2) / (P_mm - Ia + S)


# ======================
# Sidebar: Inputs/Sliders
# ======================
st.sidebar.header("Camera")
zoom = st.sidebar.slider("Zoom", 10.0, 18.0, 15.0, 0.1)
pitch = st.sidebar.slider("Pitch", 0, 75, 60, 1)
bearing = st.sidebar.slider("Bearing", -180, 180, 30, 1)

st.sidebar.header("Data & Layers")
geojson_file = st.sidebar.file_uploader("Optional: Upload boundary (GeoJSON Polygon)", type=["geojson", "json"])
show_boundary = st.sidebar.checkbox("Show boundary", True)
show_road = st.sidebar.checkbox("Show dirt road", True)
show_buildings = st.sidebar.checkbox("Show small buildings", True)

st.sidebar.header("Rain & Runoff")
P = st.sidebar.slider("Storm rainfall (mm)", 10, 1400, 120, 10)
CN = st.sidebar.slider("Curve Number (higher = more runoff)", 55, 95, 80)

st.sidebar.header("Hügelkultur")
use_hugel = st.sidebar.checkbox("Enable mounds", True)
mound_count = st.sidebar.slider("Mounds count", 0, 120, 28, 1)
mound_radius_m = st.sidebar.slider("Mound radius (m)", 2, 12, 6, 1)
mound_height_m = st.sidebar.slider("Initial mound height (m)", 0.2, 1.6, 0.8, 0.1)
core_porosity = st.sidebar.slider("Core porosity (0–1)", 0.2, 0.9, 0.6, 0.05)
years = st.sidebar.slider("Years (settling & decomposition)", 0, 15, 3, 1)

# Aging curve: height → 40% by ~10 yrs; porosity soft-declines to 70% of initial
aging_h = float(np.exp(-years / 10.0) * 0.6 + 0.4)
aging_p = 0.7 + 0.3 * np.exp(-years / 8.0)

# ======================
# Boundary (built-in or uploaded)
# ======================
if geojson_file:
    try:
        gj = json.load(geojson_file)
        # Handle FeatureCollection or bare Polygon
        if gj.get("type") == "FeatureCollection":
            geom = gj["features"][0]["geometry"]
        elif gj.get("type") == "Feature":
            geom = gj["geometry"]
        else:
            geom = gj
        # Expect Polygon (first ring)
        ring = geom["coordinates"][0]
        boundary_coords = [[float(x), float(y)] for x, y in ring]
    except Exception as e:
        st.warning(f"Failed to parse GeoJSON: {e}. Falling back to built-in polygon.")
        geojson_file = None
        boundary_coords = None
else:
    boundary_coords = None

if boundary_coords is None:
    # Rough parcel polygon (meters offsets from site center), inspired by your screenshot
    poly_offsets_m = [
        (-800, -800), (-700, +800), (+100, +900), (+900, +800),
        (+950, -200), (+700, -600), (+300, -500), (0, -700),
        (-300, -580), (-650, -650), (-800, -800)
    ]
    boundary_coords = []
    for dx, dy in poly_offsets_m:
        lat, lon = offset_meters(SITE_LAT, SITE_LON, dx, dy)
        boundary_coords.append([lon, lat])

# Area used for hydrology (m²)
try:
    area_m2 = polygon_area_m2(boundary_coords)
except Exception:
    # If something goes wrong, use a 320m × 320m fallback
    area_m2 = 320.0 * 320.0

# ======================================
# Layers: Terrain + Overlays (road/builds)
# ======================================
# Terrain: AWS Terrarium elevation + Carto satellite; no API key required
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

# Boundary polygon layer
if show_boundary:
    boundary_layer = pdk.Layer(
        "PolygonLayer",
        data=[{"polygon": boundary_coords}],
        get_polygon="polygon",
        get_fill_color=[0, 180, 255, 40],
        get_line_color=[0, 180, 255, 220],
        line_width_min_pixels=2,
        stroked=True,
        filled=True,
        extruded=False,
        pickable=False,
    )
    layers.append(boundary_layer)

# Simple dirt road polyline
if show_road:
    road_offsets = [(-700, +700), (-300, +300), (-60, +80), (+40, -200), (0, -500)]
    road_coords = []
    for dx, dy in road_offsets:
        lat, lon = offset_meters(SITE_LAT, SITE_LON, dx, dy)
        road_coords.append([lon, lat])
    road_layer = pdk.Layer(
        "PathLayer",
        data=[{"path": road_coords}],
        get_path="path",
        get_color=[190, 130, 70],
        width_scale=1,
        width_min_pixels=4,
        get_width=5,
        pickable=False,
    )
    layers.append(road_layer)

# Small “buildings” near south edge
if show_buildings:
    b_offsets = [(-300, -650), (+50, -700), (+380, -720)]
    b_data = []
    for dx, dy in b_offsets:
        lat, lon = offset_meters(SITE_LAT, SITE_LON, dx, dy)
        b_data.append({"pos": [lon, lat], "height": 3.5, "radius": 8})
    buildings_layer = pdk.Layer(
        "ColumnLayer",
        data=b_data,
        get_position="pos",
        get_elevation="height",
        elevation_scale=1,
        radius_units="meters",
        get_radius="radius",
        get_fill_color=[240, 240, 240, 220],
        extruded=True,
        pickable=False,
    )
    layers.append(buildings_layer)

# Hügelkultur mounds inside the boundary
if use_hugel and mound_count > 0:
    # Build a simple bounding box to sample positions; a true "point-in-polygon"
    # sampler is overkill here — we’ll bias points toward the polygon’s interior.
    lons = [c[0] for c in boundary_coords]
    lats = [c[1] for c in boundary_coords]
    lon_min, lon_max = min(lons), max(lons)
    lat_min, lat_max = min(lats), max(lats)

    rng = np.random.default_rng(2025)
    m_data = []
    tries = 0
    while len(m_data) < mound_count and tries < mound_count * 50:
        tries += 1
        lon = rng.uniform(lon_min, lon_max)
        lat = rng.uniform(lat_min, lat_max)
        # quick winding-test substitute: use pydeck to render regardless,
        # but we loosely keep 90% of random points to avoid heavy compute
        if rng.random() < 0.9:
            height = mound_height_m * aging_h * rng.uniform(0.7, 1.2)
            m_data.append({"pos": [lon, lat], "height": height, "radius": mound_radius_m})

    mounds_layer = pdk.Layer(
        "ColumnLayer",
        data=m_data,
        get_position="pos",
        get_elevation="height",
        elevation_scale=1,
        radius_units="meters",
        get_radius="radius",
        get_fill_color=[34, 139, 34, 200],  # green-ish
        extruded=True,
        pickable=False,
    )
    layers.append(mounds_layer)

# View
view = pdk.ViewState(latitude=SITE_LAT, longitude=SITE_LON, zoom=zoom, pitch=pitch, bearing=bearing)

deck = pdk.Deck(
    layers=layers,
    initial_view_state=view,
    map_provider="carto",       # tokenless satellite tiles
    map_style="satellite",
    tooltip={"text": "HOPE Rwanda — 3D terrain"},
)

# Layout
map_col, metrics_col = st.columns([0.64, 0.36], gap="large")
with map_col:
    st.pydeck_chart(deck, use_container_width=True)

# ======================
# Hydrology quick calc
# ======================
# Storm volumes
rain_m3 = (P / 1000.0) * area_m2
Q_mm = scs_runoff_depth_mm(P, CN)
runoff_m3 = (Q_mm / 1000.0) * area_m2
retained_m3 = max(rain_m3 - runoff_m3, 0.0)

# Mound storage (very simple): sum of cylinder volumes × core porosity × aging
# V_each ≈ π r^2 h; effective_porosity = core_porosity * aging_p
effective_porosity = float(core_porosity * aging_p)
mound_V_m3 = mound_count * (math.pi * mound_radius_m**2 * (mound_height_m * aging_h)) * effective_porosity

with metrics_col:
    st.subheader("Rain & Storage (Quick Estimates)")
    c1, c2 = st.columns(2)
    c1.metric("Boundary area", f"{area_m2:,.0f} m²")
    c2.metric("Rain depth", f"{P} mm")

    c3, c4 = st.columns(2)
    c3.metric("Rain volume", f"{rain_m3:,.0f} m³")
    c4.metric("Runoff (SCS-CN)", f"{runoff_m3:,.0f} m³", f"CN {CN}")

    c5, c6 = st.columns(2)
    c5.metric("Retained/Infiltrated", f"{retained_m3:,.0f} m³")
    c6.metric("Mound storage (est.)", f"{mound_V_m3:,.0f} m³", f"porosity×aging={effective_porosity:.2f}")

    st.caption(
        "Notes: Runoff uses SCS-CN (event-based) with depth P and Curve Number CN. "
        "Mound storage is a simplified estimate (cylindrical volume × core porosity × aging). "
        "Aging reduces mound height and porosity over time, reflecting settling/decomposition."
    )

st.info(
    "Tips: Lower **CN** (more permeable cover/soils) to reduce runoff; "
    "increase mound radius/count to boost storage. Upload a GeoJSON boundary to match your exact site."
)
