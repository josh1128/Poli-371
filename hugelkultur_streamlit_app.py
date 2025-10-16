import base64
import json
import streamlit as st
from textwrap import dedent

st.set_page_config(page_title="Import External 3D Environment", layout="wide")
st.title("🌍 Import an External 3D Environment (Model + HDRI)")

st.sidebar.header("Load external assets")

# --- Option A: URLs (simplest; server must send CORS headers) ---
model_url = st.sidebar.text_input("Model URL (.glb preferred)", value="")
env_url = st.sidebar.text_input("Environment URL (.hdr equirectangular)", value="")

st.sidebar.caption("Tip: GitHub raw links often need '?raw=1'. Ensure CORS is allowed.")

st.sidebar.markdown("---")

# --- Option B: Local uploads (no CORS needed) ---
up_model = st.sidebar.file_uploader("Upload model (.glb recommended)", type=["glb"])
up_env = st.sidebar.file_uploader("Upload environment (.hdr)", type=["hdr"])

def to_data_url(file_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"

model_source = {"kind": None, "value": None}
env_source = {"kind": None, "value": None}

# Prefer uploads if provided; otherwise use URLs if present
if up_model is not None:
    model_source = {"kind": "dataurl", "value": to_data_url(up_model.read(), "model/gltf-binary")}
elif model_url.strip():
    model_source = {"kind": "url", "value": model_url.strip()}

if up_env is not None:
    env_source = {"kind": "dataurl", "value": to_data_url(up_env.read(), "application/octet-stream")}
elif env_url.strip():
    env_source = {"kind": "url", "value": env_url.strip()}

# Scene controls
st.sidebar.header("Scene controls")
area_size = st.sidebar.slider("Ground size (m)", 50, 400, 200, 10)
fog_density = st.sidebar.slider("Fog density", 0.0, 0.02, 0.004, 0.001)
light_intensity = st.sidebar.slider("Sun light", 0.2, 2.0, 1.0, 0.1)
show_axes = st.sidebar.checkbox("Show axes", False)
auto_center = st.sidebar.checkbox("Auto-center & frame model", True)

params = dict(
    area_size=area_size,
    fog_density=fog_density,
    light_intensity=light_intensity,
    show_axes=show_axes,
    auto_center=auto_center,
    model_source=model_source,
    env_source=env_source
)

# --- Three.js app (loads GLTF + RGBE env) ---
html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  html, body {{ margin:0; height:100%; background:#a6d0ff; overflow:hidden; }}
  #wrap {{ position:relative; width:100vw; height:88vh; }}
  #hud {{
    position:absolute; left:12px; bottom:12px; padding:10px 12px;
    background:rgba(0,0,0,0.45); color:#fff; border-radius:10px; font:13px/1.35 system-ui;
    backdrop-filter: blur(4px);
  }}
  #hud b {{ color:#b6ffb6; }}
</style>
</head>
<body>
<div id="wrap"></div>
<div id="hud">
  <div><b>Tips</b>: drag = orbit, scroll = zoom, right-drag = pan</div>
  <div>External model + HDRI supported (URL or upload)</div>
</div>

<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
<script src="https://unpkg.com/three@0.160.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://unpkg.com/three@0.160.0/examples/js/loaders/GLTFLoader.js"></script>
<script src="https://unpkg.com/three@0.160.0/examples/js/loaders/RGBELoader.js"></script>

<script>
const CONFIG = {json.dumps(params)};

let scene, camera, renderer, controls, pmrem, modelRoot;

function blobFromDataURL(dataURL) {{
  const arr = dataURL.split(',');
  const mime = arr[0].match(/:(.*?);/)[1];
  const bstr = atob(arr[1]); let n = bstr.length; const u8 = new Uint8Array(n);
  while (n--) u8[n] = bstr.charCodeAt(n);
  return new Blob([u8], {{type: mime}});
}}

function init() {{
  const el = document.getElementById('wrap');
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0xa6d0ff, CONFIG.fog_density);

  const aspect = el.clientWidth / el.clientHeight;
  camera = new THREE.PerspectiveCamera(55, aspect, 0.1, 5000);
  camera.position.set(80, 80, 80);

  renderer = new THREE.WebGLRenderer({{antialias:true}});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(el.clientWidth, el.clientHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  el.appendChild(renderer.domElement);

  pmrem = new THREE.PMREMGenerator(renderer);

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // Lights
  scene.add(new THREE.HemisphereLight(0xb8e4ff, 0x2e4b2e, 0.5));
  const sun = new THREE.DirectionalLight(0xffffff, CONFIG.light_intensity);
  sun.position.set(200, 300, 100);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  scene.add(sun);

  // Ground
  const g = new THREE.Mesh(
    new THREE.PlaneGeometry(CONFIG.area_size, CONFIG.area_size),
    new THREE.MeshStandardMaterial({{ color: 0x7fc67f, roughness: 0.95 }})
  );
  g.rotation.x = -Math.PI/2;
  g.receiveShadow = true;
  scene.add(g);

  if (CONFIG.show_axes) scene.add(new THREE.AxesHelper(10));

  // Load environment (HDRI)
  setEnvironment(CONFIG.env_source).then(() => {{
    // Then load model
    return loadModel(CONFIG.model_source);
  }}).then((obj) => {{
    if (obj) {{
      modelRoot = obj;
      scene.add(modelRoot);
      if (CONFIG.auto_center) frameObject(modelRoot);
    }}
    animate();
  }});
  window.addEventListener('resize', onResize);
}}

function setEnvironment(src) {{
  if (!src || !src.kind || !src.value) return Promise.resolve();
  return new Promise((resolve, reject) => {{
    const loader = new THREE.RGBELoader();
    let url = src.value;
    if (src.kind === "dataurl") {{
      const blob = blobFromDataURL(src.value);
      url = URL.createObjectURL(blob);
    }}
    loader.load(url, (hdr) => {{
      const envMap = pmrem.fromEquirectangular(hdr).texture;
      hdr.dispose();
      scene.environment = envMap;
      scene.background = null; // keep blue sky; set to envMap if you prefer
      resolve();
    }}, undefined, (e) => {{ console.warn("HDR load error", e); resolve(); }});
  }});
}}

function loadModel(src) {{
  if (!src || !src.kind || !src.value) return Promise.resolve(null);
  return new Promise((resolve, reject) => {{
    const loader = new THREE.GLTFLoader();
    let url = src.value;
    if (src.kind === "dataurl") {{
      const blob = blobFromDataURL(src.value);
      url = URL.createObjectURL(blob);
    }}
    loader.load(url, (gltf) => {{
      const obj = gltf.scene || gltf.scenes?.[0];
      if (!obj) return resolve(null);
      obj.traverse((n) => {{
        if (n.isMesh) {{
          n.castShadow = true; n.receiveShadow = true;
          if (n.material) {{
            n.material.needsUpdate = true;
          }}
        }}
      }});
      resolve(obj);
    }}, undefined, (e) => {{ console.error("GLB load error", e); resolve(null); }});
  }});
}}

function frameObject(obj) {{
  const box = new THREE.Box3().setFromObject(obj);
  if (!box.isEmpty()) {{
    const size = box.getSize(new THREE.Vector3()).length();
    const center = box.getCenter(new THREE.Vector3());
    // Recenter
    obj.position.x -= center.x;
    obj.position.z -= center.z;
    // Camera distance
    const dist = Math.min(Math.max(size * 0.8, 20), 1000);
    camera.position.set(dist, dist * 0.6, dist);
    camera.lookAt(0, 0, 0);
  }}
}}

function onResize() {{
  const el = document.getElementById('wrap');
  camera.aspect = el.clientWidth / el.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(el.clientWidth, el.clientHeight);
}}

function animate() {{
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}}

init();
</script>
</body>
</html>
"""

st.components.v1.html(html, height=700, scrolling=False)

with st.expander("How to use (quick)"):
    st.markdown(dedent("""
    **Models**: Prefer a single-file **.glb**. For multi-file `.gltf` (with .bin + textures), pack them into a `.glb`.
    
    **Environment**: Use a **.hdr** equirectangular map (e.g., from polyhaven.com).  
    - If you paste URLs, the server must allow **CORS**.  
    - If you upload files here, we convert them to data URLs and load them directly (no CORS needed).
    
    **Auto-center** frames and centers the model over the ground. Toggle it if your model already has correct transforms.
    """))

with st.expander("Minimal requirements.txt"):
    st.code("streamlit>=1.36")

