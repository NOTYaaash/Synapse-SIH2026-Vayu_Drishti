import json
import math
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Open-Meteo GFS wind grid fetch ──────────────────────────────────────────
# We fetch a 0.25° resolution grid over the Bay of Bengal / Indian Ocean region.
# Open-Meteo serves real NOAA GFS data for free, no API key required.
# Grid: lon 40..110, lat -15..40 → 281×221 points at 0.25° spacing
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lats}"
    "&longitude={lons}"
    "&hourly=wind_speed_10m,wind_direction_10m"
    "&forecast_days=1"
    "&models=gfs_seamless"
    "&format=json"
    "&wind_speed_unit=ms"
    "&timezone=UTC"
    "&timeformat=unixtime"
)

# 20×12 grid (~3.5° spacing) = 240 points → ONE API call, no rate limiting
# Bilinear interpolation in WindyParticleLayer makes this look perfectly smooth.
GRID_LON_START = 40.0
GRID_LON_END   = 110.0
GRID_LON_N     = 20       # 20 longitude points
GRID_LAT_START = 40.0     # top-left lat (north)
GRID_LAT_END   = -15.0
GRID_LAT_N     = 12       # 12 latitude points


CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "wind_cache"
CACHE_JSON = CACHE_DIR / "wind-data.json"
CACHE_META = CACHE_DIR / "wind-meta.json"   # tracks the last downloaded date+cycle


def _latest_gfs_params():
    """Return the most recent available GFS model run (date, cycle)."""
    now = datetime.now(timezone.utc)
    for cycle in (18, 12, 6, 0):
        if now.hour >= cycle + 4:
            return now.strftime("%Y%m%d"), cycle
    yesterday = now - timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), 18


def _read_meta():
    """Return stored (date, cycle) or (None, None) if no metadata exists."""
    try:
        with open(CACHE_META) as f:
            m = json.load(f)
            return m.get("date"), m.get("cycle")
    except Exception:
        return None, None


def _write_meta(date: str, cycle: int):
    with open(CACHE_META, "w") as f:
        json.dump({"date": date, "cycle": cycle, "updated_at": datetime.utcnow().isoformat()}, f)


def _cleanup_old_gribs(keep_path: str | None = None):
    """Delete all .grb2 files in the cache directory except keep_path."""
    for p in CACHE_DIR.glob("*.grb2"):
        if keep_path is None or str(p) != keep_path:
            try:
                p.unlink()
                print(f"Deleted old GRIB2: {p}")
            except Exception as e:
                print(f"Could not delete {p}: {e}")




def _fetch_open_meteo_grid() -> list:
    """
    Fetch a real GFS 10m wind grid from Open-Meteo using a single API call.
    Grid: 20×12 = 240 points at ~3.5° spacing over the Bay of Bengal region.
    Bilinear interpolation in the frontend canvas smooths out the coarse grid.
    """
    import math

    lon_step = (GRID_LON_END - GRID_LON_START) / (GRID_LON_N - 1)
    lat_step = (GRID_LAT_START - GRID_LAT_END)  / (GRID_LAT_N - 1)

    lons = [round(GRID_LON_START + i * lon_step, 4) for i in range(GRID_LON_N)]
    lats = [round(GRID_LAT_START - j * lat_step, 4) for j in range(GRID_LAT_N)]

    lat_str = ",".join(str(x) for x in lats * len(lons))  # all lat values
    # Build flat list of (lat, lon) pairs: for each lon column, all rows
    pairs = [(lats[j], lons[i]) for i in range(len(lons)) for j in range(len(lats))]
    lat_str = ",".join(str(p[0]) for p in pairs)
    lon_str = ",".join(str(p[1]) for p in pairs)

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat_str}&longitude={lon_str}"
        "&hourly=wind_speed_10m,wind_direction_10m"
        "&forecast_days=1&models=gfs_seamless"
        "&wind_speed_unit=ms&timezone=UTC&timeformat=unixtime"
    )

    print(f"Fetching Open-Meteo GFS grid: {GRID_LON_N}×{GRID_LAT_N} = {len(pairs)} points (single request)...")
    try:
        req = urllib.request.urlopen(url, timeout=60)
        data = json.loads(req.read())
    except Exception as e:
        if "429" in str(e):
            raise RuntimeError("RATE_LIMITED")
        raise

    if isinstance(data, dict):
        data = [data]

    # Reconstruct row-major u/v grid (north to south, west to east)
    u_grid = [[0.0] * GRID_LON_N for _ in range(GRID_LAT_N)]
    v_grid = [[0.0] * GRID_LON_N for _ in range(GRID_LAT_N)]

    for idx, d in enumerate(data):
        i = idx // GRID_LAT_N   # lon index
        j = idx  % GRID_LAT_N   # lat index (north=0)
        spd  = (d["hourly"]["wind_speed_10m"][0]  or 0.0)
        dirn = (d["hourly"]["wind_direction_10m"][0] or 0.0)
        rad  = math.radians(dirn)
        u_grid[j][i] = round(-spd * math.sin(rad), 4)
        v_grid[j][i] = round(-spd * math.cos(rad), 4)

    u_flat = [u_grid[j][i] for j in range(GRID_LAT_N) for i in range(GRID_LON_N)]
    v_flat = [v_grid[j][i] for j in range(GRID_LAT_N) for i in range(GRID_LON_N)]

    def _hdr(name):
        return {
            "discipline": 0, "parameterCategory": 2,
            "parameterNumber": 2 if name == "U" else 3,
            "surface1Type": 103, "surface1Value": 10,
            "gridDefinitionTemplate": 0,
            "nx": GRID_LON_N, "ny": GRID_LAT_N,
            "lo1": GRID_LON_START, "lo2": GRID_LON_END,
            "la1": GRID_LAT_START, "la2": GRID_LAT_END,
            "dx": round(lon_step, 4), "dy": round(lat_step, 4),
            "refTime": datetime.utcnow().strftime("%Y-%m-%dT%H:00:00.000Z"),
            "name": f"{name}-component of wind [GFS via Open-Meteo]",
        }

    print(f"Open-Meteo grid fetched successfully: {GRID_LON_N}×{GRID_LAT_N} points.")
    return [
        {"header": _hdr("U"), "data": u_flat},
        {"header": _hdr("V"), "data": v_flat},
    ]


