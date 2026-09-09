import json
import logging
from ml_engine.pipelines.predictor import CyclonePipeline

# Configure logging
logging.basicConfig(level=logging.INFO)

def main():
    print("Initializing CyclonePipeline...")
    print("Loading models and loading trained .pt weights...")
    pipeline = CyclonePipeline.get_instance()
    
    print("\nRunning Full Inference on Live/Mock Satellite Feed for BOB Basin...")
    print("This will sequentially run the Vortex Detector, Intensity Classifier, Tracker, and Rainfall U-Net.\n")
    
    try:
        result = pipeline.run_full_inference(basin="BOB")
        
        print("================ SUCCESS ================")
        print(json.dumps(result, indent=2))
        print("=========================================")
        print("All four AI models executed successfully and integrated into the final JSON payload!")
        
    except Exception as e:
        print(f"Error during inference: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
