from typing import Tuple
import numpy as np
from .cds_client import CDSClient
from .mosdac_client import MOSDACClient


class SatelliteStreamRouter:

  def __init__(self):
    self.mosdac = MOSDACClient()
    self.cds = CDSClient()

  def get_stream(
      self, basin: str = "BOB"
  ) -> Tuple[np.ndarray, str, bool, str]:
    base_lat = 14.5 if basin.upper() == "BOB" else 15.5
    base_lon = 86.2 if basin.upper() == "BOB" else 66.5
    frame, data_mode = self.mosdac.fetch_latest_tir1_array(lat=base_lat, lon=base_lon)
    satellite_name = "INSAT-3D/3DS Imager"
    is_southern_hemisphere = False

    return frame, satellite_name, is_southern_hemisphere, data_mode

  def get_environmental_physics(
      self, lat: float, lon: float
  ) -> np.ndarray:
    return self.cds.fetch_latest_environmental_physics(lat, lon)

  def get_derived_channel(
      self,
      variable: str,
      basin: str = "BOB",
  ) -> Tuple[np.ndarray | None, str]:
    """
    Fetch a MOSDAC-distributed NetCDF derived product channel for the
    given basin centre as a normalised (512, 512) float32 ndarray.

    Supported variables: 'rainfall', 'precip', 'sst'

    This is the correct integration point for supplementary data layers.
    Do NOT call MOSDACClient.fetch_derived_product_nc() directly —
    route all derived-channel access through here so basin-to-coordinate
    resolution stays in one place.

    Returns:
        (patch_array, source_label) — mirrors get_stream() contract.
        source_label is 'netcdf_derived' on success or 'unknown' on failure.
    """
    base_lat = 14.5 if basin.upper() == "BOB" else 15.5
    base_lon = 86.2 if basin.upper() == "BOB" else 66.5
    return self.mosdac.fetch_derived_product_nc(
        variable=variable, lat=base_lat, lon=base_lon
    )
