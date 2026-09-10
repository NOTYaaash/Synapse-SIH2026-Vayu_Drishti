"""
process_mosdac.py  --  INSAT-3D L1C -> ML training tensors
===========================================================
Reads every 3SIMG_*.h5 file in data/order/, matches its timestamp against
IBTrACS NIO cyclone observations, crops a 256x256 patch of TIR1 and WV
channels around the storm centre, and saves the result to:

    data/training_tensors/mosdac_patches.npz

Usage:
    python ml_engine/pipelines/process_mosdac.py           # full run
    python ml_engine/pipelines/process_mosdac.py --limit 10   # quick test
    python ml_engine/pipelines/process_mosdac.py --plot     # show sample crop
"""

from __future__ import annotations

import argparse
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np

# -- Paths ---------------------------------------------------------------------
ROOT         = Path(__file__).resolve().parent.parent.parent
ORDER_DIR    = ROOT / "data" / "order"
IBTRACS_CSV  = ROOT / "data" / "ibtracs.ALL.list.v04r01.csv"
OUTPUT_DIR   = ROOT / "data" / "training_tensors"
OUTPUT_NPZ   = OUTPUT_DIR / "mosdac_patches.npz"

# -- Constants -----------------------------------------------------------------
NIO_BASINS   = {"NI", "BB", "AS"}
MATCH_HOURS  = 1.0          # accept IBTrACS obs within +/-1 h of satellite time
PATCH_SIZE   = 256          # crop size in pixels (square)
FILL_VALUE   = 999.0        # _FillValue in IMG_TIR1_TEMP lookup table

# Mercator projection parameters (from the HDF5 Projection_Information attrs)
LON0_DEG     = 77.25
STD_PAR_DEG  = 17.75
SEMI_MAJOR   = 6_378_137.0
SEMI_MINOR   = 6_356_752.3142


# -- Filename -> datetime -------------------------------------------------------
_FNAME_RE = re.compile(r"3SIMG_(\d{2}[A-Z]{3}\d{4})_(\d{4})_")
_MONTHS   = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
             "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

def _parse_filename_dt(path: Path) -> datetime | None:
    m = _FNAME_RE.search(path.name)
    if not m:
        return None
    date_str, time_str = m.group(1), m.group(2)
    day    = int(date_str[:2])
    mon    = _MONTHS.get(date_str[2:5])
    year   = int(date_str[5:])
    hour   = int(time_str[:2])
    minute = int(time_str[2:])
    if mon is None:
        return None
    return datetime(year, mon, day, hour, minute)


