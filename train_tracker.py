import argparse
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from ml_engine.architectures.tracker import MultimodalTrackPredictor
from ml_engine.training.ibtracs_loader import IBTrACSLoader
from ml_engine.training.tracker_dataset import TrackerDataset

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()

    print("Loading IBTrACS Data...")
    loader = IBTrACSLoader("data/ibtracs.ALL.list.v04r01.csv")
    records = loader.load_records(basins=["NI", "BOB"])

    print("Initializing Tracker Dataset...")
    dataset = TrackerDataset(records=records, patch_size=128, horizons=(6, 12, 24, 72))
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = MultimodalTrackPredictor(forecast_steps=4).to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    print("Starting Tracker Training...")
    model.train()
    
    for epoch in range(args.epochs):
        epoch_loss = 0.0
        
        for step, (img, env, target) in enumerate(dataloader):
            img = img.to(device)
            env = env.to(device)
            target = target.to(device)

            optimizer.zero_grad()
            pred_track = model(img, env) # Shape: (B, 4, 2)

            loss = criterion(pred_track, target)
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item()

            if step % 50 == 0:
                print(f"Epoch [{epoch+1}/{args.epochs}] Step [{step}/{len(dataloader)}] - "
                      f"MSE Loss: {loss.item():.4f}")

    os.makedirs("ml_engine/weights", exist_ok=True)
    weights_path = "ml_engine/weights/track_predictor.pt"
    torch.save(model.state_dict(), weights_path)
    print(f"Training Complete! Weights saved to {weights_path}")

if __name__ == "__main__":
    main()
