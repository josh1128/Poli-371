# web3d_in_streamlit.py
# Streamlit wrapper for browser-native 3D engines: Three.js, Babylon.js, CesiumJS, PlayCanvas (iframe)
# - Uses st.components.v1.html to embed each engine
# - Demonstrates passing Streamlit slider values into the JS scene (rainIntensity & camera height)

import streamlit as st
from textwrap import dedent

st.set_page_config(page_title="3D in Streamlit: Three.js / Babylon / Cesium / PlayCanvas", layout="wide")
st.title("🌐 3D Engines inside Streamlit")

st.sidebar.header("Global Controls")
rain_intensity = st.sidebar.slider("Rain intensity (particles / frame)", 0, 5000, 1200, 100)
camera_height  = st.sidebar.slider("Camera height (m)", 5, 80, 25, 1)

tab_three, tab_babylon, tab_cesium, tab_playcanvas = st.tabs(
    ["Three.js (WebGL)", "Babylon.js", "CesiumJS (real terrain)", "PlayCanvas (iframe)"]
)

# ------------------------ THREE.JS ------------------------
with tab_three:
    st.subheader("Three.js – particles rain + simple terrain")
    st.caption("No build step: loads from CDN. Adjust sliders in the sidebar.")

    html_three = f"""
    <div id="three-root" style="width:100%;height:600px;border:1px solid #ddd;border-radius:12px;overflow:hidden"></div>
    <script type="module">
      // CDN imports
      import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
      import {{ OrbitControls }} from 'https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js';

      const W = window.innerWidth * 0.96;
      const H = 600;

      const renderer = new THREE.WebGLRenderer({{ antialias:true }});
      renderer.setSize(W, H);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      document.getElementById('three-root').appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x1b1f2a);

      const camera = new THREE.PerspectiveCamera(60, W/H, 0.1, 1000);
      camera.position.set(30, {camera_height}, 30);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;

      // Lights
      const hemi = new THREE.HemisphereLight(0xaadfff, 0x223344, 0.8);
      scene.add(hemi);
      const dir = new THREE.DirectionalLight(0xffffff, 0.6);
      dir.position.set(50, 100, -20);
      scene.add(dir);

      // Simple heightfield terrain (procedural)
      const size = 200, seg = 128;
      const geo = new THREE.PlaneGeometry(size, size, seg, seg);
      // Push vertices for a rolling hill feel
      for (let i=0;i<geo.attributes.position.count;i++) {{
        const x = geo.attributes.position.getX(i);
        const y = geo.attributes.position.getY(i);
        const z = 6*Math.sin(x/14) + 4*Math.cos(y/17) + 2*Math.sin((x+y)/11);
        geo.attributes.position.setZ(i, z);
      }}
      geo.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({{
        color: 0x3b5d37,
        roughness: 0.9,
        metalness: 0.0,
        side: THREE.DoubleSide
      }});
      const terrain = new THREE.Mesh(geo, mat);
      terrain.rotation.x = -Math.PI/2;
      scene.add(terrain);

      // A “road strip” where we'll imagine permeable pavement
      const roadGeo = new THREE.PlaneGeometry(size, 6, 1, 1);
      const roadMat = new THREE.MeshStandardMaterial({{ color: 0x666a6e, roughness: 0.7 }});
      const road = new THREE.Mesh(roadGeo, roadMat);
      road.position.y = 0.02; // slightly above terrain
      road.rotation.x = -Math.PI/2;
      scene.add(road);

      // Rain particle system (very lightweight)
      const RAIN_COUNT = 10000;
      const rainGeo = new THREE.BufferGeometry();
      const positions = new Float32Array(RAIN_COUNT * 3);
      for (let i=0;i<RAIN_COUNT;i++) {{
        positions[3*i+0] = (Math.random()-0.5)*size; // x
        positions[3*i+1] = 60 + Math.random()*80;    // y (height)
        positions[3*i+2] = (Math.random()-0.5)*size; // z
      }}
      rainGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const rainMat = new THREE.PointsMaterial({{ size: 0.08, transparent:true, opacity:0.8 }});
      const rain = new THREE.Points(rainGeo, rainMat);
      scene.add(rain);

      // Simple "infiltration indicator": change road color toward blue as "infiltration" grows
      let infiltrAccum = 0;

      function animate() {{
        requestAnimationFrame(animate);
        const pos = rain.geometry.attributes.position.array;
        const countPerFrame = {rain_intensity};
        // Move a subset of drops per frame to simulate intensity
        for (let i=0;i<RAIN_COUNT;i++) {{
          if (i % Math.max(1, Math.floor(RAIN_COUNT / countPerFrame)) === 0) {{
            pos[3*i+1] -= 0.8 + Math.random()*0.5;
            // if below terrain plane, respawn at top
            if (pos[3*i+1] < 0) {{
              // crude test: drops near road center contribute to "infiltration"
              const rx = pos[3*i+0];
              if (Math.abs(pos[3*i+2]) < 3) {{
                infiltrAccum = Math.min(1.0, infiltrAccum + 0.0005);
              }}
              pos[3*i+0] = (Math.random()-0.5)*size;
              pos[3*i+1] = 60 + Math.random()*80;
              pos[3*i+2] = (Math.random()-0.5)*size;
            }}
          }}
        }}
        rain.geometry.attributes.position.needsUpdate = true;

        // Tint the road from gray -> bluish as infiltration proxy
        road.material.color.setHex(0x666a6e);
        const infilBlue = new THREE.Color().setHSL(0.58, 0.5*infiltrAccum, 0.4 + 0.2*infiltrAccum);
        road.material.color.lerp(infilBlue, 0.2*infiltrAccum);

        controls.update();
        renderer.render(scene, camera);
      }}
      animate();

      // Make canvas responsive inside Streamlit container
      window.addEventListener('resize', () => {{
        const root = document.getElementById('three-root');
        const w = root.clientWidth || W;
        const h = {H};
        renderer.setSize(w, h);
        camera.aspect = w/h;
        camera.updateProjectionMatrix();
      }});
    </script>
    """
    st.components.v1.html(html_three, height=620, scrolling=False)

