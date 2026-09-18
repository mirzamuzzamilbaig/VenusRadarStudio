"""
VenusRadarStudio — Radar Science Engine
========================================
Generates synthetic CPR/radar data grounded in real Venus geophysics.

Science references:
- Campbell & Campbell 2022, PSJ (Arecibo Radar Maps of Venus 1988-2020)
- Herrick & Hensley 2023, Science (Magellan volcanic change detection)
- Nature Astronomy 2024 (ongoing volcanic activity evidence)
- VERITAS/EnVision mission planning documents
"""

import numpy as np
from scipy.ndimage import gaussian_filter, zoom as ndim_zoom
from PIL import Image
import io

# ─── Venus Feature Database ──────────────────────────────────────────────────
# Coordinates: lat (-90 to 90), lon (-180 to 180)
# Venus PDS convention is 0-360°E; we convert: lon_leaflet = lon_pds - 360 if lon_pds > 180
# CPR (Circular Polarization Ratio = SCP / OCP):
#   < 0.2  : smooth volcanic plains (basalt)
#   0.2–0.5: moderately rough terrain
#   0.5–0.9: rough volcanic flows, lava fields
#   0.9–1.5: highly rough, recent flows, retroreflectors
#   > 1.5  : Maxwell Montes-type extreme retroreflection

