import os
import json
import time
import torch
import numpy as np
from typing import Dict, List, Any

from akasha_2_lite.data import IdealPendulum, HarmonicOscillator
from akasha_2_lite.models import BaselineDynamicalModel, HamiltonianLatentModel
from akasha_2_lite.training import prepare_transition_loader, train_dynamical_model
from akasha_2_lite.metrics import compute_rollout_metrics, measure_model_efficiency

def set_seed(seed: int):
    torch.manual_seed(seed)
    np.random.seed(seed)

def run_single_benchmark(
    system_name: str,
    system,
    seed: int,
    dt: float = 0.05,
    train_trajs: int = 120,
    train_steps: int = 50,
    test_trajs: int = 40,
    rollout_steps: int = 200,
    epochs: int = 35,
) -> Dict[str, Any]:
    print(f"\n>>> Running {system_name} | Seed: {seed} <<<")
    set_seed(seed)

    # 1. Generate Datasets
    train_data, _ = system.generate_trajectories(
        n_trajectories=train_trajs, n_steps=train_steps, dt=dt, seed=seed
    )
    test_data, _ = system.generate_trajectories(
        n_trajectories=test_trajs, n_steps=rollout_steps, dt=dt, seed=seed + 1000
    )

    train_loader = prepare_transition_loader(train_data, batch_size=128, shuffle=True)
    x0_test = test_data[:, 0, :]

    # 2. Train Baseline
    print("  Training Baseline SSM...")
    set_seed(seed)
    baseline_model = BaselineDynamicalModel(state_dim=2, hidden_dim=128)
    t0 = time.perf_counter()
    train_dynamical_model(baseline_model, train_loader, dt=dt, epochs=epochs)
    train_time_base = time.perf_counter() - t0

    # 3. Train Hamiltonian
    print("  Training Hamiltonian SSM...")
    set_seed(seed)
    hamiltonian_model = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=128)
    t0 = time.perf_counter()
    train_dynamical_model(hamiltonian_model, train_loader, dt=dt, epochs=epochs)
    train_time_ham = time.perf_counter() - t0

    # 4. Rollout Evaluation (200 steps without teacher forcing)
    print("  Evaluating 200-step rollouts...")
    baseline_model.eval()
    hamiltonian_model.eval()

    with torch.no_grad():
        base_rollout = baseline_model.rollout(x0_test, n_steps=rollout_steps, dt=dt)
        ham_rollout = hamiltonian_model.rollout(x0_test, n_steps=rollout_steps, dt=dt)

    base_metrics = compute_rollout_metrics(
        pred_trajectories=base_rollout,
        true_trajectories=test_data,
        hamiltonian_fn=system.hamiltonian,
    )
    ham_metrics = compute_rollout_metrics(
        pred_trajectories=ham_rollout,
        true_trajectories=test_data,
        hamiltonian_fn=system.hamiltonian,
    )

    return {
        "system": system_name,
        "seed": seed,
        "baseline": {
            "h50_mse": base_metrics.get("horizon_50_mse"),
            "h100_mse": base_metrics.get("horizon_100_mse"),
            "h200_mse": base_metrics.get("horizon_200_mse"),
            "mean_mse": base_metrics.get("mean_rollout_mse"),
            "mean_h_drift": base_metrics.get("mean_h_drift"),
            "train_time_s": train_time_base,
        },
        "hamiltonian": {
            "h50_mse": ham_metrics.get("horizon_50_mse"),
            "h100_mse": ham_metrics.get("horizon_100_mse"),
            "h200_mse": ham_metrics.get("horizon_200_mse"),
            "mean_mse": ham_metrics.get("mean_rollout_mse"),
            "mean_h_drift": ham_metrics.get("mean_h_drift"),
            "train_time_s": train_time_ham,
        },
    }

def format_stats(values: List[float]) -> str:
    mean = np.mean(values)
    std = np.std(values)
    return f"{mean:.4f} ± {std:.4f}"

def main():
    systems = [
        ("Ideal Pendulum", IdealPendulum(g=3.0)),
        ("Harmonic Oscillator", HarmonicOscillator(k=2.0)),
    ]
    seeds = [42, 43, 44]

    all_results = []

    for sys_name, sys_inst in systems:
        for seed in seeds:
            res = run_single_benchmark(sys_name, sys_inst, seed)
            all_results.append(res)

    # Aggregate by system
    os.makedirs("results", exist_ok=True)
    with open("results/raw_metrics.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n========================================================")
    print("           EXPERIMENT SUMMARY RESULTS TABLE             ")
    print("========================================================")
    
    markdown_lines = [
        "# AKASHA 2-Lite: Experimental Results\n",
        "**Hypothesis:** Does a Hamiltonian latent-state module improve long-horizon prediction stability over an ordinary state-space baseline?\n",
        "| Dataset | Architecture | Horizon-50 MSE | Horizon-100 MSE | Horizon-200 MSE | Energy Drift (ΔH/H₀) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for sys_name, _ in systems:
        sys_res = [r for r in all_results if r["system"] == sys_name]
        
        # Baseline stats
        b_h50 = [r["baseline"]["h50_mse"] for r in sys_res]
        b_h100 = [r["baseline"]["h100_mse"] for r in sys_res]
        b_h200 = [r["baseline"]["h200_mse"] for r in sys_res]
        b_drift = [r["baseline"]["mean_h_drift"] for r in sys_res]

        # Hamiltonian stats
        h_h50 = [r["hamiltonian"]["h50_mse"] for r in sys_res]
        h_h100 = [r["hamiltonian"]["h100_mse"] for r in sys_res]
        h_h200 = [r["hamiltonian"]["h200_mse"] for r in sys_res]
        h_drift = [r["hamiltonian"]["mean_h_drift"] for r in sys_res]

        markdown_lines.append(
            f"| **{sys_name}** | Baseline SSM | {format_stats(b_h50)} | {format_stats(b_h100)} | {format_stats(b_h200)} | {format_stats(b_drift)} |"
        )
        markdown_lines.append(
            f"| **{sys_name}** | **Hamiltonian SSM (Ours)** | **{format_stats(h_h50)}** | **{format_stats(h_h100)}** | **{format_stats(h_h200)}** | **{format_stats(h_drift)}** |"
        )

        h200_diff = (np.mean(b_h200) - np.mean(h_h200)) / np.mean(b_h200) * 100.0
        drift_diff = (np.mean(b_drift) - np.mean(h_drift)) / np.mean(b_drift) * 100.0
        print(f"\nDataset: {sys_name}")
        print(f"  Baseline 200-step MSE:    {format_stats(b_h200)}")
        print(f"  Hamiltonian 200-step MSE: {format_stats(h_h200)} (Error reduction: {h200_diff:+.1f}%)")
        print(f"  Baseline Energy Drift:    {format_stats(b_drift)}")
        print(f"  Hamiltonian Energy Drift: {format_stats(h_drift)} (Drift reduction: {drift_diff:+.1f}%)")

    table_md = "\n".join(markdown_lines)
    with open("results/summary.md", "w") as f:
        f.write(table_md)

    print("\nSaved markdown summary to results/summary.md and raw metrics to results/raw_metrics.json")

if __name__ == "__main__":
    main()