# ------------------------ BABYLON ------------------------
with tab_babylon:
    st.subheader("Babylon.js – quick scene + particle rain")
    html_babylon = f"""
    <div id="babylon-root" style="width:100%;height:600px;border:1px solid #ddd;border-radius:12px;overflow:hidden"></div>
    <script src="https://cdn.babylonjs.com/babylon.js"></script>
    <script src="https://cdn.babylonjs.com/materialsLibrary/babylonjs.materials.min.js"></script>
    <script>
      const canvas = document.createElement('canvas');
      canvas.style.width='100%'; canvas.style.height='100%';
      document.getElementById('babylon-root').appendChild(canvas);
      const engine = new BABYLON.Engine(canvas, true);
      const scene = new BABYLON.Scene(engine);
      scene.clearColor = new BABYLON.Color4(0.11,0.13,0.17,1);

      const camera = new BABYLON.ArcRotateCamera("cam", Math.PI/3, Math.PI/3, 60, BABYLON.Vector3.Zero(), scene);
      camera.setTarget(BABYLON.Vector3.Zero());
      camera.lowerRadiusLimit = 10; camera.upperRadiusLimit = 200;
      camera.attachControl(canvas, true);
      camera.beta = 1.0; camera.alpha = 0.9; camera.radius = 80 - 0 + {camera_height} / 2.0;

      const light = new BABYLON.HemisphericLight("h", new BABYLON.Vector3(0, 1, 0), scene);

      // Ground
      const ground = BABYLON.MeshBuilder.CreateGroundFromHeightMap("g",
        "https://assets.babylonjs.com/environments/villageheightmap.png",
        {{width:200, height:200, subdivisions: 100, minHeight:0, maxHeight:12}}, scene);
      const gMat = new BABYLON.StandardMaterial("gm", scene);
      gMat.diffuseColor = new BABYLON.Color3(0.24,0.42,0.25);
      ground.material = gMat;

      // Road strip
      const road = BABYLON.MeshBuilder.CreateGround("road", {{width:200, height:6, subdivisions:1}}, scene);
      road.position.y = 0.15;
      const rMat = new BABYLON.StandardMaterial("rm", scene);
      rMat.diffuseColor = new BABYLON.Color3(0.4,0.42,0.46);
      road.material = rMat;

      // Particle rain
      const ps = new BABYLON.ParticleSystem("rain", 50000, scene);
      ps.particleTexture = new BABYLON.Texture("https://assets.babylonjs.com/textures/flare.png", scene);
      ps.emitter = new BABYLON.Vector3(0, 60, 0);
      ps.minEmitBox = new BABYLON.Vector3(-100, 0, -100);
      ps.maxEmitBox = new BABYLON.Vector3(100, 0, 100);
      ps.minSize = 0.02; ps.maxSize = 0.06;
      ps.emitRate = {max(0, rain_intensity*4)};
      ps.direction1 = new BABYLON.Vector3(0, -1, 0);
      ps.direction2 = new BABYLON.Vector3(0, -1, 0);
      ps.minLifeTime = 2.0; ps.maxLifeTime = 3.5;
      ps.minEmitPower = 2; ps.maxEmitPower = 4;
      ps.start();

      engine.runRenderLoop(() => scene && scene.render());
      window.addEventListener('resize', () => engine.resize());
    </script>
    """
    st.components.v1.html(html_babylon, height=620, scrolling=False)

