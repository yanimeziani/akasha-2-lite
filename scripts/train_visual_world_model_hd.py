"""
High-Definition (HD) Visual World Model Training Pipeline
Trains an enhanced ConvNet autoencoder and multi-step unrolled Hamiltonian Leapfrog dynamics.
"""

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

class HDFrameEncoder(nn.Module):
    """High-Definition Frame Encoder with GroupNorm and Residual-like blocks."""
    def __init__(self, latent_dim: int = 2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=4, stride=2, padding=1),  # 32x32
            nn.GroupNorm(4, 32),
            nn.SiLU(),
            nn.Conv2d(32, 64, kernel_size=4, stride=2, padding=1), # 16x16
            nn.GroupNorm(8, 64),
            nn.SiLU(),
            nn.Conv2d(64, 128, kernel_size=4, stride=2, padding=1), # 8x8
            nn.GroupNorm(16, 128),
            nn.SiLU(),
            nn.Conv2d(128, 128, kernel_size=4, stride=2, padding=1), # 4x4
            nn.GroupNorm(16, 128),
            nn.SiLU(),
            nn.Flatten(),
            nn.Linear(128 * 4 * 4, 256),
            nn.SiLU(),
            nn.Linear(256, latent_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class HDFrameDecoder(nn.Module):
    """High-Definition Frame Decoder with Transposed Convolutions and Skip-Refinement."""
    def __init__(self, latent_dim: int = 2):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(latent_dim, 256),
            nn.SiLU(),
            nn.Linear(256, 128 * 4 * 4),
            nn.SiLU(),
        )
        self.deconv = nn.Sequential(
            nn.ConvTranspose2d(128, 128, kernel_size=4, stride=2, padding=1), # 8x8
            nn.GroupNorm(16, 128),
            nn.SiLU(),
            nn.ConvTranspose2d(128, 64, kernel_size=4, stride=2, padding=1),  # 16x16
            nn.GroupNorm(8, 64),
            nn.SiLU(),
            nn.ConvTranspose2d(64, 32, kernel_size=4, stride=2, padding=1),   # 32x32
            nn.GroupNorm(4, 32),
            nn.SiLU(),
            nn.ConvTranspose2d(32, 1, kernel_size=4, stride=2, padding=1),    # 64x64
            nn.Sigmoid(),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        feat = self.fc(z).view(-1, 128, 4, 4)
        return self.deconv(feat)


def weighted_recon_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Weights the moving pendulum mass 15x higher to guarantee sharp contour details."""
    weight = 1.0 + 15.0 * target
    return (weight * (pred - target) ** 2).mean()


def train_hd_world_model():
    device = get_device()
    print("=" * 75)
    print(f"AKASHA 2-LITE: HIGH-DEFINITION VISUAL WORLD MODEL TRAINING PIPELINE")
    print(f"Hardware Accelerator: {device}")
    print("=" * 75)

    start_total_time = time.perf_counter()

    # 1. High-Quality Dataset Generation (350 trajectories x 40 steps = 14,000 frames)
    print("\n[1/4] Generating 14,000 High-Diversity Visual Trajectories (64x64)...")
    train_vids = generate_visual_pendulum_dataset(n_trajectories=350, n_steps=40, dt=0.05, seed=42)
    test_vids = generate_visual_pendulum_dataset(n_trajectories=20, n_steps=40, dt=0.05, seed=2042)
    print(f"Training dataset shape: {train_vids.shape}")

    all_frames = train_vids.view(-1, 1, 64, 64)
    ae_loader = DataLoader(TensorDataset(all_frames), batch_size=128, shuffle=True)

    encoder = HDFrameEncoder(latent_dim=2).to(device)
    decoder = HDFrameDecoder(latent_dim=2).to(device)

    # 2. Stage 1: Autoencoder Representation Learning (30 Epochs with Cosine Annealing)
    print("\n[2/4] Stage 1: Training High-Definition Visual Autoencoder (35 Epochs)...")
    ae_epochs = 35
    ae_opt = torch.optim.AdamW(list(encoder.parameters()) + list(decoder.parameters()), lr=2e-3, weight_decay=1e-5)
    ae_sched = torch.optim.lr_scheduler.CosineAnnealingLR(ae_opt, T_max=ae_epochs, eta_min=1e-5)

    t0_ae = time.perf_counter()
    for epoch in range(ae_epochs):
        encoder.train()
        decoder.train()
        total_loss = 0.0
        n_batches = 0
        for (batch_x,) in ae_loader:
            batch_x = batch_x.to(device)
            ae_opt.zero_grad()
            z = encoder(batch_x)
            recon = decoder(z)
            loss = weighted_recon_loss(recon, batch_x)
            loss.backward()
            ae_opt.step()
            total_loss += loss.item()
            n_batches += 1
        ae_sched.step()

        if (epoch + 1) % 5 == 0 or epoch == 0:
            avg_loss = total_loss / n_batches
            print(f"  AE Epoch [{epoch+1:02d}/{ae_epochs}] | LR: {ae_sched.get_last_lr()[0]:.5f} | Weighted Loss: {avg_loss:.5f}")

    print(f"Stage 1 Completed in {time.perf_counter() - t0_ae:.2f} seconds.")

    # 3. Stage 2: Latent Hamiltonian Dynamics with Multi-Step Unrolled Loss (50 Epochs)
    print("\n[3/4] Stage 2: Training Multi-Step Latent Hamiltonian Leapfrog Dynamics (50 Epochs)...")
    encoder.eval()
    decoder.eval()

    # Project all training video sequences into continuous latent trajectories [N, T, 2]
    N, T, C, H, W = train_vids.shape
    with torch.no_grad():
        z_seqs = []
        for i in range(N):
            vid = train_vids[i].to(device)
            z_s = encoder(vid)
            z_seqs.append(z_s)
        z_seqs = torch.stack(z_seqs, dim=0) # [N, 40, 2]

    # Dataset of sequences
    dyn_loader = DataLoader(TensorDataset(z_seqs), batch_size=64, shuffle=True)

    ham_dynamics = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=128).to(device)
    ham_opt = torch.optim.AdamW(ham_dynamics.parameters(), lr=1.5e-3, weight_decay=1e-5)
    dyn_epochs = 50
    ham_sched = torch.optim.lr_scheduler.CosineAnnealingLR(ham_opt, T_max=dyn_epochs, eta_min=1e-5)

    t0_dyn = time.perf_counter()
    for epoch in range(dyn_epochs):
        ham_dynamics.train()
        total_loss = 0.0
        n_batches = 0

        # Curriculum unroll horizon: expand from 3-step to 8-step unrolling as training progresses
        unroll_steps = min(3 + (epoch // 8) * 2, 8)

        for (b_seq,) in dyn_loader:
            ham_opt.zero_grad()
            
            # Pick random starting sub-sequences of length unroll_steps
            max_start = T - unroll_steps
            start_t = np.random.randint(0, max_start)
            target_subseq = b_seq[:, start_t:start_t + unroll_steps] # [B, K, 2]

            curr_z = target_subseq[:, 0]
            pred_subseq = [curr_z]
            for _ in range(unroll_steps - 1):
                curr_z = ham_dynamics.forward_step(curr_z, dt=0.05)
                pred_subseq.append(curr_z)
            pred_subseq = torch.stack(pred_subseq, dim=1)

            loss = nn.functional.mse_loss(pred_subseq, target_subseq)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(ham_dynamics.parameters(), max_norm=1.0)
            ham_opt.step()

            total_loss += loss.item()
            n_batches += 1

        ham_sched.step()
        if (epoch + 1) % 10 == 0 or epoch == 0:
            avg_dyn_loss = total_loss / n_batches
            print(f"  Dynamics Epoch [{epoch+1:02d}/{dyn_epochs}] (Unroll {unroll_steps}-step) | Latent MSE: {avg_dyn_loss:.6f}")

    print(f"Stage 2 Completed in {time.perf_counter() - t0_dyn:.2f} seconds.")

    # 4. Stage 3: Autonomous 35-Step Visual Rollout Evaluation
    print("\n[4/4] Stage 3: Autonomous Visual Latent Rollout (35 Consecutive Steps from Frame 0)...")
    ham_dynamics.eval()
    test_seq = test_vids[0].to(device) # [40, 1, 64, 64]

    with torch.no_grad():
        z_init = encoder(test_seq[0:1])
        pred_frames = [decoder(z_init).cpu()]
        curr_z = z_init

        for _ in range(35):
            curr_z = ham_dynamics.forward_step(curr_z, dt=0.05)
            pred_frame = decoder(curr_z).cpu()
            pred_frames.append(pred_frame)

    # Render High-Quality 12-Frame Visual Comparison Strip
    n_display = 12
    fig, axes = plt.subplots(2, n_display, figsize=(18, 3.5), dpi=150)
    for col in range(n_display):
        frame_idx = col * 3
        # Ground Truth
        axes[0, col].imshow(test_seq[frame_idx, 0].cpu().numpy(), cmap="magma", vmin=0, vmax=1)
        axes[0, col].axis("off")
        axes[0, col].set_title(f"t = {frame_idx * 0.05:.2f}s", fontsize=8)

        # Autoregressive Prediction
        axes[1, col].imshow(pred_frames[frame_idx][0, 0].numpy(), cmap="magma", vmin=0, vmax=1)
        axes[1, col].axis("off")

    axes[0, 0].text(-22, 32, "Ground Truth", fontsize=9, fontweight="bold", rotation=90, va="center")
    axes[1, 0].text(-22, 32, "AKASHA HD Rollout", fontsize=9, fontweight="bold", rotation=90, va="center")

    plt.suptitle("AKASHA 2-Lite: High-Definition Autonomous Latent Rollout (Zero Teacher Forcing)", fontsize=11, fontweight="bold")
    plt.tight_layout()

    out_img = "results/visual_world_model_hd_rollout.png"
    plt.savefig(out_img)
    plt.close()
    print(f"[OK] Saved high-definition comparison strip to {out_img}")

    # Save upgraded checkpoints
    os.makedirs("checkpoints", exist_ok=True)
    ckpt_path = "checkpoints/visual_world_model_hd.pt"
    torch.save({
        "encoder": encoder.state_dict(),
        "decoder": decoder.state_dict(),
        "dynamics": ham_dynamics.state_dict(),
    }, ckpt_path)
    print(f"[OK] Saved high-definition model weights to {ckpt_path}")

    total_elapsed = time.perf_counter() - start_total_time
    print(f"\n=========================================================================")
    print(f"TRAINING COMPLETE: Total Pipeline Finished in {total_elapsed:.2f} seconds!")
    print(f"=========================================================================")

if __name__ == "__main__":
    train_hd_world_model()
