import torch
import torch.nn as nn


class MultimodalTrackPredictor(nn.Module):

  HORIZONS = (6, 12, 24, 72)

  def __init__(self, forecast_steps: int = 4):
    super().__init__()
    self.vis_branch = nn.Sequential(
        nn.Conv2d(1, 16, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d((2, 2)),
        nn.Flatten(),
    )
    self.env_branch = nn.Sequential(
        nn.Linear(5, 16),
        nn.ReLU(),
    )
    self.fusion_head = nn.Sequential(
        nn.Linear(16 * 4 + 16, 64),
        nn.ReLU(),
        nn.Linear(
            64, forecast_steps * 2
        ),
    )

  def forward(
      self, img: torch.Tensor, env: torch.Tensor
  ) -> torch.Tensor:
    v_feat = self.vis_branch(img)
    e_feat = self.env_branch(env)
    fused = torch.cat([v_feat, e_feat], dim=1)
    return self.fusion_head(fused).view(-1, 4, 2)