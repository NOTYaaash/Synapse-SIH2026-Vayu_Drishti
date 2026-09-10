"""
standing_data_loader.py — Production loader for MOSDAC standing (static) data
==============================================================================
Standing data = datasets that do NOT update frequently:
    - Cyclone shelter coordinates & capacity
    - Automatic Weather Station (AWS) positions
    - Digital Elevation Model (DEM) grids
    - Land use / land cover rasters

Design contract:
    All public methods return plain dicts or np.ndarray — never DataFrame or
    xarray objects — so results are immediately consumable by the ML engine
    and Celery tasks without additional conversion.

Caching:
    Results are cached in-process (module-level `_cache` dict) so that
    repeated calls within the same Celery worker lifetime do not re-read disk.

Logging:
    Uses Python logging exclusively (no print statements).
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _ROOT / "data"

# Module-level in-process cache: {cache_key: result}
_cache: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# 1. Cyclone shelter / AWS station loader  (CSV → list[dict])
# ---------------------------------------------------------------------------

def load_station_records(
    csv_path: str | Path | None = None,
    cache_key: str = "station_records",
) -> list[dict]:
    """
    Load static station / shelter metadata from a CSV file.

    The CSV is expected to have at minimum the columns:
        id, name, lat, lon
    Additional columns (capacity, district, state, …) are passed through.

    Args:
        csv_path: Absolute path to the CSV. Defaults to
                  data/cyclone_shelters.csv (already present in the project).
        cache_key: Override the in-process cache key (useful in tests).

    Returns:
        List of dicts, one per station / shelter row.
        Returns [] and logs a warning if the file is missing or unreadable.
    """
    if cache_key in _cache:
        logger.debug("Returning cached station records (%d rows).", len(_cache[cache_key]))
        return _cache[cache_key]

    path = Path(csv_path) if csv_path else _DATA_DIR / "cyclone_shelters.csv"
    if not path.exists():
        logger.warning("Station CSV not found: %s", path)
        return []

    records: list[dict] = []
    try:
        with open(path, encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Coerce lat/lon to float; skip rows where conversion fails
                try:
                    row["lat"] = float(row.get("lat") or row.get("latitude") or 0)
                    row["lon"] = float(row.get("lon") or row.get("longitude") or 0)
                except (ValueError, TypeError):
                    logger.debug("Skipping malformed row: %s", row)
                    continue
                records.append(dict(row))

        logger.info("Loaded %d station records from %s.", len(records), path.name)
    except Exception as exc:
        logger.error("Failed to read station CSV %s: %s", path, exc)
        return []

    _cache[cache_key] = records
    return records


# ---------------------------------------------------------------------------
# 2. Station coordinates as numpy arrays  (for vectorised distance ops)
# ---------------------------------------------------------------------------

def load_station_coords(
    csv_path: str | Path | None = None,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """
    Convenience wrapper that returns station lat/lon as numpy arrays
    alongside the full record list, ready for broadcasting in haversine
    distance calculations (e.g. in the Geospatial layer).

    Returns:
        (lat_arr, lon_arr, records)
        lat_arr: shape (N,) float32
        lon_arr: shape (N,) float32
        records: list[dict] — the raw station metadata rows
    """
    records = load_station_records(csv_path)
    if not records:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32), []

    lat_arr = np.array([r["lat"] for r in records], dtype=np.float32)
    lon_arr = np.array([r["lon"] for r in records], dtype=np.float32)
    return lat_arr, lon_arr, records


# ---------------------------------------------------------------------------
# 3. Nearest stations finder
# ---------------------------------------------------------------------------

def find_nearest_stations(
    target_lat: float,
    target_lon: float,
    n: int = 5,
    csv_path: str | Path | None = None,
) -> list[dict]:
    """
    Return the *n* nearest stations to (target_lat, target_lon) sorted by
    great-circle distance (Haversine), closest first.

    Args:
        target_lat: Query latitude in decimal degrees.
        target_lon: Query longitude in decimal degrees.
        n:          Number of nearest stations to return.
        csv_path:   Override the default station CSV path.

    Returns:
        List of station dicts, each enriched with a 'distance_km' key.
    """
    lat_arr, lon_arr, records = load_station_coords(csv_path)
    if len(records) == 0:
        logger.warning("No station records available for proximity search.")
        return []

    R = 6371.0  # Earth radius km
    dlat = np.radians(lat_arr - target_lat)
    dlon = np.radians(lon_arr - target_lon)
    a = (np.sin(dlat / 2) ** 2
         + np.cos(np.radians(target_lat))
         * np.cos(np.radians(lat_arr))
         * np.sin(dlon / 2) ** 2)
    dist_km = 2 * R * np.arcsin(np.sqrt(a))

    idx = np.argsort(dist_km)[:n]
    results = []
    for i in idx:
        entry = dict(records[i])
        entry["distance_km"] = round(float(dist_km[i]), 2)
        results.append(entry)

    logger.debug("Nearest %d stations to (%.3f, %.3f): %s",
                 n, target_lat, target_lon,
                 [(r.get("name", "?"), r["distance_km"]) for r in results])
    return results


# ---------------------------------------------------------------------------
# 4. Raw standing data refresh  (for the periodic Celery sync task)
# ---------------------------------------------------------------------------

def refresh_standing_data_cache(
    api_url: Optional[str] = None,
    csv_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Invalidate and reload all in-process cached standing data.
    Called by the Celery beat task ``sync_standing_data`` to ensure
    workers hold fresh station metadata without a full restart.

    Args:
        api_url:  If provided, fetch fresh standing data from this URL
                  (expected to return a JSON array of station objects).
        csv_path: Local CSV path to reload from if api_url is None or fails.

    Returns:
        Summary dict: {"status": "ok"|"error", "rows_loaded": int, "source": str}
    """
    global _cache
    _cache.clear()
    logger.info("Standing data in-process cache cleared.")

    # -- Option A: fetch from live MOSDAC / external API ----------------------
    if api_url:
        try:
            import requests  # optional dependency — not required at import time
            resp = requests.get(api_url, timeout=15)
            resp.raise_for_status()
            rows: list[dict] = resp.json()
            # Coerce lat/lon
            clean: list[dict] = []
            for row in rows:
                try:
                    row["lat"] = float(row.get("lat") or row.get("latitude", 0))
                    row["lon"] = float(row.get("lon") or row.get("longitude", 0))
                    clean.append(row)
                except (ValueError, TypeError):
                    continue
            _cache["station_records"] = clean
            logger.info("Refreshed %d station records from API: %s", len(clean), api_url)
            return {"status": "ok", "rows_loaded": len(clean), "source": api_url}
        except Exception as exc:
            logger.warning("API refresh failed (%s): %s. Falling back to CSV.", api_url, exc)

    # -- Option B: reload from local CSV --------------------------------------
    records = load_station_records(csv_path)
    return {
        "status": "ok" if records else "error",
        "rows_loaded": len(records),
        "source": str(csv_path or _DATA_DIR / "cyclone_shelters.csv"),
    }