VENUS_FEATURES = [
    {
        "id": "maat_mons",
        "name": "Maat Mons",
        "lat": 0.5,
        "lon": -165.4,       # 194.6°E PDS
        "type": "Shield Volcano",
        "height_km": 8.0,
        "radius_deg": 4.0,
        "cpr_peak": 1.25,
        "active": True,
        "description": (
            "Largest volcano on Venus (~8 km high). Located in Atla Regio. "
            "Herrick & Hensley (2023) detected a vent shape change between "
            "Magellan C1 (1990) and C2 (1992) consistent with lava flow. "
            "First confirmed evidence of currently active volcanism on Venus."
        ),
        "papers": [
            "Herrick & Hensley 2023, Science 379, 1205",
            "Campbell & Campbell 2022, PSJ"
        ]
    },
    {
        "id": "sapas_mons",
        "name": "Sapas Mons",
        "lat": 8.5,
        "lon": -171.7,       # 188.3°E PDS
        "type": "Shield Volcano",
        "height_km": 4.0,
        "radius_deg": 4.5,
        "cpr_peak": 0.95,
        "active": False,
        "description": (
            "Large shield volcano with extensive lava flow aprons. "
            "High Arecibo SCP backscatter consistent with rough aa-type flows. "
            "Paired with Maat Mons at Atla Regio."
        ),
        "papers": ["Campbell & Campbell 2022, PSJ"]
    },
    {
        "id": "ozza_mons",
        "name": "Ozza Mons",
        "lat": 4.5,
        "lon": -159.0,       # 201°E PDS
        "type": "Shield Volcano",
        "height_km": 5.0,
        "radius_deg": 3.0,
        "cpr_peak": 0.88,
        "active": False,
        "description": (
            "Shield volcano in southern Atla Regio. "
            "Summit height ~5 km. Extensive radar-bright flow fields."
        ),
        "papers": ["Campbell & Campbell 2022, PSJ"]
    },
    {
        "id": "atla_regio",
        "name": "Atla Regio",
        "lat": 10.0,
        "lon": -162.0,       # ~198°E PDS
        "type": "Volcanic Rise",
        "height_km": 4.0,
        "radius_deg": 18.0,
        "cpr_peak": 0.72,
        "active": True,
        "description": (
            "Major volcanic rise hosting Maat Mons, Ozza Mons, and Sapas Mons. "
            "Driven by deep mantle plume volcanism (Campbell 2025, JGR Planets). "
            "VERITAS priority target for InSAR deformation mapping."
        ),
        "papers": [
            "Evolution of Plume Volcanism at Atla Regio 2025, JGR Planets",
            "Herrick & Hensley 2023, Science"
        ]
    },
    {
        "id": "maxwell_montes",
        "name": "Maxwell Montes",
        "lat": 65.0,
        "lon": 3.0,
        "type": "Mountain Range",
        "height_km": 11.0,
        "radius_deg": 5.5,
        "cpr_peak": 1.85,
        "active": False,
        "description": (
            "Highest point on Venus (11 km above MPR). "
            "Extreme radar retroreflection (CPR > 1.8) attributed to ferroelectric "
            "minerals (perovskite/pyrite) stable at high altitudes. "
            "Arecibo 12.6 cm data shows brightest feature on the planet."
        ),
        "papers": [
            "Campbell & Campbell 2022, PSJ",
            "The surface of Venus, 2003, Rep. Prog. Phys."
        ]
    },
    {
        "id": "beta_regio",
        "name": "Beta Regio",
        "lat": 25.0,
        "lon": -78.0,        # 282°E PDS
        "type": "Volcanic Rise",
        "height_km": 5.0,
        "radius_deg": 14.0,
        "cpr_peak": 0.88,
        "active": True,
        "description": (
            "Rifted volcanic rise with active extension. "
            "Contains Theia Mons and Rhea Mons. Deep graben system. "
            "Phoebe Regio thermal anomaly detected nearby (VEx VIRTIS data)."
        ),
        "papers": [
            "Campbell & Campbell 2022, PSJ",
            "Evidence of ongoing volcanic activity 2024, Nature Astronomy"
        ]
    },
    {
        "id": "theia_mons",
        "name": "Theia Mons",
        "lat": 23.0,
        "lon": -78.0,
        "type": "Shield Volcano",
        "height_km": 4.5,
        "radius_deg": 3.5,
        "cpr_peak": 0.92,
        "active": False,
        "description": "Shield volcano at the heart of Beta Regio. Large summit caldera.",
        "papers": ["Campbell & Campbell 2022, PSJ"]
    },
    {
        "id": "rhea_mons",
        "name": "Rhea Mons",
        "lat": -32.0,
        "lon": -78.0,
        "type": "Shield Volcano",
        "height_km": 3.0,
        "radius_deg": 3.0,
        "cpr_peak": 0.72,
        "active": False,
        "description": "Southern Beta Regio shield volcano. Less radar-bright than Theia.",
        "papers": ["The surface of Venus, 2003, Rep. Prog. Phys."]
    },
    {
        "id": "idunn_mons",
        "name": "Idunn Mons",
        "lat": -46.0,
        "lon": -147.0,       # 213°E PDS
        "type": "Shield Volcano",
        "height_km": 2.5,
        "radius_deg": 2.5,
        "cpr_peak": 0.88,
        "active": True,
        "description": (
            "Volcano with anomalous thermal emissivity detected by Venus Express VIRTIS. "
            "Elevated surface temperatures suggest geologically recent volcanism. "
            "Cited in 2024 Nature Astronomy paper on ongoing Venus volcanic activity."
        ),
        "papers": [
            "Evidence of ongoing volcanic activity 2024, Nature Astronomy",
            "Ongoing Volcanic Activity on Venus 2024, EPSC"
        ]
    },
    {
        "id": "ishtar_terra",
        "name": "Ishtar Terra",
        "lat": 70.0,
        "lon": 30.0,
        "type": "Highland Plateau",
        "height_km": 3.5,
        "radius_deg": 20.0,
        "cpr_peak": 0.65,
        "active": False,
        "description": (
            "Northern polar highland containing Maxwell Montes. "
            "Lacus Tessera terrain — ancient, highly deformed crust. "
            "Area comparable to Australia. Surrounded by mountain belts."
        ),
        "papers": [
            "Venus Evolution Through Time 2023, Space Sci. Rev.",
            "The surface of Venus, 2003"
        ]
    },
    {
        "id": "aphrodite_terra",
        "name": "Aphrodite Terra",
        "lat": -10.0,
        "lon": -30.0,        # ~150°E average PDS
        "type": "Highland",
        "height_km": 4.0,
        "radius_deg": 45.0,
        "cpr_peak": 0.58,
        "active": False,
        "description": (
            "Largest highland region on Venus (~10,000 km wide, size of Africa). "
            "Complex mix of rifting and volcanism. Contains Diana Chasma deep rift. "
            "Eastern section shows Arecibo CPR enhancement from rough terrain."
        ),
        "papers": [
            "Venus Evolution Through Time 2023, Space Sci. Rev.",
            "Future of Venus Research 2018, Space Sci. Rev."
        ]
    },
    {
        "id": "phoebe_regio",
        "name": "Phoebe Regio",
        "lat": -10.0,
        "lon": -77.0,        # 283°E PDS
        "type": "Volcanic Region",
        "height_km": 2.0,
        "radius_deg": 10.0,
        "cpr_peak": 0.78,
        "active": True,
        "description": (
            "Volcanic region with evidence of recent emissivity anomalies. "
            "Thermal emission from VEx VIRTIS suggests warm surface features. "
            "VERITAS radar target for potential lava tube detection."
        ),
        "papers": [
            "Evidence of ongoing volcanic activity 2024, Nature Astronomy",
            "VERITAS Discovery Mission 2022, IEEE Aerospace"
        ]
    }
]

