import streamlit as st
from textwrap import dedent
import json

st.set_page_config(page_title="Interactive 3D Forest", layout="wide")
st.title("🌲 Interactive 3D Environment (Three.js in Streamlit)")

st.sidebar.header("Scene Controls")
area_size = st.sidebar.slider("World size (meters)", 50, 400, 200, 10)
tree_count = st.sidebar.slider("Number of trees", 50, 1500, 500, 50)
min_tree_h = st.sidebar.slider("Min tree height (m)", 2.0, 8.0, 4.0, 0.5)
max_tree_h = st.sidebar.slider("Max tree height (m)", 6.0, 16.0, 10.0, 0.5)
wind_strength = st.sidebar.slider("Wind sway (0 = none)", 0.0, 2.0, 0.6, 0.1)
ground_roughness = st.sidebar.slider("Ground roughness (bump effect)", 0.0, 1.0, 0.35, 0.05)
fog_density = st.sidebar.slider("Fog density", 0.0, 0.02, 0.006, 0.001)
show_axes = st.sidebar.checkbox("Show axes helper", False)
add_pond = st.sidebar.checkbox("Add pond (low area)", True)

PARAMS = dict(
    area_size=area_size,
    tree_count=tree_count,
    min_tree_h=min_tree_h,
    max_tree_h=max_tree_h,
    wind_strength=wind_strength,
    ground_roughness=ground_roughness,
    fog_density=fog_density,
    show_axes=show_axes,
    add_pond=add_pond
)

# --- Embed a Three.js scene via HTML ---
html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  html, body {{
    margin: 0; padding: 0; height: 100%; overflow: hidden; background: #a6d0ff;
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
  }}
  #container {{
    position: relative; width: 100vw; height: 88vh;
  }}
  #hud {{
    position: absolute; left: 12px; bottom: 12px; padding: 10px 12px;
    background: rgba(0,0,0,0.45); color: #fff; border-radius: 10px; font-size: 13px;
    line-height: 1.35; backdrop-filter: blur(4px);
  }}
  #hud b {{ color: #b6ffb6; }}
</style>
</head>
<body>
<div id="container"></div>
<div id="hud">
  <div><b>Controls</b>: drag = orbit, scroll = zoom, right-drag = pan</div>
  <div><b>Trees</b>: {tree_count} | <b>World</b>: {area_size}×{area_size} m</div>
  <div><b>Wind</b>: {wind_strength:.2f} | <b>Fog</b>: {fog_density:.4f}</div>
</div>

<!-- Three.js from CDN -->
<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
<script src="https://unpkg.com/three@0.160.0/examples/js/controls/OrbitControls.js"></script>

<script>
const CONFIG = {json.dumps(PARAMS)};
let scene, camera, renderer, controls, treesGroup, clock;

function makeCheckerTexture(size=512, squares=16, color1="#6ea96e", color2="#5e905e") {{
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  const step = size / squares;
  for (let y=0; y<squares; y++) {{
    for (let x=0; x<squares; x++) {{
      ctx.fillStyle = ((x+y)%2==0) ? color1 : color2;
      ctx.fillRect(x*step, y*step, step, step);
    }}
  }}
  return new THREE.CanvasTexture(c);
}}

function makeNoiseTexture(size=512) {{
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  const imgData = ctx.createImageData(size, size);
  for (let i=0; i<imgData.data.length; i+=4) {{
    const v = 200 + Math.random()*50;
    imgData.data[i] = v; imgData.data[i+1] = v; imgData.data[i+2] = v; imgData.data[i+3]=255;
  }}
  ctx.putImageData(imgData,0,0);
  return new THREE.CanvasTexture(c);
}}

