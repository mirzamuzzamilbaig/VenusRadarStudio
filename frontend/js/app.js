/**
 * VenusRadarStudio — Main Application Controller
 * ================================================
 * Modules:
 *   1. Starfield         — animated canvas background
 *   2. Loader            — startup sequence with progress bar
 *   3. LeafletMap        — interactive Leaflet.js Venus map
 *   4. CPRChart          — Chart.js CPR histogram
 *   5. Terrain3D         — Three.js 3D terrain viewer
 *   6. UIControls        — toggles, sliders, filters, popups
 *   7. Literature        — literature panel renderer
 *   8. Init              — orchestrates startup
 */

'use strict';

// ─── Global State ─────────────────────────────────────────────────────────────
const State = {
  hotspots:     [],
  changes:      [],
  literature:   [],
  terrain:      null,
  activeFeat:   null,
  layerFilter:  'all',
  cprThreshold: 0.50,
  overlayOpacity: 0.70,
  map:          null,
  cprChart:     null,
  terrain3d:    null,
  layers: {
    basemap:    null,
    cpr:        null,
    hotspots:   null,
    changes:    null
  }
};

// ─── 1. STARFIELD ─────────────────────────────────────────────────────────────
const Starfield = (() => {
  let canvas, ctx, stars = [], raf;

  function init() {
    canvas = document.getElementById('starfield');
    ctx    = canvas.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
    populate();
    loop();
  }

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  function populate() {
    stars = [];
    const N = Math.floor((canvas.width * canvas.height) / 3500);
    for (let i = 0; i < N; i++) {
      stars.push({
        x:    Math.random() * canvas.width,
        y:    Math.random() * canvas.height,
        r:    Math.random() * 1.3,
        a:    Math.random(),
        da:   (Math.random() - 0.5) * 0.004,
        hue:  Math.random() > 0.85 ? 200 + Math.random() * 40 : 0,  // some blue tinted
        sat:  Math.random() > 0.85 ? 60 : 0
      });
    }
  }

  function loop() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    stars.forEach(s => {
      s.a = Math.max(0.05, Math.min(1, s.a + s.da));
      if (s.a <= 0.05 || s.a >= 1) s.da = -s.da;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = s.hue
        ? `hsla(${s.hue}, ${s.sat}%, 85%, ${s.a})`
        : `rgba(255,255,255,${s.a * 0.9})`;
      ctx.fill();
    });
    raf = requestAnimationFrame(loop);
  }

  return { init };
})();

// ─── 2. LOADER ────────────────────────────────────────────────────────────────
const Loader = (() => {
  const overlay = () => document.getElementById('loading-overlay');
  const bar     = () => document.getElementById('loader-bar');
  const status  = () => document.getElementById('loader-status');

  function setProgress(pct, msg) {
    bar().style.width = `${pct}%`;
    if (msg) status().textContent = msg;
  }

  function hide() {
    const el = overlay();
    el.classList.add('fade-out');
    setTimeout(() => el.style.display = 'none', 600);
    document.getElementById('app').classList.remove('hidden');
  }

  return { setProgress, hide };
})();

