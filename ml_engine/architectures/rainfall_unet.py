import torch
import torch.nn as nn


class _ConvBlock(nn.Module):
  def __init__(self, in_ch: int, out_ch: int):
    super().__init__()
    self.block = nn.Sequential(
        nn.Conv2d(in_ch, out_ch, 3, padding=1),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
        nn.Conv2d(out_ch, out_ch, 3, padding=1),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )

  def forward(self, x: torch.Tensor) -> torch.Tensor:
    return self.block(x)


class RainfallUNet(nn.Module):
  def __init__(self, env_dim: int = 5):
    super().__init__()
    self.enc1 = _ConvBlock(1, 32)
    self.enc2 = _ConvBlock(32, 64)
    self.enc3 = _ConvBlock(64, 128)
    self.pool = nn.MaxPool2d(2)
    self.bottleneck = _ConvBlock(128, 256)

    film_in = env_dim + 1
    self.film_scale = nn.Linear(film_in, 256)
    self.film_shift = nn.Linear(film_in, 256)

    self.up3 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
    self.dec3 = _ConvBlock(256, 128)

    self.up2 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
    self.dec2 = _ConvBlock(128, 64)

    self.up1 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
    self.dec1 = _ConvBlock(64, 32)

    self.head = nn.Sequential(
        nn.Conv2d(32, 1, kernel_size=1),
        nn.AdaptiveAvgPool2d((32, 32)),
        nn.ReLU(),
    )

  def forward(
      self,
      img: torch.Tensor,
      env: torch.Tensor,
      msw: torch.Tensor,
  ) -> torch.Tensor:
    e1 = self.enc1(img)
    e2 = self.enc2(self.pool(e1))
    e3 = self.enc3(self.pool(e2))
    b = self.bottleneck(self.pool(e3))

    cond = torch.cat([env, msw], dim=1)
    gamma = self.film_scale(cond).view(-1, 256, 1, 1)
    beta = self.film_shift(cond).view(-1, 256, 1, 1)
    b = gamma * b + beta

    d3 = self.dec3(torch.cat([self.up3(b), e3], dim=1))
    d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
    d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))

    return self.head(d1)
