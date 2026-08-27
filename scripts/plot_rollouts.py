import os
import torch
import matplotlib.pyplot as plt
import numpy as np

from akasha_2_lite.data import IdealPendulum
from akasha_2_lite.models import BaselineDynamicalModel, HamiltonianLatentModel
from akasha_2_lite.training import prepare_transition_loader, train_dynamical_model

def main():
    seed = 42
    torch.manual_seed(seed)
    np.random.seed(seed)

    dt = 0.05
    n_steps = 200
    pendulum = IdealPendulum(g=3.0)

    # Generate datasets
    train_data, _ = pendulum.generate_trajectories(
        n_trajectories=120, n_steps=50, dt=dt, seed=seed
    )
    test_data, gt_energy = pendulum.generate_trajectories(
        n_trajectories=1, n_steps=n_steps, dt=dt, seed=seed + 999
    )

    train_loader = prepare_transition_loader(train_data, batch_size=128, shuffle=True)
    x0 = test_data[:, 0, :] # [1, 2]

    print("Training models for phase portrait inspection...")
    baseline = BaselineDynamicalModel(state_dim=2, hidden_dim=128)
    hamiltonian = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=128)

    train_dynamical_model(baseline, train_loader, dt=dt, epochs=35)
    train_dynamical_model(hamiltonian, train_loader, dt=dt, epochs=35)

    baseline.eval()
    hamiltonian.eval()

    with torch.no_grad():
        base_roll = baseline.rollout(x0, n_steps=n_steps, dt=dt)[0].cpu().numpy()
        ham_roll = hamiltonian.rollout(x0, n_steps=n_steps, dt=dt)[0].cpu().numpy()
        gt_roll = test_data[0].cpu().numpy()

    # Compute Hamiltonian for each rollout
    h_gt = pendulum.hamiltonian(torch.from_numpy(gt_roll[:, 0]), torch.from_numpy(gt_roll[:, 1])).numpy()
    h_base = pendulum.hamiltonian(torch.from_numpy(base_roll[:, 0]), torch.from_numpy(base_roll[:, 1])).numpy()
    h_ham = pendulum.hamiltonian(torch.from_numpy(ham_roll[:, 0]), torch.from_numpy(ham_roll[:, 1])).numpy()

    h0 = h_gt[0]
    drift_base = np.abs(h_base - h0) / (np.abs(h0) + 1e-6)
    drift_ham = np.abs(h_ham - h0) / (np.abs(h0) + 1e-6)

    t = np.linspace(0, (n_steps - 1) * dt, n_steps)

    # Plotting
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), dpi=150)

    # 1. Phase Portrait (q vs p)
    axes[0].plot(gt_roll[:, 0], gt_roll[:, 1], "k--", label="Ground Truth (Closed Orbit)", linewidth=2.0, alpha=0.7)
    axes[0].plot(base_roll[:, 0], base_roll[:, 1], color="#ff7f0e", label="Baseline SSM (RK4)", linewidth=1.8)
    axes[0].plot(ham_roll[:, 0], ham_roll[:, 1], color="#1f77b4", label="Hamiltonian SSM (Leapfrog)", linewidth=1.8)
    axes[0].set_title("Phase Portrait (q vs p)", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Position (q / angle)", fontsize=10)
    axes[0].set_ylabel("Momentum (p / velocity)", fontsize=10)
    axes[0].grid(True, linestyle=":", alpha=0.6)
    axes[0].legend(fontsize=8, loc="upper right")

    # 2. Position over time q(t)
    axes[1].plot(t, gt_roll[:, 0], "k--", label="Ground Truth", linewidth=2.0, alpha=0.7)
    axes[1].plot(t, base_roll[:, 0], color="#ff7f0e", label="Baseline SSM", linewidth=1.6)
    axes[1].plot(t, ham_roll[:, 0], color="#1f77b4", label="Hamiltonian SSM", linewidth=1.6)
    axes[1].set_title("Trajectory Evolution q(t)", fontsize=12, fontweight="bold")
    axes[1].set_xlabel("Time (s)", fontsize=10)
    axes[1].set_ylabel("Position (q)", fontsize=10)
    axes[1].grid(True, linestyle=":", alpha=0.6)
    axes[1].legend(fontsize=8, loc="upper right")

    # 3. Relative Energy Drift over time
    axes[2].plot(t, drift_base, color="#ff7f0e", label="Baseline Drift", linewidth=1.6)
    axes[2].plot(t, drift_ham, color="#1f77b4", label="Hamiltonian Drift", linewidth=1.6)
    axes[2].set_title("Relative Energy Drift (|ΔH| / H₀)", fontsize=12, fontweight="bold")
    axes[2].set_xlabel("Time (s)", fontsize=10)
    axes[2].set_ylabel("Relative Drift", fontsize=10)
    axes[2].grid(True, linestyle=":", alpha=0.6)
    axes[2].legend(fontsize=8, loc="upper left")

    plt.tight_layout()
    os.makedirs("results", exist_ok=True)
    out_path = "results/phase_portrait_comparison.png"
    plt.savefig(out_path)
    print(f"[OK] Saved plot to {out_path}")

if __name__ == "__main__":
    main()
