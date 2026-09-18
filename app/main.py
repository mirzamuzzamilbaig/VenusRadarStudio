"""
VenusRadarStudio — Flask API Server
=====================================
Run:  python main.py
Open: http://localhost:5000
"""

import os
import sys
import json

from flask import Flask, jsonify, send_from_directory, Response, request
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from radar_engine import (
    VENUS_FEATURES, CHANGE_EVENTS,
    generate_basemap, generate_cpr_map,
    generate_terrain_data, get_cpr_stats
)

# ─── App Setup ───────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
PAPERS_JSON  = os.path.join(BASE_DIR, 'top_q1_venus_papers.json')

# ─── Image Cache (generated on first request) ────────────────────────────────
_cache = {}

def _cached(key, generator_fn):
    if key not in _cache:
        _cache[key] = generator_fn()
    return _cache[key]


# ─── Static Frontend ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/css/<path:fn>')
def css(fn):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'css'), fn)

@app.route('/js/<path:fn>')
def js(fn):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'js'), fn)


# ─── API: Map Imagery ─────────────────────────────────────────────────────────

@app.route('/api/basemap')
def api_basemap():
    """Synthetic Magellan-like Venus radar basemap (RGB PNG, 2048×1024)."""
    data = _cached('basemap', lambda: generate_basemap(2048, 1024))
    return Response(data, mimetype='image/png',
                    headers={'Cache-Control': 'public, max-age=86400'})

@app.route('/api/cpr_layer')
def api_cpr_layer():
    """Synthetic CPR overlay map (RGBA PNG, 2048×1024)."""
    data = _cached('cpr', lambda: generate_cpr_map(2048, 1024))
    return Response(data, mimetype='image/png',
                    headers={'Cache-Control': 'public, max-age=86400'})


# ─── API: Science Data ────────────────────────────────────────────────────────

@app.route('/api/terrain_data')
def api_terrain_data():
    """3D terrain heightmap (JSON, 256×128 normalized heights)."""
    return jsonify(_cached('terrain', lambda: generate_terrain_data(256, 128)))

@app.route('/api/hotspots')
def api_hotspots():
    """Volcanic hotspots as GeoJSON FeatureCollection."""
    features = []
    for f in VENUS_FEATURES:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [f["lon"], f["lat"]]},
            "properties": {
                "id":          f["id"],
                "name":        f["name"],
                "type":        f["type"],
                "height_km":   f["height_km"],
                "cpr_peak":    f["cpr_peak"],
                "active":      f["active"],
                "description": f["description"],
                "papers":      f["papers"],
                "radius_deg":  f["radius_deg"]
            }
        })
    return jsonify({"type": "FeatureCollection", "features": features})

@app.route('/api/changes')
def api_changes():
    """Magellan change-detection events as GeoJSON FeatureCollection."""
    features = []
    for c in CHANGE_EVENTS:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
            "properties": {k: v for k, v in c.items() if k not in ("lat", "lon")}
        })
    return jsonify({"type": "FeatureCollection", "features": features})

@app.route('/api/literature')
def api_literature():
    """Return Venus radar literature metadata from JSON file."""
    try:
        with open(PAPERS_JSON, 'r', encoding='utf-8') as fh:
            return jsonify(json.load(fh))
    except FileNotFoundError:
        return jsonify([])

@app.route('/api/cpr_stats')
def api_cpr_stats():
    """CPR statistics for a clicked map coordinate."""
    lat    = float(request.args.get('lat',    0.0))
    lon    = float(request.args.get('lon',    0.0))
    radius = float(request.args.get('radius', 5.0))
    return jsonify(get_cpr_stats(lat, lon, radius))

@app.route('/api/status')
def api_status():
    return jsonify({
        "mode": "Demo (Synthetic Data)",
        "features": len(VENUS_FEATURES),
        "change_events": len(CHANGE_EVENTS),
        "cache_ready": list(_cache.keys())
    })


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    banner = (
        "\n"
        "  ============================================================\n"
        "      VenusRadarStudio  v1.0\n"
        "      Venus Radar CPR & Volcanic Change Detection\n"
        "      References: Campbell 2022 | Herrick 2023 | VERITAS\n"
        "  ------------------------------------------------------------\n"
        "      Open browser at:  http://localhost:5000\n"
        "  ============================================================\n"
    )
    print(banner)

    print("\n  Generating Venus maps (this takes ~15 s on first run)...")
    _cached('basemap',  lambda: generate_basemap(2048, 1024))
    print("  Basemap done.")
    _cached('cpr',      lambda: generate_cpr_map(2048, 1024))
    print("  CPR layer done.")
    _cached('terrain',  lambda: generate_terrain_data(256, 128))
    print("  Terrain done.\n  [OK] All maps ready! Starting server...\n")

    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
