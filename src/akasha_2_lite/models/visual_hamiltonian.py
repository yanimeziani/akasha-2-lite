import torch
import torch.nn as nn
from typing import Tuple
from akasha_2_lite.models.hamiltonian_ssm import HamiltonianLatentModel

class ConvEncoder(nn.Module):
    """Encodes 2 consecutive frames [B, 2, 64, 64] into latent canonical state [q, p]."""
    def __init__(self, latent_dim: int = 2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(2, 16, kernel_size=4, stride=2, padding=1), # -> [16, 32, 32]
            nn.LeakyReLU(0.2),
            nn.Conv2d(16, 32, kernel_size=4, stride=2, padding=1), # -> [32, 16, 16]
            nn.LeakyReLU(0.2),
            nn.Conv2d(32, 64, kernel_size=4, stride=2, padding=1), # -> [64, 8, 8]
            nn.LeakyReLU(0.2),
            nn.Conv2d(64, 64, kernel_size=4, stride=2, padding=1), # -> [64, 4, 4]
            nn.LeakyReLU(0.2),
            nn.Flatten(), # 64 * 4 * 4 = 1024
            nn.Linear(1024, 128),
            nn.LeakyReLU(0.2),
            nn.Linear(128, latent_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DeconvDecoder(nn.Module):
    """Decodes latent coordinate q into predicted frame [B, 1, 64, 64]."""
    def __init__(self, latent_dim: int = 2):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.LeakyReLU(0.2),
            nn.Linear(128, 1024),
            nn.LeakyReLU(0.2),
        )
        self.deconv = nn.Sequential(
            nn.ConvTranspose2d(64, 64, kernel_size=4, stride=2, padding=1), # -> [64, 8, 8]
            nn.LeakyReLU(0.2),
            nn.ConvTranspose2d(64, 32, kernel_size=4, stride=2, padding=1), # -> [32, 16, 16]
            nn.LeakyReLU(0.2),
            nn.ConvTranspose2d(32, 16, kernel_size=4, stride=2, padding=1), # -> [16, 32, 32]
            nn.LeakyReLU(0.2),
            nn.ConvTranspose2d(16, 1, kernel_size=4, stride=2, padding=1),   # -> [1, 64, 64]
            nn.Sigmoid(),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        feat = self.fc(z).view(-1, 64, 4, 4)
        return self.deconv(feat)


class VisualHamiltonianWorldModel(nn.Module):
    """
    End-to-End Pixel-to-Pixel Hamiltonian World Model:
    (I_{t-1}, I_t) -> Encoder -> z_t = [q, p] -> Symplectic Leapfrog -> z_{t+1} -> Decoder -> I_{t+1}
    """
    def __init__(self, hidden_dim: int = 128):
        super().__init__()
        self.encoder = ConvEncoder(latent_dim=2)
        self.dynamics = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=hidden_dim)
        self.decoder = DeconvDecoder(latent_dim=2)

    def encode(self, frame_pair: torch.Tensor) -> torch.Tensor:
        """Takes [B, 2, 64, 64] and returns [B, 2] canonical state [q, p]."""
        return self.encoder(frame_pair)

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """Takes [B, 2] and returns [B, 1, 64, 64] image."""
        return self.decoder(z)

    def forward(self, frame_pair: torch.Tensor, dt: float = 0.05) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward prediction:
        Returns: (pred_next_frame, z_t, z_next)
        """
        z_t = self.encode(frame_pair)
        z_next = self.dynamics.forward_step(z_t, dt)
        pred_next_frame = self.decode(z_next)
        return pred_next_frame, z_t, z_next
