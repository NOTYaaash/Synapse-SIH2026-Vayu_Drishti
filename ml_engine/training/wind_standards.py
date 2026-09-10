from typing import Literal

WindStandard = Literal["1min", "3min", "10min"]

_FACTOR: dict = {"3min": 0.93, "10min": 0.88, "1min": 1.0}


def convert_wind_speed(
    value: float,
    from_standard: WindStandard,
    to_standard: WindStandard,
) -> float:
  if from_standard == to_standard:
    return float(value)

  if from_standard not in _FACTOR:
    raise ValueError(f"Unknown wind standard: {from_standard}")
  if to_standard not in _FACTOR:
    raise ValueError(f"Unknown wind standard: {to_standard}")

  v_1min = value / _FACTOR[from_standard]
  return float(v_1min * _FACTOR[to_standard])


def get_imd_category(msw_knots: float, standard: WindStandard = "3min") -> str:
  msw_3min = convert_wind_speed(msw_knots, standard, "3min")
  if msw_3min < 31:
    return "Depression"
  elif msw_3min <= 33:
    return "Deep Depression"
  elif msw_3min <= 47:
    return "Cyclonic Storm"
  elif msw_3min <= 63:
    return "Severe Cyclonic Storm"
  elif msw_3min <= 89:
    return "Very Severe Cyclonic Storm"
  elif msw_3min <= 119:
    return "Extremely Severe Cyclonic Storm"
  else:
    return "Super Cyclonic Storm"


def get_south_pacific_category(
    msw_knots: float, standard: WindStandard = "10min"
) -> str:
  msw_10min = convert_wind_speed(msw_knots, standard, "10min")
  if msw_10min < 34:
    return "Tropical Low"
  elif msw_10min <= 47:
    return "Category 1 Tropical Cyclone"
  elif msw_10min <= 63:
    return "Category 2 Tropical Cyclone"
  elif msw_10min <= 85:
    return "Category 3 Severe Tropical Cyclone"
  elif msw_10min <= 107:
    return "Category 4 Severe Tropical Cyclone"
  else:
    return "Category 5 Severe Tropical Cyclone"


def get_basin_category(
    msw_knots: float, basin: str, input_standard: WindStandard = "3min"
) -> str:
  basin_upper = basin.upper()
  if basin_upper in ["SP", "SI"]:
    return get_south_pacific_category(msw_knots, standard=input_standard)
  return get_imd_category(msw_knots, standard=input_standard)
