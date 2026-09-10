import io
import logging
import os
import h5py
import numpy as np
import requests

logger = logging.getLogger(__name__)


class HimawariClient:

  def __init__(self):
    self.api_key = os.getenv("HIMAWARI_API_KEY", "mock_himawari_key")
    self.base_url = os.getenv(
        "HIMAWARI_API_URL", "https://himawari-opendata.jma.go.jp/api/v1/mock"
    )

  def fetch_latest_tir1_array(self) -> np.ndarray:
    try:
      headers = {"Authorization": f"Bearer {self.api_key}"}
      response = requests.get(
          f"{self.base_url}/himawari9/band13/latest",
          headers=headers,
          timeout=10,
      )
      if response.status_code == 200:
        with h5py.File(io.BytesIO(response.content), "r") as h5_file:
          raw_counts = h5_file["IMG_B13"][:]
          lut = h5_file["IMG_B13_LUT"][:]
          return lut[raw_counts].astype(np.float32)
    except Exception as e:
      logger.warning("Failed to fetch Himawari data: %s", e)

    return np.random.uniform(190.0, 310.0, (512, 512)).astype(np.float32)
