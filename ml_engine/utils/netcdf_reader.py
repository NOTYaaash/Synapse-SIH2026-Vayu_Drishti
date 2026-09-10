"""
netcdf_reader.py — Production NetCDF reader for MOSDAC derived products
=======================================================================
Reads MOSDAC-distributed NetCDF4 / HDF5.nc4 files (e.g. GPM IMERG,
SST products, Quantitative Precipitation Estimates) and returns
normalised numpy arrays in the contract expected by SatelliteStreamRouter.

Return contract (mirrors MOSDACClient.fetch_latest_tir1_array):
    np.ndarray of shape (H, W) dtype=float32
    Values normalised to [0.0, 1.0] appropriate for the variable type

Supported variables (controlled by `variable` arg):
    "rainfall"  — mm/hr  → clipped [0, 50], normalised /50
    "sst"       — Kelvin → normalised same as TIR1: (310-K)/120
    "precip"    — alias for "rainfall" (GPM/IMERG naming)
"""

from __future__ import annotations

import glob
import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Canonical patch dimensions — must match the 512×512 used by MOSDACClient
_PATCH_H = 512
_PATCH_W = 512

# Variable normalisation bounds
_NORM_BOUNDS: dict[str, tuple[float, float]] = {
    "rainfall": (0.0, 50.0),    # mm/hr
    "precip":   (0.0, 50.0),
    "sst":      (190.0, 310.0), # K — same scale as TIR1
}

# Approximate grid resolutions for common MOSDAC products
# Used when explicit lat/lon coordinate arrays are absent
_FALLBACK_RES: dict[str, float] = {
    "rainfall": 0.1,  # GPM IMERG 0.1°
    "sst":      0.25, # INSAT SST 0.25°
    "precip":   0.1,
}


def _find_nc_files(data_dir: str, extensions: tuple[str, ...] = (".nc4", ".nc", ".HDF5.nc4")) -> list[str]:
    """Return a sorted list of NetCDF files in *data_dir* matching any extension."""
    found: list[str] = []
    for ext in extensions:
        found.extend(glob.glob(os.path.join(data_dir, f"*{ext}")))
    return sorted(set(found))


def _extract_variable(
    nc_file: str,
    variable: str,
) -> Optional[np.ndarray]:
    """
    Open *nc_file* and return the first 2-D slice of *variable* as float32.

    Tries netCDF4 first (preferred for true .nc4 files), then h5py as a
    fallback for HDF5-backed NetCDF files that netCDF4 cannot open.
    """
    # --- Attempt 1: netCDF4 library ------------------------------------------
    try:
        import netCDF4 as nc  # type: ignore[import]
        with nc.Dataset(nc_file, "r") as ds:
            if variable not in ds.variables:
                # Try common aliases
                aliases = {"rainfall": ["precipitationCal", "precipitation", "rain"],
                           "precip":   ["precipitationCal", "precipitation", "rain", "rainfall"],
                           "sst":      ["sea_surface_temperature", "SST", "sst"]}
                for alias in aliases.get(variable, []):
                    if alias in ds.variables:
                        variable = alias
                        break
                else:
                    logger.warning("Variable '%s' not found in %s. Available: %s",
                                   variable, nc_file, list(ds.variables.keys()))
                    return None

            raw = ds.variables[variable][:]
            raw = np.ma.filled(raw.astype(np.float64), fill_value=np.nan)

            # Collapse leading time / level dimensions to get a 2-D array
            while raw.ndim > 2:
                raw = raw[0]

            return raw.astype(np.float32)

    except ImportError:
        logger.debug("netCDF4 library not available; trying h5py fallback.")
    except Exception as e:
        logger.warning("netCDF4 failed for %s: %s. Trying h5py.", nc_file, e)

    # --- Attempt 2: h5py fallback for HDF5-backed NetCDF ---------------------
    try:
        import h5py
        with h5py.File(nc_file, "r") as h5:
            aliases = {"rainfall": ["precipitationCal", "precipitation", "rain"],
                       "precip":   ["precipitationCal", "precipitation", "rain", "rainfall"],
                       "sst":      ["sea_surface_temperature", "SST", "sst"]}
            key = variable
            for candidate in [variable] + aliases.get(variable, []):
                if candidate in h5:
                    key = candidate
                    break
            else:
                logger.warning("Variable '%s' not found in HDF5 file %s.", variable, nc_file)
                return None

            raw = h5[key][:]
            while raw.ndim > 2:
                raw = raw[0]
            raw = raw.astype(np.float64)
            raw[raw < -9000] = np.nan       # common IMERG missing-value sentinel
            return raw.astype(np.float32)

    except Exception as e:
        logger.error("h5py fallback also failed for %s: %s", nc_file, e)
        return None


def _latlon_to_indices(lat: float, lon: float,
                       lat_arr: np.ndarray, lon_arr: np.ndarray) -> tuple[int, int]:
    """Return (row, col) nearest to (lat, lon) in coordinate arrays."""
    row = int(np.argmin(np.abs(lat_arr - lat)))
    col = int(np.argmin(np.abs(lon_arr - lon)))
    return row, col


