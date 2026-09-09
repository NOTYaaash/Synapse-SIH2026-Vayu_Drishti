from __future__ import annotations
import logging
import random
import h5py
import numpy as np
import torch
from torch.utils.data import Dataset
from typing import List, Tuple
from pathlib import Path

from ml_engine.training.global_dataset import _build_gpm_index, _latlon_to_pixel, _crop_patch
from ml_engine.training.ibtracs_loader import StormRecord

logger = logging.getLogger(__name__)

class VortexDetectorDataset(Dataset):
    """
    Dataset for training the SimpleVortexDetector.
    Applies synthetic random cropping offsets to train the model to find the storm center.
    """
    def __init__(
        self,
        records: List[StormRecord],
        patch_size: int = 128,
        max_shift: int = 32,
    ):
        self.patch_size = patch_size
        self.max_shift = max_shift
        
        gpm_index = _build_gpm_index()
        self._gpm_times = sorted(gpm_index.keys())
        self._gpm_paths = gpm_index
        
        self.records: List[StormRecord] = []
        self.gpm_file: List[Path] = []
        from datetime import timedelta
        MAX_GAP = timedelta(minutes=30)

        for rec in records:
            if not self._gpm_times:
                continue
            from datetime import datetime
            try:
                rec_dt = datetime.strptime(rec.iso_time[:16], "%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                continue
                
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

        print(f"  Detector Dataset: Matched {len(self.records):,} records.")

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        record = self.records[idx]
        gpm_path = self.gpm_file[idx]
        half = self.patch_size // 2
        
        # Synthetic shift
        dx = random.randint(-self.max_shift, self.max_shift)
        dy = random.randint(-self.max_shift, self.max_shift)

        patch = np.zeros((self.patch_size, self.patch_size), dtype=np.float32)
        confidence = 0.0
        
        try:
            with h5py.File(gpm_path, "r") as f:
                precip = f["precipitation"][0]
                lat_arr = f["lat"][:]
                lon_arr = f["lon"][:]
                
            precip = np.where(precip < 0, 0.0, precip)
            pixel = _latlon_to_pixel(record.lat, record.lon, lat_arr, lon_arr)
            
            # Apply shift to the crop center
            col_c = pixel[0] + dx
            row_c = pixel[1] + dy
            
            p = _crop_patch(precip, col_c, row_c, half)
            if p is not None and p.shape == (self.patch_size, self.patch_size):
                patch = np.clip(p / 50.0, 0.0, 1.0).astype(np.float32)
                confidence = 1.0
                
        except Exception as exc:
            pass

        img_tensor = torch.from_numpy(patch).unsqueeze(0).float()
        
        # Calculate bounding box (eye is 24x24 pixels)
        # Since crop is shifted by dx right and dy down, the eye is -dx left and -dy up
        eye_cx = half - dx
        eye_cy = half - dy
        box_w = 24
        
        x_min = max(0, eye_cx - box_w // 2)
        x_max = min(self.patch_size, eye_cx + box_w // 2)
        y_min = max(0, eye_cy - box_w // 2)
        y_max = min(self.patch_size, eye_cy + box_w // 2)
        
        # Normalize to 0-1
        box = torch.tensor([
            x_min / self.patch_size,
            y_min / self.patch_size,
            x_max / self.patch_size,
            y_max / self.patch_size
        ], dtype=torch.float32)
        
        conf_tensor = torch.tensor([confidence], dtype=torch.float32)

        return img_tensor, box, conf_tensor
