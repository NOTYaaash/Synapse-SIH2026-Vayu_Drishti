import torch
import random
from ml_engine.architectures.classifier import IntensityClassifier
from ml_engine.training.ibtracs_loader import IBTrACSLoader
from ml_engine.training.global_dataset import GlobalCycloneDataset

def test_model():
    print("Loading Trained Cyclone Intensity Model...")
    device = torch.device("cpu")
    model = IntensityClassifier()
    weights_path = "ml_engine/weights/intensity_classifier.pt"
    
    try:
        model.load_state_dict(torch.load(weights_path, map_location=device, weights_only=True))
        model.eval()
        print("Model loaded successfully.\n")
    except Exception as e:
        print(f"Error loading model weights: {e}")
        return

    print("Loading a few records from IBTrACS to test...")
    loader = IBTrACSLoader("data/ibtracs.ALL.list.v04r01.csv")
    records = loader.load_records(basins=["NI", "BOB"])
    
    # Grab a few random records to test
    random.seed(42)
    test_records = random.sample(records, 20)
    
    dataset = GlobalCycloneDataset(test_records)
    
    print("\n--- INFERENCE TEST ---")
    print(f"{'True MSW (knots)':<20} | {'Predicted MSW (knots)':<25}")
    print("-" * 50)
    
    with torch.no_grad():
        valid_tests = 0
        for i in range(len(dataset)):
            img, true_msw, true_cat, env = dataset[i]
            
            # Skip if the dataset returned an empty (zero) image because no GPM file matched
            if img.max() == 0.0:
                continue
                
            img = img.unsqueeze(0)  # Add batch dimension
            env = env.unsqueeze(0)
            
            pred_msw_norm, pred_cat_logits = model(img, env)
            
            true_knots = true_msw.item() * 100.0
            pred_knots = pred_msw_norm.item() * 100.0
            
            print(f"{true_knots:<20.1f} | {pred_knots:<25.1f}")
            valid_tests += 1
            if valid_tests >= 5:  # Print up to 5 valid matches
                break

    if valid_tests == 0:
        print("Could not find 5 matching GPM grids for the randomly selected storms.")

if __name__ == "__main__":
    test_model()
