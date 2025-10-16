import streamlit as st
from streamlit.components.v1 import html as st_html

# Lonboard + friends
from lonboard import Map, PolygonLayer, ScatterplotLayer
from lonboard.basemap import CartoBasemap
import geopandas as gpd

st.set_page_config(page_title="Rwanda 3D Mini Environment (Lonboard)", layout="wide")
st.title("🇷🇼 Rwanda – 3D-style Mini Environment (Lonboard)")

# ---- Sidebar controls ----
st.sidebar.header("View & Style")
basemap = st.sidebar.selectbox(
    "Basemap",
    ["Carto Positron (no labels)", "Carto Dark Matter (no labels)"],
    index=0,
)
pitch = st.sidebar.slider("Pitch (tilt)", 0, 85, 55, 1)
bearing = st.sidebar.slider("Bearing (heading)", 0, 360, 20, 5)
zoom = st.sidebar.slider("Zoom", 4, 10, 6, 1)

st.sidebar.header("Optional: Extruded Polygons")
geojson_url = st.sidebar.text_input(
    "Rwanda GeoJSON URL (ADM0/ADM1). Paste a direct .geojson link",
    value="",
    help="Try a direct ADM0/ADM1 GeoJSON URL from the HDX geoBoundaries Rwanda page."
)
extrude = st.sidebar.checkbox("Extrude polygon(s)", value=True)
elevation = st.sidebar.slider("Extrusion height (m)", 100, 5000, 1200, 100)
fill_opacity = st.sidebar.slider("Fill opacity", 20, 255, 120, 5)
line_width = st.sidebar.slider("Outline width (m)", 0, 500, 80, 10)

# Kigali coords (center the camera here)
# Kigali ≈ lat -1.95, lon 30.06
center_lat, center_lon = -1.95, 30.06

# ---- Build layers ----
layers = []

# Optional extruded boundary layer
if geojson_url:
    try:
        gdf = gpd.read_file(geojson_url)
        # ensure CRS is WGS84 lon/lat
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)

        poly_layer = PolygonLayer.from_geopandas(
            gdf,
            extruded=extrude,
            get_elevation=elevation,                     # constant height per feature
            get_fill_color=[10, 140, 220, fill_opacity], # semi-transparent cyan
            get_line_color=[0, 0, 0, 180],
            get_line_width=line_width,
            wireframe=False,
            pickable=True,
            auto_highlight=True,
        )
        layers.append(poly_layer)
    except Exception as e:
        st.warning(f"Could not load GeoJSON: {e}")

# Add a simple marker for Kigali
kigali_gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy([center_lon], [center_lat]), crs=4326)
kigali_layer = ScatterplotLayer.from_geopandas(
    kigali_gdf,
    get_fill_color=[255, 80, 0, 220],
    get_radius=8000,   # meters
    pickable=False,
)
layers.append(kigali_layer)

# Pick basemap style
style = CartoBasemap.PositronNoLabels if "Positron" in basemap else CartoBasemap.DarkMatterNoLabels

# Create lonboard Map with tilted view
m = Map(
    layers=layers,
    basemap_style=style,
    view_state={"longitude": center_lon, "latitude": center_lat, "zoom": zoom, "pitch": pitch, "bearing": bearing},
    height="80vh",
    custom_attribution=["© OpenStreetMap contributors", "© Carto"]
)

# Embed Lonboard map into Streamlit via HTML
# NOTE: Lonboard's recommended render path is Jupyter widgets; in non-widget envs use .as_html()
# We use that here then inject with streamlit.components.v1.html
m_html = m.as_html().data
st_html(m_html, height=700)
