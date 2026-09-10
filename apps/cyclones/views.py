import json
import os
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import StormEvent, SatelliteObservation, CycloneShelter
from .serializers import (
    StormEventSerializer,
    SatelliteObservationSerializer,
    CycloneShelterSerializer,
)

_AVAILABILITY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "shelter_data_availability.json"
)


class StormEventViewSet(viewsets.ModelViewSet):
  queryset = StormEvent.objects.all().order_by("-started_at")
  serializer_class = StormEventSerializer


class SatelliteObservationViewSet(viewsets.ReadOnlyModelViewSet):
  queryset = SatelliteObservation.objects.all().order_by("-timestamp")
  serializer_class = SatelliteObservationSerializer

  def get_queryset(self):
    queryset = super().get_queryset()
    storm = self.request.query_params.get("storm")
    if storm:
      queryset = queryset.filter(storm__name=storm)
    return queryset


class CycloneShelterViewSet(viewsets.ReadOnlyModelViewSet):
  queryset = CycloneShelter.objects.all()
  serializer_class = CycloneShelterSerializer

  def get_queryset(self):
    queryset = super().get_queryset()
    state = self.request.query_params.get("state")
    district = self.request.query_params.get("district")
    if state:
      queryset = queryset.filter(state__iexact=state)
    if district:
      queryset = queryset.filter(district__iexact=district)
    return queryset

  @action(detail=False, methods=["get"])
  def nearest(self, request):
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    try:
      limit = int(request.query_params.get("limit", 5))
    except (TypeError, ValueError):
      limit = 5

    if not lat or not lon:
      return Response(
          {"error": "lat and lon query parameters are required."},
          status=status.HTTP_400_BAD_REQUEST,
      )

    try:
      pt = Point(float(lon), float(lat), srid=4326)
    except (TypeError, ValueError):
      return Response(
          {"error": "Invalid lat/lon values."},
          status=status.HTTP_400_BAD_REQUEST,
      )

    shelters = (
        CycloneShelter.objects.annotate(dist=Distance("point", pt))
        .order_by("dist")[:limit]
    )

    results = []
    for s in shelters:
      results.append({
          "id": s.id,
          "name": s.name,
          "state": s.state,
          "district": s.district,
          "lat": s.point.y,
          "lon": s.point.x,
          "capacity": s.capacity,
          "shelter_type": s.shelter_type,
          "distance_km": round(s.dist.km, 2),
      })

    return Response(results)

  @action(detail=False, methods=["get"])
  def availability(self, request):
    try:
      path = os.path.normpath(_AVAILABILITY_PATH)
      with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    except FileNotFoundError:
      data = {}

    states_with = [s for s, v in data.items() if v.get("available")]
    states_without = [
        {"state": s, "message": v.get("note", "Data not available.")}
        for s, v in data.items()
        if not v.get("available")
    ]

    return Response({
        "states_with_data": states_with,
        "states_without_data": states_without,
        "total_shelters_loaded": CycloneShelter.objects.count(),
    })