// ─── 3. LEAFLET MAP ───────────────────────────────────────────────────────────
const VenusMap = (() => {

  function init() {
    const map = L.map('venus-map', {
      center:        [0, 0],
      zoom:          2,
      minZoom:       1,
      maxZoom:       7,
      zoomControl:   true,
      attributionControl: false,
      maxBounds:     [[-90, -180], [90, 180]],
      maxBoundsViscosity: 1.0
    });

    // attribution
    L.control.attribution({ prefix: '' }).addTo(map);

    State.map = map;

    // ── Basemap image overlay ──────────────────────────────────────────────
    const baseBounds = [[-90, -180], [90, 180]];
    State.layers.basemap = L.imageOverlay('/api/basemap', baseBounds, {
      opacity: 1,
      zIndex:  1
    }).addTo(map);

    // ── CPR overlay (RGBA) ─────────────────────────────────────────────────
    State.layers.cpr = L.imageOverlay('/api/cpr_layer', baseBounds, {
      opacity: State.overlayOpacity,
      zIndex:  2
    }).addTo(map);

    // ── Grid lines ────────────────────────────────────────────────────────
    _addGrid(map);

    // ── Coordinate readout ────────────────────────────────────────────────
    map.on('mousemove', e => {
      document.getElementById('nav-coord').textContent =
        `${e.latlng.lat.toFixed(2)}°, ${e.latlng.lng.toFixed(2)}°`;
    });

    // ── Click for CPR stats ───────────────────────────────────────────────
    map.on('click', e => {
      CPRChart.fetchAndUpdate(e.latlng.lat, e.latlng.lng);
    });

    return map;
  }

  function _addGrid(map) {
    // Latitude lines
    for (let lat = -60; lat <= 60; lat += 30) {
      L.polyline([
        [lat, -180], [lat, 180]
      ], { color: 'rgba(0,212,255,0.08)', weight: 1, dashArray: '3,6' }).addTo(map);

      if (lat !== 0) {
        L.marker([lat, -175], {
          icon: L.divIcon({ html: `<span style="color:rgba(0,212,255,0.35);font-size:9px;font-family:monospace">${lat}°</span>`, className: '' })
        }).addTo(map);
      }
    }
    // Prime meridian
    L.polyline([[-90, 0], [90, 0]], { color: 'rgba(0,212,255,0.12)', weight: 1, dashArray: '3,6' }).addTo(map);
    // Equator
    L.polyline([[0, -180], [0, 180]], { color: 'rgba(0,212,255,0.15)', weight: 1 }).addTo(map);
  }

  function loadHotspots(features) {
    if (State.layers.hotspots) State.layers.hotspots.remove();

    const filtered = State.layerFilter === 'all'
      ? features
      : features.filter(f => f.properties.type === State.layerFilter);

    const group = L.featureGroup();

    filtered.forEach(feat => {
      const props  = feat.properties;
      const [lon, lat] = feat.geometry.coordinates;
      const isActive = props.active;

      const markerHtml = isActive
        ? `<div class="volcano-marker-active"></div>`
        : `<div class="volcano-marker"></div>`;

      const icon = L.divIcon({
        html: markerHtml, className: '',
        iconSize: isActive ? [16, 16] : [12, 12],
        iconAnchor: isActive ? [8, 8] : [6, 6]
      });

      const marker = L.marker([lat, lon], { icon })
        .bindTooltip(props.name, {
          permanent: false, direction: 'top', offset: [0, -10],
          className: 'leaflet-tooltip-dark'
        })
        .on('click', () => UIControls.showFeaturePopup(props, lat, lon));

      group.addLayer(marker);

      // CPR radius circle (subtle)
      if (props.cpr_peak > 0.7) {
        L.circle([lat, lon], {
          radius: props.radius_deg * 111000,  // approx km
          color: isActive ? '#ff6b35' : '#a855f7',
          weight: 1, fillOpacity: 0.05, opacity: 0.25
        }).addTo(State.map);
      }
    });

    group.addTo(State.map);
    State.layers.hotspots = group;
  }

  function loadChanges(features) {
    if (State.layers.changes) State.layers.changes.remove();

    const group = L.featureGroup();
    features.forEach(feat => {
      const props = feat.properties;
      const [lon, lat] = feat.geometry.coordinates;

      const confColor = { High: '#ff6b35', Medium: '#ffd700', Low: '#8899cc' }[props.confidence] || '#aaa';

      const icon = L.divIcon({
        html: `<div style="
          width:16px;height:16px;border-radius:2px;transform:rotate(45deg);
          border:2px solid ${confColor};background:transparent;
          box-shadow:0 0 10px ${confColor};
          animation:pulse-change 1.5s ease-in-out infinite;
        "></div>`,
        className: '', iconSize: [16, 16], iconAnchor: [8, 8]
      });

      L.marker([lat, lon], { icon })
        .bindPopup(`
          <div style="font-size:12px;line-height:1.6">
            <b style="color:#ffd700">⚡ ${props.name}</b><br/>
            <span style="color:#8899cc">${props.epoch1} → ${props.epoch2}</span><br/>
            Type: <span style="color:#00d4ff">${props.change_type}</span><br/>
            ΔBackscatter: <b style="color:#ff6b35">+${props.delta_backscatter_db} dB</b><br/>
            Area: ${props.area_km2} km²<br/>
            Confidence: <span style="color:${confColor}">${props.confidence}</span><br/>
            <span style="font-size:10px;color:#556;">${props.paper}</span>
          </div>
        `)
        .addTo(group);
    });

    group.addTo(State.map);
    State.layers.changes = group;
  }

  function setBasemapVisible(v)  { v ? State.layers.basemap.addTo(State.map) : State.layers.basemap.remove(); }
  function setCPRVisible(v)      { v ? State.layers.cpr.addTo(State.map)     : State.layers.cpr.remove(); }
  function setHotspotsVisible(v) { State.layers.hotspots && (v ? State.layers.hotspots.addTo(State.map) : State.layers.hotspots.remove()); }
  function setChangesVisible(v)  { State.layers.changes  && (v ? State.layers.changes.addTo(State.map)  : State.layers.changes.remove()); }

  function setCPROpacity(o) {
    State.layers.cpr && State.layers.cpr.setOpacity(o);
  }

  function flyTo(lat, lon, zoom = 4) {
    State.map && State.map.flyTo([lat, lon], zoom, { duration: 1.2 });
  }

  return { init, loadHotspots, loadChanges, setBasemapVisible, setCPRVisible, setHotspotsVisible, setChangesVisible, setCPROpacity, flyTo };
})();