# ------------------------ CESIUMJS ------------------------
with tab_cesium:
    st.subheader("CesiumJS – real world terrain/imagery (needs a Cesium ion token)")
    st.caption("Best for real Rwanda terrain/roads. Put your free Cesium ion token below (or in an env var) and the viewer will load.")
    token = st.text_input("Cesium ion access token (free tier works)", value="YOUR_CESIUM_ION_TOKEN_HERE")

    # Kigali approx. (CAMERA demo)
    lon, lat, height = 30.135, -1.953, max(200.0, float(camera_height))
    html_cesium = dedent(f"""
    <div id="cesiumContainer" style="width:100%;height:600px;border:1px solid #ddd;border-radius:12px;overflow:hidden"></div>
    <script src="https://cesium.com/downloads/cesiumjs/releases/1.123/Build/Cesium/Cesium.js"></script>
    <link href="https://cesium.com/downloads/cesiumjs/releases/1.123/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
    <script>
      window.CESIUM_BASE_URL = "https://cesium.com/downloads/cesiumjs/releases/1.123/Build/Cesium/";
      Cesium.Ion.defaultAccessToken = "{token}";
      const viewer = new Cesium.Viewer("cesiumContainer", {{
        terrain: Cesium.Terrain.fromWorldTerrain(),
        animation: false, timeline: false, baseLayerPicker: true
      }});
      // Fly to Kigali region
      viewer.camera.flyTo({{
        destination: Cesium.Cartesian3.fromDegrees({lon}, {lat}, {height*100.0}),
        duration: 2
      }});
      // Add a simple road polyline (placeholder)
      const road = viewer.entities.add({{
        polyline: {{
          positions: Cesium.Cartesian3.fromDegreesArray([
            {lon-0.02}, {lat}, {lon+0.02}, {lat}
          ]),
          width: 6,
          material: Cesium.Color.GRAY
        }}
      }});
      // NOTE: For real roads/pavements load your GeoJSON:
      // const dataSource = await Cesium.GeoJsonDataSource.load('your_roads.geojson');
      // viewer.dataSources.add(dataSource);
    </script>
    """)
    st.components.v1.html(html_cesium, height=640, scrolling=False)

# ------------------------ PLAYCANVAS ------------------------
with tab_playcanvas:
    st.subheader("PlayCanvas – embed a published build via iframe")
    st.caption("Create a PlayCanvas project (free tier), publish it, then paste the build URL here.")
    default_url = "https://playcanv.as/p/your-build-id/"  # placeholder
    url = st.text_input("PlayCanvas build URL", value=default_url)
    st.components.v1.iframe(url, height=620)


