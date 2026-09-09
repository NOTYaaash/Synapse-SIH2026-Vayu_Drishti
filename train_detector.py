import argparse
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from ml_engine.architectures.detector import SimpleVortexDetector
from ml_engine.training.ibtracs_loader import IBTrACSLoader
from ml_engine.training.detector_dataset import VortexDetectorDataset

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()

    print("Loading IBTrACS Data...")
    loader = IBTrACSLoader("data/ibtracs.ALL.list.v04r01.csv")
    records = loader.load_records(basins=["NI", "BOB"])

    print("Initializing Detector Dataset...")
    dataset = VortexDetectorDataset(records=records, patch_size=128, max_shift=32)
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SimpleVortexDetector().to(device)

    box_criterion = nn.MSELoss()
    conf_criterion = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    print("Starting Detector Training...")
    model.train()
    
    for epoch in range(args.epochs):
        epoch_box_loss = 0.0
        epoch_conf_loss = 0.0
        
        for step, (img, box_target, conf_target) in enumerate(dataloader):
            img = img.to(device)
            box_target = box_target.to(device)
            conf_target = conf_target.to(device)

            optimizer.zero_grad()
            pred_box, pred_conf = model(img)

            # Mask out empty ocean frames (where conf=0) for box loss
            mask = conf_target > 0.5
            if mask.any():
                loss_box = box_criterion(pred_box[mask.squeeze()], box_target[mask.squeeze()])
            else:
                loss_box = torch.tensor(0.0, device=device)
                
            loss_conf = conf_criterion(pred_conf, conf_target)
            
            loss = loss_box + loss_conf
            loss.backward()
            optimizer.step()
            
            epoch_box_loss += loss_box.item()
            epoch_conf_loss += loss_conf.item()

            if step % 50 == 0:
                print(f"Epoch [{epoch+1}/{args.epochs}] Step [{step}/{len(dataloader)}] - "
                      f"Box Loss: {loss_box.item():.4f}, Conf Loss: {loss_conf.item():.4f}")

    os.makedirs("ml_engine/weights", exist_ok=True)
    weights_path = "ml_engine/weights/vortex_detector.pt"
    torch.save(model.state_dict(), weights_path)
    print(f"Training Complete! Weights saved to {weights_path}")

if __name__ == "__main__":
    main()
