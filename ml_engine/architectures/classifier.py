import torch
import torch.nn as nn


class IntensityClassifier(nn.Module):

  def __init__(self, num_classes: int = 7, env_dim: int = 5):
    super().__init__()
    self.backbone = nn.Sequential(
        nn.Conv2d(1, 32, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(32, 64, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d((4, 4)),
    )
    self.env_branch = nn.Sequential(
        nn.Linear(env_dim, 16),
        nn.ReLU(),
    )

    fused_dim = 64 * 4 * 4 + 16

    self.msw_head = nn.Sequential(
        nn.Linear(fused_dim, 64), nn.ReLU(), nn.Linear(64, 1)
    )
    self.cat_head = nn.Sequential(
        nn.Linear(fused_dim, 64), nn.ReLU(), nn.Linear(64, num_classes)
    )

  def forward(
      self,
      x: torch.Tensor,
      env: torch.Tensor | None = None,
  ):
    feat = torch.flatten(self.backbone(x), 1)
    if env is None:
      env = torch.zeros((x.shape[0], 5), device=x.device, dtype=x.dtype)
    e_feat = self.env_branch(env)
    feat = torch.cat([feat, e_feat], dim=1)
    msw = self.msw_head(feat)
    logits = self.cat_head(feat)
    return msw, logits