// ─── 4. CPR CHART ─────────────────────────────────────────────────────────────
const CPRChart = (() => {
  let chart = null;

  function init() {
    const ctx = document.getElementById('cpr-chart').getContext('2d');

    // Empty initial chart
    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'CPR Distribution',
          data: [],
          backgroundColor: 'rgba(0, 212, 255, 0.2)',
          borderColor: 'rgba(0, 212, 255, 0.8)',
          borderWidth: 1,
          borderRadius: 3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(5,8,35,0.95)',
            titleColor: '#00d4ff',
            bodyColor: '#8899cc',
            borderColor: 'rgba(0,212,255,0.3)',
            borderWidth: 1,
            callbacks: {
              title: items => `CPR ≈ ${parseFloat(items[0].label).toFixed(2)}`,
              label: item => `Count: ${item.raw}`
            }
          }
        },
        scales: {
          x: {
            ticks: { color: '#5a6a99', font: { size: 9, family: 'JetBrains Mono' }, maxTicksLimit: 8 },
            grid: { color: 'rgba(255,255,255,0.04)' }
          },
          y: {
            ticks: { color: '#5a6a99', font: { size: 9 } },
            grid: { color: 'rgba(255,255,255,0.04)' }
          }
        }
      }
    });

    State.cprChart = chart;
  }

  async function fetchAndUpdate(lat, lon) {
    try {
      const r = await fetch(`/api/cpr_stats?lat=${lat}&lon=${lon}`);
      const data = await r.json();
      update(data);
    } catch (e) {
      console.warn('CPR stats fetch failed:', e);
    }
  }

  function update(data) {
    // Update readout values
    document.getElementById('val-mean').textContent  = data.mean_cpr.toFixed(3);
    document.getElementById('val-max').textContent   = data.max_cpr.toFixed(3);
    document.getElementById('val-std').textContent   = data.std_cpr.toFixed(3);
    document.getElementById('val-p95').textContent   = data.p95_cpr.toFixed(3);
    document.getElementById('val-class').textContent = data.terrain_class;
    document.getElementById('interp-text').textContent = data.interpretation;

    // Color-code mean CPR
    const meanEl = document.getElementById('val-mean');
    const cpr = data.mean_cpr;
    meanEl.style.color = cpr < 0.3 ? '#1a88ff' : cpr < 0.6 ? '#00d4ff' : cpr < 0.9 ? '#ffd700' : '#ff6b35';

    // Update histogram
    const hist   = data.histogram;
    const labels = hist.bin_edges.slice(0, -1).map(v => v.toFixed(2));
    const counts = hist.counts;

    // Color bars by CPR value
    const colors = labels.map(v => {
      const c = parseFloat(v);
      if (c < 0.25) return 'rgba(30, 80, 200, 0.7)';
      if (c < 0.50) return 'rgba(0, 200, 255, 0.7)';
      if (c < 0.75) return 'rgba(255, 215, 0, 0.7)';
      if (c < 1.10) return 'rgba(255, 107, 53, 0.8)';
      return 'rgba(255, 255, 255, 0.85)';
    });

    chart.data.labels = labels;
    chart.data.datasets[0].data = counts;
    chart.data.datasets[0].backgroundColor = colors;
    chart.data.datasets[0].borderColor = colors.map(c => c.replace('0.7', '1').replace('0.8', '1').replace('0.85', '1'));
    chart.update('active');
  }

  return { init, fetchAndUpdate, update };
})();

