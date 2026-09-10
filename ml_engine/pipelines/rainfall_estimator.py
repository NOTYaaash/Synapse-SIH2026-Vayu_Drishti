from __future__ import annotations

import math
from typing import List, Tuple


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  R = 6371.0
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlam = math.radians(lon2 - lon1)
  a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
  return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_rainfall_mm(
    msw_kt: float,
    distance_km: float,
    duration_h: float = 6.0,
) -> float:
  r_max_km = 30.0 + (msw_kt * 0.5)
  peak_rate_mmh = 2.0 + (msw_kt * 0.15)

  if distance_km <= r_max_km:
    rate_mmh = peak_rate_mmh * math.sqrt(distance_km / r_max_km)
  else:
    decay_scale = r_max_km * 2.5
    rate_mmh = peak_rate_mmh * math.exp(-(distance_km - r_max_km) / decay_scale)

  return round(rate_mmh * duration_h, 1)


def _classify_risk(rainfall_mm: float) -> str:
  if rainfall_mm < 15.0:
    return "LOW"
  elif rainfall_mm < 65.0:
    return "MODERATE"
  elif rainfall_mm < 130.0:
    return "HIGH"
  else:
    return "SEVERE"


class RainfallEstimator:

  @staticmethod
  def generate_grid(
      center_lat: float,
      center_lon: float,
      radius_km: float = 200.0,
      step_deg: float = 0.25,
  ) -> List[Tuple[float, float]]:
    radius_deg = radius_km / 111.0
    points: List[Tuple[float, float]] = []
    lat = center_lat - radius_deg
    while lat <= center_lat + radius_deg + 1e-9:
      lon = center_lon - radius_deg
      while lon <= center_lon + radius_deg + 1e-9:
        points.append((round(lat, 2), round(lon, 2)))
        lon += step_deg
      lat += step_deg
    return points

  def estimate_parametric(
      self,
      msw_kt: float,
      center_lat: float,
      center_lon: float,
      grid_points: List[Tuple[float, float]],
      duration_h: float = 6.0,
  ) -> List[dict]:
    results = []
    for lat, lon in grid_points:
      dist_km = _haversine_km(center_lat, center_lon, lat, lon)
      rain_mm = estimate_rainfall_mm(msw_kt, dist_km, duration_h)
      results.append(
          {
              "lat": lat,
              "lon": lon,
              "distance_km": round(dist_km, 1),
              "rainfall_mm": rain_mm,
              "risk_level": _classify_risk(rain_mm),
          }
      )
    return results