function init() {{
  const container = document.getElementById('container');
  scene = new THREE.Scene();

  // Fog for depth
  scene.fog = new THREE.FogExp2(0xa6d0ff, CONFIG.fog_density);

  const aspect = container.clientWidth / container.clientHeight;
  camera = new THREE.PerspectiveCamera(55, aspect, 0.1, 2000);
  camera.position.set(CONFIG.area_size*0.25, Math.max(30, CONFIG.area_size*0.25), CONFIG.area_size*0.25);

  renderer = new THREE.WebGLRenderer({{ antialias: true }});
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  container.appendChild(renderer.domElement);

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // Hemi + Directional lights
  const hemi = new THREE.HemisphereLight(0xb8e4ff, 0x2e4b2e, 0.55);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xffffff, 0.9);
  sun.position.set(200, 300, 100);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  scene.add(sun);

  // Ground plane
  const gSize = CONFIG.area_size;
  const groundTex = makeCheckerTexture(1024, 32, "#7fc67f", "#6ab16a");
  groundTex.wrapS = groundTex.wrapT = THREE.RepeatWrapping;
  groundTex.repeat.set(4,4);

  const bumpTex = makeNoiseTexture(512);
  bumpTex.wrapS = bumpTex.wrapT = THREE.RepeatWrapping;
  bumpTex.repeat.set(8,8);

  const groundMat = new THREE.MeshStandardMaterial({{
    map: groundTex,
    roughness: 0.95,
    metalness: 0.0,
    bumpMap: bumpTex,
    bumpScale: CONFIG.ground_roughness * 2.0
  }});
  const groundGeo = new THREE.PlaneGeometry(gSize, gSize, 1, 1);
  const ground = new THREE.Mesh(groundGeo, groundMat);
  ground.rotation.x = -Math.PI/2;
  ground.receiveShadow = true;
  scene.add(ground);

  // Optional pond (simple transparent disc)
  if (CONFIG.add_pond) {{
    const pondRadius = gSize * 0.12;
    const pondGeo = new THREE.CircleGeometry(pondRadius, 64);
    const pondMat = new THREE.MeshPhysicalMaterial({{
      color: 0x6aaad6,
      transmission: 0.85,
      thickness: 0.5,
      roughness: 0.15,
      clearcoat: 1.0,
      transparent: true,
      opacity: 0.85
    }});
    const pond = new THREE.Mesh(pondGeo, pondMat);
    pond.rotation.x = -Math.PI/2;
    pond.position.set(-gSize*0.15, 0.02, gSize*0.1);
    pond.receiveShadow = true;
    pond.castShadow = false;
    scene.add(pond);
  }}

  if (CONFIG.show_axes) {{
    scene.add(new THREE.AxesHelper(10));
  }}

  // Create trees
  treesGroup = new THREE.Group();
  scene.add(treesGroup);
  createTrees();

  // Subtle sky gradient via large inverted sphere
  const skyGeo = new THREE.SphereGeometry(1500, 32, 32);
  const skyMat = new THREE.MeshBasicMaterial({{
    color: 0xa6d0ff,
    side: THREE.BackSide
  }});
  const sky = new THREE.Mesh(skyGeo, skyMat);
  scene.add(sky);

  window.addEventListener('resize', onResize);
  clock = new THREE.Clock();
  animate();
}}

function randInRange(min, max) {{
  return min + Math.random()*(max - min);
}}