# -- IBTrACS loader ------------------------------------------------------------
def load_ibtracs(csv_path: Path) -> list[dict]:
    records = []
    with open(csv_path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i < 2:
                continue
            parts = line.split(",")
            if len(parts) < 20:
                continue
            basin = parts[3].strip()
            if basin not in NIO_BASINS:
                continue
            iso_time = parts[6].strip()
            if not iso_time or len(iso_time) < 16:
                continue
            try:
                dt = datetime.strptime(iso_time[:16], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            try:
                lat = float(parts[8].strip())
                lon = float(parts[9].strip())
                msw = float(parts[10].strip())
            except (ValueError, IndexError):
                continue
            records.append({"dt": dt, "lat": lat, "lon": lon, "msw": msw})
    return records


def find_cyclone(sat_dt: datetime, sorted_records: list[dict]) -> dict | None:
    lo, hi = 0, len(sorted_records) - 1
    best = None
    best_delta = timedelta(hours=MATCH_HOURS + 1)
    while lo <= hi:
        mid = (lo + hi) // 2
        delta = abs(sorted_records[mid]["dt"] - sat_dt)
        if delta < best_delta:
            best_delta = delta
            best = sorted_records[mid]
        if sorted_records[mid]["dt"] < sat_dt:
            lo = mid + 1
        else:
            hi = mid - 1
    return best if best_delta <= timedelta(hours=MATCH_HOURS) else None


# -- Mercator reprojection -----------------------------------------------------
def _lon_lat_to_xy(lon_deg: float, lat_deg: float):
    e2   = 1 - (SEMI_MINOR / SEMI_MAJOR) ** 2
    e    = math.sqrt(e2)
    k0   = math.cos(math.radians(STD_PAR_DEG)) / math.sqrt(1 - e2 * math.sin(math.radians(STD_PAR_DEG)) ** 2)
    lon0 = math.radians(LON0_DEG)
    lon  = math.radians(lon_deg)
    lat  = math.radians(lat_deg)
    x    = SEMI_MAJOR * k0 * (lon - lon0)
    t    = math.tan(math.pi / 4 - lat / 2) / ((1 - e * math.sin(lat)) / (1 + e * math.sin(lat))) ** (e / 2)
    y    = -SEMI_MAJOR * k0 * math.log(t)
    return x, y


def latlon_to_pixel(lat_deg, lon_deg, X, Y):
    x_m, y_m = _lon_lat_to_xy(lon_deg, lat_deg)
    dx  = (X[-1] - X[0]) / (len(X) - 1)
    dy  = (Y[-1] - Y[0]) / (len(Y) - 1)
    col = (x_m - X[0]) / dx
    row = (y_m - Y[0]) / dy
    if not (0 <= col < len(X) and 0 <= row < len(Y)):
        return None
    return int(round(col)), int(round(row))


# -- HDF5 patch reader ---------------------------------------------------------
def read_patch(h5_path: Path, col_c: int, row_c: int, half: int = PATCH_SIZE // 2):
    with h5py.File(h5_path, "r") as f:
        H, W = f["IMG_TIR1"].shape[1], f["IMG_TIR1"].shape[2]
        r0, r1, c0, c1 = row_c - half, row_c + half, col_c - half, col_c + half
        if r0 < 0 or c0 < 0 or r1 > H or c1 > W:
            return None
        tir1_lut = f["IMG_TIR1_TEMP"][:]
        wv_lut   = f["IMG_WV_TEMP"][:]
        tir1_K   = tir1_lut[f["IMG_TIR1"][0, r0:r1, c0:c1].astype(np.uint16)].astype(np.float32)
        wv_K     = wv_lut[f["IMG_WV"][0,   r0:r1, c0:c1].astype(np.uint16)].astype(np.float32)
        for arr in (tir1_K, wv_K):
            arr[arr >= FILL_VALUE] = np.nan
        tir1_K = np.where(np.isnan(tir1_K), np.nanmean(tir1_K), tir1_K)
        wv_K   = np.where(np.isnan(wv_K),   np.nanmean(wv_K),   wv_K)
        return np.stack([tir1_K, wv_K], axis=0)   # (2, 256, 256)


# -- Main ----------------------------------------------------------------------
def run(limit: int = 0, plot: bool = False):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Loading IBTrACS from {IBTRACS_CSV.name}...")
    sorted_recs = sorted(load_ibtracs(IBTRACS_CSV), key=lambda r: r["dt"])
    print(f"  {len(sorted_recs):,} NIO cyclone observations loaded.")

    h5_files = sorted(ORDER_DIR.rglob("3SIMG_*.h5"))
    print(f"Found {len(h5_files):,} MOSDAC files in {ORDER_DIR}.")
    if not h5_files:
        print("No HDF5 files found. Check ORDER_DIR path."); return

    with h5py.File(h5_files[0], "r") as f:
        X_arr = f["X"][:]
        Y_arr = f["Y"][:]

    patches, labels, timestamps = [], [], []
    matched = skipped_no_cyc = skipped_edge = 0

    for h5_path in h5_files:
        if limit and matched >= limit:
            break
        sat_dt = _parse_filename_dt(h5_path)
        if sat_dt is None:
            continue
        cyclone = find_cyclone(sat_dt, sorted_recs)
        if cyclone is None:
            skipped_no_cyc += 1; continue
        pixel = latlon_to_pixel(cyclone["lat"], cyclone["lon"], X_arr, Y_arr)
        if pixel is None:
            skipped_edge += 1; continue
        patch = read_patch(h5_path, pixel[0], pixel[1])
        if patch is None:
            skipped_edge += 1; continue

        patches.append(patch)
        labels.append(cyclone["msw"])
        timestamps.append(sat_dt.isoformat())
        matched += 1
        if matched % 10 == 0 or matched == 1:
            print(f"  [{matched:4d}] {h5_path.name}  cyclone ({cyclone['lat']:.1f}N, "
                  f"{cyclone['lon']:.1f}E)  MSW={cyclone['msw']:.0f} kt")

    print(f"\nDone. Matched={matched} | No-cyclone={skipped_no_cyc} | Edge/OOB={skipped_edge}")
    if not patches:
        print("No patches extracted."); return

    p_arr = np.array(patches, dtype=np.float32)
    l_arr = np.array(labels,  dtype=np.float32)
    t_arr = np.array(timestamps)
    np.savez_compressed(OUTPUT_NPZ, patches=p_arr, labels=l_arr, timestamps=t_arr)
    print(f"Saved {len(p_arr)} patches -> {OUTPUT_NPZ}")
    print(f"  patches shape : {p_arr.shape}  (N, 2-channels, H, W)")
    print(f"  MSW range     : {l_arr.min():.0f} - {l_arr.max():.0f} kt")

    if plot:
        try:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 2, figsize=(10, 4))
            ax[0].imshow(p_arr[0, 0], cmap="inferno_r", vmin=200, vmax=310)
            ax[0].set_title(f"TIR1 (K)  MSW={l_arr[0]:.0f} kt")
            ax[1].imshow(p_arr[0, 1], cmap="Blues", vmin=200, vmax=280)
            ax[1].set_title("Water Vapour (K)")
            plt.suptitle(timestamps[0]); plt.tight_layout(); plt.show()
        except ImportError:
            print("matplotlib not installed - skipping plot.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Max patches (0=all)")
    ap.add_argument("--plot",  action="store_true")
    a = ap.parse_args()
    run(a.limit, a.plot)
