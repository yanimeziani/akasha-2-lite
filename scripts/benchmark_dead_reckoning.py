"""
Benchmark Script: Drone GPS-Denied Dead-Reckoning
Compares Naive Double-Integration vs Akasha-Nav Hamiltonian Symplectic Filter.
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
from akasha_2_lite.nav.imu_filter import IMUSimulator, NaiveDoubleIntegrator, AkashaHamiltonianNavFilter

def run_benchmark():
    np.random.seed(42)
    dt = 0.05
    duration = 60.0  # 60 seconds GPS blackout
    
    sim = IMUSimulator(dt=dt, duration=duration)
    t, true_pos, true_vel, true_acc = sim.generate_ground_truth()
    
    # Add realistic sensor noise + linear bias drift
    noisy_acc = sim.add_imu_sensor_noise(true_acc, noise_std=0.10, bias_drift=0.04)

    # 1. Naive Baseline
    naive = NaiveDoubleIntegrator(dt=dt)
    naive_pos, naive_vel = naive.estimate(true_pos[0], true_vel[0], noisy_acc)

    # 2. Akasha-Nav Hamiltonian Symplectic Filter
    akasha = AkashaHamiltonianNavFilter(dt=dt, mass=1.2, max_speed=8.0)
    akasha_pos, akasha_vel = akasha.estimate(true_pos[0], true_vel[0], noisy_acc)

    # Compute Absolute Trajectory Error (ATE) over time
    err_naive = np.linalg.norm(naive_pos - true_pos, axis=-1)
    err_akasha = np.linalg.norm(akasha_pos - true_pos, axis=-1)

    mean_err_naive = np.mean(err_naive)
    max_err_naive = np.max(err_naive)
    end_err_naive = err_naive[-1]

    mean_err_akasha = np.mean(err_akasha)
    max_err_akasha = np.max(err_akasha)
    end_err_akasha = err_akasha[-1]

    improvement = ((mean_err_naive - mean_err_akasha) / mean_err_naive) * 100.0

    print("=" * 70)
    print("AKASHA-NAV: 60-SECOND GPS-DENIED DRONE DEAD-RECKONING BENCHMARK")
    print("=" * 70)
    print(f"Duration:                {duration:.1f} s ({len(t)} IMU samples at 20 Hz)")
    print(f"Sensor Noise:            0.10 m/s^2 Gaussian + 0.04 m/s^2 Bias Drift")
    print("-" * 70)
    print(f"Naive Double Integrator: Mean Error: {mean_err_naive:.2f} m | End Drift: {end_err_naive:.2f} m | Max: {max_err_naive:.2f} m")
    print(f"Akasha-Nav Filter:       Mean Error: {mean_err_akasha:.2f} m | End Drift: {end_err_akasha:.2f} m | Max: {max_err_akasha:.2f} m")
    print(f"Tracking Error Reduction: +{improvement:.1f}% Error Suppression")
    print("=" * 70)

    # Save diagnostic figure
    os.makedirs("results", exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: 2D XY Trajectory
    axes[0].plot(true_pos[:, 0], true_pos[:, 1], "k--", label="Ground Truth (Corridor)", linewidth=2)
    axes[0].plot(naive_pos[:, 0], naive_pos[:, 1], "r-", label="Naive Double-Integrator (Diverges)", alpha=0.8)
    axes[0].plot(akasha_pos[:, 0], akasha_pos[:, 1], "c-", label="Akasha-Nav (Hamiltonian Bounded)", linewidth=2)
    axes[0].scatter(true_pos[0, 0], true_pos[0, 1], c="g", s=80, label="GPS Loss Origin")
    axes[0].set_title("3D Drone Flight Path (XY Projection)", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("X Position (meters)")
    axes[0].set_ylabel("Y Position (meters)")
    axes[0].legend(loc="upper left")
    axes[0].grid(True, linestyle="--", alpha=0.5)

    # Right: Error over time
    axes[1].plot(t, err_naive, "r-", label=f"Naive Baseline (End: {end_err_naive:.1f}m)", linewidth=1.5)
    axes[1].plot(t, err_akasha, "c-", label=f"Akasha-Nav (End: {end_err_akasha:.1f}m)", linewidth=2.5)
    axes[1].set_title("Absolute Trajectory Error (ATE) vs GPS-Denied Time", fontsize=12, fontweight="bold")
    axes[1].set_xlabel("Time (seconds)")
    axes[1].set_ylabel("Drift Error (meters)")
    axes[1].legend()
    axes[1].grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plot_path = "results/drone_dead_reckoning_benchmark.png"
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"Benchmark plot saved to {plot_path}")

    # Export trajectory data for interactive 3D WebGL demo
    telemetry_data = {
        "time": t.tolist(),
        "ground_truth": true_pos.tolist(),
        "naive": naive_pos.tolist(),
        "akasha": akasha_pos.tolist(),
        "metrics": {
            "mean_err_naive": float(mean_err_naive),
            "end_err_naive": float(end_err_naive),
            "mean_err_akasha": float(mean_err_akasha),
            "end_err_akasha": float(end_err_akasha),
            "improvement": float(improvement)
        }
    }

    demo_data_path = "demo/drone_data.json"
    with open(demo_data_path, "w") as f:
        json.dump(telemetry_data, f)
    print(f"Exported 3D flight telemetry to {demo_data_path}")

if __name__ == "__main__":
    run_benchmark()