# ─── Magellan Change Detection Events ────────────────────────────────────────
CHANGE_EVENTS = [
    {
        "name": "Maat Mons Vent Expansion",
        "lat": 0.5,
        "lon": -165.4,
        "epoch1": "Magellan Cycle 1 (Feb 1990)",
        "epoch2": "Magellan Cycle 2 (Oct 1991)",
        "change_type": "Lava Flow Expansion",
        "delta_backscatter_db": 3.2,
        "area_km2": 2.2,
        "confidence": "High",
        "paper": "Herrick & Hensley 2023, Science 379(6629), 1205–1208"
    },
    {
        "name": "Atla Regio Backscatter Anomaly",
        "lat": 12.0,
        "lon": -158.0,
        "epoch1": "Magellan Cycle 1 (1990)",
        "epoch2": "Magellan Cycle 3 (1993)",
        "change_type": "Surface Roughness Change",
        "delta_backscatter_db": 1.8,
        "area_km2": 15.0,
        "confidence": "Medium",
        "paper": "Ongoing Volcanic Activity on Venus, EPSC 2024"
    },
    {
        "name": "Idunn Thermal Signature",
        "lat": -46.0,
        "lon": -147.0,
        "epoch1": "Magellan C2 (1991)",
        "epoch2": "Magellan C3 (1993)",
        "change_type": "Emissivity Change",
        "delta_backscatter_db": 1.2,
        "area_km2": 8.0,
        "confidence": "Medium",
        "paper": "Nature Astronomy 2024 — ongoing volcanic activity"
    },
    {
        "name": "Phoebe Regio Anomaly",
        "lat": -10.0,
        "lon": -77.0,
        "epoch1": "Magellan C1 (1990)",
        "epoch2": "Magellan C2 (1991)",
        "change_type": "Backscatter Enhancement",
        "delta_backscatter_db": 0.9,
        "area_km2": 45.0,
        "confidence": "Low",
        "paper": "Nature Astronomy 2024 — ongoing volcanic activity"
    }
]


# ─── Basemap Generation ──────────────────────────────────────────────────────