// ─── 5. TERRAIN 3D ────────────────────────────────────────────────────────────
const Terrain3D = (() => {
  let renderer, scene, camera, controls, mesh, animFrame;
  let exaggeration = 3;

  async function init(terrainData) {
    State.terrain = terrainData;

    const canvas  = document.getElementById('terrain-canvas');
    const W = canvas.parentElement.clientWidth;
    const H = canvas.parentElement.clientHeight - 32; // minus header

    // ── Renderer ──────────────────────────────────────────────────────────
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x030310, 1);

    // ── Scene ─────────────────────────────────────────────────────────────
    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x030310, 0.025);

    // ── Camera ────────────────────────────────────────────────────────────
    camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 200);
    camera.position.set(0, 18, 30);
    camera.lookAt(0, 0, 0);

    // ── Lights ────────────────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0x223366, 1.5));

    const sunLight = new THREE.DirectionalLight(0xffa060, 2.5);
    sunLight.position.set(15, 20, 10);
    scene.add(sunLight);

    const rimLight = new THREE.DirectionalLight(0x00d4ff, 1.2);
    rimLight.position.set(-20, 5, -10);
    scene.add(rimLight);

    // ── Terrain Geometry ──────────────────────────────────────────────────
    buildTerrain(terrainData, exaggeration);

    // ── Atmosphere sphere ─────────────────────────────────────────────────
    const atmGeo = new THREE.SphereGeometry(35, 32, 32);
    const atmMat = new THREE.MeshBasicMaterial({
      color: 0xff8800, transparent: true, opacity: 0.04, side: THREE.BackSide
    });
    scene.add(new THREE.Mesh(atmGeo, atmMat));

    // ── Stars ─────────────────────────────────────────────────────────────
    const starsGeo = new THREE.BufferGeometry();
    const starPos  = new Float32Array(3000);
    for (let i = 0; i < 3000; i++) {
      starPos[i] = (Math.random() - 0.5) * 200;
    }
    starsGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
    scene.add(new THREE.Points(starsGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.2, sizeAttenuation: true })));

    // ── Orbit Controls ────────────────────────────────────────────────────
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping    = true;
    controls.dampingFactor    = 0.05;
    controls.screenSpacePanning = false;
    controls.minDistance      = 8;
    controls.maxDistance      = 80;
    controls.maxPolarAngle    = Math.PI / 2.1;

    // ── Resize ────────────────────────────────────────────────────────────
    window.addEventListener('resize', onResize);

    animate();
  }

  function buildTerrain(data, exag) {
    if (mesh) { scene.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose(); }

    const W  = data.width;
    const H  = data.height;
    const geo = new THREE.PlaneGeometry(40, 20, W - 1, H - 1);
    geo.rotateX(-Math.PI / 2);

    const posArr = geo.attributes.position.array;
    for (let i = 0, j = 0; i < posArr.length; i += 3, j++) {
      posArr[i + 1] = data.heights[j] * exag * (data.max_km - data.min_km) * 0.15;
    }
    geo.computeVertexNormals();

    // Vertex color based on height (CPR-like colormap)
    const colors = new Float32Array(posArr.length);
    for (let i = 0, j = 0; i < colors.length; i += 3, j++) {
      const h = data.heights[j];
      // Height → color (dark blue plains → orange-red mountains)
      if (h < 0.2) {
        colors[i]   = 0.05; colors[i+1] = 0.10; colors[i+2] = 0.45;  // deep blue plains
      } else if (h < 0.4) {
        const t = (h - 0.2) / 0.2;
        colors[i]   = t * 0.1;      colors[i+1] = 0.25 + t*0.35; colors[i+2] = 0.45 - t*0.2;
      } else if (h < 0.65) {
        const t = (h - 0.4) / 0.25;
        colors[i]   = 0.1 + t*0.5;  colors[i+1] = 0.6 - t*0.2;  colors[i+2] = 0.25 - t*0.2;
      } else if (h < 0.85) {
        const t = (h - 0.65) / 0.20;
        colors[i]   = 0.6 + t*0.4;  colors[i+1] = 0.4 - t*0.3;  colors[i+2] = 0.05;
      } else {
        const t = (h - 0.85) / 0.15;
        colors[i]   = 1.0;          colors[i+1] = 0.1 + t*0.9;  colors[i+2] = t * 0.9;
      }
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const mat = new THREE.MeshPhongMaterial({
      vertexColors: true,
      shininess:    30,
      specular:     new THREE.Color(0x224466),
      wireframe:    false
    });

    mesh = new THREE.Mesh(geo, mat);
    scene.add(mesh);

    // Wireframe overlay (very subtle)
    const wfMat = new THREE.MeshBasicMaterial({
      color: 0x00d4ff, opacity: 0.04, transparent: true, wireframe: true
    });
    scene.add(new THREE.Mesh(geo.clone(), wfMat));
  }

  function animate() {
    animFrame = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }

  function onResize() {
    if (!renderer) return;
    const canvas = document.getElementById('terrain-canvas');
    const W = canvas.parentElement.clientWidth;
    const H = canvas.parentElement.clientHeight - 32;
    renderer.setSize(W, H);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
  }

  function setExaggeration(v) {
    exaggeration = v;
    if (State.terrain) buildTerrain(State.terrain, v);
  }

  function resetCamera() {
    if (!camera || !controls) return;
    camera.position.set(0, 18, 30);
    camera.lookAt(0, 0, 0);
    controls.reset();
  }

  return { init, setExaggeration, resetCamera };
})();