def _crop_to_patch(data_2d: np.ndarray,
                   row_c: int, col_c: int,
                   patch_h: int = _PATCH_H,
                   patch_w: int = _PATCH_W) -> np.ndarray:
    """
    Crop a (patch_h, patch_w) window centred on (row_c, col_c).
    Pads with NaN if the crop extends beyond the array boundary.
    """
    H, W = data_2d.shape
    half_h, half_w = patch_h // 2, patch_w // 2

    # Clamp centre so a full patch fits
    row_c = max(half_h, min(H - half_h, row_c))
    col_c = max(half_w, min(W - half_w, col_c))

    patch = data_2d[row_c - half_h: row_c + half_h,
                    col_c - half_w: col_c + half_w].copy()

    if patch.shape != (patch_h, patch_w):
        out = np.full((patch_h, patch_w), np.nan, dtype=np.float32)
        ph, pw = patch.shape
        out[:ph, :pw] = patch
        patch = out

    return patch.astype(np.float32)


def _normalise(patch: np.ndarray, variable: str) -> np.ndarray:
    """
    Normalise *patch* to [0, 1] using the variable's canonical bounds.
    NaN fill-values are replaced with the patch nanmean before normalisation.
    """
    lo, hi = _NORM_BOUNDS.get(variable, (0.0, 1.0))

    if np.isnan(patch).any():
        fill = float(np.nanmean(patch)) if not np.all(np.isnan(patch)) else lo
        patch = np.where(np.isnan(patch), fill, patch)

    if variable == "sst":
        # Invert so warm SST → low value (mirrors TIR1 convention in Preprocessor)
        normed = np.clip((hi - patch) / (hi - lo), 0.0, 1.0)
    else:
        normed = np.clip((patch - lo) / (hi - lo), 0.0, 1.0)

    return normed.astype(np.float32)


class MOSDACNetCDFReader:
    """
    Production reader for MOSDAC-distributed NetCDF derived products.

    Usage in SatelliteStreamRouter:
        reader = MOSDACNetCDFReader(data_dir=".../data/gpm_imerg", variable="rainfall")
        patch, source = reader.fetch_patch(lat=14.5, lon=86.2)
        # patch: np.ndarray (512, 512) float32 normalised [0, 1]
        # source: "netcdf_derived"
    """

    def __init__(self, data_dir: str, variable: str = "rainfall"):
        self.data_dir = data_dir
        self.variable = variable
        self._files = _find_nc_files(data_dir)
        self._file_index = 0

        if self._files:
            logger.info("MOSDACNetCDFReader: found %d NetCDF file(s) in %s for variable '%s'",
                        len(self._files), data_dir, variable)
        else:
            logger.warning("MOSDACNetCDFReader: no NetCDF files found in %s", data_dir)

    def fetch_patch(
        self,
        lat: float = 14.5,
        lon: float = 86.2,
    ) -> tuple[np.ndarray | None, str]:
        """
        Load the next available NetCDF file (cycling), extract the variable,
        crop a 512×512 patch centred on (lat, lon), normalise to [0, 1].

        Returns:
            (patch_array, "netcdf_derived") on success
            (None, "unknown") when no data is available
        """
        if not self._files:
            logger.error("No NetCDF files available in %s.", self.data_dir)
            return None, "unknown"

        nc_file = self._files[self._file_index % len(self._files)]
        self._file_index += 1

        raw_2d = _extract_variable(nc_file, self.variable)
        if raw_2d is None:
            return None, "unknown"

        # Resolve lat/lon coordinate arrays from the file itself, or synthesise
        lat_arr, lon_arr = self._resolve_coords(nc_file, raw_2d.shape)
        if lat_arr is None or lon_arr is None:
            logger.warning("Could not resolve coordinate arrays from %s.", nc_file)
            return None, "unknown"

        row_c, col_c = _latlon_to_indices(lat, lon, lat_arr, lon_arr)
        patch = _crop_to_patch(raw_2d, row_c, col_c)
        patch = _normalise(patch, self.variable)

        logger.info("NetCDF patch loaded: file=%s variable=%s shape=%s",
                    os.path.basename(nc_file), self.variable, patch.shape)
        return patch, "netcdf_derived"

    def _resolve_coords(
        self,
        nc_file: str,
        data_shape: tuple[int, int],
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """
        Attempt to read lat/lon arrays from the file. Falls back to a synthetic
        regular grid using the known resolution for the variable type.
        """
        # --- Try netCDF4 -------------------------------------------------------
        try:
            import netCDF4 as nc  # type: ignore[import]
            with nc.Dataset(nc_file, "r") as ds:
                lat_key = next((k for k in ("lat", "latitude", "Latitude") if k in ds.variables), None)
                lon_key = next((k for k in ("lon", "longitude", "Longitude") if k in ds.variables), None)
                if lat_key and lon_key:
                    return ds.variables[lat_key][:].astype(np.float32), \
                           ds.variables[lon_key][:].astype(np.float32)
        except Exception:
            pass

        # --- Try h5py ----------------------------------------------------------
        try:
            import h5py
            with h5py.File(nc_file, "r") as h5:
                lat_key = next((k for k in ("lat", "latitude", "Latitude") if k in h5), None)
                lon_key = next((k for k in ("lon", "longitude", "Longitude") if k in h5), None)
                if lat_key and lon_key:
                    return h5[lat_key][:].astype(np.float32), h5[lon_key][:].astype(np.float32)
        except Exception:
            pass

        # --- Fallback: synthesise a regular grid --------------------------------
        res = _FALLBACK_RES.get(self.variable, 0.1)
        H, W = data_shape
        logger.warning("Synthesising %s° regular grid for %s (%d×%d).",
                       res, os.path.basename(nc_file), H, W)
        # GPM IMERG global extent: lat [-90, 90], lon [-180, 180]
        lat_arr = np.linspace(89.95, -89.95, H, dtype=np.float32)
        lon_arr = np.linspace(-179.95, 179.95, W, dtype=np.float32)
        return lat_arr, lon_arr
