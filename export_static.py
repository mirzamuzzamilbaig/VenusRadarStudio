"""
export_static.py
Generates static assets for GitHub Pages deployment.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
from radar_engine import (
    VENUS_FEATURES, CHANGE_EVENTS,
    generate_basemap, generate_cpr_map,
    generate_terrain_data
)

def export_all():
    base_dir = os.path.dirname(__file__)
    for target in [os.path.join(base_dir, 'frontend', 'data'), os.path.join(base_dir, 'docs', 'data')]:
        os.makedirs(target, exist_ok=True)
        print(f"Exporting to {target}...")

        # Basemap
        bm = generate_basemap(2048, 1024)
        with open(os.path.join(target, 'basemap.png'), 'wb') as f:
            f.write(bm)

        # CPR layer
        cpr = generate_cpr_map(2048, 1024)
        with open(os.path.join(target, 'cpr_layer.png'), 'wb') as f:
            f.write(cpr)

        # Terrain
        terrain = generate_terrain_data(256, 128)
        with open(os.path.join(target, 'terrain_data.json'), 'w', encoding='utf-8') as f:
            json.dump(terrain, f)

        # Hotspots
        hotspots = []
        for feat in VENUS_FEATURES:
            hotspots.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [feat["lon"], feat["lat"]]},
                "properties": {
                    "id": feat["id"],
                    "name": feat["name"],
                    "type": feat["type"],
                    "height_km": feat["height_km"],
                    "cpr_peak": feat["cpr_peak"],
                    "active": feat["active"],
                    "description": feat["description"],
                    "papers": feat["papers"],
                    "radius_deg": feat["radius_deg"]
                }
            })
        with open(os.path.join(target, 'hotspots.json'), 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": hotspots}, f, indent=2)

        # Changes
        changes = []
        for c in CHANGE_EVENTS:
            changes.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": {k: v for k, v in c.items() if k not in ("lat", "lon")}
            })
        with open(os.path.join(target, 'changes.json'), 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": changes}, f, indent=2)

        # Literature
        lit_path = os.path.join(base_dir, 'top_q1_venus_papers.json')
        if os.path.exists(lit_path):
            with open(lit_path, 'r', encoding='utf-8') as f:
                papers = json.load(f)
            with open(os.path.join(target, 'literature.json'), 'w', encoding='utf-8') as f:
                json.dump(papers, f, indent=2)

    print("Static export complete!")

if __name__ == '__main__':
    export_all()
