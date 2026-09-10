from __future__ import annotations
import logging
import h5py
import numpy as np
import torch
from torch.utils.data import Dataset
from typing import List, Tuple, Dict
from datetime import datetime, timedelta
from collections import defaultdict

from ml_engine.training.global_dataset import _build_gpm_index, _latlon_to_pixel, _crop_patch
from ml_engine.training.ibtracs_loader import StormRecord

logger = logging.getLogger(__name__)

class TrackerDataset(Dataset):
    """
    Dataset for training the MultimodalTrackPredictor.
    Matches current storm image/env with future trajectory offsets (dx, dy) 
    for horizons +6h, +12h, +24h, +72h.
    """
    def __init__(
        self,
        records: List[StormRecord],
        patch_size: int = 128,
        horizons: Tuple[int, ...] = (6, 12, 24, 72),
    ):
        self.patch_size = patch_size
        self.horizons = horizons
        
        gpm_index = _build_gpm_index()
        self._gpm_times = sorted(gpm_index.keys())
        self._gpm_paths = gpm_index
        
        # Group records by SID to build tracks
        self.tracks: Dict[str, List[Tuple[datetime, StormRecord]]] = defaultdict(list)
        for r in records:
            try:
                dt = datetime.strptime(r.iso_time[:16], "%Y-%m-%d %H:%M")
                self.tracks[r.sid].append((dt, r))
            except:
                pass
                
        for sid in self.tracks:
            self.tracks[sid].sort(key=lambda x: x[0])

        self.samples = []
        MAX_GAP = timedelta(minutes=30)

        for sid, track in self.tracks.items():
            # Build a fast lookup for this track
            track_dict = {dt: rec for dt, rec in track}
            
            for dt, rec in track:
                if not self._gpm_times:
                    continue
                    
                import bisect
                pos = bisect.bisect_left(self._gpm_times, dt)
                candidates = []
                if pos < len(self._gpm_times):
                    candidates.append(self._gpm_times[pos])
                if pos > 0:
                    candidates.append(self._gpm_times[pos - 1])
                best = min(candidates, key=lambda t: abs(t - dt))
                
                if abs(best - dt) <= MAX_GAP:
                    # Collect future targets
                    future_offsets = []
                    valid_track = True
                    for h in self.horizons:
                        target_dt = dt + timedelta(hours=h)
                        if target_dt in track_dict:
                            fut_rec = track_dict[target_dt]
                            dlat = fut_rec.lat - rec.lat
                            dlon = fut_rec.lon - rec.lon
                            future_offsets.append([dlat, dlon])
                        else:
                            # Storm dissipated, assume it stays stationary relative to last known pos
                            future_offsets.append([0.0, 0.0])
                            
                    self.samples.append((rec, self._gpm_paths[best], future_offsets))

        print(f"  Tracker Dataset: Built {len(self.samples):,} valid track samples.")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        record, gpm_path, future_offsets = self.samples[idx]
        half = self.patch_size // 2
        
        patch = np.zeros((self.patch_size, self.patch_size), dtype=np.float32)
        
        try:
            with h5py.File(gpm_path, "r") as f:
                precip = f["precipitation"][0]
                lat_arr = f["lat"][:]
                lon_arr = f["lon"][:]
                
            precip = np.where(precip < 0, 0.0, precip)
            pixel = _latlon_to_pixel(record.lat, record.lon, lat_arr, lon_arr)
            
            p = _crop_patch(precip, pixel[0], pixel[1], half)
            if p is not None and p.shape == (self.patch_size, self.patch_size):
                patch = np.clip(p / 50.0, 0.0, 1.0).astype(np.float32)
                
                if record.is_southern_hemisphere:
                    patch = np.fliplr(patch).copy()
        except Exception as exc:
            pass

        img_tensor = torch.from_numpy(patch).unsqueeze(0).float()
        
        env_features = torch.tensor([
            record.msw_knots / 160.0, 
            (1013.0 - record.pressure_hpa) / 100.0, 
            record.lat / 90.0, 
            record.lon / 180.0, 
            0.0
        ], dtype=torch.float32)
        
        target_tensor = torch.tensor(future_offsets, dtype=torch.float32) # Shape: (4, 2)

        return img_tensor, env_features, target_tensor
