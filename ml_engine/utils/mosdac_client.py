import io
import logging
import os
import glob
import h5py
import numpy as np
import requests

from ml_engine.utils.netcdf_reader import MOSDACNetCDFReader

logger = logging.getLogger(__name__)

# ── Canonical INSAT-3DS grid for the ASIA_MER sector ─────────────────────────
# Bounding box from HDF5 metadata: lat [-10, 45.5], lon [44.5, 110], ~2745x2860 pixels
_GRID_LAT_MIN = -10.0
_GRID_LAT_MAX =  45.5
_GRID_LON_MIN =  44.5
_GRID_LON_MAX = 110.0

# Active historical data directory — priority-ordered list of candidate subdirs
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ORDER_ROOT = os.path.join(_ROOT, "data", "Order", "Order")

# Prefer the cyclone-active window (Sep26_189692 = 20–30 May 2024, Cyclone Remal-era)
# Followed by other available windows as fallback
_PREFERRED_SUBDIRS = [
    "Sep26_189692",   # 20–30 May 2024 — INSAT-3DS, active cyclone window
    "Sep26_189696",   # 21–27 Oct 2024
    "Sep26_189694",   # 01–31 Aug 2024
    "Sep26_189584",   # 01–05 Sep 2026 (calm — kept as last resort)
]


def _find_h5_files():
    """Return a sorted list of .h5 files from the preferred active data directory."""
    for subdir in _PREFERRED_SUBDIRS:
        candidate = os.path.join(_ORDER_ROOT, subdir)
        if not os.path.isdir(candidate):
            continue
        files = sorted(
            glob.glob(os.path.join(candidate, "*.h5")) +
            glob.glob(os.path.join(candidate, "*.HDF5"))
        )
        if files:
            logger.info("Using historical INSAT-3DS data from: %s (%d files)", subdir, len(files))
            return files
    return []


def _load_tir1_patch(h5_path: str, lat: float, lon: float) -> np.ndarray | None:
    """
    Read IMG_TIR1 grey counts, apply the 1D IMG_TIR1_TEMP LUT to get brightness
    temperatures [K], then extract a 512×512 patch centred on (lat, lon).
    Pixel coordinates are derived from the X/Y geostationary projection arrays.
    """
    try:
        with h5py.File(h5_path, "r") as h5:
            raw_counts = h5["IMG_TIR1"][0, :, :].astype(np.int32)   # (H, W) grey counts
            lut = h5["IMG_TIR1_TEMP"][:]                              # (1024,) BT LUT
            bt = lut[raw_counts].astype(np.float32)                  # (H, W) brightness temps

            H, W = bt.shape

            # Use X/Y geostationary projection arrays (in metres)
            X = h5["X"][:]  # shape (W,) — easting
            Y = h5["Y"][:]  # shape (H,) — northing

            # Convert target lat/lon to approximate geostationary projection metres
            # INSAT-3DS is at 82°E — using simplified equidistant mapping
            LON_SS = 82.0  # sub-satellite longitude
            R_SAT  = 36000e3  # nominal altitude (m)
            DEG2RAD = np.pi / 180.0

            target_x = R_SAT * (lon - LON_SS) * DEG2RAD * np.cos(lat * DEG2RAD)
            target_y = R_SAT * lat * DEG2RAD

            # Find closest column and row
            cx = int(np.argmin(np.abs(X - target_x)))
            cy = int(np.argmin(np.abs(Y - target_y)))

            # Clamp so 512×512 patch stays in-bounds
            cy = max(256, min(H - 256, cy))
            cx = max(256, min(W - 256, cx))

            patch = bt[cy - 256:cy + 256, cx - 256:cx + 256].copy()
            if patch.shape != (512, 512):
                out = np.full((512, 512), 290.0, dtype=np.float32)
                ph, pw = patch.shape
                out[:ph, :pw] = patch
                patch = out

            return patch.astype(np.float32)
    except Exception as e:
        logger.warning("Failed to read TIR1 patch from %s: %s", h5_path, e)
        return None