function createTrees() {{
  // Base materials & geometries (instanced for perf)
  const trunkMat = new THREE.MeshStandardMaterial({{ color: 0x6b4f2e, roughness: 0.9 }});
  const leafMat  = new THREE.MeshStandardMaterial({{ color: 0x2b7a2b, roughness: 0.7 }});
  const coneMat2 = new THREE.MeshStandardMaterial({{ color: 0x2f8a2f, roughness: 0.7 }});

  const trunkGeo = new THREE.CylinderGeometry(0.15, 0.25, 1.0, 8);
  const coneGeo  = new THREE.ConeGeometry(0.8, 1.6, 10);
  const coneGeo2 = new THREE.ConeGeometry(0.6, 1.2, 10);

  for (let i=0; i<CONFIG.tree_count; i++) {{
    const h = randInRange(CONFIG.min_tree_h, CONFIG.max_tree_h);
    const trunkH = h * 0.35;
    const foliageH = h - trunkH;

    const x = randInRange(-CONFIG.area_size/2+2, CONFIG.area_size/2-2);
    const z = randInRange(-CONFIG.area_size/2+2, CONFIG.area_size/2-2);

    // Avoid putting trees in the pond
    const pondCx = -CONFIG.area_size*0.15;
    const pondCz =  CONFIG.area_size*0.1;
    const inPond = CONFIG.add_pond && Math.hypot(x-pondCx, z-pondCz) < (CONFIG.area_size*0.12 + 2.5);
    if (inPond) {{ continue; }}

    // Trunk
    const trunk = new THREE.Mesh(trunkGeo.clone(), trunkMat);
    trunk.scale.set(1, trunkH, 1);
    trunk.position.set(x, trunkH/2, z);
    trunk.castShadow = true;
    treesGroup.add(trunk);

    // Foliage (two cones stacked, slight offsets for fuller canopy)
    const cone = new THREE.Mesh(coneGeo.clone(), leafMat);
    cone.position.set(x + randInRange(-0.05,0.05), trunkH + foliageH*0.35, z + randInRange(-0.05,0.05));
    const scale1 = THREE.MathUtils.mapLinear(foliageH, 2.0, 12.0, 0.6, 1.6);
    cone.scale.set(scale1, THREE.MathUtils.mapLinear(foliageH, 2.0, 12.0, 0.8, 1.8), scale1);
    cone.castShadow = true;
    treesGroup.add(cone);

    const cone2 = new THREE.Mesh(coneGeo2.clone(), coneMat2);
    cone2.position.set(x + randInRange(-0.04,0.04), trunkH + foliageH*0.85, z + randInRange(-0.04,0.04));
    const scale2 = THREE.MathUtils.mapLinear(foliageH, 2.0, 12.0, 0.5, 1.3);
    cone2.scale.set(scale2, THREE.MathUtils.mapLinear(foliageH, 2.0, 12.0, 0.8, 1.6), scale2);
    cone2.castShadow = true;
    treesGroup.add(cone);

    // Store phase for wind sway
    const phase = Math.random() * Math.PI * 2;
    cone.userData.phase = phase;
    cone2.userData.phase = phase + 0.7;
  }}
}}

function onResize() {{
  const container = document.getElementById('container');
  camera.aspect = container.clientWidth / container.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.clientWidth, container.clientHeight);
}}

function animate() {{
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();

  // Wind sway on foliage
  const sway = CONFIG.wind_strength * 0.06;
  treesGroup.children.forEach((obj) => {{
    // Only sway foliage cones (they have userData.phase)
    if (obj.userData && typeof obj.userData.phase !== 'undefined') {{
      const p = obj.userData.phase;
      obj.rotation.z = Math.sin(t*1.6 + p) * sway;
      obj.rotation.x = Math.cos(t*1.3 + p*1.2) * sway*0.6;
    }}
  }});

  controls.update();
  renderer.render(scene, camera);
}}

init();
</script>
</body>
</html>
"""

# Use components.html to render the scene
st.components.v1.html(html, height=700, scrolling=False)

st.caption(
    "Tip: increase “World size” and “Number of trees” for a dense forest; "
    "raise “Wind sway” to see animated canopies; toggle “Add pond” for variety."
)

with st.expander("Notes / Minimal dependencies"):
    st.markdown(dedent("""
    - This app uses **Three.js** via CDN inside Streamlit (no extra Python 3D libs required).
    - You can deploy as-is; your `requirements.txt` only needs `streamlit`.
    - If you want real terrain or satellite textures later, I can add a map-based version (pydeck TerrainLayer with a Mapbox token).
    """))