// ─── 6. UI CONTROLS ───────────────────────────────────────────────────────────
const UIControls = (() => {

  function init() {
    // Layer toggles
    _tog('tog-basemap', v => VenusMap.setBasemapVisible(v));
    _tog('tog-cpr',     v => VenusMap.setCPRVisible(v));
    _tog('tog-hotspots',v => VenusMap.setHotspotsVisible(v));
    _tog('tog-changes', v => {
      VenusMap.setChangesVisible(v);
      if (v && State.changes.length > 0) VenusMap.loadChanges(State.changes);
    });

    // CPR threshold slider
    const sldThresh = document.getElementById('sld-cpr-thresh');
    const lblThresh = document.getElementById('lbl-cpr-thresh');
    sldThresh.addEventListener('input', () => {
      const val = parseFloat(sldThresh.value) / 100;
      State.cprThreshold = val;
      lblThresh.textContent = val.toFixed(2);
    });

    // Opacity slider
    const sldOp = document.getElementById('sld-opacity');
    const lblOp = document.getElementById('lbl-opacity');
    sldOp.addEventListener('input', () => {
      const val = parseInt(sldOp.value) / 100;
      State.overlayOpacity = val;
      lblOp.textContent = `${sldOp.value}%`;
      VenusMap.setCPROpacity(val);
    });

    // Filter chips
    document.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.chip').forEach(c => c.classList.remove('chip-active'));
        chip.classList.add('chip-active');
        State.layerFilter = chip.dataset.type;
        VenusMap.loadHotspots(State.hotspots);
      });
    });

    // Height exaggeration
    const sldExag = document.getElementById('sld-exag');
    const lblExag = document.getElementById('lbl-exag');
    sldExag.addEventListener('input', () => {
      lblExag.textContent = sldExag.value;
      Terrain3D.setExaggeration(parseInt(sldExag.value));
    });

    // Reset camera
    document.getElementById('btn-reset-cam').addEventListener('click', Terrain3D.resetCamera);

    // Popup close
    document.getElementById('popup-close').addEventListener('click', hideFeaturePopup);

    // Popup analyze button
    document.getElementById('popup-analyze').addEventListener('click', () => {
      const f = State.activeFeat;
      if (f) {
        CPRChart.fetchAndUpdate(f.lat, f.lon);
        hideFeaturePopup();
      }
    });

    // About modal
    document.getElementById('btn-help').addEventListener('click',   () => document.getElementById('modal-about').classList.remove('hidden'));
    document.getElementById('modal-close').addEventListener('click', () => document.getElementById('modal-about').classList.add('hidden'));
    document.getElementById('modal-about').addEventListener('click', e => {
      if (e.target === document.getElementById('modal-about')) document.getElementById('modal-about').classList.add('hidden');
    });
  }

  function _tog(id, cb) {
    document.getElementById(id).addEventListener('change', e => cb(e.target.checked));
  }

  function showFeaturePopup(props, lat, lon) {
    State.activeFeat = { ...props, lat, lon };

    document.getElementById('popup-badge').textContent   = props.type;
    document.getElementById('popup-name').textContent    = props.name;
    document.getElementById('popup-height').textContent  = `${props.height_km} km`;
    document.getElementById('popup-cpr').textContent     = props.cpr_peak.toFixed(2);
    document.getElementById('popup-active').textContent  = props.active ? '🔴 Active' : 'Inactive';
    document.getElementById('popup-active').style.color  = props.active ? '#ff6b35' : '#8899cc';
    document.getElementById('popup-desc').textContent    = props.description;

    // Papers
    const papersEl = document.getElementById('popup-papers');
    papersEl.innerHTML = (props.papers || []).map(p =>
      `<div class="popup-paper">${p}</div>`
    ).join('');

    // Badge color
    const badge = document.getElementById('popup-badge');
    badge.style.background = props.active
      ? 'rgba(255,107,53,0.2)' : 'rgba(0,212,255,0.15)';
    badge.style.borderColor = props.active ? '#ff6b35' : '#00d4ff';
    badge.style.color       = props.active ? '#ff6b35' : '#00d4ff';

    document.getElementById('feature-popup').classList.remove('hidden');

    // Fly to location
    VenusMap.flyTo(lat, lon, 4);

    // Auto-fetch CPR stats
    CPRChart.fetchAndUpdate(lat, lon);
  }

  function hideFeaturePopup() {
    document.getElementById('feature-popup').classList.add('hidden');
    State.activeFeat = null;
  }

  return { init, showFeaturePopup, hideFeaturePopup };
})();

