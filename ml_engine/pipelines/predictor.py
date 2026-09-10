from ml_engine.architectures.classifier import IntensityClassifier
from ml_engine.architectures.detector import SimpleVortexDetector
from ml_engine.architectures.tracker import MultimodalTrackPredictor
from ml_engine.pipelines.preprocessor import Preprocessor
from ml_engine.pipelines.rainfall_estimator import RainfallEstimator
from ml_engine.training.wind_standards import (
    convert_wind_speed,
    get_imd_category,
    get_south_pacific_category,
    get_basin_category,
)
from ml_engine.utils.stream_router import SatelliteStreamRouter
import torch

_SUPPORTED_BASINS = frozenset({"BOB", "AS"})
_HORIZONS = MultimodalTrackPredictor.HORIZONS


class CyclonePipeline:

  _instance = None

  def __init__(self):
    self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    self.detector = SimpleVortexDetector().to(self.device).eval()
    self.classifier = IntensityClassifier().to(self.device).eval()
    self.tracker = MultimodalTrackPredictor().to(self.device).eval()
    
    from pathlib import Path
    import os
    weights_dir = Path(__file__).resolve().parent.parent / "weights"
    
    detector_path = weights_dir / "vortex_detector.pt"
    if detector_path.exists():
      self.detector.load_state_dict(torch.load(detector_path, map_location=self.device, weights_only=True))
      
    classifier_path = weights_dir / "intensity_classifier.pt"
    if classifier_path.exists():
      self.classifier.load_state_dict(torch.load(classifier_path, map_location=self.device, weights_only=True))
      
    tracker_path = weights_dir / "track_predictor.pt"
    if tracker_path.exists():
      self.tracker.load_state_dict(torch.load(tracker_path, map_location=self.device, weights_only=True))
    self.router = SatelliteStreamRouter()
    self.rainfall = RainfallEstimator()

  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def _get_base_coordinates(self, basin: str) -> tuple[float, float]:
    if basin.upper() == "AS":
      return 15.5, 66.5
    return 14.5, 86.2

  @staticmethod
  def _get_eye_label(confidence: float) -> str:
    if confidence < 0.35:
      return "No Organised Circulation"
    elif confidence < 0.60:
      return "Partial Circulation / Weak Eye"
    elif confidence < 0.80:
      return "Developing Eye"
    else:
      return "Well-Defined Eye"

  @staticmethod
  def validate_and_enrich(result: dict) -> dict:
    out = dict(result)
    for key in ("msw", "msw_3min", "msw_10min", "msw_1min"):
      if key in out:
        out[key] = round(max(17.0, min(float(out[key]), 250.0)), 2)
    if "central_pressure_hpa" in out:
      out["central_pressure_hpa"] = round(max(870.0, min(float(out["central_pressure_hpa"]), 1013.0)), 2)
    if "eye_confidence" in out:
      out["eye_confidence"] = round(max(0.0, min(float(out["eye_confidence"]), 1.0)), 2)
    if "max_rainfall_mm" in out:
      out["max_rainfall_mm"] = round(float(out["max_rainfall_mm"]), 2)
    if "center_lat" in out:
      out["center_lat"] = round(float(out["center_lat"]), 2)
    if "center_lon" in out:
      out["center_lon"] = round(float(out["center_lon"]), 2)

    mapping = {
        "Depression": "YELLOW",
        "Deep Depression": "YELLOW",
        "Cyclonic Storm": "ORANGE",
        "Severe Cyclonic Storm": "ORANGE",
        "Very Severe Cyclonic Storm": "RED",
        "Extremely Severe Cyclonic Storm": "RED",
        "Super Cyclonic Storm": "RED",
    }
    out["alert_colour"] = mapping.get(out.get("imd_category", ""), "GREEN")
    return out

  def run_full_inference(self, basin: str = "BOB") -> dict:
    basin_upper = basin.upper()
    if basin_upper not in _SUPPORTED_BASINS:
      raise ValueError(
          f"Basin '{basin_upper}' is not supported for live monitoring. "
          f"Supported: {sorted(_SUPPORTED_BASINS)}."
      )

    full_disk, satellite_name, is_southern, data_mode = self.router.get_stream(basin_upper)

    in_tensor = torch.from_numpy(full_disk).float().unsqueeze(0).unsqueeze(0).to(self.device)

    with torch.no_grad():
      box, confidence_t = self.detector(in_tensor)
      box = box.cpu().numpy()[0]
      eye_confidence = float(torch.sigmoid(confidence_t).cpu().item())
      
    patch = Preprocessor.crop_storm_patch(full_disk, is_southern_hemisphere=is_southern)
    
    # Storm Detection Gate: Filter out blank ocean or false-positive hallucinations.
    # Threshold calibrated against real INSAT-3DS data:
    #   - Genuine storm (25 May 2024 peak): eye_confidence ≈ 0.73, patch.max ≈ 0.76
    #   - Blank sky / calm window: eye_confidence ≈ 0.50, patch.max ≈ 0.02
    if eye_confidence < 0.65 or float(patch.max()) < 0.1:
      return {
          "status": "no_cyclone_detected",
          "message": "No active system found in the specified window.",
          "coordinates": []
      }

    base_lat, base_lon = self._get_base_coordinates(basin_upper)
    b_lat_offset = max(-5.0, min(5.0, float(box[0])))
    b_lon_offset = max(-5.0, min(5.0, float(box[1])))
    center_lat = max(-90.0, min(90.0, base_lat + b_lat_offset))
    center_lon = max(-180.0, min(180.0, base_lon + b_lon_offset))

    patch = Preprocessor.crop_storm_patch(full_disk, is_southern_hemisphere=is_southern)
    patch_tensor = torch.from_numpy(patch).float().unsqueeze(0).unsqueeze(0).to(self.device)

    env_vector = self.router.get_environmental_physics(center_lat, center_lon)
    env_tensor = torch.from_numpy(env_vector).unsqueeze(0).float().to(self.device)

    with torch.no_grad():
      msw_pred, cat_logits = self.classifier(patch_tensor, env_tensor)
      future_tracks = self.tracker(patch_tensor, env_tensor)

    estimated_msw_3min = min(250.0, max(17.0, float(msw_pred.item() * 100.0)))
    estimated_msw_10min = convert_wind_speed(estimated_msw_3min, "3min", "10min")
    estimated_msw_1min = convert_wind_speed(estimated_msw_3min, "3min", "1min")

    imd_cat = get_imd_category(estimated_msw_3min, standard="3min")
    sp_cat = get_south_pacific_category(estimated_msw_10min, standard="10min")
    primary_category = get_basin_category(estimated_msw_3min, basin_upper, input_standard="3min")

    offsets = future_tracks.cpu().numpy()[0]
    forecast_timeline = []

    # Physically-grounded offset clamping:
    # - Tropical cyclones typically move 2-8 deg/day (~250-500 km/day).
    # - Max per-step delta clamped to +-5 deg latitude, +-5 deg longitude.
    # - Cumulative tracking: each step anchors to the previous position,
    #   NOT all relative to center. This prevents geometric box artefacts.
    _MAX_DELTA_DEG = 3.0
    prev_lat = center_lat
    prev_lon = center_lon

    # Only use horizons up to 48h — T+72h predictions diverge excessively
    active_horizons = [h for h in _HORIZONS if h <= 48]

    for step, horizon_h in enumerate(active_horizons):
      raw_lat_d = float(offsets[step][0])
      raw_lon_d = float(offsets[step][1])

      # Clamp individual deltas to physically possible range
      lat_delta = max(-_MAX_DELTA_DEG, min(_MAX_DELTA_DEG, raw_lat_d))
      lon_delta = max(-_MAX_DELTA_DEG, min(_MAX_DELTA_DEG, raw_lon_d))

      if is_southern:
        lat_delta = -abs(lat_delta)

      # Cumulative: offset is relative to *previous* step, not center
      step_lat = max(-90.0, min(90.0, prev_lat + lat_delta))
      step_lon = max(-180.0, min(180.0, prev_lon + lon_delta))

      # Smooth: blend 70% model + 30% linear extrapolation from last step
      if step > 0:
        lin_lat = prev_lat + (prev_lat - center_lat) * 0.3
        lin_lon = prev_lon + (prev_lon - center_lon) * 0.3
        step_lat = 0.7 * step_lat + 0.3 * lin_lat
        step_lon = 0.7 * step_lon + 0.3 * lin_lon

      prev_lat = step_lat
      prev_lon = step_lon

      decay = 1.0 - (horizon_h / 72.0) * 0.15
      step_msw = estimated_msw_3min * decay
      step_category = get_imd_category(step_msw, standard="3min")
      step_pressure = 1010.0 - (step_msw / 6.7) ** (1 / 0.644)

      step_grid = self.rainfall.generate_grid(step_lat, step_lon, radius_km=200, step_deg=0.5)
      step_rainfall = self.rainfall.estimate_parametric(
          msw_kt=step_msw,
          center_lat=step_lat,
          center_lon=step_lon,
          grid_points=step_grid,
          duration_h=float(horizon_h),
      )
      step_max_rain = max((p["rainfall_mm"] for p in step_rainfall), default=0.0)

      forecast_timeline.append({
          "forecast_hour": horizon_h,
          "lat": round(float(step_lat), 2),
          "lon": round(float(step_lon), 2),
          "msw_kt": round(float(step_msw), 2),
          "imd_category": step_category,
          "max_rainfall_mm": round(float(step_max_rain), 2),
          "central_pressure_hpa": round(float(step_pressure), 2),
          "rainfall_grid": step_rainfall,
      })

    central_pressure_hpa = float(env_vector[4]) if len(env_vector) >= 5 else 1013.0
    current_grid = self.rainfall.generate_grid(center_lat, center_lon, radius_km=200, step_deg=0.5)
    current_rainfall = self.rainfall.estimate_parametric(
        msw_kt=estimated_msw_3min,
        center_lat=center_lat,
        center_lon=center_lon,
        grid_points=current_grid,
        duration_h=6.0,
    )
    current_max_rain = max((p["rainfall_mm"] for p in current_rainfall), default=0.0)

    result = {
        "data_mode": str(data_mode),
        "basin": basin_upper,
        "satellite_source": satellite_name,
        "is_southern_hemisphere": is_southern,
        "center_lon": float(center_lon),
        "center_lat": float(center_lat),
        "msw": float(estimated_msw_3min),
        "msw_3min": float(estimated_msw_3min),
        "msw_10min": float(estimated_msw_10min),
        "msw_1min": float(estimated_msw_1min),
        "category": primary_category,
        "imd_category": imd_cat,
        "south_pacific_category": sp_cat,
        "central_pressure_hpa": float(central_pressure_hpa),
        "eye_confidence": float(eye_confidence),
        "eye_confidence_label": self._get_eye_label(eye_confidence),
        "max_rainfall_mm": float(current_max_rain),
        "forecast_timeline": forecast_timeline,
    }
    return self.validate_and_enrich(result)