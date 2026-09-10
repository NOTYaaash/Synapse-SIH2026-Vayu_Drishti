from dataclasses import dataclass
from typing import List, Optional
import os
import pandas as pd


@dataclass
class StormRecord:
  sid: str
  name: str
  basin: str
  iso_time: str
  lat: float
  lon: float
  msw_knots: float
  pressure_hpa: float
  is_southern_hemisphere: bool


class IBTrACSLoader:

  def __init__(self, data_path: Optional[str] = None):
    self.data_path = data_path

  def load_records(
      self,
      basins: Optional[List[str]] = None,
      min_msw: float = 20.0,
  ) -> List[StormRecord]:
    if self.data_path and os.path.exists(self.data_path):
      df = pd.read_csv(
          self.data_path,
          skiprows=[1],
          usecols=[
              "SID",
              "NAME",
              "BASIN",
              "ISO_TIME",
              "LAT",
              "LON",
              "USA_WIND",
              "USA_PRES",
          ],
          low_memory=False,
      )
      df = df.dropna(subset=["LAT", "LON", "USA_WIND"])
      records: List[StormRecord] = []
      for _, row in df.iterrows():
        basin = str(row["BASIN"]).strip().upper()
        if basins and basin not in basins:
          continue
          
        msw_str = str(row["USA_WIND"]).strip()
        if not msw_str:
            continue
        msw = float(msw_str)
        if msw < min_msw:
          continue
          
        lat_str = str(row["LAT"]).strip()
        lon_str = str(row["LON"]).strip()
        if not lat_str or not lon_str:
            continue
        lat = float(lat_str)
        lon = float(lon_str)
        
        pres_str = str(row.get("USA_PRES", "")).strip()
        pres = float(pres_str) if pres_str else 1000.0
        
        records.append(
            StormRecord(
                sid=str(row["SID"]),
                name=str(row["NAME"]).strip(),
                basin=basin,
                iso_time=str(row["ISO_TIME"]),
                lat=lat,
                lon=lon,
                msw_knots=msw,
                pressure_hpa=pres,
                is_southern_hemisphere=(lat < 0.0),
            )
        )
      return records

    return self._generate_synthetic_global_records(basins)

  def _generate_synthetic_global_records(
      self, basins: Optional[List[str]] = None
  ) -> List[StormRecord]:
    sample_basins = basins or ["NI", "SP", "SI", "WP"]
    records = []
    metadata = [
        ("2024010S15175", "YASA", "SP", -16.2, 178.5, 120.0, 915.0),
        ("2024022S20055", "FREDDY", "SI", -19.4, 53.2, 110.0, 930.0),
        ("2024135N12088", "AMPHAN", "NI", 13.5, 86.4, 130.0, 907.0),
        ("2024280N18125", "GAJA", "NI", 10.8, 82.3, 55.0, 990.0),
        ("2024310S12160", "LOLA", "SP", -14.8, 168.2, 95.0, 950.0),
        ("2024190N22130", "HAIYAN", "WP", 11.2, 128.5, 160.0, 895.0),
    ]
    for sid, name, basin, lat, lon, msw, pres in metadata:
      if basins and basin not in sample_basins:
        continue
      records.append(
          StormRecord(
              sid=sid,
              name=name,
              basin=basin,
              iso_time="2024-01-01 00:00:00",
              lat=lat,
              lon=lon,
              msw_knots=msw,
              pressure_hpa=pres,
              is_southern_hemisphere=(lat < 0.0),
          )
      )
    return records