// ─── 7. LITERATURE PANEL ──────────────────────────────────────────────────────
const Literature = (() => {

  function render(papers) {
    State.literature = papers;
    document.getElementById('lit-count').textContent = papers.length;

    const container = document.getElementById('lit-list');
    container.innerHTML = papers.map((p, i) => {
      const year  = p.year || '—';
      const cites = p.citations || 0;
      const oa    = p.is_oa;
      const url   = p.doi || p.oa_url || '#';
      const journal = p.journal || 'Preprint';

      return `
        <div class="paper-card" onclick="window.open('${url}','_blank')" title="${p.title}">
          <div class="paper-title">${p.title}</div>
          <div class="paper-meta">
            <span class="paper-year">${year}</span>
            <span class="paper-cite">⭐ ${cites}</span>
            ${oa ? '<span class="paper-oa-badge">Open Access</span>' : ''}
          </div>
          <div style="font-size:10px;color:#334;margin-top:3px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${journal}</div>
        </div>
      `;
    }).join('');
  }

  return { render };
})();

// ─── 8. QUICK JUMP ────────────────────────────────────────────────────────────
function buildQuickJump(features) {
  const container = document.getElementById('quick-jump');
  const top = features
    .sort((a, b) => b.properties.cpr_peak - a.properties.cpr_peak)
    .slice(0, 8);

  container.innerHTML = top.map(f => {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    return `
      <button class="jump-btn" onclick="VenusMap.flyTo(${lat},${lon},4);UIControls.showFeaturePopup(${JSON.stringify(JSON.stringify(p))}.replace ? JSON.parse(${JSON.stringify(JSON.stringify(p))}) : ${JSON.stringify(p)}, ${lat}, ${lon})">
        <span>${p.name}</span>
        <span style="display:flex;align-items:center;gap:5px">
          ${p.active ? '<span class="jump-active-dot"></span>' : ''}
          <span class="jump-cpr-badge">${p.cpr_peak.toFixed(2)}</span>
        </span>
      </button>
    `;
  }).join('');

  // Re-attach with proper handler (avoid JSON double-parse issues)
  container.innerHTML = '';
  top.forEach(f => {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    const btn = document.createElement('button');
    btn.className = 'jump-btn';
    btn.innerHTML = `
      <span>${p.name}</span>
      <span style="display:flex;align-items:center;gap:5px">
        ${p.active ? '<span class="jump-active-dot"></span>' : ''}
        <span class="jump-cpr-badge">${p.cpr_peak.toFixed(2)}</span>
      </span>
    `;
    btn.addEventListener('click', () => {
      VenusMap.flyTo(lat, lon, 4);
      UIControls.showFeaturePopup(p, lat, lon);
    });
    container.appendChild(btn);
  });
}