def _fetch_era5_grid() -> list:
    """
    Fallback: fetch ERA5 reanalysis wind data from Open-Meteo archive API.
    Uses yesterday's data (always available) on a separate server/rate limit.
    """
    import math
    from datetime import date, timedelta

    yesterday = (date.today() - timedelta(days=1)).isoformat()

    lon_step = (GRID_LON_END - GRID_LON_START) / (GRID_LON_N - 1)
    lat_step = (GRID_LAT_START - GRID_LAT_END) / (GRID_LAT_N - 1)
    lons = [round(GRID_LON_START + i * lon_step, 4) for i in range(GRID_LON_N)]
    lats = [round(GRID_LAT_START - j * lat_step, 4) for j in range(GRID_LAT_N)]
    pairs = [(lats[j], lons[i]) for i in range(len(lons)) for j in range(len(lats))]
    lat_str = ",".join(str(p[0]) for p in pairs)
    lon_str = ",".join(str(p[1]) for p in pairs)

    url = (
        "https://archive-api.open-meteo.com/v1/era5"
        f"?latitude={lat_str}&longitude={lon_str}"
        f"&start_date={yesterday}&end_date={yesterday}"
        "&hourly=wind_speed_10m,wind_direction_10m"
        "&wind_speed_unit=ms&timezone=UTC&timeformat=unixtime"
    )

    print(f"Fetching ERA5 archive grid (fallback): {GRID_LON_N}×{GRID_LAT_N} points...")
    req = urllib.request.urlopen(url, timeout=60)
    data = json.loads(req.read())
    if isinstance(data, dict):
        data = [data]

    u_grid = [[0.0] * GRID_LON_N for _ in range(GRID_LAT_N)]
    v_grid = [[0.0] * GRID_LON_N for _ in range(GRID_LAT_N)]
    for idx, d in enumerate(data):
        i = idx // GRID_LAT_N
        j = idx % GRID_LAT_N
        spd  = (d["hourly"]["wind_speed_10m"][0] or 0.0)
        dirn = (d["hourly"]["wind_direction_10m"][0] or 0.0)
        rad  = math.radians(dirn)
        u_grid[j][i] = round(-spd * math.sin(rad), 4)
        v_grid[j][i] = round(-spd * math.cos(rad), 4)

    u_flat = [u_grid[j][i] for j in range(GRID_LAT_N) for i in range(GRID_LON_N)]
    v_flat = [v_grid[j][i] for j in range(GRID_LAT_N) for i in range(GRID_LON_N)]

    def _hdr(name):
        return {
            "discipline": 0, "parameterCategory": 2,
            "parameterNumber": 2 if name == "U" else 3,
            "surface1Type": 103, "surface1Value": 10,
            "gridDefinitionTemplate": 0,
            "nx": GRID_LON_N, "ny": GRID_LAT_N,
            "lo1": GRID_LON_START, "lo2": GRID_LON_END,
            "la1": GRID_LAT_START, "la2": GRID_LAT_END,
            "dx": round(lon_step, 4), "dy": round(lat_step, 4),
            "refTime": yesterday + "T00:00:00.000Z",
            "name": f"{name}-component of wind [ERA5 via Open-Meteo]",
        }

    print(f"ERA5 grid fetched successfully.")
    return [
        {"header": _hdr("U"), "data": u_flat},
        {"header": _hdr("V"), "data": v_flat},
    ]


