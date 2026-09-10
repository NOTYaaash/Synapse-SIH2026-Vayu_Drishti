import json

from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.http import JsonResponse
from django.views.generic import TemplateView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from ml_engine.pipelines.predictor import CyclonePipeline
from ml_engine.pipelines.rainfall_estimator import _haversine_km
from apps.cyclones.models import CycloneShelter
from .models import ForecastTrack, PincodeLocation
from .serializers import ForecastTrackSerializer


def _affected_radius_km(msw_kt: float) -> float:
  if msw_kt < 34:
    return 150.0
  elif msw_kt < 64:
    return 250.0
  elif msw_kt < 90:
    return 350.0
  else:
    return 500.0


def _advisory(is_affected: bool, risk_level: str, distance_km: float) -> str:
  if not is_affected:
    return f"Your location is {distance_km:.0f} km from the storm centre. No direct threat expected."
  mapping = {
      "LOW": "Light rainfall expected. Monitor IMD advisories.",
      "MODERATE": "Moderate to heavy rain expected. Avoid low-lying areas.",
      "HIGH": "You are in a HIGH risk zone. Be prepared to evacuate.",
      "SEVERE": "SEVERE risk. Evacuate immediately to the nearest cyclone shelter.",
  }
  return mapping.get(risk_level, "Monitor IMD advisories.")


class CycloneMapView(TemplateView):
  template_name = "predictions/map.html"


class ForecastTrackViewSet(viewsets.ReadOnlyModelViewSet):
  queryset = ForecastTrack.objects.all().order_by("-generated_at")
  serializer_class = ForecastTrackSerializer

  def get_queryset(self):
    queryset = super().get_queryset()
    basin = self.request.query_params.get("basin")
    if basin:
      queryset = queryset.filter(basin=basin.upper())
    return queryset

  @action(detail=False, methods=["get", "post"], url_path="live")
  def live_inference(self, request):
    basin = request.query_params.get("basin") or request.data.get("basin") or "BOB"
    pipeline = CyclonePipeline.get_instance()
    result = pipeline.run_full_inference(basin=basin)
    return Response(result)