def _make_noise_layer(shape, scale, sigma, amplitude):
    """Create a single fractal noise layer."""
    h, w = shape
    rh, rw = max(2, h // scale), max(2, w // scale)
    raw = np.random.randn(rh, rw).astype(np.float32)
    if rh != h or rw != w:
        upsampled = ndim_zoom(raw, (h / rh, w / rw))[:h, :w]
    else:
        upsampled = raw
    return gaussian_filter(upsampled, sigma=sigma) * amplitude


def generate_basemap(width: int = 2048, height: int = 1024) -> bytes:
    """
    Generate a synthetic Magellan-like Venus radar basemap (RGB PNG).
    Uses multi-scale fractal noise + planetary feature overlays.
    """
    np.random.seed(42)

    # ── Coordinate grids ──────────────────────────────────────────────────────
    lon_g = np.linspace(-180, 180, width)
    lat_g = np.linspace(90, -90, height)
    lon_map, lat_map = np.meshgrid(lon_g, lat_g)

    # ── Multi-scale fractal noise ─────────────────────────────────────────────
    terrain = np.zeros((height, width), dtype=np.float32)
    terrain += _make_noise_layer((height, width), 32, 30, 0.40)
    terrain += _make_noise_layer((height, width), 8,  8,  0.30)
    terrain += _make_noise_layer((height, width), 2,  2,  0.15)
    terrain += np.random.randn(height, width).astype(np.float32) * 0.04

    # ── Planetary-scale geologic features ────────────────────────────────────
    # Ishtar Terra (N polar highland)
    ishtar = (lat_map > 58) & (lat_map < 82) & (lon_map > -15) & (lon_map < 75)
    terrain[ishtar] += 0.60

    # Aphrodite Terra (equatorial, wraps from 60°E to 210°E → -150°)
    aphro = (lat_map > -28) & (lat_map < 12) & ((lon_map > 55) | (lon_map < -140))
    terrain[aphro] += 0.42

    # Beta-Atla-Themis belt
    bat = (lat_map > -20) & (lat_map < 38) & ((lon_map < -60) | (lon_map > 155))
    terrain[bat] += 0.28

    # Lowland plains (Atalanta/Sedna/Guinevere)
    plains = (lat_map > 30) & (lat_map < 60) & (lon_map > -80) & (lon_map < 80)
    terrain[plains] -= 0.18

    # ── Volcano hotspot blobs ─────────────────────────────────────────────────
    yy_idx = np.arange(height)
    xx_idx = np.arange(width)
    xx, yy = np.meshgrid(xx_idx, yy_idx)

    for feat in VENUS_FEATURES:
        px = int((feat["lon"] + 180) / 360 * width)
        py = int((90 - feat["lat"]) / 180 * height)
        r  = feat["radius_deg"]
        sx = max(1.0, r / 360 * width * 0.65)
        sy = max(1.0, r / 180 * height * 0.65)
        blob = feat["cpr_peak"] * 0.4 * np.exp(
            -((xx - px)**2 / (2 * sx**2) + (yy - py)**2 / (2 * sy**2))
        )
        terrain += blob.astype(np.float32)

    # ── Radar SAR stripe artifact (characteristic of Magellan) ───────────────
    stripe = np.random.randn(height, 1).astype(np.float32) * 0.012
    terrain += stripe

    # ── Normalize + gamma ─────────────────────────────────────────────────────
    terrain = (terrain - terrain.min()) / (terrain.max() - terrain.min())
    terrain = np.power(np.clip(terrain, 0, 1), 0.72)

    # ── Magellan false-color (warm gray-brown radar look) ────────────────────
    r_ch = np.clip(terrain * 0.78 * 255, 0, 255).astype(np.uint8)
    g_ch = np.clip(terrain * 0.68 * 255, 0, 255).astype(np.uint8)
    b_ch = np.clip(terrain * 0.55 * 255, 0, 255).astype(np.uint8)

    img = Image.fromarray(np.stack([r_ch, g_ch, b_ch], axis=2), 'RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


# ─── CPR Layer Generation ────────────────────────────────────────────────────

def generate_cpr_map(width: int = 2048, height: int = 1024) -> bytes:
    """
    Generate a synthetic CPR map as RGBA PNG overlay.

    CPR colormap:
    0.0–0.25  → Deep blue   (smooth basaltic plains)
    0.25–0.50 → Cyan→green  (transitional)
    0.50–0.75 → Yellow      (rough volcanic flows)
    0.75–1.00 → Orange→red  (highly rough, lava)
    >1.00     → Red→white   (retroreflector, Maxwell-type)
    """
    np.random.seed(123)

    cpr = np.ones((height, width), dtype=np.float32) * 0.14
    cpr += np.abs(np.random.randn(height, width).astype(np.float32)) * 0.025
    cpr = gaussian_filter(cpr, sigma=3)

    yy_idx = np.arange(height)
    xx_idx = np.arange(width)
    xx, yy = np.meshgrid(xx_idx, yy_idx)

    for feat in VENUS_FEATURES:
        px = int((feat["lon"] + 180) / 360 * width)
        py = int((90 - feat["lat"]) / 180 * height)
        r  = feat["radius_deg"]
        sx = max(1.0, r / 360 * width * 0.6)
        sy = max(1.0, r / 180 * height * 0.6)
        blob = feat["cpr_peak"] * np.exp(
            -((xx - px)**2 / (2 * sx**2) + (yy - py)**2 / (2 * sy**2))
        )
        cpr = np.maximum(cpr, blob.astype(np.float32))

    cpr = gaussian_filter(cpr, sigma=2.5)

    # ── CPR → RGBA colormap (plasma-like) ────────────────────────────────────
    cpr_n = np.clip(cpr / 2.0, 0, 1)   # normalize 0–2 CPR to 0–1

    r_ch = np.zeros((height, width), dtype=np.float32)
    g_ch = np.zeros((height, width), dtype=np.float32)
    b_ch = np.zeros((height, width), dtype=np.float32)

    # Segment 0: deep blue  (cpr_n 0.00–0.20)
    m = cpr_n <= 0.20
    t = cpr_n[m] / 0.20
    r_ch[m] = t * 30
    g_ch[m] = t * 80
    b_ch[m] = 180 + t * 75

    # Segment 1: blue→cyan (cpr_n 0.20–0.40)
    m = (cpr_n > 0.20) & (cpr_n <= 0.40)
    t = (cpr_n[m] - 0.20) / 0.20
    r_ch[m] = 30 + t * 0
    g_ch[m] = 80 + t * 175
    b_ch[m] = 255 - t * 80

    # Segment 2: cyan→yellow (cpr_n 0.40–0.65)
    m = (cpr_n > 0.40) & (cpr_n <= 0.65)
    t = (cpr_n[m] - 0.40) / 0.25
    r_ch[m] = t * 255
    g_ch[m] = 255
    b_ch[m] = 175 - t * 175

    # Segment 3: yellow→orange→red (cpr_n 0.65–0.90)
    m = (cpr_n > 0.65) & (cpr_n <= 0.90)
    t = (cpr_n[m] - 0.65) / 0.25
    r_ch[m] = 255
    g_ch[m] = 255 - t * 200
    b_ch[m] = 0

    # Segment 4: red→white (cpr_n > 0.90)
    m = cpr_n > 0.90
    t = np.clip((cpr_n[m] - 0.90) / 0.10, 0, 1)
    r_ch[m] = 255
    g_ch[m] = t * 255
    b_ch[m] = t * 255

    # Alpha: transparent for background plains, opaque for anomalies
    alpha = np.clip((cpr - 0.10) / 1.90 * 210, 0, 210).astype(np.uint8)

    img = Image.fromarray(np.stack([
        np.clip(r_ch, 0, 255).astype(np.uint8),
        np.clip(g_ch, 0, 255).astype(np.uint8),
        np.clip(b_ch, 0, 255).astype(np.uint8),
        alpha
    ], axis=2), 'RGBA')

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


# ─── 3D Terrain Heightmap ────────────────────────────────────────────────────

def generate_terrain_data(width: int = 256, height: int = 128) -> dict:
    """
    Generate terrain heightmap for Three.js viewer.
    Based on real Venus VGDR statistics: mean +0 km, std ~2 km, max ~11 km.
    """
    np.random.seed(77)

    terrain = np.zeros((height, width), dtype=np.float32)
    terrain += _make_noise_layer((height, width), 8, 5, 3.0)
    terrain += _make_noise_layer((height, width), 2, 2, 1.0)
    terrain += np.random.randn(height, width).astype(np.float32) * 0.2

    yy_idx = np.arange(height)
    xx_idx = np.arange(width)
    xx, yy = np.meshgrid(xx_idx, yy_idx)

    for feat in VENUS_FEATURES:
        px = int((feat["lon"] + 180) / 360 * width)
        py = int((90 - feat["lat"]) / 180 * height)
        r  = feat.get("radius_deg", 3)
        sx = max(0.5, r / 360 * width * 0.45)
        sy = max(0.5, r / 180 * height * 0.45)
        peak = feat["height_km"] * np.exp(
            -((xx - px)**2 / (2 * sx**2) + (yy - py)**2 / (2 * sy**2))
        )
        terrain += peak.astype(np.float32)

    min_h = float(terrain.min())
    max_h = float(terrain.max())
    terrain_norm = (terrain - min_h) / max(max_h - min_h, 1e-6)

    return {
        "heights": terrain_norm.flatten().tolist(),
        "width": width,
        "height": height,
        "min_km": round(min_h, 2),
        "max_km": round(max_h, 2)
    }


# ─── CPR Statistics ──────────────────────────────────────────────────────────

def get_cpr_stats(lat: float, lon: float, radius_deg: float = 5.0) -> dict:
    """Compute CPR statistics for a clicked map region."""
    seed = int(abs(lat * 137 + lon * 97)) % 9999
    np.random.seed(seed)

    # Find nearest named feature
    min_dist = float('inf')
    nearest = None
    for feat in VENUS_FEATURES:
        d = np.sqrt((feat["lat"] - lat) ** 2 + (feat["lon"] - lon) ** 2)
        if d < min_dist:
            min_dist = d
            nearest = feat

    # Base CPR from proximity
    if nearest and min_dist < nearest.get("radius_deg", 5):
        t = 1.0 - min_dist / nearest["radius_deg"]
        center_cpr = 0.14 + (nearest["cpr_peak"] - 0.14) * t
    else:
        center_cpr = 0.14 + np.random.uniform(0, 0.08)

    # Generate realistic sample distribution
    n = 1200
    cpr_samples = np.random.gamma(shape=2.0, scale=center_cpr / 2.0, size=n)
    cpr_samples = np.clip(cpr_samples, 0.01, 3.5)

    hist, bins = np.histogram(cpr_samples, bins=35, range=(0.0, 2.5))

    return {
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "radius_deg": radius_deg,
        "mean_cpr": round(float(np.mean(cpr_samples)), 4),
        "median_cpr": round(float(np.median(cpr_samples)), 4),
        "max_cpr": round(float(np.max(cpr_samples)), 4),
        "std_cpr": round(float(np.std(cpr_samples)), 4),
        "p95_cpr": round(float(np.percentile(cpr_samples, 95)), 4),
        "histogram": {
            "counts": hist.tolist(),
            "bin_edges": [round(b, 3) for b in bins.tolist()]
        },
        "interpretation": _interpret_cpr(float(np.mean(cpr_samples))),
        "terrain_class": _classify_terrain(float(np.mean(cpr_samples))),
        "nearest_feature": nearest["name"] if nearest else "Open Plains",
        "distance_to_feature_deg": round(min_dist, 2)
    }


def _interpret_cpr(mean_cpr: float) -> str:
    if mean_cpr < 0.20:
        return "Smooth volcanic plains — basaltic lowlands, minimal surface roughness at 12.6 cm wavelength"
    elif mean_cpr < 0.40:
        return "Moderately rough terrain — pahoehoe-type lava flows or fractured plains"
    elif mean_cpr < 0.70:
        return "Rough volcanic surface — aa-type lava flows or deformed tesserae terrain"
    elif mean_cpr < 1.10:
        return "Highly rough — probable recent/active volcanic flow field (similar to Maat Mons)"
    else:
        return "Extreme retroreflection — mountain/highland terrain with specular coherent backscatter (Maxwell-type)"


def _classify_terrain(mean_cpr: float) -> str:
    if mean_cpr < 0.20:
        return "Plains"
    elif mean_cpr < 0.45:
        return "Lava Fields"
    elif mean_cpr < 0.75:
        return "Rough Volcanic"
    elif mean_cpr < 1.10:
        return "Active Flow Zone"
    else:
        return "Retroreflector (Highland)"
