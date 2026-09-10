import os
import json
import time
import torch
import numpy as np
from scipy import stats
from typing import Dict, List, Any

from akasha_2_lite.data import IdealPendulum, HarmonicOscillator, DampedPendulum
from akasha_2_lite.models import (
    BaselineDynamicalModel,
    HamiltonianLatentModel,
    SeparableHamiltonianModel,
    PortHamiltonianSSM,
)
from akasha_2_lite.training import (
    prepare_transition_loader,
    prepare_multistep_loader,
    train_dynamical_model,
    train_multistep_dynamical_model,
)
from akasha_2_lite.metrics import compute_rollout_metrics

def set_seed(seed: int):
    torch.manual_seed(seed)
    np.random.seed(seed)

def evaluate_model(model, test_data, system, dt, rollout_steps):
    model.eval()
    x0 = test_data[:, 0, :]
    with torch.no_grad():
        rollout = model.rollout(x0, n_steps=rollout_steps, dt=dt)
    return compute_rollout_metrics(rollout, test_data, system.hamiltonian)

def run_autoresearch_suite():
    print("===================================================================")
    print("      AKASHA 2-Lite: Rigorous Autoresearch Benchmark Suite         ")
    print("===================================================================")

    dt = 0.05
    train_trajs = 120
    train_steps = 50
    test_trajs = 40
    rollout_steps = 200
    epochs = 35
    seeds = [42, 43, 44]

    systems = [
        ("Ideal Pendulum", IdealPendulum(g=3.0)),
        ("Harmonic Oscillator", HarmonicOscillator(k=2.0)),
        ("Damped Pendulum (Dissipative)", DampedPendulum(g=3.0, gamma=0.2)),
    ]

    all_results = []

    for sys_name, system in systems:
        for seed in seeds:
            print(f"\n>>> Running {sys_name} | Seed: {seed} <<<")
            set_seed(seed)

            # Generate datasets
            train_data, _ = system.generate_trajectories(
                n_trajectories=train_trajs, n_steps=train_steps, dt=dt, seed=seed
            )
            test_data, _ = system.generate_trajectories(
                n_trajectories=test_trajs, n_steps=rollout_steps, dt=dt, seed=seed + 1000
            )

            loader_1step = prepare_transition_loader(train_data, batch_size=128)
            loader_mstep = prepare_multistep_loader(train_data, horizon=5, batch_size=64)

            # 1. Baseline SSM (RK4)
            print("  [1/4] Training Baseline SSM (RK4)...")
            set_seed(seed)
            baseline = BaselineDynamicalModel(state_dim=2, hidden_dim=128)
            t0 = time.perf_counter()
            train_dynamical_model(baseline, loader_1step, dt=dt, epochs=epochs)
            t_base = time.perf_counter() - t0
            m_base = evaluate_model(baseline, test_data, system, dt, rollout_steps)

            # 2. Hamiltonian SSM (1-Step)
            print("  [2/4] Training Hamiltonian SSM (1-Step)...")
            set_seed(seed)
            ham1 = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=128)
            t0 = time.perf_counter()
            train_dynamical_model(ham1, loader_1step, dt=dt, epochs=epochs)
            t_ham1 = time.perf_counter() - t0
            m_ham1 = evaluate_model(ham1, test_data, system, dt, rollout_steps)

            # 3. Separable Hamiltonian SSM (Multi-Step K=5)
            print("  [3/4] Training Separable Hamiltonian SSM (Multi-Step K=5)...")
            set_seed(seed)
            sep_multi = SeparableHamiltonianModel(coordinate_dim=1, hidden_dim=92)
            t0 = time.perf_counter()
            train_multistep_dynamical_model(sep_multi, loader_mstep, dt=dt, epochs=epochs)
            t_sep = time.perf_counter() - t0
            m_sep = evaluate_model(sep_multi, test_data, system, dt, rollout_steps)

            # 4. Port-Hamiltonian SSM (Multi-Step K=5)
            print("  [4/4] Training Port-Hamiltonian SSM (Multi-Step K=5)...")
            set_seed(seed)
            ph_multi = PortHamiltonianSSM(coordinate_dim=1, hidden_dim=128, init_damping=0.05)
            t0 = time.perf_counter()
            train_multistep_dynamical_model(ph_multi, loader_mstep, dt=dt, epochs=epochs)
            t_ph = time.perf_counter() - t0
            m_ph = evaluate_model(ph_multi, test_data, system, dt, rollout_steps)

            res_entry = {
                "system": sys_name,
                "seed": seed,
                "baseline": {
                    "h50_mse": m_base["horizon_50_mse"],
                    "h100_mse": m_base["horizon_100_mse"],
                    "h200_mse": m_base["horizon_200_mse"],
                    "mean_mse": m_base["mean_rollout_mse"],
                    "energy_drift": m_base["mean_h_drift"],
                    "train_time_s": t_base,
                },
                "hamiltonian_1step": {
                    "h50_mse": m_ham1["horizon_50_mse"],
                    "h100_mse": m_ham1["horizon_100_mse"],
                    "h200_mse": m_ham1["horizon_200_mse"],
                    "mean_mse": m_ham1["mean_rollout_mse"],
                    "energy_drift": m_ham1["mean_h_drift"],
                    "train_time_s": t_ham1,
                },
                "separable_multistep": {
                    "h50_mse": m_sep["horizon_50_mse"],
                    "h100_mse": m_sep["horizon_100_mse"],
                    "h200_mse": m_sep["horizon_200_mse"],
                    "mean_mse": m_sep["mean_rollout_mse"],
                    "energy_drift": m_sep["mean_h_drift"],
                    "train_time_s": t_sep,
                },
                "port_hamiltonian_multistep": {
                    "h50_mse": m_ph["horizon_50_mse"],
                    "h100_mse": m_ph["horizon_100_mse"],
                    "h200_mse": m_ph["horizon_200_mse"],
                    "mean_mse": m_ph["mean_rollout_mse"],
                    "energy_drift": m_ph["mean_h_drift"],
                    "learned_damping": m_ph.get("learned_damping", ph_multi.damping.item()),
                    "train_time_s": t_ph,
                },
            }
            all_results.append(res_entry)

    # Save raw results
    os.makedirs("results", exist_ok=True)
    with open("results/autoresearch_metrics.json", "w") as f:
        json.dump(all_results, f, indent=2)

    # Statistical Summary Generation
    def fmt(vals):
        return f"{np.mean(vals):.4f} ± {np.std(vals):.4f}"

    summary_md_lines = [
        "# AKASHA 2-Lite: Autoresearch Benchmark Results\n",
        "Comprehensive 200-step autoregressive rollout evaluation across 3 seeds (42, 43, 44).\n",
        "| Dataset | Architecture | Horizon-50 MSE | Horizon-100 MSE | Horizon-200 MSE | Energy Drift ($|\\Delta H|/H_0$) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for sys_name, _ in systems:
        sys_res = [r for r in all_results if r["system"] == sys_name]
        models = [
            ("Baseline SSM (RK4)", "baseline"),
            ("Hamiltonian SSM (1-Step)", "hamiltonian_1step"),
            ("Separable HNN (Multi-Step)", "separable_multistep"),
            ("Port-Hamiltonian SSM (Multi-Step)", "port_hamiltonian_multistep"),
        ]

        for label, mkey in models:
            h50 = [r[mkey]["h50_mse"] for r in sys_res]
            h100 = [r[mkey]["h100_mse"] for r in sys_res]
            h200 = [r[mkey]["h200_mse"] for r in sys_res]
            drift = [r[mkey]["energy_drift"] for r in sys_res]
            summary_md_lines.append(
                f"| **{sys_name}** | {label} | {fmt(h50)} | {fmt(h100)} | {fmt(h200)} | {fmt(drift)} |"
            )

    summary_md = "\n".join(summary_md_lines)
    with open("results/autoresearch_summary.md", "w") as f:
        f.write(summary_md)

    print("\n" + summary_md)
    print("\nAutoresearch evaluation completed successfully!")

if __name__ == "__main__":
    run_autoresearch_suite()