class MOSDACClient:

    def __init__(self):
        self.api_key = os.getenv("MOSDAC_API_KEY", "mock_key")
        self.base_url = os.getenv(
            "MOSDAC_API_URL", "https://mosdac.gov.in/api/v1/mock"
        )
        # Cache the file list so we don't re-scan on every call
        self._h5_files = _find_h5_files()
        # Start at the peak-intensity file (largest = most convective activity)
        if self._h5_files:
            sizes = [os.path.getsize(f) for f in self._h5_files]
            self._file_index = int(np.argmax(sizes))
        else:
            self._file_index = 0

        # Lazy-initialised NetCDF readers per variable type.
        # Instantiated on first call to fetch_derived_product_nc().
        self._nc_readers: dict[str, MOSDACNetCDFReader] = {}

    def fetch_latest_tir1_array(self, lat: float = 14.5, lon: float = 86.2) -> tuple[np.ndarray | None, str]:
        # ── 1. Try live MOSDAC API ────────────────────────────────────────────
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get(
                f"{self.base_url}/insat3d/latest", headers=headers, timeout=10
            )
            if response.status_code == 200:
                with h5py.File(io.BytesIO(response.content), "r") as h5_file:
                    raw_counts = h5_file["IMG_TIR1"][:]
                    if "IMG_TIR1_TEMP" in h5_file:
                        return h5_file["IMG_TIR1_TEMP"][:].astype(np.float32), "live"
                    lut = h5_file.get("IMG_TIR1_LUT")
                    if lut is not None:
                        return lut[:][raw_counts].astype(np.float32), "live"
        except Exception as e:
            logger.warning("Failed to fetch MOSDAC API data: %s", e)

        # ── 2. Load from local INSAT-3DS HDF5 historical archive ─────────────
        if self._h5_files:
            # Pick the file at the current index (cycles across all files in the window)
            chosen = self._h5_files[self._file_index % len(self._h5_files)]
            self._file_index += 1

            patch = _load_tir1_patch(chosen, lat, lon)
            if patch is not None:
                logger.info("Loaded TIR1 patch from: %s", os.path.basename(chosen))
                return patch, "archived"

        # ── 3. GPM IMERG precipitation fallback (last resort) ─────────────────
        try:
            data_dir = os.path.join(_ROOT, "data", "gpm_imerg")
            imerg_files = (
                glob.glob(os.path.join(data_dir, "*.HDF5.nc4")) +
                glob.glob(os.path.join(data_dir, "*.nc4")) +
                glob.glob(os.path.join(data_dir, "*.HDF5")) +
                glob.glob(os.path.join(data_dir, "*.h5"))
            )
            if imerg_files:
                with h5py.File(imerg_files[0], "r") as h5_file:
                    raw_data = h5_file['precipitation'][0, :, :].T  # (lon,lat) → (lat,lon)

                    lat_idx = int((lat - (-2.45)) / 0.1)
                    lon_idx = int((lon - 55.15) / 0.1)
                    h, w = raw_data.shape

                    y_start, y_end = lat_idx - 256, lat_idx + 256
                    x_start, x_end = lon_idx - 256, lon_idx + 256

                    src_y1, src_y2 = max(0, y_start), min(h, y_end)
                    src_x1, src_x2 = max(0, x_start), min(w, x_end)

                    patch = np.zeros((512, 512), dtype=np.float32)
                    dst_y1 = 256 - (lat_idx - src_y1)
                    dst_y2 = dst_y1 + (src_y2 - src_y1)
                    dst_x1 = 256 - (lon_idx - src_x1)
                    dst_x2 = dst_x1 + (src_x2 - src_x1)

                    patch[dst_y1:dst_y2, dst_x1:dst_x2] = raw_data[src_y1:src_y2, src_x1:src_x2]
                    patch = np.clip(310.0 - (patch * 2.0), 190.0, 310.0)
                    logger.info("IMERG fallback. Using: %s", os.path.basename(imerg_files[0]))
                    return patch, "archived"
        except Exception as fallback_e:
            logger.warning("IMERG fallback failed: %s", fallback_e)

        logger.error("No valid satellite data available. Returning None.")
        return None, "unknown"

    def fetch_derived_product_nc(
        self,
        variable: str = "rainfall",
        lat: float = 14.5,
        lon: float = 86.2,
        data_dir: str | None = None,
    ) -> tuple[np.ndarray | None, str]:
        """
        Fetch a MOSDAC-distributed NetCDF derived product (e.g. rainfall, SST)
        as a normalised (512, 512) float32 ndarray.

        Args:
            variable:  One of 'rainfall', 'precip', 'sst'. Maps to the
                       correct NetCDF variable name and normalisation bounds.
            lat, lon:  Centre coordinates for the 512×512 crop.
            data_dir:  Override the default NetCDF search directory.
                       Defaults to data/gpm_imerg for rainfall/precip,
                       and data/sst for sst products.

        Returns:
            (patch_array, "netcdf_derived") on success, (None, "unknown") on failure.
        """
        # Resolve default data directory per variable
        if data_dir is None:
            if variable in ("rainfall", "precip"):
                data_dir = os.path.join(_ROOT, "data", "gpm_imerg")
            else:
                data_dir = os.path.join(_ROOT, "data", variable)

        # Instantiate reader once per (variable, data_dir) combination
        cache_key = f"{variable}::{data_dir}"
        if cache_key not in self._nc_readers:
            self._nc_readers[cache_key] = MOSDACNetCDFReader(
                data_dir=data_dir, variable=variable
            )

        return self._nc_readers[cache_key].fetch_patch(lat=lat, lon=lon)