// ─── 9. MAIN INIT ─────────────────────────────────────────────────────────────
async function init() {
  // Start starfield immediately
  Starfield.init();

  // Simulate progress while loading API data
  Loader.setProgress(10, 'Starting starfield engine…');
  await sleep(200);

  Loader.setProgress(20, 'Connecting to Flask API…');
  await sleep(200);

  try {
    // Parallel data fetch
    Loader.setProgress(30, 'Fetching Venus feature database…');
    const [hotspotsRes, changesRes, litRes, terrainRes] = await Promise.all([
      fetch('/api/hotspots'),
      fetch('/api/changes'),
      fetch('/api/literature'),
      fetch('/api/terrain_data')
    ]);

    const hotspotsGJ = await hotspotsRes.json();
    const changesGJ  = await changesRes.json();
    const papers     = await litRes.json();
    const terrain    = await terrainRes.json();

    State.hotspots  = hotspotsGJ.features;
    State.changes   = changesGJ.features;

    Loader.setProgress(55, 'Initializing Leaflet map…');
    await sleep(100);

    // Init Leaflet map
    VenusMap.init();
    VenusMap.loadHotspots(State.hotspots);

    Loader.setProgress(70, 'Rendering CPR chart…');
    CPRChart.init();
    Literature.render(papers);

    Loader.setProgress(82, 'Building 3D terrain viewer…');
    await sleep(150);

    // Init Three.js terrain
    await Terrain3D.init(terrain);

    Loader.setProgress(92, 'Setting up UI controls…');
    UIControls.init();
    buildQuickJump(State.hotspots);

    // Update navbar count
    document.getElementById('ind-features').textContent = `${State.hotspots.length} Features`;

    Loader.setProgress(100, '✅ Ready!');
    await sleep(400);

    Loader.hide();

    // Auto-analyze Maat Mons on load
    setTimeout(() => {
      CPRChart.fetchAndUpdate(0.5, -165.4);
    }, 800);

  } catch (err) {
    console.error('Init error:', err);
    document.getElementById('loader-status').textContent = `Error: ${err.message} — Is the Flask server running?`;
    Loader.setProgress(100);
  }
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// Start
document.addEventListener('DOMContentLoaded', init);
