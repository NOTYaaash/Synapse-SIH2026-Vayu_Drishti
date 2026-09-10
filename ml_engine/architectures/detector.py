import torch
import torch.nn as nn


class SimpleVortexDetector(nn.Module):

  def __init__(self):
    super().__init__()
    self.features = nn.Sequential(
        nn.Conv2d(1, 16, kernel_size=3, stride=2, padding=1),
        nn.BatchNorm2d(16),
        nn.ReLU(),
        nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
        nn.BatchNorm2d(32),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d((1, 1)),
    )
    self.box_head = nn.Linear(32, 4)
    self.conf_head = nn.Linear(32, 1)

  def forward(
      self, x: torch.Tensor
  ) -> tuple[torch.Tensor, torch.Tensor]:
    flat = torch.flatten(self.features(x), 1)
    box = self.box_head(flat)
    confidence = torch.sigmoid(self.conf_head(flat))
    return box, confidence