import numpy as np


class CDSClient:

  _FALLBACK_BOB = np.array(
      [12.5, 301.2, 75.0, 3.4e-5, 1005.0], dtype=np.float32
  )
  _FALLBACK_AS = np.array(
      [14.0, 299.8, 68.0, 2.8e-5, 1008.0], dtype=np.float32
  )

  def fetch_latest_environmental_physics(
      self, lat: float, lon: float
  ) -> np.ndarray:
    if lon < 78.0:
      return self._FALLBACK_AS.copy()
    return self._FALLBACK_BOB.copy()