class AffectedAreaView(APIView):

  def get(self, request):
    pincode = request.query_params.get("pincode")
    district = request.query_params.get("district")
    lat_param = request.query_params.get("lat")
    lon_param = request.query_params.get("lon")

    location_info = {}
    user_lat = None
    user_lon = None

    if pincode:
      rec = PincodeLocation.objects.filter(pincode=pincode.strip()).first()
      if not rec:
        return Response(
            {"error": f"Pincode '{pincode}' not found. Run load_pincodes first."},
            status=status.HTTP_404_NOT_FOUND,
        )
      user_lat = rec.point.y
      user_lon = rec.point.x
      location_info = {"pincode": pincode, "district": rec.district, "state": rec.state}

    elif district:
      rec = PincodeLocation.objects.filter(district__iexact=district).first()
      if not rec:
        return Response(
            {"error": f"District '{district}' not found in pincode dataset."},
            status=status.HTTP_404_NOT_FOUND,
        )
      user_lat = rec.point.y
      user_lon = rec.point.x
      location_info = {"district": rec.district, "state": rec.state}

    elif lat_param and lon_param:
      try:
        user_lat = float(lat_param)
        user_lon = float(lon_param)
        location_info = {"lat": user_lat, "lon": user_lon}
      except ValueError:
        return Response(
            {"error": "Invalid lat/lon values."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    else:
      return Response(
          {"error": "Provide pincode, district, or lat+lon query parameters."},
          status=status.HTTP_400_BAD_REQUEST,
      )

    pipeline = CyclonePipeline.get_instance()
    storm = pipeline.run_full_inference(basin="BOB")
    
    if storm.get("status") == "no_cyclone_detected":
      return Response(storm)

    center_lat = storm["center_lat"]
    center_lon = storm["center_lon"]
    distance_km = _haversine_km(user_lat, user_lon, center_lat, center_lon)
    msw = storm["msw"]
    affected_radius = _affected_radius_km(msw)
    is_affected = distance_km <= affected_radius

    risk_level = "NONE"
    expected_rainfall_mm = 0.0
    if is_affected and storm.get("forecast_timeline"):
      first_horizon = storm["forecast_timeline"][0]
      grid = first_horizon.get("rainfall_grid", [])
      if grid:
        grid_sorted = sorted(grid, key=lambda p: abs(p["lat"] - user_lat) + abs(p["lon"] - user_lon))
        nearest_cell = grid_sorted[0]
        expected_rainfall_mm = nearest_cell["rainfall_mm"]
        risk_level = nearest_cell["risk_level"]

    nearest_shelter = None
    state = location_info.get("state")
    if state and is_affected:
      try:
        pt = Point(user_lon, user_lat, srid=4326)
        shelter = (
            CycloneShelter.objects.annotate(dist=Distance("point", pt))
            .order_by("dist")
            .first()
        )
        if shelter:
          nearest_shelter = {
              "name": shelter.name,
              "state": shelter.state,
              "district": shelter.district,
              "lat": shelter.point.y,
              "lon": shelter.point.x,
              "capacity": shelter.capacity,
              "distance_km": round(shelter.dist.km, 2),
          }
      except Exception:
        nearest_shelter = None

    shelter_data_note = None
    if state and not CycloneShelter.objects.filter(state__iexact=state).exists():
      shelter_data_note = (
          f"Cyclone shelter location data is not publicly available for {state}. "
          "Contact your State Disaster Management Authority."
      )

    return Response({
        "query": location_info,
        "location": {"lat": user_lat, "lon": user_lon},
        "is_affected": is_affected,
        "distance_km": round(distance_km, 1),
        "affected_radius_km": affected_radius,
        "risk_level": risk_level,
        "expected_rainfall_mm": round(expected_rainfall_mm, 1),
        "imd_category": storm["imd_category"],
        "msw_knots": storm["msw"],
        "central_pressure_hpa": storm["central_pressure_hpa"],
        "eye_confidence": storm["eye_confidence"],
        "eye_confidence_label": storm["eye_confidence_label"],
        "nearest_shelter": nearest_shelter,
        "shelter_data_note": shelter_data_note,
        "advisory": _advisory(is_affected, risk_level, distance_km),
    })


class RainfallView(APIView):

  def get(self, request):
    district = request.query_params.get("district")
    horizon_h = request.query_params.get("horizon")

    if not district:
      return Response(
          {"error": "district query parameter is required."},
          status=status.HTTP_400_BAD_REQUEST,
      )

    pincode_rec = PincodeLocation.objects.filter(district__iexact=district).first()
    if not pincode_rec:
      return Response(
          {"error": f"District '{district}' not found in pincode dataset."},
          status=status.HTTP_404_NOT_FOUND,
      )

    dist_lat = pincode_rec.point.y
    dist_lon = pincode_rec.point.x

    pipeline = CyclonePipeline.get_instance()
    storm = pipeline.run_full_inference(basin="BOB")
    
    if storm.get("status") == "no_cyclone_detected":
      return Response(storm)
      
    timeline = storm.get("forecast_timeline", [])

    forecasts = []
    for step in timeline:
      if horizon_h and str(step["forecast_hour"]) != str(horizon_h):
        continue
      grid = step.get("rainfall_grid", [])
      if not grid:
        continue
      grid_sorted = sorted(
          grid,
          key=lambda p: (p["lat"] - dist_lat) ** 2 + (p["lon"] - dist_lon) ** 2,
      )
      nearby = grid_sorted[:9]
      if not nearby:
        continue
      max_mm = max(p["rainfall_mm"] for p in nearby)
      mean_mm = sum(p["rainfall_mm"] for p in nearby) / len(nearby)

      # Derive risk_level from aggregated max_mm, NOT from nearby[0]'s per-cell tag.
      # nearby[0] is the single closest grid point and can have an arbitrary value;
      # computing from max_mm gives the correct district-level severity.
      if max_mm < 15.0:
        risk_level = "LOW"
      elif max_mm < 65.0:
        risk_level = "MODERATE"
      elif max_mm < 130.0:
        risk_level = "HIGH"
      else:
        risk_level = "SEVERE"

      forecasts.append({
          "forecast_hour": step["forecast_hour"],
          "max_mm": round(max_mm, 1),
          "mean_mm": round(mean_mm, 1),
          "risk_level": risk_level,
          "storm_lat": step["lat"],
          "storm_lon": step["lon"],
          "storm_msw_kt": step["msw_kt"],
          "storm_category": step["imd_category"],
      })

    return Response({
        "district": pincode_rec.district,
        "state": pincode_rec.state,
        "district_lat": dist_lat,
        "district_lon": dist_lon,
        "forecasts": forecasts,
    })


class WindDataView(APIView):

  def get(self, request):
    from ml_engine.pipelines.fetch_wind_data import fetch_and_cache, get_cached_json_path
    refresh = request.query_params.get("refresh", "0") == "1"
    try:
      path = fetch_and_cache() if refresh else get_cached_json_path()
      with open(path, "r") as f:
        payload = json.load(f)
      return JsonResponse(payload, safe=False)
    except Exception as e:
      return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
