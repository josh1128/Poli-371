# rwabutenge_3d_streamlit.py
# Streamlit + deck.gl (pydeck) interactive 3D environment for HOPE Rwanda (Rwabutenge, Gahanga, Kicukiro)
# - Realistic terrain using Mapbox Terrain-RGB (requires a Mapbox token)
# - Satellite texture draped over terrain using Esri World Imagery (public tile service)
# - Live 3D buildings from OpenStreetMap via Overpass API (extruded by height / levels)
# - Adjustable vertical exaggeration, search radius, and building toggles
# - Optional site boundary (paste GeoJSON)
#
# Quick start (locally):
#   pip install streamlit pydeck requests
#   (optional) pip install shapely
#   streamlit run rwabutenge_3d_streamlit.py
#
# If you deploy to Streamlit Cloud, set an environment secret named MAPBOX_TOKEN

import os
import json
import re
import math
import requests
import streamlit as st
import pydeck as pdk

# ------------------------- Page setup -------------------------
st.set_page_config(page_title="HOPE Rwanda – Rwabutenge 3D", layout="wide")
st.title("HOPE Rwanda: Rwabutenge 3D Environment")
st.caption("Interactive terrain + satellite + OSM buildings. Tweak the controls in the sidebar.")

# ------------------------- Sidebar controls -------------------------
st.sidebar.header("Location & Data Sources")
# NOTE: If you know the exact coordinates of the site center, set them here.
# The defaults place you on the SE side of Kigali near Gahanga Sector.
center_lat = st.sidebar.number_input("Center latitude", value=-2.030, format="%0.6f")
center_lon = st.sidebar.number_input("Center longitude", value=30.139, format="%0.6f")

radius_m = st.sidebar.slider("Search radius for OSM buildings (m)", min_value=200, max_value=4000, value=1500, step=100)

st.sidebar.header("Rendering & Layers")
exaggeration = st.sidebar.slider("Vertical exaggeration (×)", min_value=1.0, max_value=8.0, value=2.0, step=0.1)
show_buildings = st.sidebar.toggle("Show 3D buildings (OSM)", value=True)
base_opacity = st.sidebar.slider("Satellite texture opacity", 0.2, 1.0, 0.95, 0.05)

st.sidebar.header("Mapbox Token")
mapbox_token = st.sidebar.text_input(
    "MAPBOX_TOKEN (required for terrain)",
    value=os.getenv("MAPBOX_TOKEN", ""),
    type="password",
    help="Create one at https://account.mapbox.com. Required for Terrain-RGB elevation tiles."
)

st.sidebar.header("Optional Site Boundary")
use_boundary = st.sidebar.toggle("Overlay site boundary (GeoJSON)", value=False)
boundary_geojson_text = ""
if use_boundary:
    boundary_geojson_text = st.sidebar.text_area(
        "Paste GeoJSON Feature/FeatureCollection (Polygon/LineString)",
        value="",
        height=140,
        help="Paste a valid GeoJSON geometry for your site boundary."
    )

# ------------------------- Helpers -------------------------
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

@st.cache_data(show_spinner=True, ttl=60*30)
def fetch_osm_buildings(lat: float, lon: float, radius_m: int):
    """Fetch building footprints around (lat, lon) within radius using Overpass API.
    Returns a GeoJSON FeatureCollection with Polygon/MultiPolygon features and 'height' property (m).
    """
    # Overpass query: buildings around point
    # out geom gives node coordinates per way
    query = f"""
    [out:json][timeout:25];
    (
      way["building"](around:{radius_m},{lat},{lon});
      relation["building"](around:{radius_m},{lat},{lon});
    );
    out body geom tags;
    """
    resp = requests.post(OVERPASS_URL, data={"data": query})
    resp.raise_for_status()
    data = resp.json()

    # Build an index of nodes (not strictly needed when using 'geom')
    features = []

    def parse_height(tags):
        # Prefer explicit height in meters, else derive from levels (3 m/level)
        h = None
        if not tags:
            return None
        if "height" in tags:
            raw = str(tags.get("height"))
            m = re.match(r"([0-9]*\.?[0-9]+)", raw)
            if m:
                h = float(m.group(1))
        if h is None and ("building:levels" in tags or "levels" in tags):
            lv_raw = str(tags.get("building:levels", tags.get("levels", "")))
            m = re.match(r"([0-9]*\.?[0-9]+)", lv_raw)
            if m:
                levels = float(m.group(1))
                h = max(3.0, levels * 3.0)
        # Fallback modest height
        if h is None:
            h = 4.0
        return float(h)

    # Convert Overpass ways/relations into GeoJSON
    for el in data.get("elements", []):
        el_type = el.get("type")
        tags = el.get("tags", {})
        if not tags or "building" not in tags:
            continue
        height_m = parse_height(tags)

        if el_type == "way":
            geom = el.get("geometry", [])
            # Ensure closed ring
            coords = [(p["lon"], p["lat"]) for p in geom]
            if not coords:
                continue
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            # Skip tiny or invalid
            if len(coords) < 4:
                continue
            feature = {
                "type": "Feature",
                "properties": {
                    "name": tags.get("name", "building"),
                    "height": height_m,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                }
            }
            features.append(feature)
        elif el_type == "relation":
            # Basic multipolygon handling
            members = el.get("members", [])
            outers = []
            inners = []
            for mbr in members:
                if mbr.get("type") == "way" and "geometry" in mbr:
                    coords = [(p["lon"], p["lat"]) for p in mbr["geometry"]]
                    if not coords:
                        continue
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    if mbr.get("role") == "inner":
                        inners.append(coords)
                    else:
                        outers.append(coords)
            if outers:
                geom = {
                    "type": "MultiPolygon" if len(outers) > 1 else "Polygon",
                    "coordinates": [outers] if len(outers) > 1 else [outers[0]]
                }
                feature = {
                    "type": "Feature",
                    "properties": {
                        "name": tags.get("name", "building"),
                        "height": height_m,
                    },
                    "geometry": geom
                }
                features.append(feature)

    return {"type": "FeatureCollection", "features": features}

