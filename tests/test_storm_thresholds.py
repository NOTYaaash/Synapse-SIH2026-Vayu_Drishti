import os
import django
import pytest
from unittest.mock import patch
import numpy as np

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from ml_engine.pipelines.predictor import CyclonePipeline


class TestStormThresholds:
    
    @patch('ml_engine.utils.stream_router.SatelliteStreamRouter.get_stream')
    def test_calm_window_no_cyclone_detected(self, mock_get_stream):
        """
        Verify that a completely calm, empty sky (all zeros in normalized IR)
        is caught by the Storm Detection Gate, returning the empty state payload
        instead of a hallucinated storm track.
        """
        # Create a mock calm full disk (310K -> normalized to 0.0)
        calm_full_disk = np.full((512, 512), 310.0, dtype=np.float32)
        mock_get_stream.return_value = (calm_full_disk, "Mock Satellite", False, "archived")
        
        pipeline = CyclonePipeline.get_instance()
        result = pipeline.run_full_inference(basin="BOB")
        
        assert result.get("status") == "no_cyclone_detected"
        assert "message" in result
        assert result.get("coordinates") == []

    @patch('ml_engine.utils.stream_router.SatelliteStreamRouter.get_stream')
    def test_active_storm_window_precision(self, mock_get_stream):
        """
        Verify that an active storm safely passes the gate, and all serialized 
        floats (MSW, pressure, confidence, lat/lon) are strictly capped at 2 decimal places.
        """
        # Create a mock active storm full disk (190K -> normalized to 1.0)
        active_full_disk = np.full((512, 512), 190.0, dtype=np.float32)
        mock_get_stream.return_value = (active_full_disk, "Mock Satellite", False, "archived")
        
        pipeline = CyclonePipeline.get_instance()
        
        with patch.object(pipeline.detector, 'forward') as mock_detector, \
             patch.object(pipeline.classifier, 'forward') as mock_classifier, \
             patch.object(pipeline.tracker, 'forward') as mock_tracker, \
             patch.object(pipeline.router, 'get_environmental_physics') as mock_env:
             
            import torch
            mock_detector.return_value = (torch.tensor([[0.0, 0.0]]), torch.tensor(10.0)) # high confidence
            mock_classifier.return_value = (torch.tensor([[0.65]]), torch.tensor([[0.0]*7])) # 65 knots MSW
            mock_tracker.return_value = torch.zeros(1, 4, 2)
            mock_env.return_value = np.array([0.0, 0.0, 0.0, 0.0, 980.0])
            
            result = pipeline.run_full_inference(basin="BOB")
            
            assert "status" not in result or result.get("status") != "no_cyclone_detected"
            assert isinstance(result.get("msw"), float)
            
            # Check 2 decimal places exactly
            assert len(str(result["msw"]).split('.')[-1]) <= 2
            assert len(str(result["central_pressure_hpa"]).split('.')[-1]) <= 2
            assert len(str(result["eye_confidence"]).split('.')[-1]) <= 2
            assert len(str(result["center_lat"]).split('.')[-1]) <= 2
            assert len(str(result["center_lon"]).split('.')[-1]) <= 2
            
            timeline = result.get("forecast_timeline", [])
            assert len(timeline) > 0
            for step in timeline:
                assert len(str(step["lat"]).split('.')[-1]) <= 2
                assert len(str(step["lon"]).split('.')[-1]) <= 2
                assert len(str(step["msw_kt"]).split('.')[-1]) <= 2
