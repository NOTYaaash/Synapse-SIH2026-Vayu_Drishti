from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset

from .ibtracs_loader import StormRecord
from .wind_standards import convert_wind_speed

# Path to the downloaded NASA GPM IMERG files
_GPM_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "gpm_imerg"

# Regex to parse the timestamp from a GPM filename:
# 3B-HHR.MS.MRG.3IMERG.YYYYMMDD-SHHMMSS-EHHMMSS.MMMM.V07B.HDF5.nc4
_GPM_RE = re.compile(r"3IMERG\.([0-9]{8})-S([0-9]{6})")


def _parse_gpm_dt(path: Path) -> datetime | None:
    m = _GPM_RE.search(path.name)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")


def _build_gpm_index() -> dict[datetime, Path]:
    """Scan GPM directory and build a dict of {start_time -> Path}."""
    index: dict[datetime, Path] = {}
    if not _GPM_DIR.exists():
        return index
    for p in _GPM_DIR.glob("*.nc4"):
        dt = _parse_gpm_dt(p)
        if dt is not None:
            index[dt] = p
    return index


def _latlon_to_pixel(
    lat_deg: float, lon_deg: float,
    lat_arr: np.ndarray, lon_arr: np.ndarray
) -> tuple[int, int] | None:
    """Convert lat/lon to nearest pixel in the GPM grid."""
    # GPM lat runs south-to-north, lon runs west-to-east
    lat_idx = np.argmin(np.abs(lat_arr - lat_deg))
    lon_idx = np.argmin(np.abs(lon_arr - lon_deg))
    return int(lon_idx), int(lat_idx)   # (col, row) – GPM is [lon, lat]


def _crop_patch(
    data: np.ndarray,   # (lon, lat) GPM grid
    col_c: int, row_c: int,
    half: int,
) -> np.ndarray | None:
    """Crop a square patch; returns None if out-of-bounds."""
    W, H = data.shape
    c0, c1 = col_c - half, col_c + half
    r0, r1 = row_c - half, row_c + half
    if c0 < 0 or r0 < 0 or c1 > W or r1 > H:
        # Pad instead of reject so we never silently drop data
        patch = np.pad(
            data,
            ((max(0, -c0), max(0, c1 - W)),
             (max(0, -r0), max(0, r1 - H))),
            mode="constant", constant_values=0.0,
        )
        # After padding the centre shifts – just centre-crop the padded array
        ph, pw = patch.shape
        cc, rc = ph // 2, pw // 2
        return patch[cc - half: cc + half, rc - half: rc + half]
    return data[c0:c1, r0:r1]


class GlobalCycloneDataset(Dataset):
    """PyTorch Dataset that loads real NASA GPM IMERG precipitation images.

    Each item is:
      - img_tensor  : (1, patch_size, patch_size) float32  – precipitation
      - msw_target  : (1,) float32  – max sustained wind / 100
      - cat_target  : ()   int64    – Saffir-Simpson category [0-6]
      - env_features: (5,) float32  – [0,0,0,0, pressure_hpa]
    """

    def __init__(
        self,
        records: List[StormRecord],
        patch_size: int = 128,
        target_wind_standard: str = "3min",
    ):
        self.patch_size = patch_size
        self.target_wind_standard = target_wind_standard

        # Build GPM time index once at startup
        gpm_index = _build_gpm_index()
        self._gpm_times = sorted(gpm_index.keys())
        self._gpm_paths = gpm_index

        if gpm_index:
            print(f"  GPM dataset: {len(gpm_index):,} files available in {_GPM_DIR}")
        else:
            print(f"  WARNING: No GPM .nc4 files found in {_GPM_DIR}. "
                  "Training will use zero-filled patches.")

        # Keep only records whose timestamp is within 30 min of a GPM file
        self.records: List[StormRecord] = []
        self.gpm_file: List[Path | None] = []
        from datetime import timedelta
        MAX_GAP = timedelta(minutes=30)

        for rec in records:
            if not self._gpm_times:
                # No GPM files – keep all records, will use zeros
                self.records.append(rec)
                self.gpm_file.append(None)
                continue
            try:
                rec_dt = datetime.strptime(rec.iso_time[:16], "%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                continue
            # Find closest GPM timestamp
            import bisect
            pos = bisect.bisect_left(self._gpm_times, rec_dt)
            candidates = []
            if pos < len(self._gpm_times):
                candidates.append(self._gpm_times[pos])
            if pos > 0:
                candidates.append(self._gpm_times[pos - 1])
            best = min(candidates, key=lambda t: abs(t - rec_dt))
            if abs(best - rec_dt) <= MAX_GAP:
                self.records.append(rec)
                self.gpm_file.append(self._gpm_paths[best])

        print(f"  Matched {len(self.records):,} IBTrACS records to GPM files.")

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(
        self, idx: int
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        record = self.records[idx]
        gpm_path = self.gpm_file[idx]
        half = self.patch_size // 2

        # ── Load real precipitation image ──────────────────────────────────
        if gpm_path is not None:
            try:
                with h5py.File(gpm_path, "r") as f:
                    precip = f["precipitation"][0]  # (lon, lat) float32 mm/hr
                    lat_arr = f["lat"][:]            # ascending
                    lon_arr = f["lon"][:]            # ascending

                # Replace missing / negative values with 0
                precip = np.where(precip < 0, 0.0, precip)

                # Locate cyclone centre in the grid
                pixel = _latlon_to_pixel(record.lat, record.lon, lat_arr, lon_arr)
                patch = _crop_patch(precip, pixel[0], pixel[1], half)

                if patch is None or patch.shape != (self.patch_size, self.patch_size):
                    patch = np.zeros((self.patch_size, self.patch_size), dtype=np.float32)

                # Normalize: GPM precip typically 0-100 mm/hr; clip at 50 for stability
                patch = np.clip(patch / 50.0, 0.0, 1.0).astype(np.float32)

                # Flip image for southern-hemisphere storms to give consistent rotation
                if record.is_southern_hemisphere:
                    patch = np.fliplr(patch)

            except Exception:
                patch = np.zeros((self.patch_size, self.patch_size), dtype=np.float32)
        else:
            patch = np.zeros((self.patch_size, self.patch_size), dtype=np.float32)

        img_tensor = torch.from_numpy(patch).unsqueeze(0).float()   # (1, 128, 128)

        # ── Labels ─────────────────────────────────────────────────────────
        converted_msw = convert_wind_speed(
            record.msw_knots,
            from_standard="1min",
            to_standard=self.target_wind_standard,
        )
        msw_target = torch.tensor([converted_msw / 100.0], dtype=torch.float32)
        cat_idx = min(6, max(0, int(converted_msw // 20)))
        cat_target = torch.tensor(cat_idx, dtype=torch.long)

        env_features = torch.tensor(
            [0.0, 0.0, 0.0, 0.0, record.pressure_hpa],
            dtype=torch.float32,
        )

        return img_tensor, msw_target, cat_target, env_features
