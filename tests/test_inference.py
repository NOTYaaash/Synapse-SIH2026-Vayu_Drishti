import unittest
import numpy as np
import torch
from ml_engine.pipelines.predictor import CyclonePipeline
from ml_engine.pipelines.preprocessor import Preprocessor
from ml_engine.pipelines.rainfall_estimator import RainfallEstimator, estimate_rainfall_mm
from ml_engine.architectures.tracker import MultimodalTrackPredictor
from ml_engine.training import (
    CycloneModelTrainer,
    IBTrACSLoader,
    convert_wind_speed,
    get_basin_category,
    get_imd_category,
    get_south_pacific_category,
)


class CyclonePipelineTestCase(unittest.TestCase):

  def setUp(self):
    self.pipeline = CyclonePipeline.get_instance()

  def test_bob_inference(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    self.assertEqual(output["basin"], "BOB")
    self.assertFalse(output["is_southern_hemisphere"])
    self.assertIn("center_lat", output)
    self.assertIn("center_lon", output)
    self.assertIn("category", output)
    self.assertGreaterEqual(output["msw"], 17.0)

  def test_arabian_sea_inference(self):
    output = self.pipeline.run_full_inference(basin="AS")
    self.assertEqual(output["basin"], "AS")
    self.assertGreaterEqual(output["msw"], 17.0)

  def test_sp_basin_rejected(self):
    with self.assertRaises(ValueError) as ctx:
      self.pipeline.run_full_inference(basin="SP")
    self.assertIn("SP", str(ctx.exception))

  def test_si_basin_rejected(self):
    with self.assertRaises(ValueError):
      self.pipeline.run_full_inference(basin="SI")

  def test_unknown_basin_rejected(self):
    with self.assertRaises(ValueError):
      self.pipeline.run_full_inference(basin="WP")

  def test_eye_confidence_in_output(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    self.assertIn("eye_confidence", output)
    self.assertIn("eye_confidence_label", output)
    self.assertGreaterEqual(output["eye_confidence"], 0.0)
    self.assertLessEqual(output["eye_confidence"], 1.0)
    self.assertIn(
        output["eye_confidence_label"],
        [
            "No Organised Circulation",
            "Partial Circulation / Weak Eye",
            "Developing Eye",
            "Well-Defined Eye",
        ],
    )

  def test_detector_returns_tuple(self):
    from ml_engine.architectures.detector import SimpleVortexDetector
    det = SimpleVortexDetector().eval()
    dummy = torch.zeros(1, 1, 64, 64)
    result = det(dummy)
    self.assertIsInstance(result, tuple)
    self.assertEqual(len(result), 2)
    box, conf = result
    self.assertEqual(box.shape, (1, 4))
    self.assertEqual(conf.shape, (1, 1))
    self.assertTrue(0.0 <= conf.item() <= 1.0)

  def test_pressure_in_output(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    self.assertIn("central_pressure_hpa", output)
    p = output["central_pressure_hpa"]
    self.assertGreaterEqual(p, 870.0)
    self.assertLessEqual(p, 1013.0)

  def test_env_vector_is_5_elements(self):
    from ml_engine.utils.cds_client import CDSClient
    client = CDSClient()
    vec = client.fetch_latest_environmental_physics(14.5, 86.2)
    self.assertEqual(vec.shape, (5,))

  def test_classifier_accepts_env(self):
    from ml_engine.architectures.classifier import IntensityClassifier
    clf = IntensityClassifier().eval()
    img = torch.zeros(2, 1, 128, 128)
    env = torch.zeros(2, 5)
    msw, logits = clf(img, env)
    self.assertEqual(msw.shape, (2, 1))
    self.assertEqual(logits.shape, (2, 7))
    msw2, logits2 = clf(img)
    self.assertEqual(msw2.shape, (2, 1))

  def test_forecast_timeline_structure(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    self.assertIn("forecast_timeline", output)
    self.assertNotIn("forecast_points", output)
    self.assertNotIn("rainfall_6h", output)
    timeline = output["forecast_timeline"]
    self.assertEqual(len(timeline), 4)
    self.assertEqual(
        [s["forecast_hour"] for s in timeline],
        list(MultimodalTrackPredictor.HORIZONS),
    )

  def test_forecast_timeline_fields(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    for step in output["forecast_timeline"]:
      for key in ("forecast_hour", "lat", "lon", "msw_kt", "imd_category", "max_rainfall_mm", "rainfall_grid"):
        self.assertIn(key, step)

  def test_msw_decay_per_horizon(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    timeline = output["forecast_timeline"]
    msw_values = [s["msw_kt"] for s in timeline]
    self.assertTrue(msw_values[0] >= msw_values[-1], "MSW should decay over longer horizons")

  def test_rainfall_in_timeline(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    for step in output["forecast_timeline"]:
      self.assertIsInstance(step["rainfall_grid"], list)
      self.assertGreater(len(step["rainfall_grid"]), 0)
      self.assertGreaterEqual(step["max_rainfall_mm"], 0.0)

  def test_parametric_rainfall_physics(self):
    rain_near = estimate_rainfall_mm(80.0, distance_km=30.0, duration_h=6.0)
    rain_far = estimate_rainfall_mm(80.0, distance_km=300.0, duration_h=6.0)
    self.assertGreater(rain_near, rain_far)

  def test_rainfall_non_negative(self):
    for dist in [0, 10, 50, 100, 200, 500]:
      r = estimate_rainfall_mm(60.0, float(dist))
      self.assertGreaterEqual(r, 0.0)

  def test_rainfall_risk_levels(self):
    estimator = RainfallEstimator()
    grid = estimator.generate_grid(14.5, 86.2, radius_km=100, step_deg=0.5)
    results = estimator.estimate_parametric(
        msw_kt=65.0, center_lat=14.5, center_lon=86.2,
        grid_points=grid, duration_h=6.0,
    )
    valid = {"LOW", "MODERATE", "HIGH", "SEVERE"}
    for r in results:
      self.assertIn(r["risk_level"], valid)

  def test_coriolis_hemisphere_flip(self):
    dummy_disk = np.arange(512 * 512, dtype=np.float32).reshape(512, 512)
    nh_patch = Preprocessor.crop_storm_patch(dummy_disk, is_southern_hemisphere=False)
    sh_patch = Preprocessor.crop_storm_patch(dummy_disk, is_southern_hemisphere=True)
    self.assertTrue(np.allclose(sh_patch, np.fliplr(nh_patch)))

  def test_wind_conversions(self):
    v_1min = 100.0
    v_10min = convert_wind_speed(v_1min, "1min", "10min")
    self.assertAlmostEqual(v_10min, 88.0, places=1)
    v_3min = convert_wind_speed(v_1min, "1min", "3min")
    self.assertAlmostEqual(v_3min, 93.0, places=1)
    self.assertNotAlmostEqual(v_3min, v_10min, places=1)
    v_back = convert_wind_speed(convert_wind_speed(v_3min, "3min", "1min"), "1min", "3min")
    self.assertAlmostEqual(v_back, v_3min, places=3)
    self.assertEqual(get_imd_category(125.0, standard="3min"), "Super Cyclonic Storm")
    self.assertEqual(
        get_south_pacific_category(110.0, standard="10min"),
        "Category 5 Severe Tropical Cyclone",
    )
    self.assertEqual(
        get_basin_category(125.0, basin="BOB", input_standard="3min"),
        "Super Cyclonic Storm",
    )

  def test_ibtracs_and_two_stage_training(self):
    loader = IBTrACSLoader()
    records = loader.load_records()
    self.assertGreaterEqual(len(records), 4)
    trainer = CycloneModelTrainer()
    history = trainer.run_two_stage_training(
        global_records=records,
        regional_records=records[:2],
        pretrain_epochs=1,
        finetune_epochs=1,
        batch_size=2,
    )
    self.assertEqual(len(history["pretraining"]), 1)
    self.assertEqual(len(history["finetuning"]), 1)
    self.assertIn("loss", history["pretraining"][0])

  def test_tracker_horizons_constant(self):
    self.assertEqual(MultimodalTrackPredictor.HORIZONS, (6, 12, 24, 72))

  def test_alert_colour_in_output(self):
    output = self.pipeline.run_full_inference(basin="BOB")
    self.assertIn("alert_colour", output)
    self.assertIn(output["alert_colour"], {"GREEN", "YELLOW", "ORANGE", "RED"})

  def test_rainfall_unet_forward(self):
    from ml_engine.architectures.rainfall_unet import RainfallUNet
    model = RainfallUNet()
    img = torch.zeros(1, 1, 128, 128)
    env = torch.zeros(1, 5)
    msw = torch.zeros(1, 1)
    out = model(img, env, msw)
    self.assertEqual(out.shape, (1, 1, 32, 32))


if __name__ == "__main__":
  unittest.main()