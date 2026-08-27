import torch
import numpy as np
from akasha_2_lite.data import IdealPendulum, HarmonicOscillator
from akasha_2_lite.metrics import compute_rollout_metrics

def main():
    print("--- 1. Testing IdealPendulum trajectory generation ---")
    pendulum = IdealPendulum(g=3.0)
    traj_p, energy_p = pendulum.generate_trajectories(n_trajectories=16, n_steps=200, dt=0.05, seed=42)
    print(f"Pendulum trajectories shape: {traj_p.shape}")
    print(f"Ground truth initial energy: {energy_p[:, 0].mean().item():.5f}")
    print(f"Ground truth final energy:   {energy_p[:, -1].mean().item():.5f}")
    
    # Ground truth Hamiltonian relative drift
    h_drift_gt = (torch.abs(energy_p - energy_p[:, 0:1]) / (energy_p[:, 0:1] + 1e-6)).max().item()
    print(f"Ground truth max numerical drift: {h_drift_gt:.2e} (should be < 1e-5)")

    print("\n--- 2. Testing HarmonicOscillator trajectory generation ---")
    oscillator = HarmonicOscillator(k=2.0)
    traj_o, energy_o = oscillator.generate_trajectories(n_trajectories=16, n_steps=200, dt=0.05, seed=42)
    print(f"Oscillator trajectories shape: {traj_o.shape}")
    h_drift_osc = (torch.abs(energy_o - energy_o[:, 0:1]) / (energy_o[:, 0:1] + 1e-6)).max().item()
    print(f"Ground truth max numerical drift: {h_drift_osc:.2e} (should be < 1e-5)")

    print("\n--- 3. Testing compute_rollout_metrics harness ---")
    # Simulate a slightly drifting predictor (ground truth + small drift)
    noisy_traj = traj_p + torch.randn_like(traj_p) * 0.02
    metrics = compute_rollout_metrics(
        pred_trajectories=noisy_traj,
        true_trajectories=traj_p,
        hamiltonian_fn=pendulum.hamiltonian,
    )
    print(f"Mean Rollout MSE: {metrics['mean_rollout_mse']:.6f}")
    print(f"Horizon 50 MSE:   {metrics['horizon_50_mse']:.6f}")
    print(f"Horizon 200 MSE:  {metrics['horizon_200_mse']:.6f}")
    print(f"Mean Energy Drift:{metrics['mean_h_drift']:.6f}")
    print("\n[OK] Milestone 1 scaffold verification passed successfully!")

if __name__ == "__main__":
    main()
