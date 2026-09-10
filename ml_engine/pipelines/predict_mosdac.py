"""
predict_mosdac.py  --  Run ML Inference on Live MOSDAC Satellite Data
====================================================================
Loads the trained intensity_classifier.pt model, reads a raw MOSDAC
HDF5 file, crops a 128x128 patch over a given coordinate (e.g. an active storm),
and predicts the Maximum Sustained Wind (MSW).
"""

import argparse
from pathlib import Path
import math
import warnings
warnings.filterwarnings("ignore")

import torch
import numpy as np
import h5py

from ml_engine.architectures.classifier import IntensityClassifier

ROOT = Path(__file__).resolve().parent.parent.parent
ORDER_DIR = ROOT / "data" / "order"
WEIGHTS_PATH = ROOT / "ml_engine" / "weights" / "intensity_classifier.pt"

# INSAT-3D Mercator Constants
LON0_DEG = 77.25
STD_PAR_DEG = 17.75
SEMI_MAJOR = 6_378_137.0
SEMI_MINOR = 6_356_752.3142
FILL_VALUE = 999.0


def _lon_lat_to_xy(lon_deg: float, lat_deg: float):
    e2 = 1 - (SEMI_MINOR / SEMI_MAJOR) ** 2
    e = math.sqrt(e2)
    k0 = math.cos(math.radians(STD_PAR_DEG)) / math.sqrt(1 - e2 * math.sin(math.radians(STD_PAR_DEG)) ** 2)
    lon0 = math.radians(LON0_DEG)
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    x = SEMI_MAJOR * k0 * (lon - lon0)
    t = math.tan(math.pi / 4 - lat / 2) / ((1 - e * math.sin(lat)) / (1 + e * math.sin(lat))) ** (e / 2)
    y = -SEMI_MAJOR * k0 * math.log(t)
    return x, y


def latlon_to_pixel(lat_deg, lon_deg, X, Y):
    x_m, y_m = _lon_lat_to_xy(lon_deg, lat_deg)
    dx = (X[-1] - X[0]) / (len(X) - 1)
    dy = (Y[-1] - Y[0]) / (len(Y) - 1)
    col = (x_m - X[0]) / dx
    row = (y_m - Y[0]) / dy
    if not (0 <= col < len(X) and 0 <= row < len(Y)):
        return None
    return int(round(col)), int(round(row))


def run_inference(lat: float, lon: float, pressure_hpa: float):
    print("Loading Trained Model...")
    if not WEIGHTS_PATH.exists():
        print(f"Error: Weights not found at {WEIGHTS_PATH}")
        return

    device = torch.device("cpu")
    model = IntensityClassifier()
    model.load_state_dict(torch.load(WEIGHTS_PATH, map_location=device, weights_only=True))
    model.eval()

    h5_files = sorted(ORDER_DIR.rglob("3SIMG_*.h5"))
    if not h5_files:
        print(f"No MOSDAC files found in {ORDER_DIR}.")
        return

    latest_file = h5_files[-1]
    print(f"\nReading latest MOSDAC file: {latest_file.name}")

    with h5py.File(latest_file, "r") as f:
        X_arr = f["X"][:]
        Y_arr = f["Y"][:]
        pixel = latlon_to_pixel(lat, lon, X_arr, Y_arr)
        if not pixel:
            print("Error: Coordinate is outside the bounds of the satellite image.")
            return
        
        col_c, row_c = pixel
        half = 64  # 128x128 patch
        r0, r1 = row_c - half, row_c + half
        c0, c1 = col_c - half, col_c + half
        
        if r0 < 0 or c0 < 0 or r1 > len(Y_arr) or c1 > len(X_arr):
            print("Error: Bounding box falls outside the image.")
            return

        tir1_lut = f["IMG_TIR1_TEMP"][:]
        tir1_gc = f["IMG_TIR1"][0, r0:r1, c0:c1].astype(np.uint16)
        patch_K = tir1_lut[tir1_gc].astype(np.float32)

    # Clean fill values
    patch_K[patch_K >= FILL_VALUE] = np.nan
    patch_K = np.where(np.isnan(patch_K), np.nanmean(patch_K), patch_K)

    # Normalize image identically to how global_dataset.py trained it (180K to 320K)
    patch_norm = np.clip((patch_K - 180.0) / (320.0 - 180.0), 0.0, 1.0)
    img_tensor = torch.from_numpy(patch_norm).unsqueeze(0).unsqueeze(0).float()  # (1, 1, 128, 128)

    # Env features matching global_dataset.py [0, 0, 0, 0, pressure]
    env_tensor = torch.tensor([[0.0, 0.0, 0.0, 0.0, pressure_hpa]], dtype=torch.float32)

    print(f"\n--- INFERENCE RESULTS (Target Lat: {lat}N, Lon: {lon}E) ---")
    with torch.no_grad():
        msw_pred, cat_logits = model(img_tensor, env_tensor)
        msw_knots = msw_pred.item() * 100.0  # Un-scale MSW
        cat_pred = torch.argmax(cat_logits, dim=1).item()
    
    print(f"Predicted Max Sustained Wind: {msw_knots:.1f} knots")
    print(f"Predicted Cyclone Category:   {cat_pred} (Saffir-Simpson Scale)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=15.0, help="Latitude of storm center")
    parser.add_argument("--lon", type=float, default=85.0, help="Longitude of storm center")
    parser.add_argument("--pressure", type=float, default=980.0, help="Current pressure (hPa)")
    args = parser.parse_args()
    run_inference(args.lat, args.lon, args.pressure)