# ------------------------- Layers -------------------------
# Terrain-RGB (Mapbox) elevation tiles
terrain_url = None
if mapbox_token:
    terrain_url = (
        "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=" + mapbox_token
    )

# Esri World Imagery for realistic surface texture
texture_url = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

layers = []

if terrain_url:
    terrain = pdk.Layer(
        "TerrainLayer",
        data=None,
        elevation_decoder={  # Mapbox Terrain-RGB decoder
            "rScaler": 6553.6,  # 256*256*0.1
            "gScaler": 25.6,    # 256*0.1
            "bScaler": 0.1,     # 0.1
            "offset": -10000
        },
        texture=texture_url,
        elevation_data=terrain_url,
        max_zoom=15,
        min_zoom=0,
        strategy='no-overlap',
        opacity=base_opacity,
        wireframe=False,
        elevation_multiplier=exaggeration,
    )
    layers.append(terrain)
else:
    st.warning("Add a Mapbox token to render 3D terrain. The satellite texture will still appear as a flat basemap.")
    # Flat imagery as a fallback (BitmapLayer over a large quad)
    # Define a local bounds around the center to draw imagery bitmap
    # ~1.5 km square at this latitude
    dlat = 0.015
    dlon = 0.015
    bounds = [
        [center_lon - dlon, center_lat - dlat],
        [center_lon - dlon, center_lat + dlat],
        [center_lon + dlon, center_lat + dlat],
        [center_lon + dlon, center_lat - dlat],
    ]
    layers.append(
        pdk.Layer(
            "BitmapLayer",
            data=None,
            image=texture_url.replace("{z}", "16").replace("{y}", "24456").replace("{x}", "33212"),
            bounds=[b for b in bounds],
            opacity=base_opacity,
        )
    )

# Optional site boundary
if use_boundary and boundary_geojson_text.strip():
    try:
        boundary_obj = json.loads(boundary_geojson_text)
        # Wrap a single geometry into a Feature if needed
        if boundary_obj.get("type") in ("Polygon", "LineString", "MultiPolygon", "MultiLineString"):
            boundary_obj = {"type": "Feature", "properties": {}, "geometry": boundary_obj}
        # If it's a Feature, wrap to FeatureCollection for pydeck
        if boundary_obj.get("type") == "Feature":
            boundary_obj = {"type": "FeatureCollection", "features": [boundary_obj]}
        boundary_layer = pdk.Layer(
            "GeoJsonLayer",
            data=boundary_obj,
            stroked=True,
            filled=False,
            get_line_color=[255, 255, 0, 255],
            get_line_width=3,
        )
        layers.append(boundary_layer)
    except Exception as e:
        st.error(f"Boundary GeoJSON parse error: {e}")

# Buildings (extruded)
if show_buildings:
    with st.spinner("Loading OSM buildings from Overpass…"):
        try:
            buildings_geojson = fetch_osm_buildings(center_lat, center_lon, int(radius_m))
            if buildings_geojson["features"]:
                bldg_layer = pdk.Layer(
                    "GeoJsonLayer",
                    data=buildings_geojson,
                    extruded=True,
                    wireframe=False,
                    opacity=0.9,
                    get_elevation="properties.height",
                    get_fill_color="[30, 144, 255, 180]",  # dodgerblue
                    pickable=True,
                    auto_highlight=True,
                )
                layers.append(bldg_layer)
            else:
                st.info("No building footprints returned for this radius.")
        except Exception as e:
            st.warning(f"Overpass request failed: {e}")

# ------------------------- View / Lighting -------------------------
initial_view = pdk.ViewState(
    latitude=center_lat,
    longitude=center_lon,
    zoom=15.5,
    pitch=60,
    bearing=30,
)

# Nice lighting for 3D
ambient_light = {
    "type": "AmbientLight",
    "color": [255, 255, 255],
    "intensity": 1.0,
}

directional_light = {
    "type": "DirectionalLight",
    "color": [255, 255, 255],
    "intensity": 2.0,
    "direction": [-1, -3, -1],  # sun-ish
}

effects = [
    {"type": "LightingEffect", "lights": [ambient_light, directional_light]}
]

# Tooltip for buildings
tooltip = {
    "html": "<b>{name}</b><br/>Height: {height} m",
    "style": {"backgroundColor": "#2e2e2e", "color": "white"}
}

# ------------------------- Render deck -------------------------
r = pdk.Deck(
    layers=layers,
    initial_view_state=initial_view,
    map_provider=None,  # we'll provide our own terrain/imagery
    views=[pdk.View(type="MapView", controller=True)],
    effects=effects,
    tooltip=tooltip,
)

st.pydeck_chart(r, use_container_width=True)

# ------------------------- Footer hints -------------------------
st.markdown(
    """
**Tips**
- For best realism, provide a valid **Mapbox token** (Terrain-RGB) and keep **satellite opacity** near 1.0.
- If you know your exact site polygon, toggle **Overlay site boundary** and paste a small GeoJSON.
- Increase **Vertical exaggeration** to emphasize relief; reduce if peaks look distorted.
- Expand **Search radius** to load more OSM buildings (larger areas take longer to fetch).
    """
)

