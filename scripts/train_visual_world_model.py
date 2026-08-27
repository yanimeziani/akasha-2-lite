import os
import time
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
import matplotlib.pyplot as plt
import numpy as np

from akasha_2_lite.data.visual_pendulum import generate_visual_pendulum_dataset
from akasha_2_lite.models.hamiltonian_ssm import HamiltonianLatentModel

def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

class FrameEncoder(nn.Module):
    """Encodes single frame [B, 1, 64, 64] into 2D latent state z = [q_cos, q_sin]."""
    def __init__(self, latent_dim: int = 2):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=4, stride=2, padding=1),  # 32x32
            nn.ReLU(),
            nn.Conv2d(16, 32, kernel_size=4, stride=2, padding=1), # 16x16
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=4, stride=2, padding=1), # 8x8
            nn.ReLU(),
            nn.Conv2d(64, 64, kernel_size=4, stride=2, padding=1), # 4x4
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(64 * 4 * 4, 128),
            nn.ReLU(),
            nn.Linear(128, latent_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class FrameDecoder(nn.Module):
    """Decodes 2D latent state z into frame [B, 1, 64, 64]."""
    def __init__(self, latent_dim: int = 2):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64 * 4 * 4),
            nn.ReLU(),
        )
        self.deconv = nn.Sequential(
            nn.ConvTranspose2d(64, 64, kernel_size=4, stride=2, padding=1), # 8x8
            nn.ReLU(),
            nn.ConvTranspose2d(64, 32, kernel_size=4, stride=2, padding=1), # 16x16
            nn.ReLU(),
            nn.ConvTranspose2d(32, 16, kernel_size=4, stride=2, padding=1), # 32x32
            nn.ReLU(),
            nn.ConvTranspose2d(16, 1, kernel_size=4, stride=2, padding=1),   # 64x64
            nn.Sigmoid(),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        feat = self.fc(z).view(-1, 64, 4, 4)
        return self.deconv(feat)


def weighted_mse_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Weight pendulum pixels 10x higher to prevent trivial black-background collapse."""
    weights = 1.0 + 12.0 * target
    return (weights * (pred - target) ** 2).mean()


def main():
    device = get_device()
    print(f"Using compute acceleration: {device}")

    # 1. Dataset generation
    print("Generating visual trajectories (64x64)...")
    train_vids = generate_visual_pendulum_dataset(n_trajectories=150, n_steps=30, dt=0.05, seed=42)
    test_vids = generate_visual_pendulum_dataset(n_trajectories=10, n_steps=20, dt=0.05, seed=1042)

    # Flatten frames for Stage 1 Autoencoder
    all_frames = train_vids.view(-1, 1, 64, 64)
    ae_loader = DataLoader(TensorDataset(all_frames), batch_size=64, shuffle=True)

    encoder = FrameEncoder(latent_dim=2).to(device)
    decoder = FrameDecoder(latent_dim=2).to(device)

    # --- STAGE 1: Visual Representation Autoencoder Training ---
    print("\n--- Stage 1: Training Visual Autoencoder (Representation Learning) ---")
    ae_opt = torch.optim.AdamW(list(encoder.parameters()) + list(decoder.parameters()), lr=1.5e-3)
    ae_epochs = 12

    for epoch in range(ae_epochs):
        encoder.train()
        decoder.train()
        total_loss = 0.0
        n_b = 0
        for (batch_x,) in ae_loader:
            batch_x = batch_x.to(device)
            ae_opt.zero_grad()
            z = encoder(batch_x)
            recon = decoder(z)
            loss = weighted_mse_loss(recon, batch_x)
            loss.backward()
            ae_opt.step()
            total_loss += loss.item()
            n_b += 1
        print(f"AE Epoch [{epoch+1:02d}/{ae_epochs}] | Weighted Recon Loss: {total_loss/n_b:.4f}")

    # --- STAGE 2: Latent Hamiltonian Dynamics Training ---
    print("\n--- Stage 2: Training Latent Hamiltonian Dynamics (Leapfrog SSM) ---")
    encoder.eval()
    decoder.eval()

    # Extract consecutive latent states (z_t, z_{t+1}) from trajectories
    N, T, C, H, W = train_vids.shape
    with torch.no_grad():
        z_trajs = []
        for i in range(N):
            vid = train_vids[i].to(device)
            z_seq = encoder(vid) # [T, 2]
            z_trajs.append(z_seq)
        z_trajs = torch.stack(z_trajs, dim=0) # [N, T, 2]

    # Prepare transition dataset
    z_t = z_trajs[:, :-1, :].reshape(-1, 2)
    z_next = z_trajs[:, 1:, :].reshape(-1, 2)
    dyn_loader = DataLoader(TensorDataset(z_t, z_next), batch_size=128, shuffle=True)

    ham_dynamics = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=128).to(device)
    ham_opt = torch.optim.AdamW(ham_dynamics.parameters(), lr=1e-3, weight_decay=1e-5)
    crit_dyn = nn.MSELoss()

    dyn_epochs = 25
    for epoch in range(dyn_epochs):
        ham_dynamics.train()
        total_loss = 0.0
        n_b = 0
        for b_zt, b_znext in dyn_loader:
            ham_opt.zero_grad()
            pred_z = ham_dynamics.forward_step(b_zt, dt=0.05)
            loss = crit_dyn(pred_z, b_znext)
            loss.backward()
            ham_opt.step()
            total_loss += loss.item()
            n_b += 1
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"Dynamics Epoch [{epoch+1:02d}/{dyn_epochs}] | Latent MSE: {total_loss/n_b:.6f}")

    # --- STAGE 3: Autonomous End-to-End Latent Video Rollout ---
    print("\n--- Stage 3: Autonomous Visual Latent Rollout from Frame 0 ---")
    ham_dynamics.eval()
    test_seq = test_vids[0].to(device) # [20, 1, 64, 64]

    with torch.no_grad():
        # Encode only the very first frame to seed the latent state
        z_curr = encoder(test_seq[0:1]) # [1, 2]
        pred_frames = [decoder(z_curr).cpu()]

        # Roll forward 19 steps purely through latent Hamiltonian leapfrog!
        for _ in range(19):
            z_curr = ham_dynamics.forward_step(z_curr, dt=0.05)
            frame_pred = decoder(z_curr).cpu()
            pred_frames.append(frame_pred)

    # 4. Render Strip
    fig, axes = plt.subplots(2, 10, figsize=(15, 3.2), dpi=150)
    for idx in range(10):
        t_idx = idx * 2
        # Ground truth
        axes[0, idx].imshow(test_seq[t_idx, 0].cpu().numpy(), cmap="gray", vmin=0, vmax=1)
        axes[0, idx].axis("off")
        axes[0, idx].set_title(f"t={t_idx}", fontsize=8)

        # Autoregressive Prediction
        axes[1, idx].imshow(pred_frames[t_idx][0, 0].numpy(), cmap="gray", vmin=0, vmax=1)
        axes[1, idx].axis("off")

    axes[0, 0].text(-20, 32, "Ground Truth", fontsize=9, fontweight="bold", rotation=90, va="center")
    axes[1, 0].text(-20, 32, "AKASHA Latent Rollout", fontsize=9, fontweight="bold", rotation=90, va="center")

    plt.suptitle("AKASHA 2-Lite: Visual World Model (Autonomous Latent Hamiltonian Rollout)", fontsize=11, fontweight="bold")
    plt.tight_layout()

    out_path = "results/visual_world_model_rollout.png"
    plt.savefig(out_path)
    print(f"[OK] Saved visual comparison strip to {out_path}")

    os.makedirs("checkpoints", exist_ok=True)
    torch.save({
        "encoder": encoder.state_dict(),
        "decoder": decoder.state_dict(),
        "dynamics": ham_dynamics.state_dict(),
    }, "checkpoints/visual_world_model_mps.pt")
    print("[OK] Saved full visual world model checkpoints to checkpoints/visual_world_model_mps.pt")

if __name__ == "__main__":
    main()