def _mock_velocity_json() -> list:
    """Synthetic cyclone vortex — used only when NOAA is unreachable."""
    nx, ny = 281, 221
    lo1, lo2, la1, la2 = 40.0, 110.0, -15.0, 40.0
    dx = (lo2 - lo1) / (nx - 1)
    dy = (la2 - la1) / (ny - 1)

    u_data, v_data = [], []
    for j in range(ny):
        lat = la1 + j * dy
        for i in range(nx):
            lon = lo1 + i * dx
            dist = math.hypot(lon - 86, lat - 15)
            angle = math.atan2(lat - 15, lon - 86)
            speed = max(0.5, 8.0 * math.exp(-dist / 12))
            u_data.append(round(-speed * math.sin(angle), 4))
            v_data.append(round(speed * math.cos(angle), 4))

    def _hdr(name):
        return {
            "discipline": 0, "parameterCategory": 2,
            "parameterNumber": 2 if name == "U" else 3,
            "surface1Type": 103, "surface1Value": 10,
            "gridDefinitionTemplate": 0,
            "nx": nx, "ny": ny,
            "lo1": lo1, "lo2": lo2, "la1": la1, "la2": la2,
            "dx": round(dx, 4), "dy": round(dy, 4),
            "refTime": "2026-09-06T00:00:00.000Z",
            "name": f"{name}-component of wind [synthetic]",
        }

    return [
        {"header": _hdr("U"), "data": u_data},
        {"header": _hdr("V"), "data": v_data},
    ]


def is_cache_stale() -> bool:
    """Return True if the cached data is older than 6 hours or does not exist."""
    if not CACHE_JSON.exists():
        return True
    cached_date, cached_cycle = _read_meta()
    if cached_date is None:
        return True
    latest_date, latest_cycle = _latest_gfs_params()
    return (cached_date, cached_cycle) != (latest_date, latest_cycle)


def fetch_and_cache(force: bool = False) -> str:
    """
    Fetch the latest GFS wind field via Open-Meteo API, save as wind-data.json.
    Old GRIB2 files are deleted. Only re-fetches if the cache is stale or force=True.
    Returns path to wind-data.json.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force and not is_cache_stale() and CACHE_JSON.exists():
        print("Wind cache is fresh — skipping fetch.")
        return str(CACHE_JSON)

    # 3-tier fallback: GFS forecast → ERA5 archive → synthetic vortex
    payload = None
    try:
        payload = _fetch_open_meteo_grid()
    except RuntimeError as e:
        if "RATE_LIMITED" in str(e):
            print("GFS forecast API rate-limited. Trying ERA5 archive (yesterday's real data)...")
            try:
                payload = _fetch_era5_grid()
            except Exception as e2:
                print(f"ERA5 archive fetch also failed: {e2}. Falling back to synthetic field.")
        else:
            print(f"Open-Meteo GFS fetch failed: {e}. Trying ERA5 archive...")
            try:
                payload = _fetch_era5_grid()
            except Exception as e2:
                print(f"ERA5 fallback also failed: {e2}.")
    except Exception as e:
        print(f"Unexpected error: {e}. Trying ERA5 archive...")
        try:
            payload = _fetch_era5_grid()
        except Exception as e2:
            print(f"ERA5 fallback failed: {e2}.")

    if payload is None:
        print("All real data sources failed. Using synthetic wind field.")
        payload = _mock_velocity_json()

    # Overwrite single JSON file
    with open(CACHE_JSON, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wind JSON written to {CACHE_JSON}")

    # Save metadata and clean up any old GRIB2 files
    date, cycle = _latest_gfs_params()
    _write_meta(date, cycle)
    _cleanup_old_gribs()  # no GRIB2s to keep — we use JSON API

    return str(CACHE_JSON)


def get_cached_json_path() -> str:
    if CACHE_JSON.exists():
        return str(CACHE_JSON)
    return fetch_and_cache()


if __name__ == "__main__":
    fetch_and_cache(force=True)
